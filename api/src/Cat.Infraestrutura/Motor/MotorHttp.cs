using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;
using Cat.Aplicacao.Log;
using Cat.Aplicacao.Trabalhos;
using Cat.Infraestrutura.Configuracao;
using Microsoft.Extensions.Logging;

namespace Cat.Infraestrutura.Motor;

/// <summary>
/// O canal interno com o motor Python: <c>127.0.0.1</c>, rotas <c>/interno</c>
/// fora do repasse público, e um segredo compartilhado em cabeçalho.
///
/// Cada chamada tem o seu prazo. Apagar pasta leva segundos; inspecionar uma
/// base de milhares de arquivos na rede leva minutos; uma remessa de um GB tem
/// de subir inteira antes de o motor começar a ler.
/// </summary>
public sealed class MotorHttp(HttpClient cliente, ConfigCat config, ILogger<MotorHttp> log) : IMotor
{
    public const string CabecalhoSegredo = "X-Cat-Motor-Segredo";

    public static readonly TimeSpan PrazoApagar = TimeSpan.FromMinutes(5);
    public static readonly TimeSpan PrazoInspecionar = TimeSpan.FromMinutes(30);
    public static readonly TimeSpan PrazoRemessa = TimeSpan.FromMinutes(60);

    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };

    public async Task<PastasApagadas> ApagarPastas(IReadOnlyList<string> pastas, CancellationToken cancelar)
    {
        var json = await Chamar("interno/pastas/apagar", JsonContent.Create(new { pastas }), PrazoApagar, cancelar);
        return new PastasApagadas(
            json.GetProperty("apagadas").EnumerateArray().Select(x => x.GetString()!).ToList(),
            json.GetProperty("recusadas").EnumerateArray().Select(x => x.GetString()!).ToList());
    }

    public async Task<LoteInspecionado> InspecionarLote(int projetoId, string pasta, CancellationToken cancelar)
    {
        var json = await Chamar("interno/lotes/inspecionar",
            JsonContent.Create(new Dictionary<string, object> { ["projeto_id"] = projetoId, ["pasta"] = pasta }),
            PrazoInspecionar, cancelar);
        return json.Deserialize<LoteInspecionado>(Json)
               ?? throw new MotorIndisponivel("resposta vazia à inspeção do lote");
    }

    public async Task<JsonObject> AnalisarRemessa(Stream corpo, string tipoDoConteudo, long? tamanho,
        CancellationToken cancelar)
    {
        // o corpo multipart segue como chegou, com a mesma fronteira: remontar o
        // formulário obrigaria a ter o arquivo inteiro em memória aqui também
        var conteudo = new StreamContent(corpo);
        conteudo.Headers.ContentType = MediaTypeHeaderValue.Parse(tipoDoConteudo);
        if (tamanho is { } bytes)
            conteudo.Headers.ContentLength = bytes;
        var json = await Chamar("interno/remessas/analisar", conteudo, PrazoRemessa, cancelar);
        return JsonNode.Parse(json.GetRawText())!.AsObject();
    }

    private async Task<JsonElement> Chamar(string rota, HttpContent conteudo, TimeSpan prazo, CancellationToken cancelar)
    {
        if (string.IsNullOrEmpty(config.MotorSegredo))
            throw new MotorIndisponivel("CAT_MOTOR_SEGREDO não está definido no backend/.env");

        using var limite = CancellationTokenSource.CreateLinkedTokenSource(cancelar);
        limite.CancelAfter(prazo);
        using var pedido = new HttpRequestMessage(HttpMethod.Post, new Uri(config.MotorUrl, rota)) { Content = conteudo };
        pedido.Headers.Add(CabecalhoSegredo, config.MotorSegredo);

        HttpResponseMessage resposta;
        try
        {
            resposta = await cliente.SendAsync(pedido, HttpCompletionOption.ResponseHeadersRead, limite.Token);
        }
        catch (Exception erro) when (erro is HttpRequestException or TaskCanceledException && !cancelar.IsCancellationRequested)
        {
            log.Erro("motor não respondeu ao canal interno", new { rota, destino = config.MotorUrl.ToString() }, erro);
            throw new MotorIndisponivel(erro is TaskCanceledException ? $"passou de {prazo.TotalMinutes} min" : erro.GetType().Name, erro);
        }

        using (resposta)
        {
            var texto = await resposta.Content.ReadAsStringAsync(limite.Token);
            if (resposta.IsSuccessStatusCode)
                return JsonDocument.Parse(texto).RootElement.Clone();

            // recusa com motivo (pasta que não existe, trabalho que não existe, remessa
            // sem SPED) segue para a tela com o texto do motor; o resto é falha do canal
            var codigo = (int)resposta.StatusCode;
            if (codigo is 404 or 422 && Detalhe(texto) is { } detalhe)
                throw new MotorRecusou(codigo, detalhe);
            log.Erro("motor recusou chamada do canal interno", new { rota, status = codigo, corpo = texto });
            throw new MotorIndisponivel($"HTTP {codigo}");
        }
    }

    private static string? Detalhe(string texto)
    {
        try
        {
            return JsonDocument.Parse(texto).RootElement.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.String
                ? d.GetString()
                : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }
}

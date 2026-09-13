using System.Net.Http.Json;
using System.Text.Json;
using Cat.Aplicacao.Log;
using Cat.Aplicacao.Trabalhos;
using Cat.Infraestrutura.Configuracao;
using Microsoft.Extensions.Logging;

namespace Cat.Infraestrutura.Motor;

/// <summary>
/// O canal interno com o motor Python: <c>127.0.0.1</c>, rotas <c>/interno</c>
/// fora do repasse público, e um segredo compartilhado em cabeçalho.
///
/// O identificador da requisição segue junto, para a linha de log do motor
/// casar com a da API.
/// </summary>
public sealed class MotorHttp(HttpClient cliente, ConfigCat config, ILogger<MotorHttp> log) : IMotor
{
    public const string CabecalhoSegredo = "X-Cat-Motor-Segredo";

    public async Task<PastasApagadas> ApagarPastas(IReadOnlyList<string> pastas, CancellationToken cancelar)
    {
        if (string.IsNullOrEmpty(config.MotorSegredo))
            throw new MotorIndisponivel("CAT_MOTOR_SEGREDO não está definido no backend/.env");

        using var pedido = new HttpRequestMessage(HttpMethod.Post, new Uri(config.MotorUrl, "interno/pastas/apagar"))
        {
            Content = JsonContent.Create(new { pastas }),
        };
        pedido.Headers.Add(CabecalhoSegredo, config.MotorSegredo);

        HttpResponseMessage resposta;
        try
        {
            resposta = await cliente.SendAsync(pedido, cancelar);
        }
        catch (Exception erro) when (erro is HttpRequestException or TaskCanceledException && !cancelar.IsCancellationRequested)
        {
            log.Erro("motor não respondeu ao pedido de apagar pastas",
                new { destino = config.MotorUrl.ToString(), pastas = pastas.Count }, erro);
            throw new MotorIndisponivel(erro.GetType().Name, erro);
        }

        using (resposta)
        {
            if (!resposta.IsSuccessStatusCode)
            {
                var corpo = await resposta.Content.ReadAsStringAsync(cancelar);
                log.Erro("motor recusou o pedido de apagar pastas", new { status = (int)resposta.StatusCode, corpo });
                throw new MotorIndisponivel($"HTTP {(int)resposta.StatusCode}");
            }
            var json = await resposta.Content.ReadFromJsonAsync<JsonElement>(cancelar);
            return new PastasApagadas(
                json.GetProperty("apagadas").EnumerateArray().Select(x => x.GetString()!).ToList(),
                json.GetProperty("recusadas").EnumerateArray().Select(x => x.GetString()!).ToList());
        }
    }
}

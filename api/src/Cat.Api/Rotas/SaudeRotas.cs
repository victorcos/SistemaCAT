using System.Text.Json;
using Cat.Infraestrutura.Configuracao;
using Cat.Infraestrutura.Motor;
using Cat.Aplicacao.Log;

namespace Cat.Api.Rotas;

public static class SaudeRotas
{
    public const string ClienteDoMotor = "motor-saude";

    /// <summary>
    /// Vivo, e com QUAL configuração — só o que não é segredo.
    ///
    /// Mesmos campos da versão Python, mais dois que só fazem sentido agora
    /// que são dois processos: <c>api</c>, para saber quem respondeu, e
    /// <c>motor</c>, com a versão que o Python diz ter. Versões diferentes nos
    /// dois lados é o sinal de que um deles não foi reiniciado depois do pull.
    /// </summary>
    public static void MapearSaude(this IEndpointRouteBuilder rotas) =>
        rotas.MapGet("/api/saude", async (ConfigCat config, IHttpClientFactory clientes,
            ILogger<ConfigCat> log, CancellationToken cancelar) => new Dictionary<string, object?>
        {
            ["status"] = "ok",
            ["versao"] = config.Versao,
            ["pasta_de_trabalho"] = config.PastaDeTrabalho,
            ["memoria_analitica"] = config.MemoriaAnalitica,
            ["threads_analiticas"] = config.ThreadsAnaliticas,
            ["api"] = "csharp",
            ["motor"] = await ConsultarMotor(config, clientes.CreateClient(ClienteDoMotor), log, cancelar),
        }).WithTags("infra");

    private static async Task<Dictionary<string, object?>> ConsultarMotor(ConfigCat config,
        HttpClient cliente, ILogger log, CancellationToken cancelar)
    {
        var situacao = new Dictionary<string, object?> { ["url"] = config.MotorUrl.ToString() };
        try
        {
            // pelo canal interno, como tudo o que a API pede ao motor: sem o
            // segredo certo ele responde 403 (ou 503, sem segredo configurado),
            // e a saúde mostra isso em vez de "ok"
            using var pedido = new HttpRequestMessage(HttpMethod.Get, new Uri(config.MotorUrl, "interno/saude"));
            pedido.Headers.Add(MotorHttp.CabecalhoSegredo, config.MotorSegredo);
            using var resposta = await cliente.SendAsync(pedido, cancelar);
            await using var corpo = await resposta.Content.ReadAsStreamAsync(cancelar);
            using var json = await JsonDocument.ParseAsync(corpo, cancellationToken: cancelar);
            situacao["situacao"] = resposta.IsSuccessStatusCode ? "ok" : $"http {(int)resposta.StatusCode}";
            situacao["versao"] = json.RootElement.TryGetProperty("versao", out var v) ? v.GetString() : null;
        }
        catch (Exception erro) when (erro is HttpRequestException or TaskCanceledException or JsonException)
        {
            // A saúde da API não cai junto com a do motor: quem pergunta quer
            // saber justamente qual dos dois está fora.
            log.Aviso("motor não respondeu à consulta de saúde",
                new { destino = config.MotorUrl.ToString(), erro = erro.GetType().Name });
            situacao["situacao"] = "fora do ar";
        }
        return situacao;
    }
}

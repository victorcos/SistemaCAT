using Cat.Infraestrutura.Configuracao;
using Cat.Aplicacao.Log;
using Microsoft.Extensions.Primitives;
using Yarp.ReverseProxy.Configuration;
using Yarp.ReverseProxy.Forwarder;

namespace Cat.Api.Infra;

/// <summary>
/// O que ainda não foi portado para C# segue para o Python.
///
/// É a peça que deixa migrar rota por rota: o front só conhece esta API, e
/// cada rota escrita aqui passa a ser atendida antes de chegar ao repasse. No
/// fim da migração, este arquivo encolhe até sobrar só o que for do motor.
/// </summary>
public sealed class RepasseAoMotor(ConfigCat config) : IProxyConfigProvider
{
    // Uma planilha de dezenas de milhões de linhas leva minutos para começar
    // a sair: o motor gera o arquivo antes do primeiro byte. Os 100 s padrão
    // do YARP cortariam o download que o front acabou de aprender a fazer.
    public static readonly TimeSpan TempoSemAtividade = TimeSpan.FromMinutes(30);

    // Rotas escritas em C# vencem o repasse por terem ordem menor.
    private const int OrdemDoRepasse = 1000;

    private readonly IProxyConfig _config = new Repasse(
        [
            Rota("motor-api", "/api/{**resto}"),
            // a documentação interativa do FastAPI, enquanto for ele quem descreve a API
            Rota("motor-docs", "/docs"),
            Rota("motor-openapi", "/openapi.json"),
        ],
        [
            new ClusterConfig
            {
                ClusterId = "motor",
                Destinations = new Dictionary<string, DestinationConfig>
                {
                    ["python"] = new() { Address = config.MotorUrl.ToString() },
                },
                HttpRequest = new ForwarderRequestConfig { ActivityTimeout = TempoSemAtividade },
            },
        ]);

    public IProxyConfig GetConfig() => _config;

    private static RouteConfig Rota(string id, string caminho) => new()
    {
        RouteId = id,
        ClusterId = "motor",
        Order = OrdemDoRepasse,
        Match = new RouteMatch { Path = caminho },
        // O CORS é respondido aqui. Se o Origin seguisse, o FastAPI poria o
        // próprio Access-Control-Allow-Origin e a resposta sairia com dois — o
        // navegador recusa cabeçalho duplicado.
        Transforms = [new Dictionary<string, string> { ["RequestHeaderRemove"] = "Origin" }],
    };

    /// <summary>
    /// Motor fora do ar vira resposta que o front sabe ler. Sem isto o YARP
    /// devolve 502 de corpo vazio, e a tela mostraria só "erro".
    /// </summary>
    public static async Task TraduzirFalha(HttpContext http, Func<Task> proximo)
    {
        await proximo();
        var falha = http.GetForwarderErrorFeature();
        if (falha is null)
            return;

        var log = http.RequestServices.GetRequiredService<ILogger<RepasseAoMotor>>();
        log.Erro("repasse ao motor falhou",
            new { erro = falha.Error.ToString(), destino = http.RequestServices
                .GetRequiredService<ConfigCat>().MotorUrl.ToString() },
            falha.Exception);

        if (http.Response.HasStarted)
            return;
        var expirou = falha.Error is ForwarderError.RequestTimedOut;
        http.Response.StatusCode = expirou
            ? StatusCodes.Status504GatewayTimeout
            : StatusCodes.Status502BadGateway;
        await http.Response.WriteAsJsonAsync(new Dictionary<string, string>
        {
            ["detail"] = expirou
                ? "O motor do sistema demorou demais para responder."
                : "O motor do sistema não respondeu. Confira se ele está no ar.",
        });
    }

    private sealed class Repasse(IReadOnlyList<RouteConfig> rotas, IReadOnlyList<ClusterConfig> clusters)
        : IProxyConfig
    {
        public IReadOnlyList<RouteConfig> Routes { get; } = rotas;
        public IReadOnlyList<ClusterConfig> Clusters { get; } = clusters;
        // a configuração nasce com o processo e não muda em execução
        public IChangeToken ChangeToken { get; } = new CancellationChangeToken(CancellationToken.None);
    }
}

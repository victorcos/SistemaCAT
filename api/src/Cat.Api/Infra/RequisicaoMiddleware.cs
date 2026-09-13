using System.Diagnostics;
using Cat.Aplicacao.Log;

namespace Cat.Api.Infra;

/// <summary>
/// Toda requisição carrega um identificador. Sem isso não dá para juntar as
/// linhas de log de um mesmo pedido quando há concorrência.
///
/// O identificador é gravado de volta no cabeçalho do PEDIDO, e não só da
/// resposta: é assim que ele segue no repasse ao motor Python, que já reusa o
/// <c>X-Request-Id</c> que recebe. A linha do C# e a do Python saem com o mesmo
/// <c>requisicao_id</c>.
/// </summary>
public sealed class RequisicaoMiddleware(RequestDelegate proximo, ILogger<RequisicaoMiddleware> log)
{
    public const string Cabecalho = "X-Request-Id";

    public async Task InvokeAsync(HttpContext http)
    {
        var id = http.Request.Headers[Cabecalho].FirstOrDefault() is { Length: > 0 } recebido
            ? recebido
            : Guid.NewGuid().ToString("N")[..12];
        http.Request.Headers[Cabecalho] = id;
        http.Response.OnStarting(() =>
        {
            http.Response.Headers[Cabecalho] = id;
            return Task.CompletedTask;
        });

        var relogio = Stopwatch.StartNew();
        using var _ = log.Contexto(new Dictionary<string, object?>
        {
            ["requisicao_id"] = id,
            ["rota"] = http.Request.Path.Value,
            ["metodo"] = http.Request.Method,
        });

        try
        {
            await proximo(http);
        }
        catch (Exception erro)
        {
            log.Erro("falha não tratada", new { ms = Milissegundos(relogio) }, erro);
            if (http.Response.HasStarted)
                throw;
            http.Response.Clear();
            http.Response.StatusCode = StatusCodes.Status500InternalServerError;
            await http.Response.WriteAsJsonAsync(new Dictionary<string, string>
            {
                ["detail"] = "Erro interno.",
                ["requisicao_id"] = id,
            });
            return;
        }

        // 4xx e 5xx merecem atenção; 2xx é rotina
        var campos = new { status = http.Response.StatusCode, ms = Milissegundos(relogio) };
        if (http.Response.StatusCode >= 400)
            log.Aviso("requisição atendida", campos);
        else
            log.Info("requisição atendida", campos);
    }

    private static double Milissegundos(Stopwatch relogio) =>
        Math.Round(relogio.Elapsed.TotalMilliseconds, 1);
}

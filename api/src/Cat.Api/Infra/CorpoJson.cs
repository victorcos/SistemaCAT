using System.Text.Json;
using Microsoft.AspNetCore.Http.Json;
using Microsoft.Extensions.Options;

namespace Cat.Api.Infra;

/// <summary>
/// Lê o corpo JSON do pedido devolvendo recusa que a tela sabe mostrar.
///
/// O vínculo automático do ASP.NET responde 400 de corpo vazio a JSON
/// quebrado; o FastAPI respondia 422. Aqui sai 422 com texto em "detail",
/// que é o que <c>services/api.ts</c> lê.
/// </summary>
public static class CorpoJson
{
    public static async Task<(T? Corpo, IResult? Recusa)> Ler<T>(HttpContext http) where T : class
    {
        try
        {
            var opcoes = http.RequestServices.GetRequiredService<IOptions<JsonOptions>>().Value.SerializerOptions;
            var corpo = await JsonSerializer.DeserializeAsync<T>(http.Request.Body, opcoes, http.RequestAborted);
            return corpo is null ? (null, Recusar("O corpo do pedido está vazio.")) : (corpo, null);
        }
        catch (JsonException)
        {
            return (null, Recusar("O corpo do pedido não é um JSON válido para esta operação."));
        }
    }

    public static IResult Recusar(string mensagem, int status = StatusCodes.Status422UnprocessableEntity) =>
        Results.Json(new Dictionary<string, string> { ["detail"] = mensagem }, statusCode: status);
}

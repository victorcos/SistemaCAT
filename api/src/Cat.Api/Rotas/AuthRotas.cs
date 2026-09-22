using System.Diagnostics;
using System.Globalization;
using Cat.Api.Infra;
using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;

namespace Cat.Api.Rotas;

/// <summary>
/// Rotas de autenticação. Finas: validam entrada, chamam o caso de uso, traduzem erro.
/// Portadas de <c>auth_router.py</c> com os mesmos códigos, mensagens e campos.
/// </summary>
public static class AuthRotas
{
    // Atraso mínimo da resposta de login, para "usuário não existe" e "senha
    // errada" levarem o mesmo tempo e não dar para descobrir contas pelo relógio.
    public static readonly TimeSpan PisoDeResposta = TimeSpan.FromMilliseconds(350);

    public sealed record RespostaUsuario(
        int Id, string Usuario, string Email, string NomeExibicao, string Papel, string Cargo,
        IReadOnlyList<int> Empresas, IReadOnlyList<string> Segmentos, string? Entrada,
        bool SenhaProvisoria, string? UltimoAcesso);

    public sealed record RespostaToken(string AccessToken, string TokenType, int ExpiresIn, RespostaUsuario Usuario);

    public static void MapearAuth(this IEndpointRouteBuilder rotas)
    {
        var grupo = rotas.MapGroup("/api/auth").WithTags("autenticação");

        // o padrão OAuth2 que a tela segue exige formulário, não JSON
        grupo.MapPost("/token", Entrar).DisableAntiforgery();
        grupo.MapGet("/eu", (HttpContext http) => Results.Json(ParaResposta(http.UsuarioAtual())))
            .ExigirUsuario();
    }

    private static async Task<IResult> Entrar(HttpContext http, Autenticar caso, ILogger<Autenticar> log)
    {
        var relogio = Stopwatch.StartNew();
        using var _ = log.Contexto(new Dictionary<string, object?>
        {
            ["etapa"] = "login",
            ["origem"] = http.Connection.RemoteIpAddress?.ToString() ?? "?",
        });

        var formulario = http.Request.HasFormContentType
            ? await http.Request.ReadFormAsync(http.RequestAborted)
            : null;
        var nome = formulario?["username"].ToString();
        var senha = formulario?["password"].ToString();
        if (string.IsNullOrEmpty(nome) || string.IsNullOrEmpty(senha))
        {
            // O FastAPI devolvia a lista de erros de validação dele; a tela só
            // lê texto em "detail", e com a lista mostrava a mensagem genérica.
            await Nivelar(relogio);
            return Results.Json(Detalhe("Informe usuário e senha."), statusCode: StatusCodes.Status422UnprocessableEntity);
        }

        try
        {
            var r = await caso.Executar(nome, senha, http.RequestAborted);
            await Nivelar(relogio);
            return Results.Json(new RespostaToken(r.Token, "bearer", r.ExpiraEmSegundos, ParaResposta(r.Usuario)));
        }
        catch (CredencialInvalida erro)
        {
            await Nivelar(relogio);
            return Sessao.NaoAutorizado(http, erro.Message);
        }
        catch (ErroDeAcesso erro) // inativo, bloqueado, bloqueado por um tempo
        {
            await Nivelar(relogio);
            return Results.Json(Detalhe(erro.Message), statusCode: StatusCodes.Status403Forbidden);
        }
    }

    public static RespostaUsuario ParaResposta(Usuario u) => new(
        u.Id, u.NomeDeUsuario, u.Email, u.NomeExibicao, u.Papel.Valor(), u.Cargo.Valor(),
        u.Empresas,
        // o que a pessoa de fato enxerga — para gestor e dev, todos
        Dominio.Acesso.Segmentos.De(u).Select(s => s.Chave).ToList(),
        // e para onde a tela deve mandá-la sem pedir clique nenhum
        Destino(u),
        u.SenhaProvisoria, u.UltimoAcesso is { } acesso ? IsoComoPython(acesso) : null);

    /// <summary>
    /// O caminho em que a tela inicial deve parar, já resolvido no servidor: a
    /// tela de segmentos, um segmento, ou direto um módulo. Nulo quando a pessoa
    /// não tem segmento nenhum liberado — aí a tela pede que procure o gestor,
    /// em vez de mostrar uma página vazia sem explicar por quê.
    /// </summary>
    private static string? Destino(Usuario u)
    {
        var entrada = Dominio.Acesso.Segmentos.Entrada(u);
        if (entrada.TodosOsSegmentos)
            return "/segmentos";
        if (entrada.Segmento is null)
            return null;
        return entrada.Modulo is { } modulo
            ? $"/modulos/{modulo}"
            : $"/segmentos/{entrada.Segmento}";
    }

    /// <summary>
    /// O <c>datetime.isoformat()</c> do Python: microssegundos, fuso como
    /// <c>+00:00</c>, e a fração some quando é zero.
    /// </summary>
    public static string IsoComoPython(DateTimeOffset instante)
    {
        var utc = instante.ToUniversalTime();
        var microssegundos = utc.Ticks / 10 % 1_000_000;
        return utc.ToString(microssegundos == 0 ? "yyyy-MM-dd'T'HH:mm:sszzz" : "yyyy-MM-dd'T'HH:mm:ss.ffffffzzz",
            CultureInfo.InvariantCulture);
    }

    private static Dictionary<string, string> Detalhe(string mensagem) => new() { ["detail"] = mensagem };

    private static Task Nivelar(Stopwatch relogio)
    {
        var restante = PisoDeResposta - relogio.Elapsed;
        return restante > TimeSpan.Zero ? Task.Delay(restante) : Task.CompletedTask;
    }
}

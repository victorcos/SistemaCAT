using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;

namespace Cat.Api.Infra;

/// <summary>
/// Quem é o usuário da requisição.
///
/// O token prova quem a pessoa é; o que ela pode vem do banco, relido a cada
/// pedido. Se foi desativada ou perdeu a alocação depois de o token ser
/// emitido, o acesso cai na hora — mesma regra do <c>seguranca.py</c>.
/// </summary>
public static class Sessao
{
    private const string Chave = "cat.usuario";
    public const string MensagemInvalida = "Sessão inválida ou expirada.";

    /// <summary>A rota só roda com usuário válido; sem ele, 401.</summary>
    public static RouteHandlerBuilder ExigirUsuario(this RouteHandlerBuilder rota) =>
        rota.AddEndpointFilter(async (contexto, proximo) =>
        {
            var http = contexto.HttpContext;
            var usuario = await Identificar(http);
            if (usuario is null)
                return NaoAutorizado(http);
            http.Items[Chave] = usuario;
            return await proximo(contexto);
        });

    public static Usuario UsuarioAtual(this HttpContext http) =>
        http.Items[Chave] as Usuario
        ?? throw new InvalidOperationException("Rota sem ExigirUsuario() pediu o usuário atual.");

    public static IResult NaoAutorizado(HttpContext http, string mensagem = MensagemInvalida)
    {
        http.Response.Headers.WWWAuthenticate = "Bearer";
        return Results.Json(new Dictionary<string, string> { ["detail"] = mensagem },
            statusCode: StatusCodes.Status401Unauthorized);
    }

    private static async Task<Usuario?> Identificar(HttpContext http)
    {
        var cabecalho = http.Request.Headers.Authorization.ToString();
        if (!cabecalho.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
            return null;

        var servicos = http.RequestServices;
        var log = servicos.GetRequiredService<ILogger<Usuario>>();
        ConteudoDoToken conteudo;
        try
        {
            conteudo = await servicos.GetRequiredService<IEmissorDeToken>().Ler(cabecalho["Bearer ".Length..].Trim());
        }
        catch (TokenInvalido erro)
        {
            log.Aviso("token recusado", new { motivo = erro.Motivo });
            return null;
        }

        var usuario = await servicos.GetRequiredService<IRepositorioDeUsuario>()
            .BuscarPorId(conteudo.UsuarioId, http.RequestAborted);
        if (usuario is null || !usuario.Ativo)
        {
            log.Aviso("token válido de usuário ausente ou inativo", new { usuario_id = conteudo.UsuarioId });
            return null;
        }
        return usuario;
    }
}

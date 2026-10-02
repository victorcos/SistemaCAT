using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Log;
using Cat.Aplicacao.Trabalhos;
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
    private const string ChaveTiquete = "cat.tiquete";
    public const string MensagemInvalida = "Sessão inválida ou expirada.";
    public const string MensagemDeTiquete = "Link de download inválido ou expirado. Peça o arquivo de novo na tela.";

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

    /// <summary>
    /// A rota aceita o cabeçalho <c>Authorization</c> **ou** um tíquete na URL.
    ///
    /// Só para download. A navegação do navegador não manda cabeçalho, e é por
    /// isso que o tíquete existe — ver <see cref="ITiquetesDeDownload"/>. Em
    /// nenhuma outra rota isto é aceitável: credencial em URL anda no histórico
    /// e no log, e só se justifica por ser de vida curta e por autorizar **um**
    /// arquivo.
    ///
    /// O usuário é relido do banco nos dois caminhos, com a mesma regra: quem
    /// foi desativada depois de o tíquete ser emitido não baixa.
    /// </summary>
    public static RouteHandlerBuilder ExigirUsuarioOuTiquete(this RouteHandlerBuilder rota) =>
        rota.AddEndpointFilter(async (contexto, proximo) =>
        {
            var http = contexto.HttpContext;
            var usuario = await Identificar(http);
            if (usuario is null)
            {
                var (porTiquete, autorizacao) = await PorTiquete(http);
                if (porTiquete is null)
                    return NaoAutorizado(http, TemTiquete(http) ? MensagemDeTiquete : MensagemInvalida);
                usuario = porTiquete;
                http.Items[ChaveTiquete] = autorizacao;
            }
            http.Items[Chave] = usuario;
            return await proximo(contexto);
        });

    /// <summary>
    /// O que o tíquete desta requisição autoriza, ou nulo se veio por cabeçalho.
    ///
    /// **A rota tem de servir o que ele diz, e não o que a URL pede.** Sem isso,
    /// um tíquete de um CSV pequeno pediria o xlsx inteiro trocando o parâmetro.
    /// </summary>
    public static AutorizacaoDeDownload? TiqueteAtual(this HttpContext http) =>
        http.Items.TryGetValue(ChaveTiquete, out var valor) ? valor as AutorizacaoDeDownload : null;

    private static bool TemTiquete(HttpContext http) =>
        !string.IsNullOrWhiteSpace(http.Request.Query[Tiquete.Parametro].FirstOrDefault());

    private static async Task<(Usuario?, AutorizacaoDeDownload?)> PorTiquete(HttpContext http)
    {
        var segredo = http.Request.Query[Tiquete.Parametro].FirstOrDefault();
        if (string.IsNullOrWhiteSpace(segredo))
            return (null, null);

        var servicos = http.RequestServices;
        var log = servicos.GetRequiredService<ILogger<Usuario>>();
        var autorizacao = await servicos.GetRequiredService<ITiquetesDeDownload>()
            .Resgatar(segredo, DateTimeOffset.UtcNow, http.RequestAborted);
        if (autorizacao is null)
        {
            log.Aviso("tíquete de download recusado", new { motivo = "inexistente ou vencido" });
            return (null, null);
        }

        var usuario = await servicos.GetRequiredService<IRepositorioDeUsuario>()
            .BuscarPorId(autorizacao.UsuarioId, http.RequestAborted);
        if (usuario is null || !usuario.Ativo)
        {
            log.Aviso("tíquete de usuário ausente ou inativo",
                new { usuario_id = autorizacao.UsuarioId });
            return (null, null);
        }
        return (usuario, autorizacao);
    }

    /// <summary>
    /// Exige uma CAPACIDADE do domínio, não um papel: enumerar papéis na rota
    /// faz todo papel novo exigir caçar rotas para atualizar. Vem depois de
    /// <see cref="ExigirUsuario"/> — sem sessão é 401, sem permissão é 403.
    /// </summary>
    public static RouteHandlerBuilder ExigirCapacidade(this RouteHandlerBuilder rota,
        Func<Papel, bool> capacidade, string nome, string descricao) =>
        rota.ExigirUsuario().AddEndpointFilter(async (contexto, proximo) =>
        {
            var usuario = contexto.HttpContext.UsuarioAtual();
            if (capacidade(usuario.Papel))
                return await proximo(contexto);
            contexto.HttpContext.RequestServices.GetRequiredService<ILogger<Usuario>>()
                .Aviso("acesso negado por falta de capacidade",
                    new { usuario_id = usuario.Id, papel = usuario.Papel.Valor(), capacidade_exigida = nome });
            return Results.Json(new Dictionary<string, string> { ["detail"] = $"Você não tem permissão para {descricao}." },
                statusCode: StatusCodes.Status403Forbidden);
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

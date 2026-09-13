using Cat.Api.Infra;
using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Cat.Infraestrutura.Auth;

namespace Cat.Api.Rotas;

/// <summary>
/// Gestão de usuários, portada de <c>usuarios_router.py</c>. Só gestor entra,
/// com uma exceção: a troca da própria senha, único caminho para sair da
/// senha provisória.
/// </summary>
public static class UsuariosRotas
{
    private const string AvisoCriado =
        "Entregue esta senha pessoalmente. Ela não será exibida de novo e " +
        "só serve para o primeiro acesso, quando a troca é obrigatória.";

    private const string AvisoRedefinido =
        "Entregue esta senha pessoalmente. Ela não será exibida de novo e " +
        "só serve para o próximo acesso, quando a troca é obrigatória.";

    // ---------- contratos ----------
    public sealed record UsuarioResumo(
        int Id, string Usuario, string Email, string NomeExibicao, string Papel, string Cargo,
        bool Ativo, bool Bloqueado, bool SenhaProvisoria, int TentativasFalhas,
        IReadOnlyList<int> Empresas, string? UltimoAcesso);

    public sealed record RespostaCriado(UsuarioResumo Usuario, string SenhaProvisoria, string Aviso);
    public sealed record RespostaSenhaRedefinida(string SenhaProvisoria, string Aviso);
    public sealed record AcessoDto(int EmpresaId, string RazaoSocial, string? Uf, bool TemAcesso, string? Desde);
    public sealed record MudancaDeAcessoDto(IReadOnlyList<string> Concedidas, IReadOnlyList<string> Encerradas);

    private sealed record PedidoCriar(string? Usuario, string? Email, string? NomeExibicao, string? Papel, string? Cargo);
    private sealed record PedidoPapel(string? Papel);
    private sealed record PedidoCargo(string? Cargo);
    private sealed record PedidoDados(string? NomeExibicao, string? Email);
    private sealed record PedidoDeAcesso(List<int>? Empresas);
    private sealed record PedidoSituacao(bool? Ativo);
    private sealed record PedidoTrocarSenha(string? SenhaAtual, string? SenhaNova);

    public static void MapearUsuarios(this IEndpointRouteBuilder rotas)
    {
        var grupo = rotas.MapGroup("/api/usuarios").WithTags("usuários");

        // A de qualquer usuário autenticado. O literal "eu" vence o parâmetro
        // {alvoId:int} pela precedência de rota — no FastAPI dependia da ordem
        // de declaração, e um descuido capturava "eu" como identificador.
        grupo.MapPost("/eu/senha", TrocarPropriaSenha).ExigirUsuario();

        grupo.MapGet("", async (GerirUsuarios caso, TimeProvider relogio, CancellationToken c) =>
                Results.Json((await caso.Listar(c)).Select(u => Resumo(u, relogio)).ToList()))
            .SoGestor();
        grupo.MapPost("", Criar).SoGestor();
        grupo.MapPost("/{alvoId:int}/senha", async (int alvoId, HttpContext http, GerirUsuarios caso) =>
                await Traduzir(http, "redefinir_senha", async () =>
                    Results.Json(new RespostaSenhaRedefinida(
                        await caso.RedefinirSenha(alvoId, http.UsuarioAtual(), http.RequestAborted), AvisoRedefinido))))
            .SoGestor();
        grupo.MapPatch("/{alvoId:int}/papel", AlterarPapel).SoGestor();
        grupo.MapGet("/{alvoId:int}/empresas", ListarAcesso).SoGestor();
        grupo.MapPut("/{alvoId:int}/empresas", DefinirAcesso).SoGestor();
        grupo.MapPatch("/{alvoId:int}/dados", AlterarDados).SoGestor();
        grupo.MapPatch("/{alvoId:int}/cargo", AlterarCargo).SoGestor();
        grupo.MapPatch("/{alvoId:int}/situacao", DefinirSituacao).SoGestor();
        grupo.MapPost("/{alvoId:int}/desbloquear", async (int alvoId, HttpContext http, GerirUsuarios caso, TimeProvider relogio) =>
                await Traduzir(http, "desbloquear", async () =>
                    Results.Json(Resumo(await caso.Desbloquear(alvoId, http.UsuarioAtual(), http.RequestAborted), relogio))))
            .SoGestor();
    }

    /// <summary>
    /// Quem administra usuários: gestor e dev. A lista de papéis mora no
    /// domínio, em <see cref="Capacidades.AdministraUsuarios"/>, e não aqui.
    /// </summary>
    private static RouteHandlerBuilder SoGestor(this RouteHandlerBuilder rota) =>
        rota.ExigirCapacidade(Capacidades.AdministraUsuarios, "administra_usuarios", "administrar usuários");

    // ---------- rotas ----------
    private static async Task<IResult> TrocarPropriaSenha(HttpContext http, GerirUsuarios caso)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoTrocarSenha>(http);
        if (recusa is not null)
            return recusa;
        if (pedido!.SenhaAtual is null || pedido.SenhaNova is null)
            return CorpoJson.Recusar("Informe a senha atual e a nova.");

        var usuario = http.UsuarioAtual();
        return await Traduzir(http, "trocar_propria_senha", async () =>
        {
            await caso.TrocarPropriaSenha(usuario, pedido.SenhaAtual, pedido.SenhaNova, http.RequestAborted);
            return Results.NoContent();
        }, new { usuario_id = usuario.Id });
    }

    private static async Task<IResult> Criar(HttpContext http, GerirUsuarios caso, TimeProvider relogio)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoCriar>(http);
        if (recusa is not null)
            return recusa;
        // os limites que o Pydantic conferia antes de chegar ao caso de uso
        if (pedido!.Usuario is not { Length: >= 3 and <= 40 })
            return CorpoJson.Recusar("Nome de usuário deve ter de 3 a 40 caracteres.");
        if (pedido.Email is null)
            return CorpoJson.Recusar("Informe o e-mail.");
        if (pedido.NomeExibicao is not { Length: >= 2 })
            return CorpoJson.Recusar("O nome de exibição precisa de pelo menos 2 caracteres.");
        if (!TextoDeAcesso.TentarPapel(pedido.Papel, out var papel))
            return CorpoJson.Recusar($"Papel desconhecido: {pedido.Papel}.");
        var cargo = Cargo.Outro;
        if (pedido.Cargo is not null && !TextoDeAcesso.TentarCargo(pedido.Cargo, out cargo))
            return CorpoJson.Recusar($"Cargo desconhecido: {pedido.Cargo}.");

        var gestor = http.UsuarioAtual();
        return await Traduzir(http, "criar_usuario", async () =>
        {
            var r = await caso.Criar(pedido.Usuario, pedido.Email, pedido.NomeExibicao, papel, cargo, gestor,
                http.RequestAborted);
            return Results.Json(new RespostaCriado(Resumo(r.Usuario, relogio), r.SenhaProvisoria, AvisoCriado),
                statusCode: StatusCodes.Status201Created);
        });
    }

    private static async Task<IResult> AlterarPapel(int alvoId, HttpContext http, GerirUsuarios caso, TimeProvider relogio)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoPapel>(http);
        if (recusa is not null)
            return recusa;
        if (!TextoDeAcesso.TentarPapel(pedido!.Papel, out var papel))
            return CorpoJson.Recusar($"Papel desconhecido: {pedido.Papel}.");
        return await Traduzir(http, "alterar_papel", async () =>
            Results.Json(Resumo(await caso.AlterarPapel(alvoId, papel, http.UsuarioAtual(), http.RequestAborted), relogio)));
    }

    private static async Task<IResult> AlterarCargo(int alvoId, HttpContext http, GerirUsuarios caso, TimeProvider relogio)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoCargo>(http);
        if (recusa is not null)
            return recusa;
        if (!TextoDeAcesso.TentarCargo(pedido!.Cargo, out var cargo))
            return CorpoJson.Recusar($"Cargo desconhecido: {pedido.Cargo}.");
        return await Traduzir(http, "alterar_cargo", async () =>
            Results.Json(Resumo(await caso.AlterarCargo(alvoId, cargo, http.UsuarioAtual(), http.RequestAborted), relogio)));
    }

    /// <summary>
    /// Nome de exibição e e-mail. Papel, cargo e situação têm rota própria
    /// porque têm regra própria (mínimo de gestores, não alterar a si mesmo).
    /// </summary>
    private static async Task<IResult> AlterarDados(int alvoId, HttpContext http, GerirUsuarios caso, TimeProvider relogio)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoDados>(http);
        if (recusa is not null)
            return recusa;
        if (pedido!.NomeExibicao is not { Length: >= 2 })
            return CorpoJson.Recusar("O nome de exibição precisa de pelo menos 2 caracteres.");
        if (pedido.Email is null)
            return CorpoJson.Recusar("Informe o e-mail.");
        return await Traduzir(http, "alterar_dados", async () =>
            Results.Json(Resumo(await caso.AlterarDados(alvoId, pedido.NomeExibicao, pedido.Email,
                http.UsuarioAtual(), http.RequestAborted), relogio)));
    }

    private static async Task<IResult> DefinirSituacao(int alvoId, HttpContext http, GerirUsuarios caso, TimeProvider relogio)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoSituacao>(http);
        if (recusa is not null)
            return recusa;
        if (pedido!.Ativo is not { } ativo)
            return CorpoJson.Recusar("Informe se o usuário fica ativo.");
        return await Traduzir(http, "definir_situacao", async () =>
            Results.Json(Resumo(await caso.DefinirSituacao(alvoId, ativo, http.UsuarioAtual(), http.RequestAborted), relogio)));
    }

    /// <summary>Todas as empresas, marcando quais esta pessoa alcança hoje.</summary>
    private static Task<IResult> ListarAcesso(int alvoId, HttpContext http, AcessoAEmpresas caso) =>
        Traduzir(http, "listar_acesso", async () => Results.Json(
            (await caso.Listar(alvoId, http.RequestAborted))
            .Select(a => new AcessoDto(a.EmpresaId, a.RazaoSocial, a.Uf, a.TemAcesso,
                a.Desde is { } desde ? AuthRotas.IsoComoPython(desde) : null))
            .ToList()));

    /// <summary>
    /// Faz o acesso ser exatamente esta lista. Tirar acesso não apaga a
    /// alocação, encerra: quem tinha acesso a um dado em determinado mês
    /// precisa continuar respondível.
    /// </summary>
    private static async Task<IResult> DefinirAcesso(int alvoId, HttpContext http, AcessoAEmpresas caso)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoDeAcesso>(http);
        if (recusa is not null)
            return recusa;
        if (pedido!.Empresas is null)
            return CorpoJson.Recusar("Informe a lista de empresas.");
        return await Traduzir(http, "alocar_em_empresas", async () =>
        {
            var mudou = await caso.Definir(alvoId, pedido.Empresas.ToHashSet(), http.UsuarioAtual(), http.RequestAborted);
            return Results.Json(new MudancaDeAcessoDto(mudou.Concedidas, mudou.Encerradas));
        }, new { alvo_id = alvoId });
    }

    // ---------- tradução ----------
    public static UsuarioResumo Resumo(Usuario u, TimeProvider relogio) => new(
        u.Id, u.NomeDeUsuario, u.Email, u.NomeExibicao, u.Papel.Valor(), u.Cargo.Valor(),
        u.Ativo, u.Bloqueado(relogio.GetUtcNow()), u.SenhaProvisoria, u.TentativasFalhas, u.Empresas,
        u.UltimoAcesso is { } acesso ? AuthRotas.IsoComoPython(acesso) : null);

    /// <summary>
    /// Recusa de regra vira resposta HTTP. A regra fica no domínio e no caso de
    /// uso; aqui só o código, na mesma tabela do <c>_traduzir</c> do Python.
    /// </summary>
    private static async Task<IResult> Traduzir(HttpContext http, string etapa, Func<Task<IResult>> operacao,
        object? extra = null)
    {
        var log = http.RequestServices.GetRequiredService<ILogger<GerirUsuarios>>();
        var contexto = new Dictionary<string, object?> { ["etapa"] = etapa };
        if (http.Items.ContainsKey("cat.usuario"))
            contexto["por_usuario_id"] = http.UsuarioAtual().Id;
        foreach (var (chave, valor) in Registro.ParaDicionario(extra))
            contexto[chave] = valor;
        using var _ = log.Contexto(contexto);

        try
        {
            return await operacao();
        }
        catch (Exception erro) when (Codigo(erro) is { } status)
        {
            return CorpoJson.Recusar(erro.Message, status);
        }
    }

    private static int? Codigo(Exception erro) => erro switch
    {
        NaoPodeAlocar => StatusCodes.Status403Forbidden,
        // Era 401 no Python. A tela entende 401 com token como sessão vencida:
        // errar a senha atual na troca expulsava a pessoa para o login. 403 é o
        // que a confirmação de exclusão de trabalho já usa para senha errada.
        SenhaAtualIncorreta => StatusCodes.Status403Forbidden,
        UsuarioNaoEncontrado => StatusCodes.Status404NotFound,
        UltimoGestor or NaoPodeAlterarSiMesmo or UsuarioJaExiste => StatusCodes.Status409Conflict,
        NaoPodeTirarDeSi or EmpresaInexistente or SenhaFraca or SenhaRepetida or DadoInvalido or SenhaLonga
            => StatusCodes.Status422UnprocessableEntity,
        _ => null,
    };
}

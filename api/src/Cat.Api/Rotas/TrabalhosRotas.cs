using System.Globalization;
using Cat.Api.Infra;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Comum;
using Cat.Dominio.Projeto;

namespace Cat.Api.Rotas;

/// <summary>
/// Empresas, frentes e projetos, portados de <c>importacao_router.py</c>. A
/// análise da remessa, que lê o arquivo enviado, segue no motor.
/// </summary>
public static class TrabalhosRotas
{
    // ---------- contratos ----------
    public sealed record EmpresaDto(
        int Id, string CnpjRaiz, string? CnpjMatriz, string? CnpjMatrizFormatado, string RazaoSocial, string? Uf,
        string? InscricaoEstadual, bool PreCadastro, int Projetos);

    public sealed record ProjetoDto(
        int Id, int EmpresaId, string Empresa, string? CnpjMatriz, string? CnpjMatrizFormatado, string? Uf,
        string Frente, string FrenteRotulo, string Nome, DateOnly CompetenciaIni, DateOnly CompetenciaFim,
        string Status, string StatusRotulo, bool PreCadastro, int EtapasFeitas, int EtapasTotais,
        string? CriadoPor, int? CriadoPorId, string? Responsavel, int? ResponsavelId, int Comentarios,
        string VendaAConsumidor, string VendaAConsumidorRotulo);

    public sealed record EtapaDto(
        string Chave, string Nome, string Descricao, string Situacao, string SituacaoRotulo, bool Implementada, bool Acessivel);

    public sealed record ProjetoDetalheDto(ProjetoDto Projeto, IReadOnlyList<EtapaDto> Etapas);

    public sealed record OQueSeraApagadoDto(string Projeto, string Empresa, int Lotes, int Arquivos, int Execucoes);

    private sealed record PedidoEmpresa(
        string? CnpjRaiz, string? CnpjMatriz, string? RazaoSocial, string? Uf, string? InscricaoEstadual, string? GrupoEconomico);

    private sealed record PedidoProjeto(
        int? EmpresaId, string? Frente, string? Nome, string? CompetenciaIni, string? CompetenciaFim, string? Observacao);

    private sealed record ConfirmacaoDeExclusao(string? Senha);

    private sealed record PedidoVendaAConsumidor(string? Valor);

    public sealed record OpcaoDto(string Valor, string Rotulo, string Explicacao);

    public static void MapearTrabalhos(this IEndpointRouteBuilder rotas)
    {
        var api = rotas.MapGroup("/api").WithTags("trabalhos");

        api.MapGet("/empresas", async (HttpContext http, Trabalhos caso) =>
                Results.Json((await caso.ListarEmpresas(http.UsuarioAtual(), http.RequestAborted)).Select(Empresa).ToList()))
            .ExigirUsuario();
        api.MapPost("/empresas", CriarEmpresa).PodeEscrever();

        // aberta como no Python: é a lista fixa das frentes, não dado de cliente
        api.MapGet("/frentes", () => Results.Json(Frentes.Todas.ToDictionary(f => f.Key, f => f.Value)));

        api.MapGet("/projetos", async (HttpContext http, Trabalhos caso) =>
                Results.Json((await caso.ListarProjetos(http.UsuarioAtual(), http.RequestAborted)).Select(Projeto).ToList()))
            .ExigirUsuario();
        api.MapPost("/projetos", CriarProjeto).PodeEscrever();
        api.MapGet("/projetos/{projetoId:int}", async (int projetoId, HttpContext http, Trabalhos caso) =>
                await Traduzir(async () =>
                {
                    var p = await caso.Detalhar(projetoId, http.UsuarioAtual(), http.RequestAborted);
                    return Results.Json(new ProjetoDetalheDto(Projeto(p), p.Etapas.Select(Etapa).ToList()));
                }))
            .ExigirUsuario();

        // as duas leituras da venda a consumidor final: a tela mostra as duas, com o porquê
        api.MapGet("/venda-a-consumidor", () =>
            Results.Json(VendaAConsumidor.Todas.Select(v => new OpcaoDto(v.Valor, v.Rotulo, v.Explicacao)).ToList()));
        api.MapPut("/projetos/{projetoId:int}/venda-a-consumidor", DefinirVendaAConsumidor)
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "mudar o enquadramento da venda a consumidor");

        api.MapGet("/projetos/{projetoId:int}/exclusao", async (int projetoId, HttpContext http, ExcluirTrabalho caso) =>
                await Traduzir(async () =>
                    Results.Json(Apagado(await caso.Resumir(projetoId, http.UsuarioAtual(), http.RequestAborted)))))
            .PodeExcluir();
        api.MapDelete("/projetos/{projetoId:int}", Excluir).PodeExcluir();
    }

    private static RouteHandlerBuilder PodeEscrever(this RouteHandlerBuilder rota) =>
        rota.ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "importar arquivos");

    /// <summary>
    /// Apagar um trabalho é de quem responde pelo cliente: gestores e a conta de
    /// manutenção. Analista e revisor escrevem, mas não desfazem meses de trabalho.
    /// </summary>
    private static RouteHandlerBuilder PodeExcluir(this RouteHandlerBuilder rota) =>
        rota.ExigirCapacidade(Capacidades.PodeExcluirTrabalho, "pode_excluir_trabalho", "excluir um trabalho");

    // ---------- rotas ----------
    private static async Task<IResult> CriarEmpresa(HttpContext http, Trabalhos caso)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoEmpresa>(http);
        if (recusa is not null)
            return recusa;
        // os limites que o Pydantic conferia antes de chegar à regra
        if (pedido!.CnpjRaiz is not { Length: 8 })
            return CorpoJson.Recusar("A raiz do CNPJ tem 8 caracteres.");
        if (pedido.CnpjMatriz is null)
            return CorpoJson.Recusar("Informe o CNPJ da matriz.");
        if (pedido.RazaoSocial is not { Length: >= 2 })
            return CorpoJson.Recusar("A razão social precisa de pelo menos 2 caracteres.");
        if (pedido.Uf is not { Length: 2 })
            return CorpoJson.Recusar("A UF tem 2 letras.");

        return await Traduzir(async () =>
        {
            var e = await caso.CriarEmpresa(pedido.CnpjRaiz, pedido.CnpjMatriz, pedido.RazaoSocial, pedido.Uf,
                pedido.InscricaoEstadual, pedido.GrupoEconomico, http.UsuarioAtual(), http.RequestAborted);
            return Results.Json(Empresa(e), statusCode: StatusCodes.Status201Created);
        });
    }

    private static async Task<IResult> CriarProjeto(HttpContext http, Trabalhos caso)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoProjeto>(http);
        if (recusa is not null)
            return recusa;
        if (pedido!.EmpresaId is not { } empresaId)
            return CorpoJson.Recusar("Informe a empresa.");
        if (pedido.Frente is null)
            return CorpoJson.Recusar("Informe a frente.");
        if (pedido.Nome is not { Length: >= 2 })
            return CorpoJson.Recusar("O nome do projeto precisa de pelo menos 2 caracteres.");
        if (!Data(pedido.CompetenciaIni, out var ini) || !Data(pedido.CompetenciaFim, out var fim))
            return CorpoJson.Recusar("Competência inicial e final são datas no formato AAAA-MM-DD.");

        return await Traduzir(async () =>
        {
            var p = await caso.CriarProjeto(empresaId, pedido.Frente, pedido.Nome, ini, fim, pedido.Observacao,
                http.UsuarioAtual(), http.RequestAborted);
            return Results.Json(Projeto(p), statusCode: StatusCodes.Status201Created);
        });
    }

    private static async Task<IResult> DefinirVendaAConsumidor(int projetoId, HttpContext http, Trabalhos caso)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoVendaAConsumidor>(http);
        if (recusa is not null)
            return recusa;
        if (pedido!.Valor is not { Length: > 0 })
            return CorpoJson.Recusar("Informe a escolha para a venda a consumidor.");
        return await Traduzir(async () =>
            Results.Json(Projeto(await caso.DefinirVendaAConsumidor(projetoId, pedido.Valor, http.UsuarioAtual(),
                http.RequestAborted))));
    }

    private static async Task<IResult> Excluir(int projetoId, HttpContext http, ExcluirTrabalho caso)
    {
        var (pedido, recusa) = await CorpoJson.Ler<ConfirmacaoDeExclusao>(http);
        if (recusa is not null)
            return recusa;
        // o contrato exige senha não vazia: sem ela, nem se pergunta ao resumo
        if (pedido!.Senha is not { Length: >= 1 and <= 200 })
            return CorpoJson.Recusar("Informe a sua senha para confirmar a exclusão.");

        return await Traduzir(async () =>
            Results.Json(Apagado(await caso.Executar(projetoId, http.UsuarioAtual(), pedido.Senha, http.RequestAborted))));
    }

    // ---------- tradução ----------
    private static bool Data(string? texto, out DateOnly data) =>
        DateOnly.TryParseExact(texto, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out data);

    public static EmpresaDto Empresa(EmpresaLida e) => new(
        e.Id, e.CnpjRaiz, e.CnpjMatriz, Cnpj.Tentar(e.CnpjMatriz)?.Formatado, e.RazaoSocial, e.Uf, e.InscricaoEstadual,
        e.PreCadastro, e.TemProjeto ? 1 : 0);

    public static ProjetoDto Projeto(ProjetoComEtapas pe)
    {
        var p = pe.Projeto;
        var (feitas, totais) = pe.Progresso;
        return new ProjetoDto(
            p.Id, p.EmpresaId, p.Empresa, p.CnpjMatriz, Cnpj.Tentar(p.CnpjMatriz)?.Formatado, p.Uf,
            p.Frente, Frentes.Rotulo(p.Frente), p.Nome, p.CompetenciaIni, p.CompetenciaFim,
            p.Status, StatusDoProjeto.Rotulo(p.Status), p.PreCadastro, feitas, totais,
            p.CriadoPor, p.CriadoPorId, p.Responsavel, p.ResponsavelId, p.Comentarios,
            VendaAConsumidor.DoBanco(p.VendaAConsumidor).Valor, VendaAConsumidor.DoBanco(p.VendaAConsumidor).Rotulo);
    }

    private static EtapaDto Etapa(EtapaDoProjeto e) => new(
        e.Definicao.Chave, e.Definicao.Nome, e.Definicao.Descricao, e.Situacao.Valor(), e.Situacao.Rotulo(),
        e.Definicao.Implementada, e.Acessivel);

    private static OQueSeraApagadoDto Apagado(OQueSeraApagado o) => new(o.Projeto, o.Empresa, o.Lotes, o.Arquivos, o.Execucoes);

    private static async Task<IResult> Traduzir(Func<Task<IResult>> operacao)
    {
        try
        {
            return await operacao();
        }
        catch (Exception erro) when (Codigo(erro) is { } status)
        {
            return CorpoJson.Recusar(erro is MotorIndisponivel
                ? "O motor do sistema não respondeu. O trabalho não foi apagado."
                : erro.Message, status);
        }
    }

    private static int? Codigo(Exception erro) => erro switch
    {
        SemAcessoAEmpresa or SenhaNaoConfere => StatusCodes.Status403Forbidden,
        ProjetoNaoEncontrado or EmpresaNaoEncontrada => StatusCodes.Status404NotFound,
        EmpresaJaCadastrada or ProjetoRepetido => StatusCodes.Status409Conflict,
        DadoInvalido or RaizNaoConfere or FrenteDesconhecida or CompetenciasInvertidas
            or VendaAConsumidorDesconhecida => StatusCodes.Status422UnprocessableEntity,
        MesmaVendaAConsumidor => StatusCodes.Status409Conflict,
        MotorIndisponivel => StatusCodes.Status502BadGateway,
        _ => null,
    };
}

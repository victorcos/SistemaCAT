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
        string Frente, string FrenteRotulo, string Modulo, string ModuloRotulo,
        string Nome, DateOnly CompetenciaIni, DateOnly CompetenciaFim,
        string Status, string StatusRotulo, bool PreCadastro, int EtapasFeitas, int EtapasTotais,
        string? CriadoPor, int? CriadoPorId, string? Responsavel, int? ResponsavelId, int Comentarios,
        string VendaAConsumidor, string VendaAConsumidorRotulo);

    /// <param name="NomeCurto">o rótulo da barra do trabalho: "Arquivos", "Quebras"…</param>
    public sealed record EtapaDto(
        string Chave, string Nome, string NomeCurto, string Descricao, string Situacao,
        string SituacaoRotulo, bool Implementada, bool Acessivel);

    /// <summary>
    /// Uma frente de trabalho do módulo — a CAT 42, o crédito outorgado, a
    /// quebra de XML —, com as etapas que cabem dentro dela e quanto já foi
    /// feito. É o card que a tela do trabalho abre.
    /// </summary>
    /// <param name="Etapas">chaves de <c>EtapaDto</c>, na ordem da frente</param>
    /// <param name="Construida">
    /// Se a frente já existe no sistema. Falso quando nenhuma etapa própria dela
    /// foi construída — `importar`, que toda frente tem, não conta aqui: sem
    /// isso a quebra de XML apareceria como "1 de 1 concluída" só porque a base
    /// foi importada.
    /// </param>
    public sealed record TrilhaDto(string Chave, string Rotulo, string Sigla, string Descricao,
        IReadOnlyList<string> Etapas, int Feitas, int Totais, bool Construida);

    public sealed record ProjetoDetalheDto(ProjetoDto Projeto, IReadOnlyList<EtapaDto> Etapas,
        BaseDto Base, IReadOnlyList<TrilhaDto> Trilhas);

    /// <summary>De quando é a base importada; `fora_do_periodo` são as EFD fora do período do cadastro.</summary>
    public sealed record BaseDto(int Efds, DateOnly? Primeira, DateOnly? Ultima, int ForaDoPeriodo);

    public sealed record OQueSeraApagadoDto(string Projeto, string Empresa, int Lotes, int Arquivos, int Execucoes);

    private sealed record PedidoEmpresa(
        string? CnpjRaiz, string? CnpjMatriz, string? RazaoSocial, string? Uf, string? InscricaoEstadual, string? GrupoEconomico);

    private sealed record PedidoProjeto(
        int? EmpresaId, string? Frente, string? Modulo, string? Nome, string? CompetenciaIni,
        string? CompetenciaFim, string? Observacao);

    private sealed record ConfirmacaoDeExclusao(string? Senha);

    private sealed record PedidoVendaAConsumidor(string? Valor);

    private sealed record PedidoDeCadastro(string? Nome, string? CompetenciaIni, string? CompetenciaFim);

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

        // ?modulo= é o recorte da tela do segmento: sem ele, a lista sai inteira,
        // como sempre saiu, e nenhuma tela antiga muda de comportamento
        api.MapGet("/projetos", async (HttpContext http, Trabalhos caso) =>
            {
                var todos = await caso.ListarProjetos(http.UsuarioAtual(), http.RequestAborted);
                var modulo = http.Request.Query["modulo"].FirstOrDefault();
                var recorte = string.IsNullOrWhiteSpace(modulo)
                    ? todos
                    : todos.Where(p => p.Projeto.Modulo == modulo).ToList();
                return Results.Json(recorte.Select(Projeto).ToList());
            })
            .ExigirUsuario();
        api.MapPost("/projetos", CriarProjeto).PodeEscrever();
        api.MapGet("/projetos/{projetoId:int}", async (int projetoId, HttpContext http, Trabalhos caso) =>
                await Traduzir(async () =>
                {
                    var p = await caso.Detalhar(projetoId, http.UsuarioAtual(), http.RequestAborted);
                    var b = await caso.BaseDoTrabalho(p.Projeto, http.RequestAborted);
                    return Results.Json(new ProjetoDetalheDto(Projeto(p), p.Etapas.Select(Etapa).ToList(),
                        new BaseDto(b.Efds, b.Primeira, b.Ultima, b.ForaDoPeriodo),
                        Trilhas(p)));
                }))
            .ExigirUsuario();

        // as duas leituras da venda a consumidor final: a tela mostra as duas, com o porquê
        api.MapGet("/venda-a-consumidor", () =>
            Results.Json(VendaAConsumidor.Todas.Select(v => new OpcaoDto(v.Valor, v.Rotulo, v.Explicacao)).ToList()));
        api.MapPatch("/projetos/{projetoId:int}/cadastro", AlterarCadastro)
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "alterar o cadastro do trabalho");
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
                http.UsuarioAtual(), http.RequestAborted, pedido.Modulo);
            return Results.Json(Projeto(p), statusCode: StatusCodes.Status201Created);
        });
    }

    private static async Task<IResult> AlterarCadastro(int projetoId, HttpContext http, Trabalhos caso)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoDeCadastro>(http);
        if (recusa is not null)
            return recusa;
        DateOnly? ini = null, fim = null;
        if (pedido!.CompetenciaIni is not null)
        {
            if (!Data(pedido.CompetenciaIni, out var d))
                return CorpoJson.Recusar("Competência inicial e final são datas no formato AAAA-MM-DD.");
            ini = d;
        }
        if (pedido.CompetenciaFim is not null)
        {
            if (!Data(pedido.CompetenciaFim, out var d))
                return CorpoJson.Recusar("Competência inicial e final são datas no formato AAAA-MM-DD.");
            fim = d;
        }
        return await Traduzir(async () =>
            Results.Json(Projeto(await caso.AlterarCadastro(projetoId, pedido.Nome, ini, fim, http.UsuarioAtual(),
                http.RequestAborted))));
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

    /// <summary>Módulo que saiu do catálogo aparece pela chave, não some da tela.</summary>
    private static string RotuloDoModulo(string chave) =>
        Segmentos.Todos.SelectMany(s => s.Modulos).FirstOrDefault(m => m.Chave == chave)?.Rotulo ?? chave;

    public static ProjetoDto Projeto(ProjetoComEtapas pe)
    {
        var p = pe.Projeto;
        var (feitas, totais) = pe.Progresso;
        return new ProjetoDto(
            p.Id, p.EmpresaId, p.Empresa, p.CnpjMatriz, Cnpj.Tentar(p.CnpjMatriz)?.Formatado, p.Uf,
            p.Frente, Frentes.Rotulo(p.Frente), p.Modulo, RotuloDoModulo(p.Modulo),
            p.Nome, p.CompetenciaIni, p.CompetenciaFim,
            p.Status, StatusDoProjeto.Rotulo(p.Status), p.PreCadastro, feitas, totais,
            p.CriadoPor, p.CriadoPorId, p.Responsavel, p.ResponsavelId, p.Comentarios,
            VendaAConsumidor.DoBanco(p.VendaAConsumidor).Valor, VendaAConsumidor.DoBanco(p.VendaAConsumidor).Rotulo);
    }

    /// <summary>
    /// As frentes do módulo, com o progresso de cada uma medido sobre as
    /// etapas dela — e não sobre o trabalho inteiro. O denominador segue a
    /// mesma regra do progresso geral: só conta o que existe e o que conclui.
    /// </summary>
    private static IReadOnlyList<TrilhaDto> Trilhas(ProjetoComEtapas pe)
    {
        var porChave = pe.Etapas.ToDictionary(e => e.Definicao.Chave);
        return Etapas.TrilhasDo(pe.Projeto.Modulo).Select(t =>
        {
            var minhas = t.Etapas.Where(porChave.ContainsKey).Select(c => porChave[c]).ToList();
            var (feitas, totais) = Cat.Dominio.Projeto.Etapas.Progresso(minhas);
            // qualquer etapa própria da frente serve. O `!= "importar"` que havia
            // aqui existia porque `importar` era a primeira etapa de **todas**,
            // e sem a exclusão toda frente pareceria construída só por ter a
            // base. Desde 30/09/2026 ela é trilha própria e só aparece na sua,
            // onde é a etapa dela — a exclusão passou a apagar o card certo
            var construida = minhas.Any(e => e.Definicao.Implementada);
            return new TrilhaDto(t.Chave, t.Rotulo, t.Sigla, t.Descricao,
                minhas.Select(e => e.Definicao.Chave).ToList(), feitas, totais, construida);
        }).ToList();
    }

    private static EtapaDto Etapa(EtapaDoProjeto e) => new(
        e.Definicao.Chave, e.Definicao.Nome, e.Definicao.Rotulo, e.Definicao.Descricao,
        e.Situacao.Valor(), e.Situacao.Rotulo(),
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
        SemAcessoAEmpresa or SemAcessoAoSegmento or SenhaNaoConfere => StatusCodes.Status403Forbidden,
        ProjetoNaoEncontrado or EmpresaNaoEncontrada => StatusCodes.Status404NotFound,
        EmpresaJaCadastrada or ProjetoRepetido => StatusCodes.Status409Conflict,
        DadoInvalido or RaizNaoConfere or FrenteDesconhecida or CompetenciasInvertidas
            or VendaAConsumidorDesconhecida => StatusCodes.Status422UnprocessableEntity,
        MesmaVendaAConsumidor or CadastroSemMudanca => StatusCodes.Status409Conflict,
        MotorIndisponivel => StatusCodes.Status502BadGateway,
        _ => null,
    };
}

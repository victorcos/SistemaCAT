using Cat.Api.Infra;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Lote;
using Microsoft.AspNetCore.Http.Features;

namespace Cat.Api.Rotas;

/// <summary>
/// Lote de arquivos e análise da remessa, portados de <c>lote_router.py</c> e
/// <c>importacao_router.py</c>. O que é leitura de disco vai ao motor pelo canal interno.
/// </summary>
public static class LotesRotas
{
    // quantos arquivos a tela recebe de volta na conferência: a lista existe para
    // o usuário reconhecer o que está vendo, não para ler 7.036 linhas
    public const int AmostraNaTela = 40;

    // ---------- contratos ----------
    public sealed record ContagemDto(string Tipo, string Rotulo, string Grupo, bool AlimentaACat, int Quantidade);

    public sealed record ArquivoDto(
        string Nome, string Caminho, long Tamanho, string Tipo, string TipoRotulo, string Grupo, bool AlimentaACat,
        string? Cnpj, DateOnly? Competencia, string Uf, string Detalhe, string Motivo);

    public sealed record ResumoDto(
        string Pasta, int TotalArquivos, int ArquivosUteis, long BytesTotais, int DeOutraEmpresa, bool Serve,
        DateOnly? CompetenciaIni, DateOnly? CompetenciaFim, IReadOnlyList<string> Cnpjs, IReadOnlyList<ContagemDto> Contagens,
        IReadOnlyList<string> Avisos, IReadOnlyList<ArquivoDto> Amostra, int JaNoTrabalho, int Copias);

    public sealed record LoteDto(
        int Id, int ProjetoId, string Pasta, int TotalArquivos, int ArquivosUteis, long BytesTotais,
        DateOnly? CompetenciaIni, DateOnly? CompetenciaFim, string? Observacao, string CriadoEm,
        IReadOnlyList<ContagemDto> Contagens);

    public sealed record LoteApagadoDto(string Pasta, int Arquivos, int ConferenciasInvalidadas);

    private sealed record PastaEntrada(string? Pasta, string? Observacao);

    public static void MapearLotes(this IEndpointRouteBuilder rotas)
    {
        var api = rotas.MapGroup("/api").WithTags("lote");

        api.MapPost("/projetos/{projetoId:int}/lotes/inspecionar", Inspecionar).PodeImportarLote();
        api.MapPost("/projetos/{projetoId:int}/lotes", Registrar).PodeImportarLote();
        api.MapGet("/projetos/{projetoId:int}/lotes", async (int projetoId, HttpContext http, Lotes caso) =>
                await Traduzir(async () => Results.Json(
                    (await caso.Listar(projetoId, http.UsuarioAtual(), http.RequestAborted)).Select(Lote).ToList())))
            .ExigirUsuario();
        // não pede senha: desfaz uma importação, não o trabalho
        api.MapDelete("/projetos/{projetoId:int}/lotes/{loteId:int}", async (int projetoId, int loteId, HttpContext http, Lotes caso) =>
                await Traduzir(async () =>
                {
                    var r = await caso.Remover(projetoId, loteId, http.UsuarioAtual(), http.RequestAborted);
                    return Results.Json(new LoteApagadoDto(r.Pasta, r.Arquivos, r.ConferenciasInvalidadas));
                }))
            .PodeImportarLote();

        api.MapPost("/importacoes/analisar", AnalisarRemessa).DisableAntiforgery()
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "importar arquivos");
    }

    private static RouteHandlerBuilder PodeImportarLote(this RouteHandlerBuilder rota) =>
        rota.ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "importar lote de arquivos");

    // ---------- rotas ----------
    private static async Task<(PastaEntrada? Pedido, IResult? Recusa)> LerPasta(HttpContext http)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PastaEntrada>(http);
        if (recusa is not null)
            return (null, recusa);
        if (pedido!.Pasta is not { Length: >= 1 and <= 1000 })
            return (null, CorpoJson.Recusar("Informe a pasta onde estão os arquivos."));
        if (pedido.Observacao is { Length: > 500 })
            return (null, CorpoJson.Recusar("A observação passa de 500 caracteres."));
        return (pedido, null);
    }

    private static async Task<IResult> Inspecionar(int projetoId, HttpContext http, Lotes caso)
    {
        var (pedido, recusa) = await LerPasta(http);
        if (recusa is not null)
            return recusa;
        return await Traduzir(async () =>
            Results.Json(Resumo(await caso.Inspecionar(projetoId, pedido!.Pasta!, http.UsuarioAtual(), http.RequestAborted))));
    }

    private static async Task<IResult> Registrar(int projetoId, HttpContext http, Lotes caso)
    {
        var (pedido, recusa) = await LerPasta(http);
        if (recusa is not null)
            return recusa;
        return await Traduzir(async () => Results.Json(
            Lote(await caso.Registrar(projetoId, pedido!.Pasta!, pedido.Observacao, http.UsuarioAtual(), http.RequestAborted)),
            statusCode: StatusCodes.Status201Created));
    }

    /// <summary>
    /// A remessa sobe pela tela, e SPED de empresa grande passa de um GB. O limite
    /// de 30 MB do Kestrel sai só nesta rota: desde a fundação ele cortava a
    /// remessa grande, e o repasse relatava como se o motor não tivesse respondido.
    /// </summary>
    private static async Task<IResult> AnalisarRemessa(HttpContext http, Lotes caso)
    {
        if (http.Features.Get<IHttpMaxRequestBodySizeFeature>() is { IsReadOnly: false } limite)
            limite.MaxRequestBodySize = null;
        if (!http.Request.HasFormContentType || http.Request.ContentType is not { } tipo)
            return CorpoJson.Recusar("Envie o arquivo da remessa.");

        return await Traduzir(async () => Results.Json(
            await caso.AnalisarRemessa(http.Request.Body, tipo, http.Request.ContentLength, http.RequestAborted)));
    }

    // ---------- tradução ----------
    private static ContagemDto Contagem(string tipo, int quantidade)
    {
        var t = TiposDeArquivo.Buscar(tipo);
        return new ContagemDto(tipo, t.Rotulo, t.Grupo, t.AlimentaACat, quantidade);
    }

    /// <summary>O que serve primeiro e, dentro disso, o mais numeroso primeiro.</summary>
    private static IReadOnlyList<ContagemDto> Contagens(IEnumerable<(string Tipo, int Quantidade)> porTipo) =>
        porTipo.Select(c => Contagem(c.Tipo, c.Quantidade))
            .OrderBy(c => !c.AlimentaACat).ThenByDescending(c => c.Quantidade).ToList();

    public static ResumoDto Resumo(LoteInspecionado r)
    {
        // a amostra mostra primeiro o que NÃO entrou: é o que o usuário precisa ver
        var amostra = r.Arquivos.OrderBy(a => a.AlimentaACat).ThenBy(a => a.Nome, StringComparer.Ordinal)
            .Take(AmostraNaTela)
            .Select(a =>
            {
                var t = TiposDeArquivo.Buscar(a.Tipo);
                return new ArquivoDto(a.Nome, a.Caminho, a.Tamanho, a.Tipo, t.Rotulo, t.Grupo, t.AlimentaACat, a.Cnpj,
                    a.Competencia, a.Uf, a.Detalhe, a.Motivo);
            }).ToList();
        return new ResumoDto(
            r.Pasta, r.Arquivos.Count, r.Arquivos.Count(a => a.AlimentaACat), r.Arquivos.Sum(a => a.Tamanho),
            r.DeOutraEmpresa, r.Serve,
            r.Competencias.Count > 0 ? r.Competencias[0] : null, r.Competencias.Count > 0 ? r.Competencias[^1] : null,
            r.Cnpjs.Take(20).ToList(),
            Contagens(r.Arquivos.GroupBy(a => a.Tipo).Select(g => (g.Key, g.Count()))),
            r.Avisos, amostra, r.Arquivos.Count(a => a.JaNoTrabalho), r.Copias);
    }

    public static LoteDto Lote(LoteLido l) => new(
        l.Id, l.ProjetoId, l.Pasta, l.TotalArquivos, l.ArquivosUteis, l.BytesTotais, l.CompetenciaIni, l.CompetenciaFim,
        l.Observacao, AuthRotas.IsoComoPython(l.CriadoEm), Contagens(l.Contagens));

    private static async Task<IResult> Traduzir(Func<Task<IResult>> operacao)
    {
        try
        {
            return await operacao();
        }
        catch (MotorRecusou erro)
        {
            return CorpoJson.Recusar(erro.Message, erro.Status);
        }
        catch (MotorIndisponivel)
        {
            return CorpoJson.Recusar("O motor do sistema não respondeu. Nada foi gravado.", StatusCodes.Status502BadGateway);
        }
        catch (Exception erro) when (Codigo(erro) is { } status)
        {
            return CorpoJson.Recusar(erro.Message, status);
        }
    }

    private static int? Codigo(Exception erro) => erro switch
    {
        SemAcessoAEmpresa => StatusCodes.Status403Forbidden,
        ProjetoNaoEncontrado or LoteNaoEncontrado => StatusCodes.Status404NotFound,
        SoCopias or TudoJaNoTrabalho => StatusCodes.Status409Conflict,
        NadaParaACat => StatusCodes.Status422UnprocessableEntity,
        _ => null,
    };
}

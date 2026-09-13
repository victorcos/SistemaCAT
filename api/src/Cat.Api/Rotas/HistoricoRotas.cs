using System.Text.Json;
using Cat.Api.Infra;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;

namespace Cat.Api.Rotas;

/// <summary>
/// O histórico de um trabalho, portado de <c>historico_router.py</c>: linha do
/// tempo, comentário, status e sucessão.
/// </summary>
public static class HistoricoRotas
{
    // ---------- contratos ----------
    public sealed record EventoDto(
        int Id, string Tipo, string RotuloDoTipo, string Texto, JsonElement Dados, string Autor, int? AutorId,
        string Quando, bool EComentario);

    public sealed record PaginaDeHistorico(IReadOnlyList<EventoDto> Eventos, bool TemMais, int? ProximoCursor);

    public sealed record StatusDto(string Valor, string Rotulo, string Explicacao, bool ExigeMotivo);

    public sealed record PessoaDto(int Id, string NomeExibicao, string Usuario, string Papel, string Cargo, bool PrecisaDeAcesso);

    private sealed record PedidoDeComentario(string? Texto);
    private sealed record PedidoDeStatus(string? Status, string? Motivo);
    private sealed record PedidoDeSucessao(int? ResponsavelId, string? Motivo);

    private static readonly JsonElement ObjetoVazio = JsonDocument.Parse("{}").RootElement.Clone();

    public static void MapearHistorico(this IEndpointRouteBuilder rotas)
    {
        var api = rotas.MapGroup("/api").WithTags("histórico");

        api.MapGet("/projetos/{projetoId:int}/historico", Ler).ExigirUsuario();
        api.MapPost("/projetos/{projetoId:int}/historico/comentarios", Comentar)
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "mexer no trabalho");

        // o catálogo, com rótulo e explicação — a tela não reescreve nenhum
        api.MapGet("/status-de-projeto", () => Results.Json(StatusDoProjeto.Todos
            .Select(s => new StatusDto(s.Valor, s.Rotulo, s.Explicacao, s.ExigeMotivo)).ToList()));
        api.MapPatch("/projetos/{projetoId:int}/status", MudarStatus)
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "mexer no trabalho");

        api.MapGet("/projetos/{projetoId:int}/sucessores", async (int projetoId, HttpContext http, HistoricoDoProjeto caso) =>
                await Traduzir(async () => Results.Json(
                    (await caso.Sucessores(projetoId, http.UsuarioAtual(), http.RequestAborted))
                    .Select(c => new PessoaDto(c.Id, c.NomeExibicao, c.Usuario, c.Papel, c.Cargo, !c.Alcanca)).ToList())))
            .ExigirUsuario();
        // qualquer usuário chega; a regra de que só gestor passa trabalho é do caso de uso
        api.MapPatch("/projetos/{projetoId:int}/responsavel", Suceder).ExigirUsuario();
    }

    // ---------- rotas ----------
    private static Task<IResult> Ler(int projetoId, HttpContext http, HistoricoDoProjeto caso) =>
        Traduzir(async () =>
        {
            var q = http.Request.Query;
            int? antesDe = int.TryParse(q["antes_de"], out var a) ? a : null;
            var quantos = int.TryParse(q["quantos"], out var n) ? n : HistoricoDoProjeto.PorPagina;
            var soComentarios = Booleano(q["so_comentarios"]);

            var (eventos, temMais) = await caso.Listar(projetoId, http.UsuarioAtual(), antesDe, quantos, soComentarios,
                http.RequestAborted);
            return Results.Json(new PaginaDeHistorico(
                eventos.Select(Dto).ToList(), temMais,
                eventos.Count > 0 && temMais ? eventos[^1].Id : null));
        });

    private static async Task<IResult> Comentar(int projetoId, HttpContext http, HistoricoDoProjeto caso)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoDeComentario>(http);
        if (recusa is not null)
            return recusa;
        if (pedido!.Texto is null or { Length: 0 })
            return CorpoJson.Recusar("O comentário não pode ficar vazio.");
        if (pedido.Texto.Length > Historico.TamanhoMaximoDoComentario)
            return CorpoJson.Recusar(new ComentarioLongoDemais().Message);

        return await Traduzir(async () => Results.Json(
            Dto(await caso.Comentar(projetoId, pedido.Texto, http.UsuarioAtual(), http.RequestAborted)),
            statusCode: StatusCodes.Status201Created));
    }

    private static async Task<IResult> MudarStatus(int projetoId, HttpContext http, HistoricoDoProjeto caso)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoDeStatus>(http);
        if (recusa is not null)
            return recusa;
        if (pedido!.Status is null)
            return CorpoJson.Recusar("Informe o status.");

        return await Traduzir(async () =>
        {
            var novo = await caso.MudarStatus(projetoId, pedido.Status, pedido.Motivo ?? "", http.UsuarioAtual(),
                http.RequestAborted);
            return Results.Json(new Dictionary<string, string> { ["status"] = novo.Valor, ["rotulo"] = novo.Rotulo });
        });
    }

    private static async Task<IResult> Suceder(int projetoId, HttpContext http, HistoricoDoProjeto caso)
    {
        var (pedido, recusa) = await CorpoJson.Ler<PedidoDeSucessao>(http);
        if (recusa is not null)
            return recusa;
        if (pedido!.ResponsavelId is not { } novoId)
            return CorpoJson.Recusar("Informe quem passa a responder pelo trabalho.");

        return await Traduzir(async () =>
        {
            var r = await caso.Suceder(projetoId, novoId, pedido.Motivo ?? "", http.UsuarioAtual(), http.RequestAborted);
            return Results.Json(new Dictionary<string, object?> { ["responsavel_id"] = r.ResponsavelId, ["responsavel"] = r.Responsavel });
        });
    }

    // ---------- tradução ----------
    private static EventoDto Dto(EventoLido e) => new(
        e.Id, e.Tipo, TipoDeEvento.Rotulo(e.Tipo), e.Texto,
        e.Dados is { ValueKind: JsonValueKind.Object } d ? d : ObjetoVazio,
        e.Autor, e.AutorId, AuthRotas.IsoComoPython(e.Quando), e.Tipo == TipoDeEvento.Comentario);

    /// <summary>Os mesmos textos que o FastAPI aceitava como verdadeiro num parâmetro de consulta.</summary>
    private static bool Booleano(string? valor) =>
        valor?.ToLowerInvariant() is "true" or "1" or "yes" or "on" or "t" or "y";

    private static async Task<IResult> Traduzir(Func<Task<IResult>> operacao)
    {
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
        SemAcessoAEmpresa or NaoPodeSuceder => StatusCodes.Status403Forbidden,
        ProjetoNaoEncontrado => StatusCodes.Status404NotFound,
        MesmoStatus or MotivoObrigatorio or SucessorInvalido or StatusDesconhecido or ComentarioVazio
            or ComentarioLongoDemais => StatusCodes.Status422UnprocessableEntity,
        _ => null,
    };
}

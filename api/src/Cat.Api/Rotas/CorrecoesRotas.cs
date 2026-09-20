using Cat.Api.Infra;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;

namespace Cat.Api.Rotas;

/// <summary>
/// Correções à mão do trabalho. Ler é de quem enxerga a empresa; corrigir e
/// desfazer é de quem escreve — analista, revisor e gestor.
///
/// A correção não some quando a etapa roda de novo: ela fica no banco e o motor
/// a aplica a cada montagem do razão. Desfazer devolve o cálculo ao sistema.
/// </summary>
public static class CorrecoesRotas
{
    private sealed record PedidoDeCorrecoes(IReadOnlyList<CorrecaoDto>? Correcoes);

    private sealed record CorrecaoDto(
        string? Campo, string? Valor, string? Motivo, string? Cnpj, string? Codigo, string? Documento,
        int? NumeroItem, string? ValorAnterior);

    public static void MapearCorrecoes(this IEndpointRouteBuilder rotas)
    {
        var api = rotas.MapGroup("/api").WithTags("correcoes");

        api.MapGet("/projetos/{projetoId:int}/correcoes", async (int projetoId, bool? todas, HttpContext http,
                    CorrecoesDoTrabalho caso) =>
                await Traduzir(async () => Results.Json(new Dictionary<string, object>
                {
                    ["correcoes"] = await caso.Listar(projetoId, somenteAtivas: todas != true,
                        http.UsuarioAtual(), http.RequestAborted),
                    ["campos"] = Correcao.Campos.Select(c => new Dictionary<string, object>
                    {
                        ["campo"] = c, ["rotulo"] = Correcao.Rotulo(c),
                        ["alvo"] = Correcao.EhDaMercadoria(c) ? "mercadoria" : "linha",
                    }),
                })))
            .ExigirUsuario();

        api.MapPost("/projetos/{projetoId:int}/correcoes", async (int projetoId, HttpContext http,
                    CorrecoesDoTrabalho caso) =>
                await Traduzir(async () =>
                {
                    var (corpo, recusa) = await CorpoJson.Ler<PedidoDeCorrecoes>(http);
                    if (recusa is not null)
                        return recusa;
                    var pedidas = (corpo!.Correcoes ?? []).Select(c => Correcao.Validar(
                        c.Campo, c.Valor, c.Motivo, c.Cnpj, c.Codigo, c.Documento, c.NumeroItem,
                        c.ValorAnterior)).ToList();
                    var gravadas = await caso.Gravar(projetoId, pedidas, http.UsuarioAtual(), http.RequestAborted);
                    return Results.Json(new Dictionary<string, int> { ["gravadas"] = gravadas });
                }))
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "corrigir à mão");

        api.MapDelete("/projetos/{projetoId:int}/correcoes/{correcaoId:int}", async (int projetoId, int correcaoId,
                    HttpContext http, CorrecoesDoTrabalho caso) =>
                await Traduzir(async () =>
                    Results.Json(await caso.Desfazer(projetoId, correcaoId, http.UsuarioAtual(),
                        http.RequestAborted))))
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "desfazer correção");
    }

    private static async Task<IResult> Traduzir(Func<Task<IResult>> operacao)
    {
        try
        {
            return await operacao();
        }
        catch (ProjetoNaoEncontrado)
        {
            return CorpoJson.Recusar("Trabalho não encontrado.", StatusCodes.Status404NotFound);
        }
        catch (SemAcessoAEmpresa erro)
        {
            return CorpoJson.Recusar(erro.Message, StatusCodes.Status403Forbidden);
        }
        catch (DadoInvalido erro)
        {
            return CorpoJson.Recusar(erro.Message, StatusCodes.Status422UnprocessableEntity);
        }
    }
}

using Cat.Api.Infra;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;
using Microsoft.AspNetCore.Http.Features;

namespace Cat.Api.Rotas;

/// <summary>
/// Correções à mão do trabalho. Ler é de quem enxerga a empresa; corrigir e
/// desfazer é de quem escreve — analista, revisor e gestor.
///
/// A correção não some quando a etapa roda de novo: ela fica no banco e o motor
/// a aplica a cada montagem do razão. Desfazer devolve o cálculo ao sistema.
///
/// São **duas portas e um só caminho de gravação**: a pessoa corrige na tela do
/// razão, linha a linha, ou sobe a Ficha 3 editada no Excel. A planilha entra
/// pela rota de conferência, que só compara e devolve o antes e o depois de cada
/// mudança; gravar é sempre o mesmo POST, depois de ela ver o que vai mudar. Sem
/// essa separação, uma coluna arrastada sem querer viraria dez mil correções.
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

        api.MapPost("/razao/{execucaoId:int}/correcoes/planilha", ConferirPlanilha).DisableAntiforgery()
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "corrigir à mão");
    }

    /// <summary>
    /// A Ficha 3 editada sobe e volta o que mudou — **sem gravar**. A planilha de
    /// uma base grande passa dos 30 MB do Kestrel, como a remessa: o limite sai
    /// nesta rota também, senão o arquivo é cortado e o erro aparece como se o
    /// motor não tivesse respondido.
    /// </summary>
    private static async Task<IResult> ConferirPlanilha(int execucaoId, HttpContext http, Execucoes caso)
    {
        if (http.Features.Get<IHttpMaxRequestBodySizeFeature>() is { IsReadOnly: false } limite)
            limite.MaxRequestBodySize = null;
        if (!http.Request.HasFormContentType || http.Request.ContentType is not { } tipo)
            return CorpoJson.Recusar("Envie a Ficha 3 preenchida, em xlsx ou csv.");

        return await Traduzir(async () => Results.Json(await caso.ConferirPlanilhaDeCorrecoes(
            execucaoId, http.Request.Body, tipo, http.Request.ContentLength, http.UsuarioAtual(),
            http.RequestAborted)));
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
        catch (ExecucaoNaoEncontrada erro)
        {
            return CorpoJson.Recusar(erro.Message, StatusCodes.Status404NotFound);
        }
        catch (SemAcessoAEmpresa erro)
        {
            return CorpoJson.Recusar(erro.Message, StatusCodes.Status403Forbidden);
        }
        // a recusa do motor vem com motivo escrito — razão que ainda não terminou,
        // material apagado do disco, planilha que não é a Ficha 3 — e é isso que a
        // pessoa precisa ler, não "erro interno"
        catch (MotorRecusou erro)
        {
            return CorpoJson.Recusar(erro.Message, erro.Status);
        }
        catch (MotorIndisponivel)
        {
            return CorpoJson.Recusar("O motor do sistema não respondeu.", StatusCodes.Status502BadGateway);
        }
        catch (DadoInvalido erro)
        {
            return CorpoJson.Recusar(erro.Message, StatusCodes.Status422UnprocessableEntity);
        }
    }
}

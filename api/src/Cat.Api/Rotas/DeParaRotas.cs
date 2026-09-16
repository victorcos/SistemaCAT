using Cat.Api.Infra;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;

namespace Cat.Api.Rotas;

/// <summary>
/// De-para de códigos do trabalho. Ler é de quem enxerga a empresa; decidir é
/// de quem escreve — analista, revisor e gestor.
/// </summary>
public static class DeParaRotas
{
    private sealed record PedidoDeDecisoes(IReadOnlyList<DecisaoDto>? Decisoes);

    private sealed record DecisaoDto(
        string? Cnpj, string? Origem, string? Destino, string? Fator, string? Motivo, string? Situacao,
        string? Confianca, string? Explicacao);

    public static void MapearDePara(this IEndpointRouteBuilder rotas)
    {
        var api = rotas.MapGroup("/api").WithTags("depara");

        api.MapGet("/projetos/{projetoId:int}/depara", async (int projetoId, HttpContext http, DeParaDoTrabalho caso) =>
                await Traduzir(async () =>
                    Results.Json(await caso.Listar(projetoId, http.UsuarioAtual(), http.RequestAborted))))
            .ExigirUsuario();

        api.MapPost("/projetos/{projetoId:int}/depara", async (int projetoId, HttpContext http, DeParaDoTrabalho caso) =>
                await Traduzir(async () =>
                {
                    var (corpo, recusa) = await CorpoJson.Ler<PedidoDeDecisoes>(http);
                    if (recusa is not null)
                        return recusa;
                    var decisoes = (corpo!.Decisoes ?? []).Select(d => DePara.Validar(
                        d.Cnpj, d.Origem, d.Destino, d.Fator, d.Motivo, d.Situacao, d.Confianca, d.Explicacao)).ToList();
                    var gravadas = await caso.Decidir(projetoId, decisoes, http.UsuarioAtual(), http.RequestAborted);
                    return Results.Json(new Dictionary<string, int> { ["gravadas"] = gravadas });
                }))
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "decidir o de-para");
    }

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
            return CorpoJson.Recusar("O motor do sistema não respondeu.", StatusCodes.Status502BadGateway);
        }
        catch (SemAcessoAEmpresa erro)
        {
            return CorpoJson.Recusar(erro.Message, StatusCodes.Status403Forbidden);
        }
        catch (ProjetoNaoEncontrado erro)
        {
            return CorpoJson.Recusar(erro.Message, StatusCodes.Status404NotFound);
        }
        catch (DadoInvalido erro)
        {
            return CorpoJson.Recusar(erro.Message);
        }
    }
}

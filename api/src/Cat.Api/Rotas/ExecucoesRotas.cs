using System.Text.Json;
using Cat.Api.Infra;
using Cat.Aplicacao.Log;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Infraestrutura.Configuracao;

namespace Cat.Api.Rotas;

/// <summary>Conferência, movimentos e ICMS suportado: pedir a rodada, acompanhar, cancelar e baixar as planilhas.</summary>
public static class ExecucoesRotas
{
    public sealed record ExecucaoDto(
        int Id, int ProjetoId, string Etapa, string Situacao, string? Passo, double Fracao, int ArquivosTotais,
        int ArquivosLidos, long BytesLidos, long Documentos, string? Erro, string IniciadaEm, string? TerminadaEm,
        JsonElement? Resumo);

    public static void MapearExecucoes(this IEndpointRouteBuilder rotas)
    {
        var api = rotas.MapGroup("/api").WithTags("execuções");
        Etapa(api, Execucoes.Conferencia, "conferencias", detalheExigeEtapa: false, "conferir documentos");
        Etapa(api, Execucoes.Movimentos, "movimentos", detalheExigeEtapa: true, "extrair movimentos");
        Etapa(api, Execucoes.Suportado, "suportado", detalheExigeEtapa: true, "apurar o ICMS suportado");
        Etapa(api, Execucoes.Razao, "razao", detalheExigeEtapa: true, "montar o razão");
        Etapa(api, Execucoes.Apuracao, "apuracao", detalheExigeEtapa: true, "apurar ressarcimento e complemento");

        api.MapGet("/apuracao/{execucaoId:int}/competencias", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var pedido = new PedidoDeCompetencias(
                        q["so"].FirstOrDefault() is { Length: > 0 } s ? s : null,
                        q["busca"].FirstOrDefault() is { Length: > 0 } b ? b : null,
                        Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 50));
                    return Results.Json(await caso.CompetenciasApuradas(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirUsuario();

        api.MapGet("/razao/{execucaoId:int}/fichas", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var pedido = new PedidoDeFichas(
                        q["busca"].FirstOrDefault() is { Length: > 0 } b ? b : null,
                        q["so"].FirstOrDefault() is { Length: > 0 } s ? s : null,
                        Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 50));
                    return Results.Json(await caso.FichasDoRazao(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirUsuario();

        api.MapGet("/razao/{execucaoId:int}/ficha", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var cnpj = q["cnpj"].FirstOrDefault() ?? "";
                    var codigo = q["codigo"].FirstOrDefault() ?? "";
                    if (cnpj.Length == 0 || codigo.Length == 0)
                        return CorpoJson.Recusar("Informe o estabelecimento e a mercadoria da ficha.", StatusCodes.Status422UnprocessableEntity);
                    var pedido = new PedidoDeFicha(cnpj, codigo, Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 50));
                    return Results.Json(await caso.LinhasDoRazao(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirUsuario();

        // o analítico pagina no servidor: numa base real são 8,7 milhões de itens
        api.MapGet("/suportado/{execucaoId:int}/linhas", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var pedido = new PedidoDeLinhas(
                        q["escopo"].FirstOrDefault() is { Length: > 0 } e ? e : "documento",
                        q["fonte"].FirstOrDefault() is { Length: > 0 } f ? f : null,
                        q["busca"].FirstOrDefault() is { Length: > 0 } b ? b : null,
                        int.TryParse(q["pagina"], out var pagina) && pagina > 0 ? pagina : 1,
                        int.TryParse(q["por_pagina"], out var porPagina) && porPagina > 0 ? porPagina : 50);
                    return Results.Json(await caso.LinhasDoSuportado(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirUsuario();
    }

    /// <param name="detalheExigeEtapa">
    /// Pelo identificador, a rota de conferência mostra qualquer execução; a de
    /// movimentos só as de movimentos. É o contrato que a tela já usa.
    /// </param>
    /// <param name="acao">Como a recusa por permissão fala: "Você não tem permissão para {acao}."</param>
    private static void Etapa(RouteGroupBuilder api, string etapa, string segmento, bool detalheExigeEtapa, string acao)
    {
        var exigida = detalheExigeEtapa ? etapa : null;

        api.MapPost($"/projetos/{{projetoId:int}}/{segmento}", async (int projetoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () => Results.Json(
                    Dto(await caso.Iniciar(etapa, projetoId, http.UsuarioAtual(), http.RequestAborted)),
                    statusCode: StatusCodes.Status202Accepted)))
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", acao);

        // quem pode iniciar pode parar; a etapa que não confere o pedido o motor recusa
        api.MapPost($"/{segmento}/{{execucaoId:int}}/cancelar", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () => Results.Json(
                    Dto(await caso.Cancelar(execucaoId, exigida, http.UsuarioAtual(), http.RequestAborted)))))
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", acao);

        api.MapGet($"/projetos/{{projetoId:int}}/{segmento}", async (int projetoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () => Results.Json(
                    (await caso.Listar(etapa, projetoId, http.UsuarioAtual(), http.RequestAborted)).Select(Dto).ToList())))
            .ExigirUsuario();

        api.MapGet($"/{segmento}/{{execucaoId:int}}", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () => Results.Json(
                    Dto(await caso.Detalhar(execucaoId, exigida, http.UsuarioAtual(), http.RequestAborted)))))
            .ExigirUsuario();

        api.MapGet($"/{segmento}/{{execucaoId:int}}/planilhas/{{qual}}",
                async (int execucaoId, string qual, HttpContext http, Execucoes caso, ConfigCat config, ILogger<Execucoes> log) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var formato = q["formato"].FirstOrDefault() is { Length: > 0 } f ? f : "xlsx";
                    var pronta = await caso.Planilha(execucaoId, etapa, exigida, qual, q["modelos"].FirstOrDefault(),
                        q["classificacoes"].FirstOrDefault(), formato, http.UsuarioAtual(), http.RequestAborted);
                    return Arquivo(pronta, config, log);
                }))
            .ExigirUsuario();
    }

    /// <summary>
    /// O arquivo sai direto do disco, em fluxo: um CSV de dezenas de milhões de
    /// linhas tem gigabytes. E só de dentro da pasta de trabalho — o caminho vem do
    /// motor, e a API não serve arquivo de outro lugar da máquina nem se ele pedir.
    /// </summary>
    private static IResult Arquivo(PlanilhaPronta pronta, ConfigCat config, ILogger log)
    {
        var raiz = Path.GetFullPath(config.PastaDeTrabalho).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var caminho = Path.GetFullPath(pronta.Caminho);
        if (!caminho.StartsWith(raiz, StringComparison.OrdinalIgnoreCase) || !File.Exists(caminho))
        {
            log.Erro("motor devolveu planilha fora da pasta de trabalho ou inexistente",
                new { caminho, raiz, existe = File.Exists(caminho) });
            return CorpoJson.Recusar("A planilha não pôde ser entregue. Veja o log do servidor.", StatusCodes.Status502BadGateway);
        }
        return Results.File(caminho, pronta.Tipo, pronta.Nome, enableRangeProcessing: true);
    }

    private static int Inteiro(Microsoft.Extensions.Primitives.StringValues valor, int padrao) =>
        int.TryParse(valor, out var n) && n > 0 ? n : padrao;

    private static ExecucaoDto Dto(ExecucaoLida e) => new(
        e.Id, e.ProjetoId, e.Etapa, e.Situacao, e.Passo, e.Fracao, e.ArquivosTotais, e.ArquivosLidos, e.BytesLidos,
        e.Documentos, e.Erro, AuthRotas.IsoComoPython(e.IniciadaEm),
        e.TerminadaEm is { } t ? AuthRotas.IsoComoPython(t) : null, e.Resumo);

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
        catch (Exception erro) when (erro is ProjetoNaoEncontrado or ExecucaoNaoEncontrada)
        {
            return CorpoJson.Recusar(erro.Message, StatusCodes.Status404NotFound);
        }
    }
}

using System.Text.Json;
using Cat.Api.Infra;
using Cat.Aplicacao.Log;
using Cat.Aplicacao.Trabalhos;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;
using Cat.Infraestrutura.Configuracao;

namespace Cat.Api.Rotas;

/// <summary>Conferência, movimentos e ICMS suportado: pedir a rodada, acompanhar, cancelar e baixar as planilhas.</summary>
public static class ExecucoesRotas
{
    public sealed record ExecucaoDto(
        int Id, int ProjetoId, string Etapa, string Situacao, string? Passo, double Fracao, int ArquivosTotais,
        int ArquivosLidos, long BytesLidos, long Documentos, string? Erro, string IniciadaEm, string? TerminadaEm,
        JsonElement? Resumo, string? AprovadaPor, string? AprovadaEm);

    private sealed record PedidoDeAprovacao(string? Observacao);

    private sealed record PedidoDeFiltro(IReadOnlyList<string>? Ncms, IReadOnlyList<string>? Termos,
        bool SemFiltro, bool GuardarDescartados);

    /// <summary>Teto do filtro. Não é regra fiscal: é o que impede um colar acidental
    /// de planilha inteira de virar uma varredura que nunca termina.</summary>
    private const int LimiteDoFiltro = 2000;

    public static void MapearExecucoes(this IEndpointRouteBuilder rotas)
    {
        var api = rotas.MapGroup("/api").WithTags("execuções");
        Etapa(api, Execucoes.Conferencia, "conferencias", detalheExigeEtapa: false, "conferir documentos");
        Etapa(api, Execucoes.Movimentos, "movimentos", detalheExigeEtapa: true, "extrair movimentos");
        Etapa(api, Execucoes.Suportado, "suportado", detalheExigeEtapa: true, "apurar o ICMS suportado");
        Etapa(api, Execucoes.Razao, "razao", detalheExigeEtapa: true, "montar o razão");
        Etapa(api, Execucoes.Apuracao, "apuracao", detalheExigeEtapa: true, "apurar ressarcimento e complemento");
        Etapa(api, Execucoes.ArquivoDigital, "arquivo-digital", detalheExigeEtapa: true, "gerar o arquivo digital");
        Etapa(api, Execucoes.Entrega, "entrega", detalheExigeEtapa: true, "montar a entrega");
        Etapa(api, Execucoes.QuebraDeSped, "quebra-de-sped", detalheExigeEtapa: true,
            "quebrar os SPED");
        Etapa(api, Execucoes.ApuracaoContribuicoes, "apuracao-contribuicoes", detalheExigeEtapa: true,
            "apurar as contribuições");
        Etapa(api, Execucoes.ApuracaoPisCofins, "apuracao-piscofins", detalheExigeEtapa: true,
            "apurar PIS/COFINS");
        Etapa(api, Execucoes.CreditoOutorgado, "credito-outorgado", detalheExigeEtapa: true,
            "apurar o crédito outorgado");
        Etapa(api, Execucoes.Exclusoes, "exclusoes", detalheExigeEtapa: true,
            "apurar as exclusões da base");
        Etapa(api, Execucoes.QuebraXml, "quebra-xml", detalheExigeEtapa: true,
            "quebrar os XML");

        // o catálogo de colunas do XML não depende de execução: é o que a
        // planilha sabe produzir, e a tela precisa dele antes de existir rodada
        api.MapGet("/quebra-xml/campos", async (HttpContext http, Execucoes caso) =>
                await Traduzir(async () => Results.Json(
                    await caso.CamposDoXml(http.UsuarioAtual(), http.RequestAborted))))
            .ExigirUsuario();

        api.MapGet("/entrega/{execucaoId:int}/estabelecimentos", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var pedido = new PedidoDeEstabelecimentos(
                        q["so"].FirstOrDefault() is { Length: > 0 } s ? s : null,
                        q["busca"].FirstOrDefault() is { Length: > 0 } b ? b : null,
                        Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 50));
                    return Results.Json(await caso.EstabelecimentosDaEntrega(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirUsuario();

        // aprovar é o que conclui a etapa 8: revisor ou gestor, nunca quem só monta
        api.MapPost("/entrega/{execucaoId:int}/aprovar", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    string? observacao = null;
                    if (http.Request.ContentLength is > 0)
                    {
                        var (corpo, recusa) = await CorpoJson.Ler<PedidoDeAprovacao>(http);
                        if (recusa is not null)
                            return recusa;
                        observacao = corpo!.Observacao;
                    }
                    return Results.Json(Dto(await caso.AprovarEntrega(execucaoId, observacao, http.UsuarioAtual(), http.RequestAborted)));
                }))
            .ExigirCapacidade(Capacidades.PodeAprovarEntrega, "pode_aprovar_entrega", "aprovar a entrega");

        api.MapGet("/arquivo-digital/{execucaoId:int}/arquivos", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var pedido = new PedidoDeArquivos(
                        q["so"].FirstOrDefault() is { Length: > 0 } s ? s : null,
                        q["busca"].FirstOrDefault() is { Length: > 0 } b ? b : null,
                        Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 50));
                    return Results.Json(await caso.ArquivosGerados(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirUsuario();

        Etapa(api, Execucoes.PreValidacao, "pre-validacao", detalheExigeEtapa: true, "pré-validar os arquivos do cliente");

        api.MapGet("/pre-validacao/{execucaoId:int}/arquivos", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var pedido = new PedidoDeArquivos(
                        q["so"].FirstOrDefault() is { Length: > 0 } s ? s : null,
                        q["busca"].FirstOrDefault() is { Length: > 0 } b ? b : null,
                        Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 50));
                    return Results.Json(await caso.ArquivosDoCliente(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirUsuario();

        foreach (var (segmento, etapa) in new[] { ("arquivo-digital", Execucoes.ArquivoDigital), ("pre-validacao", Execucoes.PreValidacao) })
            api.MapGet($"/{segmento}/{{execucaoId:int}}/ocorrencias", async (int execucaoId, HttpContext http, Execucoes caso) =>
                    await Traduzir(async () =>
                    {
                        var q = http.Request.Query;
                        var nome = q["arquivo"].FirstOrDefault() ?? "";
                        if (nome.Length == 0)
                            return CorpoJson.Recusar("Informe o arquivo.", StatusCodes.Status422UnprocessableEntity);
                        var pedido = new PedidoDeOcorrencias(nome, Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 50));
                        return Results.Json(await caso.OcorrenciasDoArquivo(execucaoId, etapa, pedido, http.UsuarioAtual(), http.RequestAborted));
                    }))
                .ExigirUsuario();

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

        // O razão contábil da ECD: escolher a conta, depois ver os lançamentos.
        // Sai da apuração de PIS/COFINS, e não da quebra — as duas se separaram
        // em 23/09/2026, e o parquet do razão foi junto.
        // Pagina no servidor como todo o resto — uma ECD de rede de supermercado
        // passa de milhão de partidas, e nenhuma delas cabe numa resposta só.
        api.MapGet("/apuracao-piscofins/{execucaoId:int}/contas", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var pedido = new PedidoDeContasContabeis(
                        q["busca"].FirstOrDefault() is { Length: > 0 } b ? b : null,
                        q["cnpj"].FirstOrDefault() is { Length: > 0 } c ? c : null,
                        q["so"].FirstOrDefault() is { Length: > 0 } s ? s : null,
                        Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 100),
                        q["pai"].FirstOrDefault() is { Length: > 0 } p ? p : null,
                        q["arvore"].FirstOrDefault() == "true");
                    return Results.Json(await caso.ContasDoRazaoContabil(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirUsuario();

        api.MapGet("/apuracao-piscofins/{execucaoId:int}/lancamentos", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var cnpj = q["cnpj"].FirstOrDefault() ?? "";
                    var conta = q["conta"].FirstOrDefault() ?? "";
                    if (cnpj.Length == 0 || conta.Length == 0)
                        return CorpoJson.Recusar("Informe o estabelecimento e a conta do razão.", StatusCodes.Status422UnprocessableEntity);
                    var pedido = new PedidoDeLancamentos(cnpj, conta,
                        q["busca"].FirstOrDefault() is { Length: > 0 } b ? b : null,
                        q["de"].FirstOrDefault() is { Length: > 0 } d ? d : null,
                        q["ate"].FirstOrDefault() is { Length: > 0 } a ? a : null,
                        Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 100));
                    return Results.Json(await caso.LancamentosDoRazaoContabil(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirUsuario();

        api.MapGet("/apuracao-piscofins/{execucaoId:int}/estabelecimentos", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                    Results.Json(await caso.EstabelecimentosDoRazaoContabil(execucaoId, http.UsuarioAtual(), http.RequestAborted))))
            .ExigirUsuario();

        // A Consulta de Saídas (047): recortar na tela e olhar, como o razão
        // contábil acima. Pagina no servidor pelo mesmo motivo — sete milhões
        // de linhas em cinco anos não cabem numa resposta nem num Excel.
        api.MapGet("/apuracao-piscofins/{execucaoId:int}/saidas/filtros", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                    Results.Json(await caso.FiltrosDasSaidas(execucaoId, RecorteDeSaidas(http.Request.Query),
                        http.UsuarioAtual(), http.RequestAborted))))
            .ExigirUsuario();

        api.MapGet("/apuracao-piscofins/{execucaoId:int}/saidas", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var pedido = new PedidoDasSaidas(RecorteDeSaidas(q),
                        Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 100));
                    return Results.Json(await caso.LinhasDasSaidas(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirUsuario();

        api.MapGet("/apuracao-piscofins/{execucaoId:int}/saidas/planilha",
                async (int execucaoId, HttpContext http, Execucoes caso, ConfigCat config, ILogger<Execucoes> log) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var formato = q["formato"].FirstOrDefault() is { Length: > 0 } f ? f : "xlsx";
                    var pronta = await caso.PlanilhaDasSaidas(execucaoId,
                        new PedidoDaPlanilhaDasSaidas(RecorteDeSaidas(q), formato),
                        http.UsuarioAtual(), http.RequestAborted);
                    return Arquivo(pronta, config, log);
                }))
            .ExigirUsuario();

        // A extração de registro da quebra: o que há para extrair, e a planilha
        // de um alvo. Fica fora do `/planilhas/{qual}` das outras etapas porque
        // o que sai depende do registro pedido, e não de uma lista fixa.
        api.MapGet("/quebra-de-sped/{execucaoId:int}/alvos", async (int execucaoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                    Results.Json(await caso.AlvosDaQuebra(execucaoId, http.UsuarioAtual(), http.RequestAborted))))
            .ExigirUsuario();

        api.MapGet("/quebra-de-sped/{execucaoId:int}/extracao",
                async (int execucaoId, HttpContext http, Execucoes caso, ConfigCat config, ILogger<Execucoes> log) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var alvo = q["alvo"].FirstOrDefault() ?? "";
                    // `alvos` marca o lote: vários registros num zip só
                    var alvos = q["alvos"].FirstOrDefault() is { Length: > 0 } muitos
                        ? muitos.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                        : [];
                    if (alvo.Length > 40 || (alvo.Length == 0 && alvos.Length == 0))
                        return CorpoJson.Recusar("Informe o registro ou a hierarquia a extrair.",
                            StatusCodes.Status422UnprocessableEntity);
                    var formato = q["formato"].FirstOrDefault() is { Length: > 0 } f ? f : "xlsx";
                    var pronta = await caso.ExtrairDaQuebra(execucaoId,
                        new PedidoDeExtracao(alvo, formato, Recorte(q), alvos),
                        http.UsuarioAtual(), http.RequestAborted);
                    return Arquivo(pronta, config, log);
                }))
            .ExigirUsuario();

        // O crédito outorgado: o filtro do trabalho, e a leitura do que ele
        // capturou. O filtro é a única configuração de etapa que a tela grava —
        // ele existe antes da primeira rodada e sobrevive a todas, e por isso
        // pende do trabalho, e não da execução.
        api.MapGet("/projetos/{projetoId:int}/credito-outorgado/filtro", async (int projetoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                    Results.Json(await caso.FiltroDoCreditoOutorgado(projetoId, http.UsuarioAtual(), http.RequestAborted))))
            .ExigirUsuario();

        api.MapPut("/projetos/{projetoId:int}/credito-outorgado/filtro", async (int projetoId, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var (corpo, recusa) = await CorpoJson.Ler<PedidoDeFiltro>(http);
                    if (recusa is not null)
                        return recusa;
                    var pedido = new PedidoDeFiltroOutorgado(
                        corpo!.Ncms ?? [], corpo.Termos ?? [], corpo.SemFiltro, corpo.GuardarDescartados);
                    if (pedido.Ncms.Count > LimiteDoFiltro || pedido.Termos.Count > LimiteDoFiltro)
                        return CorpoJson.Recusar($"O filtro aceita até {LimiteDoFiltro} NCM e {LimiteDoFiltro} termos.",
                            StatusCodes.Status422UnprocessableEntity);
                    return Results.Json(await caso.GravarFiltroDoCreditoOutorgado(projetoId, pedido, http.UsuarioAtual(), http.RequestAborted));
                }))
            .ExigirCapacidade(Capacidades.PodeEscrever, "pode_escrever", "mudar o filtro do crédito outorgado");

        foreach (var (rota, porProduto) in new[] { ("produtos", true), ("itens", false) })
            api.MapGet($"/credito-outorgado/{{execucaoId:int}}/{rota}", async (int execucaoId, HttpContext http, Execucoes caso) =>
                    await Traduzir(async () =>
                    {
                        var q = http.Request.Query;
                        var pedido = new PedidoDaListaOutorgada(
                            q["descartados"].FirstOrDefault() == "true",
                            q["busca"].FirstOrDefault() is { Length: > 0 } b ? b : null,
                            q["codigo"].FirstOrDefault() is { Length: > 0 } c ? c : null,
                            Inteiro(q["pagina"], 1), Inteiro(q["por_pagina"], 100));
                        return Results.Json(porProduto
                            ? await caso.ProdutosDoCreditoOutorgado(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted)
                            : await caso.ItensDoCreditoOutorgado(execucaoId, pedido, http.UsuarioAtual(), http.RequestAborted));
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

        // O tíquete: autoriza o download sem gerar nada, para o navegador poder
        // baixar por navegação — sem o arquivo passar pela memória da aba. Ver
        // `ITiquetesDeDownload`. É POST porque cria uma autorização
        api.MapPost($"/{segmento}/{{execucaoId:int}}/planilhas/{{qual}}/tiquete",
                async (int execucaoId, string qual, HttpContext http, Execucoes caso) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var formato = q["formato"].FirstOrDefault() is { Length: > 0 } f ? f : "xlsx";
                    var emitido = await caso.TiqueteDePlanilha(execucaoId, etapa, exigida, qual,
                        q["modelos"].FirstOrDefault(), q["classificacoes"].FirstOrDefault(),
                        formato, http.UsuarioAtual(), http.RequestAborted);
                    return Results.Json(new Dictionary<string, object>
                    {
                        ["tiquete"] = emitido.Tiquete,
                        ["vale_por_segundos"] = emitido.ValePorSegundos,
                    });
                }))
            .ExigirUsuario();

        api.MapGet($"/{segmento}/{{execucaoId:int}}/planilhas/{{qual}}",
                async (int execucaoId, string qual, HttpContext http, Execucoes caso, ConfigCat config, ILogger<Execucoes> log) =>
                await Traduzir(async () =>
                {
                    var q = http.Request.Query;
                    var formato = q["formato"].FirstOrDefault() is { Length: > 0 } f ? f : "xlsx";
                    var modelos = q["modelos"].FirstOrDefault();
                    var classificacoes = q["classificacoes"].FirstOrDefault();

                    // **o tíquete manda, não a URL.** Quem entrou por tíquete
                    // baixa exatamente o que foi autorizado: sem isto, um
                    // tíquete de um CSV pequeno serviria para pedir o xlsx
                    // inteiro trocando o parâmetro na barra de endereço
                    if (http.TiqueteAtual() is { } autorizado)
                    {
                        qual = autorizado.Qual;
                        formato = autorizado.Formato;
                        modelos = autorizado.Modelos;
                        classificacoes = autorizado.Classificacoes;
                    }

                    var pronta = await caso.Planilha(execucaoId, etapa, exigida, qual, modelos,
                        classificacoes, formato, http.UsuarioAtual(), http.RequestAborted);
                    return Arquivo(pronta, config, log);
                }))
            .ExigirUsuarioOuTiquete();
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

    /// <summary>
    /// O recorte da extração, lido da consulta. Lista vem separada por vírgula.
    ///
    /// Campo ausente é ausência de filtro, e não filtro vazio: `cfop=` sem
    /// valor não pode significar "nenhum CFOP passa".
    /// </summary>
    /// <summary>O recorte da tela da 047, lido da query. Listas vêm separadas por vírgula.</summary>
    private static RecorteDasSaidas RecorteDeSaidas(IQueryCollection q)
    {
        IReadOnlyList<string> Lista(string nome) =>
            q[nome].FirstOrDefault() is { Length: > 0 } bruto
                ? bruto.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                : [];
        return new RecorteDasSaidas(
            Lista("cnpjs"), Lista("competencias"), Lista("ramos"), Lista("cfops"),
            Lista("cst_pis"), q["busca"].FirstOrDefault() is { Length: > 0 } b ? b : "");
    }

    private static RecorteDaExtracao Recorte(IQueryCollection q)
    {
        IReadOnlyList<string> Lista(string nome) =>
            q[nome].FirstOrDefault() is { Length: > 0 } bruto
                ? bruto.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                : [];
        string Texto(string nome) => q[nome].FirstOrDefault() is { Length: > 0 } v ? v : "";

        return new RecorteDaExtracao(
            Lista("cnpjs"), Texto("de"), Texto("ate"),
            Lista("cst_pis"), Lista("cst_cofins"), Lista("cfop"), Lista("cod_item"),
            Lista("cod_nat"), Lista("num_doc"), Lista("ind_aj"), Lista("cod_aj"),
            Texto("ind_oper"), Lista("descricao"),
            Texto("doc_de"), Texto("doc_ate"),
            Texto("vl_pis_min"), Texto("vl_pis_max"),
            Texto("vl_item_min"), Texto("vl_item_max"));
    }

    private static int Inteiro(Microsoft.Extensions.Primitives.StringValues valor, int padrao) =>
        int.TryParse(valor, out var n) && n > 0 ? n : padrao;

    private static ExecucaoDto Dto(ExecucaoLida e) => new(
        e.Id, e.ProjetoId, e.Etapa, e.Situacao, e.Passo, e.Fracao, e.ArquivosTotais, e.ArquivosLidos, e.BytesLidos,
        e.Documentos, e.Erro, AuthRotas.IsoComoPython(e.IniciadaEm),
        e.TerminadaEm is { } t ? AuthRotas.IsoComoPython(t) : null, e.Resumo,
        e.AprovadaPor, e.AprovadaEm is { } a ? AuthRotas.IsoComoPython(a) : null);

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
        catch (Exception erro) when (erro is EntregaNaoMontada or EntregaJaAprovada or EntregaSuperada
                                         or EntregaDesatualizada or TrabalhoParadoNaoEntrega)
        {
            return CorpoJson.Recusar(erro.Message, StatusCodes.Status409Conflict);
        }
        catch (ObservacaoDaEntregaLongaDemais erro)
        {
            return CorpoJson.Recusar(erro.Message, StatusCodes.Status422UnprocessableEntity);
        }
    }
}

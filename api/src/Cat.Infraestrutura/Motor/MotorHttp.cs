using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;
using Cat.Aplicacao.Log;
using Cat.Aplicacao.Trabalhos;
using Cat.Infraestrutura.Configuracao;
using Microsoft.Extensions.Logging;

namespace Cat.Infraestrutura.Motor;

/// <summary>
/// O canal interno com o motor Python: <c>127.0.0.1</c>, rotas <c>/interno</c>
/// fora do repasse público, e um segredo compartilhado em cabeçalho.
///
/// Cada chamada tem o seu prazo. Apagar pasta leva segundos; inspecionar uma
/// base de milhares de arquivos na rede leva minutos; uma remessa de um GB tem
/// de subir inteira antes de o motor começar a ler.
/// </summary>
public sealed class MotorHttp(HttpClient cliente, ConfigCat config, ILogger<MotorHttp> log) : IMotor
{
    public const string CabecalhoSegredo = "X-Cat-Motor-Segredo";

    public static readonly TimeSpan PrazoApagar = TimeSpan.FromMinutes(5);
    public static readonly TimeSpan PrazoInspecionar = TimeSpan.FromMinutes(30);
    public static readonly TimeSpan PrazoRemessa = TimeSpan.FromMinutes(60);
    public static readonly TimeSpan PrazoPedirExecucao = TimeSpan.FromMinutes(2);
    // a planilha de dezenas de milhões de linhas é escrita antes de o primeiro byte sair
    public static readonly TimeSpan PrazoPlanilha = TimeSpan.FromMinutes(60);
    // agrupar milhões de itens por documento a cada página leva segundos, não minutos
    public static readonly TimeSpan PrazoLinhas = TimeSpan.FromMinutes(2);
    // as propostas agrupam a movimentação inteira: numa base do tamanho do Amigão, dezenas de segundos
    public static readonly TimeSpan PrazoDePara = TimeSpan.FromMinutes(5);

    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };

    public async Task<PastasApagadas> ApagarPastas(IReadOnlyList<string> pastas, CancellationToken cancelar)
    {
        var json = await Chamar("interno/pastas/apagar", JsonContent.Create(new { pastas }), PrazoApagar, cancelar);
        return new PastasApagadas(
            json.GetProperty("apagadas").EnumerateArray().Select(x => x.GetString()!).ToList(),
            json.GetProperty("recusadas").EnumerateArray().Select(x => x.GetString()!).ToList());
    }

    public async Task<LoteInspecionado> InspecionarLote(int projetoId, string pasta, CancellationToken cancelar)
    {
        var json = await Chamar("interno/lotes/inspecionar",
            JsonContent.Create(new Dictionary<string, object> { ["projeto_id"] = projetoId, ["pasta"] = pasta }),
            PrazoInspecionar, cancelar);
        return json.Deserialize<LoteInspecionado>(Json)
               ?? throw new MotorIndisponivel("resposta vazia à inspeção do lote");
    }

    public async Task<JsonObject> AnalisarRemessa(Stream corpo, string tipoDoConteudo, long? tamanho,
        CancellationToken cancelar)
    {
        // o corpo multipart segue como chegou, com a mesma fronteira: remontar o
        // formulário obrigaria a ter o arquivo inteiro em memória aqui também
        var conteudo = new StreamContent(corpo);
        conteudo.Headers.ContentType = MediaTypeHeaderValue.Parse(tipoDoConteudo);
        if (tamanho is { } bytes)
            conteudo.Headers.ContentLength = bytes;
        var json = await Chamar("interno/remessas/analisar", conteudo, PrazoRemessa, cancelar);
        return JsonNode.Parse(json.GetRawText())!.AsObject();
    }

    public async Task<int> PedirExecucao(string etapa, int projetoId, int usuarioId, CancellationToken cancelar)
    {
        var json = await Chamar("interno/execucoes", JsonContent.Create(new Dictionary<string, object>
        {
            ["etapa"] = etapa, ["projeto_id"] = projetoId, ["usuario_id"] = usuarioId,
        }), PrazoPedirExecucao, cancelar);
        return json.GetProperty("id").GetInt32();
    }

    public async Task<PlanilhaPronta> GerarPlanilha(int execucaoId, string etapa, string qual, string? modelos,
        string? classificacoes, string formato, CancellationToken cancelar)
    {
        var json = await Chamar("interno/planilhas", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["etapa"] = etapa, ["qual"] = qual,
            ["modelos"] = modelos, ["classificacoes"] = classificacoes, ["formato"] = formato,
        }), PrazoPlanilha, cancelar);
        return new PlanilhaPronta(json.GetProperty("caminho").GetString()!, json.GetProperty("nome").GetString()!,
            json.GetProperty("tipo").GetString()!);
    }

    public async Task CancelarExecucao(int execucaoId, int usuarioId, CancellationToken cancelar) =>
        await Chamar($"interno/execucoes/{execucaoId}/cancelar",
            JsonContent.Create(new Dictionary<string, object> { ["usuario_id"] = usuarioId }), PrazoPedirExecucao, cancelar);

    public async Task<JsonElement> LinhasDoSuportado(int execucaoId, PedidoDeLinhas pedido, CancellationToken cancelar) =>
        await Chamar("interno/suportado/linhas", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["escopo"] = pedido.Escopo, ["fonte"] = pedido.Fonte,
            ["busca"] = pedido.Busca, ["pagina"] = pedido.Pagina, ["por_pagina"] = pedido.PorPagina,
        }), PrazoLinhas, cancelar);

    public async Task<JsonElement> FichasDoRazao(int execucaoId, PedidoDeFichas pedido, CancellationToken cancelar) =>
        await Chamar("interno/razao/fichas", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["busca"] = pedido.Busca, ["so"] = pedido.So,
            ["pagina"] = pedido.Pagina, ["por_pagina"] = pedido.PorPagina,
        }), PrazoLinhas, cancelar);

    public async Task<JsonElement> LinhasDoRazao(int execucaoId, PedidoDeFicha pedido, CancellationToken cancelar) =>
        await Chamar("interno/razao/ficha", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["cnpj"] = pedido.Cnpj, ["codigo"] = pedido.Codigo,
            ["pagina"] = pedido.Pagina, ["por_pagina"] = pedido.PorPagina,
        }), PrazoLinhas, cancelar);

    public async Task<JsonElement> ContasDoRazaoContabil(int execucaoId, PedidoDeContasContabeis pedido, CancellationToken cancelar) =>
        await Chamar("interno/razao-contabil/contas", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["busca"] = pedido.Busca, ["cnpj"] = pedido.Cnpj,
            ["so"] = pedido.So, ["pagina"] = pedido.Pagina, ["por_pagina"] = pedido.PorPagina,
        }), PrazoLinhas, cancelar);

    public async Task<JsonElement> LancamentosDoRazaoContabil(int execucaoId, PedidoDeLancamentos pedido, CancellationToken cancelar) =>
        await Chamar("interno/razao-contabil/lancamentos", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["cnpj"] = pedido.Cnpj, ["conta"] = pedido.Conta,
            ["busca"] = pedido.Busca, ["de"] = pedido.De, ["ate"] = pedido.Ate,
            ["pagina"] = pedido.Pagina, ["por_pagina"] = pedido.PorPagina,
        }), PrazoLinhas, cancelar);

    public async Task<JsonElement> EstabelecimentosDoRazaoContabil(int execucaoId, CancellationToken cancelar) =>
        await Chamar("interno/razao-contabil/estabelecimentos", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId,
        }), PrazoLinhas, cancelar);

    /// <summary>
    /// A Ficha 3 corrigida à mão sobe inteira antes de o motor começar a ler: ela
    /// tem o tamanho da ficha do trabalho, e por isso vai no prazo da remessa.
    ///
    /// O razão vai na query, e não no formulário: o corpo multipart atravessa daqui
    /// como chegou do navegador, e um identificador embutido nele seria escolhido
    /// por quem sobe o arquivo. Na query quem o escreve somos nós, depois de o caso
    /// de uso conferir que a pessoa enxerga aquele trabalho.
    /// </summary>
    public async Task<JsonElement> ConferirPlanilhaDeCorrecoes(int execucaoId, Stream corpo, string tipoDoConteudo,
        long? tamanho, CancellationToken cancelar)
    {
        var conteudo = new StreamContent(corpo);
        conteudo.Headers.ContentType = MediaTypeHeaderValue.Parse(tipoDoConteudo);
        if (tamanho is { } bytes)
            conteudo.Headers.ContentLength = bytes;
        return await Chamar($"interno/correcoes/planilha?execucao_id={execucaoId}", conteudo, PrazoRemessa, cancelar);
    }

    public async Task<JsonElement> CompetenciasApuradas(int execucaoId, PedidoDeCompetencias pedido, CancellationToken cancelar) =>
        await Chamar("interno/apuracao/competencias", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["so"] = pedido.So, ["busca"] = pedido.Busca,
            ["pagina"] = pedido.Pagina, ["por_pagina"] = pedido.PorPagina,
        }), PrazoLinhas, cancelar);

    public async Task<JsonElement> ArquivosGerados(int execucaoId, PedidoDeArquivos pedido, CancellationToken cancelar) =>
        await Chamar("interno/arquivo_digital/arquivos", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["so"] = pedido.So, ["busca"] = pedido.Busca,
            ["pagina"] = pedido.Pagina, ["por_pagina"] = pedido.PorPagina,
        }), PrazoLinhas, cancelar);

    public async Task<JsonElement> OcorrenciasDoArquivo(int execucaoId, PedidoDeOcorrencias pedido, CancellationToken cancelar) =>
        await Chamar("interno/arquivo_digital/ocorrencias", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["nome"] = pedido.Nome,
            ["pagina"] = pedido.Pagina, ["por_pagina"] = pedido.PorPagina,
        }), PrazoLinhas, cancelar);

    public async Task<JsonElement> ArquivosDoCliente(int execucaoId, PedidoDeArquivos pedido, CancellationToken cancelar) =>
        await Chamar("interno/pre_validacao/arquivos", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["so"] = pedido.So, ["busca"] = pedido.Busca,
            ["pagina"] = pedido.Pagina, ["por_pagina"] = pedido.PorPagina,
        }), PrazoLinhas, cancelar);

    public async Task<JsonElement> CandidatosDeDePara(int projetoId, CancellationToken cancelar) =>
        await Chamar("interno/depara/candidatos", JsonContent.Create(new Dictionary<string, object?>
        {
            ["projeto_id"] = projetoId,
        }), PrazoDePara, cancelar);

    public async Task<JsonElement> EstabelecimentosDaEntrega(int execucaoId, PedidoDeEstabelecimentos pedido, CancellationToken cancelar) =>
        await Chamar("interno/entrega/estabelecimentos", JsonContent.Create(new Dictionary<string, object?>
        {
            ["execucao_id"] = execucaoId, ["so"] = pedido.So, ["busca"] = pedido.Busca,
            ["pagina"] = pedido.Pagina, ["por_pagina"] = pedido.PorPagina,
        }), PrazoLinhas, cancelar);

    private async Task<JsonElement> Chamar(string rota, HttpContent conteudo, TimeSpan prazo, CancellationToken cancelar)
    {
        if (string.IsNullOrEmpty(config.MotorSegredo))
            throw new MotorIndisponivel("CAT_MOTOR_SEGREDO não está definido no backend/.env");

        using var limite = CancellationTokenSource.CreateLinkedTokenSource(cancelar);
        limite.CancelAfter(prazo);
        using var pedido = new HttpRequestMessage(HttpMethod.Post, new Uri(config.MotorUrl, rota)) { Content = conteudo };
        pedido.Headers.Add(CabecalhoSegredo, config.MotorSegredo);

        HttpResponseMessage resposta;
        try
        {
            resposta = await cliente.SendAsync(pedido, HttpCompletionOption.ResponseHeadersRead, limite.Token);
        }
        catch (Exception erro) when (erro is HttpRequestException or TaskCanceledException && !cancelar.IsCancellationRequested)
        {
            log.Erro("motor não respondeu ao canal interno", new { rota, destino = config.MotorUrl.ToString() }, erro);
            throw new MotorIndisponivel(erro is TaskCanceledException ? $"passou de {prazo.TotalMinutes} min" : erro.GetType().Name, erro);
        }

        using (resposta)
        {
            var texto = await resposta.Content.ReadAsStringAsync(limite.Token);
            if (resposta.IsSuccessStatusCode)
                return JsonDocument.Parse(texto).RootElement.Clone();

            // recusa com motivo (pasta que não existe, remessa sem SPED, rodada já em
            // andamento, planilha apagada do disco) segue para a tela com o texto do
            // motor; o resto é falha do canal
            var codigo = (int)resposta.StatusCode;
            if (codigo is 404 or 409 or 410 or 422 && Detalhe(texto) is { } detalhe)
                throw new MotorRecusou(codigo, detalhe);
            log.Erro("motor recusou chamada do canal interno", new { rota, status = codigo, corpo = texto });
            throw new MotorIndisponivel($"HTTP {codigo}");
        }
    }

    private static string? Detalhe(string texto)
    {
        try
        {
            return JsonDocument.Parse(texto).RootElement.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.String
                ? d.GetString()
                : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }
}

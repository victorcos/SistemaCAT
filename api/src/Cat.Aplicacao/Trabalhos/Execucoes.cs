using System.Text.Json;
using Cat.Aplicacao.Log;
using Cat.Dominio.Acesso;
using Cat.Dominio.Projeto;
using Microsoft.Extensions.Logging;

namespace Cat.Aplicacao.Trabalhos;

public sealed record ExecucaoLida(
    int Id, int ProjetoId, string Etapa, string Situacao, string? Passo, double Fracao, int ArquivosTotais,
    int ArquivosLidos, long BytesLidos, long Documentos, string? Erro, DateTimeOffset IniciadaEm,
    DateTimeOffset? TerminadaEm, JsonElement? Resumo, string? AprovadaPor = null, DateTimeOffset? AprovadaEm = null);

public sealed record PlanilhaPronta(string Caminho, string Nome, string Tipo);

/// <param name="Escopo">"documento" (uma linha por nota, com os itens) ou "item".</param>
public sealed record PedidoDeLinhas(string Escopo, string? Fonte, string? Busca, int Pagina, int PorPagina);

/// <param name="So">recorte das fichas que pedem atenção: negativas, sem_aliquota, indefinidas</param>
public sealed record PedidoDeFichas(string? Busca, string? So, int Pagina, int PorPagina);

public sealed record PedidoDeFicha(string Cnpj, string Codigo, int Pagina, int PorPagina);

/// <summary>O seletor de conta do razão contábil da ECD.</summary>
/// <param name="So">recorte pelo saldo: devedoras, credoras, zeradas, com_movimento</param>
/// <param name="Pai">o galho aberto da árvore do plano referencial</param>
/// <param name="Arvore">true: galhos e as contas do galho; false: a lista chapada</param>
public sealed record PedidoDeContasContabeis(string? Busca, string? Cnpj, string? So, int Pagina, int PorPagina,
    string? Pai = null, bool Arvore = false);

/// <summary>Os lançamentos de uma conta. <paramref name="De"/> e <paramref name="Ate"/> em aaaa-mm-dd.</summary>
public sealed record PedidoDeLancamentos(string Cnpj, string Conta, string? Busca, string? De, string? Ate,
    int Pagina, int PorPagina);

/// <param name="So">aptas, bloqueadas, ou o código de um motivo de bloqueio</param>
public sealed record PedidoDeCompetencias(string? So, string? Busca, int Pagina, int PorPagina);

/// <param name="So">envio, previa, ou o código de uma trava</param>
public sealed record PedidoDeArquivos(string? So, string? Busca, int Pagina, int PorPagina);

public sealed record PedidoDeOcorrencias(string Nome, int Pagina, int PorPagina);

/// <param name="So">no_dossie, fora_do_dossie, com_previa, fora_de_sp</param>
public sealed record PedidoDeEstabelecimentos(string? So, string? Busca, int Pagina, int PorPagina);

public interface IRepositorioDeExecucoes
{
    Task<ExecucaoLida?> Buscar(int id, CancellationToken cancelar);

    /// <summary>As mais recentes primeiro.</summary>
    Task<IReadOnlyList<ExecucaoLida>> Listar(int projetoId, string etapa, int limite, CancellationToken cancelar);

    /// <summary>A última rodada da etapa que concluiu, ou nulo.</summary>
    Task<int?> UltimaConcluida(int projetoId, string etapa, CancellationToken cancelar);

    /// <summary>
    /// Grava quem aprovou e quando, e o evento na linha do tempo, juntos. Falso se
    /// outra pessoa aprovou no meio do caminho: só grava sobre entrega sem aprovação.
    /// </summary>
    Task<bool> AprovarEntrega(int execucaoId, int projetoId, Usuario por, string texto, object dados,
        DateTimeOffset agora, CancellationToken cancelar);
}

public sealed class ExecucaoNaoEncontrada() : RecusaDeRegra("Execução não encontrada.");

/// <summary>
/// Conferência e movimentos, portados de <c>conferencia_router.py</c> e
/// <c>movimentos_router.py</c>. A rodada não cabe numa requisição: aqui se pede
/// a execução, o motor a põe na fila e a roda, e a tela acompanha lendo a tabela.
///
/// Preparar (se há o que conferir, se a conferência já concluiu, se o trabalho
/// está parado) é do motor, porque são as mesmas regras da leitura.
/// </summary>
public sealed class Execucoes(
    IRepositorioDeTrabalhos trabalhos,
    IRepositorioDeExecucoes execucoes,
    IMotor motor,
    TimeProvider relogio,
    ILogger<Execucoes> log)
{
    public const string Conferencia = "conferencia";
    public const string Movimentos = "movimentos";
    public const string Suportado = "st_suportado";
    public const string Razao = "razao";
    public const string Apuracao = "apuracao";
    public const string ArquivoDigital = "arquivo_digital";
    public const string Entrega = "entrega";
    /// <summary>Primeira etapa do módulo de PIS/COFINS depois da importação.</summary>
    public const string QuebraDeSped = "quebra_de_sped";
    public const string ApuracaoContribuicoes = "apuracao_contribuicoes";
    public const string ApuracaoPisCofins = "apuracao_piscofins";

    /// <summary>
    /// A entrega montada e ainda não aprovada. Não é situação gravada: é como o
    /// roteiro lê a rodada concluída da entrega sem aprovação.
    /// </summary>
    public const string AguardandoAprovacao = "aguardando_aprovacao";

    /// <summary>
    /// Fora do roteiro de propósito: pré-validar o que o cliente já transmitiu não
    /// depende de nenhuma etapa, e trabalho de auditoria pode nem ter EFD.
    /// </summary>
    public const string PreValidacao = "pre_validacao";

    /// <summary>
    /// As etapas que concluem com uma rodada do motor. Uma lista só: o roteiro
    /// do trabalho e a consulta que o alimenta liam cada uma a sua, e a etapa
    /// nova que entrasse numa e não na outra ficaria para sempre "pendente".
    /// </summary>
    public static IReadOnlyList<string> DeProcessamento => Etapas.DeProcessamento;

    /// <summary>Ainda não terminou: inclui o pedido de parar que a rodada não atendeu ainda.</summary>
    public static bool EmCurso(string situacao) => situacao is "na_fila" or "rodando" or "cancelando";

    // quantas rodadas a tela lista: a última é a que importa, as outras são contexto
    public const int NaLista = 20;

    private async Task Projeto(int projetoId, Usuario usuario, CancellationToken cancelar)
    {
        var p = await trabalhos.BuscarProjeto(projetoId, cancelar) ?? throw new ProjetoNaoEncontrado("Trabalho não encontrado.");
        Escopo.Exigir(usuario, p.EmpresaId, log);
    }

    public async Task<ExecucaoLida> Iniciar(string etapa, int projetoId, Usuario por, CancellationToken cancelar)
    {
        await Projeto(projetoId, por, cancelar);
        var id = await motor.PedirExecucao(etapa, projetoId, por.Id, cancelar);
        log.Info("execução pedida ao motor", new { execucao_id = id, etapa, projeto_id = projetoId, por_usuario_id = por.Id });
        return await execucoes.Buscar(id, cancelar) ?? throw new ExecucaoNaoEncontrada();
    }

    public async Task<IReadOnlyList<ExecucaoLida>> Listar(string etapa, int projetoId, Usuario usuario, CancellationToken cancelar)
    {
        await Projeto(projetoId, usuario, cancelar);
        return await execucoes.Listar(projetoId, etapa, NaLista, cancelar);
    }

    /// <param name="etapaExigida">
    /// A rota de movimentos só mostra execução de movimentos; a de conferência,
    /// como no Python, mostra qualquer uma pelo identificador.
    /// </param>
    public async Task<ExecucaoLida> Detalhar(int execucaoId, string? etapaExigida, Usuario usuario, CancellationToken cancelar)
    {
        var e = await execucoes.Buscar(execucaoId, cancelar) ?? throw new ExecucaoNaoEncontrada();
        await Projeto(e.ProjetoId, usuario, cancelar);
        if (etapaExigida is not null && e.Etapa != etapaExigida)
            throw new ExecucaoNaoEncontrada();
        return e;
    }

    /// <summary>
    /// Na fila, cancela na hora; rodando, o motor pede para parar no próximo
    /// ponto seguro. Quem pode cancelar é quem pode iniciar.
    /// </summary>
    public async Task<ExecucaoLida> Cancelar(int execucaoId, string? etapaExigida, Usuario por, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, etapaExigida, por, cancelar);
        await motor.CancelarExecucao(e.Id, por.Id, cancelar);
        log.Info("cancelamento pedido ao motor", new { execucao_id = e.Id, etapa = e.Etapa, por_usuario_id = por.Id });
        return await execucoes.Buscar(e.Id, cancelar) ?? throw new ExecucaoNaoEncontrada();
    }

    /// <summary>Uma página do analítico da apuração, montada pelo motor a partir do parquet.</summary>
    public async Task<JsonElement> LinhasDoSuportado(int execucaoId, PedidoDeLinhas pedido, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, Suportado, usuario, cancelar);
        return await motor.LinhasDoSuportado(e.Id, pedido, cancelar);
    }

    /// <summary>A lista de fichas do razão, maior ressarcimento primeiro.</summary>
    public async Task<JsonElement> FichasDoRazao(int execucaoId, PedidoDeFichas pedido, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, Razao, usuario, cancelar);
        return await motor.FichasDoRazao(e.Id, pedido, cancelar);
    }

    /// <summary>Uma página das linhas da Ficha 3 de uma mercadoria num estabelecimento.</summary>
    public async Task<JsonElement> LinhasDoRazao(int execucaoId, PedidoDeFicha pedido, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, Razao, usuario, cancelar);
        return await motor.LinhasDoRazao(e.Id, pedido, cancelar);
    }

    // O razão contábil é outro razão: sai da ECD, pela quebra de SPED, no módulo
    // de PIS/COFINS. O acima é a Ficha 3 da CAT 42, no de ICMS. Mesma forma de
    // tela, etapas diferentes — e é por isso que a etapa exigida muda aqui.

    /// <summary>O seletor de conta do razão contábil: uma linha por conta, com saldo.</summary>
    public async Task<JsonElement> ContasDoRazaoContabil(int execucaoId, PedidoDeContasContabeis pedido, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, ApuracaoPisCofins, usuario, cancelar);
        return await motor.ContasDoRazaoContabil(e.Id, pedido, cancelar);
    }

    /// <summary>Uma página dos lançamentos de uma conta, em ordem de data.</summary>
    public async Task<JsonElement> LancamentosDoRazaoContabil(int execucaoId, PedidoDeLancamentos pedido, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, ApuracaoPisCofins, usuario, cancelar);
        return await motor.LancamentosDoRazaoContabil(e.Id, pedido, cancelar);
    }

    /// <summary>Os estabelecimentos do razão contábil, para o filtro da tela.</summary>
    public async Task<JsonElement> EstabelecimentosDoRazaoContabil(int execucaoId, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, ApuracaoPisCofins, usuario, cancelar);
        return await motor.EstabelecimentosDoRazaoContabil(e.Id, cancelar);
    }

    /// <summary>
    /// A Ficha 3 editada à mão volta e o motor diz o que ela muda. Nada é gravado
    /// aqui: o que volta é a proposta, e gravar é o POST das correções, depois de
    /// a pessoa ver o antes e o depois de cada linha.
    /// </summary>
    public async Task<JsonElement> ConferirPlanilhaDeCorrecoes(int execucaoId, Stream corpo, string tipoDoConteudo,
        long? tamanho, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, Razao, usuario, cancelar);
        var resposta = await motor.ConferirPlanilhaDeCorrecoes(e.Id, corpo, tipoDoConteudo, tamanho, cancelar);
        log.Info("planilha de correções conferida", new
        {
            execucao_id = e.Id, projeto_id = e.ProjetoId, por_usuario_id = usuario.Id,
            correcoes = resposta.TryGetProperty("total", out var t) ? t.GetInt32() : 0,
        });
        return resposta;
    }

    /// <summary>As competências fechadas, maior ressarcimento primeiro.</summary>
    public async Task<JsonElement> CompetenciasApuradas(int execucaoId, PedidoDeCompetencias pedido, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, Apuracao, usuario, cancelar);
        return await motor.CompetenciasApuradas(e.Id, pedido, cancelar);
    }

    /// <summary>Os arquivos gerados: os de envio primeiro, depois as prévias.</summary>
    public async Task<JsonElement> ArquivosGerados(int execucaoId, PedidoDeArquivos pedido, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, ArquivoDigital, usuario, cancelar);
        return await motor.ArquivosGerados(e.Id, pedido, cancelar);
    }

    /// <summary>As ocorrências da pré-validação de um arquivo — gerado pelo sistema ou do cliente.</summary>
    public async Task<JsonElement> OcorrenciasDoArquivo(int execucaoId, string etapa, PedidoDeOcorrencias pedido, Usuario usuario,
        CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, etapa, usuario, cancelar);
        return await motor.OcorrenciasDoArquivo(e.Id, pedido, cancelar);
    }

    /// <summary>Os arquivos que o cliente transmitiu, com o que a pré-validação achou em cada um.</summary>
    public async Task<JsonElement> ArquivosDoCliente(int execucaoId, PedidoDeArquivos pedido, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, PreValidacao, usuario, cancelar);
        return await motor.ArquivosDoCliente(e.Id, pedido, cancelar);
    }

    /// <summary>Os estabelecimentos da entrega: os do dossiê primeiro.</summary>
    public async Task<JsonElement> EstabelecimentosDaEntrega(int execucaoId, PedidoDeEstabelecimentos pedido, Usuario usuario,
        CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, Entrega, usuario, cancelar);
        return await motor.EstabelecimentosDaEntrega(e.Id, pedido, cancelar);
    }

    /// <summary>
    /// Aprovar a entrega, que é o que conclui a etapa 8. Quem pode é capacidade do
    /// papel, conferida na rota; o que a entrega precisa estar é regra do domínio.
    /// </summary>
    public async Task<ExecucaoLida> AprovarEntrega(int execucaoId, string? observacao, Usuario por, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, Entrega, por, cancelar);
        var projeto = await trabalhos.BuscarProjeto(e.ProjetoId, cancelar) ?? throw new ProjetoNaoEncontrado("Trabalho não encontrado.");
        var ultima = (await execucoes.Listar(e.ProjetoId, Entrega, 1, cancelar)).FirstOrDefault()?.Id ?? e.Id;
        var arquivoUsado = Inteiro(e.Resumo, "arquivo_digital_execucao_id");
        var ultimoArquivo = await execucoes.UltimaConcluida(e.ProjetoId, ArquivoDigital, cancelar);
        Dominio.Projeto.Entrega.ValidarAprovacao(new EntregaParaAprovar(
            e.Id, e.Situacao, e.AprovadaEm, e.AprovadaPor, ultima, arquivoUsado, ultimoArquivo,
            StatusDoProjeto.DoBanco(projeto.Status)));
        var nota = Dominio.Projeto.Entrega.ValidarObservacao(observacao);

        var paraEnvio = Inteiro(e.Resumo, "para_envio") ?? 0;
        var ressarcimento = Texto(e.Resumo, "ressarcimento_para_envio") ?? "0.00";
        var texto = $"Entrega aprovada · {paraEnvio} competências para envio" + (nota is null ? "" : $" · {nota}");
        var dados = new Dictionary<string, object?>
        {
            ["execucao_id"] = e.Id, ["etapa"] = Entrega, ["para_envio"] = paraEnvio,
            ["ressarcimento_para_envio"] = ressarcimento, ["observacao"] = nota,
        };
        if (!await execucoes.AprovarEntrega(e.Id, e.ProjetoId, por, texto, dados, relogio.GetUtcNow(), cancelar))
        {
            var agora = await execucoes.Buscar(e.Id, cancelar) ?? throw new ExecucaoNaoEncontrada();
            throw new EntregaJaAprovada(agora.AprovadaPor, agora.AprovadaEm ?? relogio.GetUtcNow());
        }
        // conclui a última etapa do trabalho: aviso, para se achar no log sem filtro
        log.Aviso("entrega aprovada",
            new { execucao_id = e.Id, projeto_id = e.ProjetoId, por_usuario_id = por.Id, para_envio = paraEnvio,
                  ressarcimento_para_envio = ressarcimento });
        return await execucoes.Buscar(e.Id, cancelar) ?? throw new ExecucaoNaoEncontrada();
    }

    private static int? Inteiro(JsonElement? resumo, string campo) =>
        resumo is { ValueKind: JsonValueKind.Object } r && r.TryGetProperty(campo, out var v) && v.ValueKind == JsonValueKind.Number
            ? v.GetInt32() : null;

    private static string? Texto(JsonElement? resumo, string campo) =>
        resumo is { ValueKind: JsonValueKind.Object } r && r.TryGetProperty(campo, out var v) && v.ValueKind == JsonValueKind.String
            ? v.GetString() : null;

    public async Task<PlanilhaPronta> Planilha(int execucaoId, string etapaDaRota, string? etapaExigida, string qual,
        string? modelos, string? classificacoes, string formato, Usuario usuario, CancellationToken cancelar)
    {
        var e = await Detalhar(execucaoId, etapaExigida, usuario, cancelar);
        return await motor.GerarPlanilha(e.Id, etapaDaRota, qual, modelos, classificacoes, formato, cancelar);
    }
}

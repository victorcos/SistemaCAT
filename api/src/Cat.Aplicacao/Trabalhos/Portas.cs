using Cat.Dominio.Acesso;

namespace Cat.Aplicacao.Trabalhos;

public sealed record EmpresaLida(
    int Id, string CnpjRaiz, string? CnpjMatriz, string RazaoSocial, string? Uf,
    string? InscricaoEstadual, bool PreCadastro, bool TemProjeto);

public sealed record NovaEmpresa(
    string CnpjRaiz, string CnpjMatriz, string RazaoSocial, string Uf, string? InscricaoEstadual, string? GrupoEconomico);

/// <summary>
/// O projeto com tudo que o cartão mostra, já agregado. O Python fazia quatro
/// consultas por projeto da listagem; aqui são poucas para a lista inteira.
/// </summary>
public sealed record ProjetoLido(
    int Id, int EmpresaId, string Empresa, string? CnpjMatriz, string? Uf, bool PreCadastro,
    string Frente, string Modulo, string Nome, DateOnly CompetenciaIni, DateOnly CompetenciaFim,
    string Status,
    string? CriadoPor, int? CriadoPorId, string? Responsavel, int? ResponsavelId, int Comentarios,
    bool TemBase, IReadOnlyDictionary<string, string> UltimaSituacaoPorEtapa, string VendaAConsumidor);

public sealed record NovoProjeto(
    int EmpresaId, string Frente, string Modulo, string Nome, DateOnly CompetenciaIni, DateOnly CompetenciaFim, string? Observacao);

/// <summary>O que some se a exclusão for confirmada, e as pastas de trabalho que vão junto.</summary>
public sealed record OQueSeraApagado(string Projeto, string Empresa, int Lotes, int Arquivos, int Execucoes);

public interface IRepositorioDeTrabalhos
{
    /// <summary>Todas, por razão social. O filtro de escopo é do caso de uso.</summary>
    Task<IReadOnlyList<EmpresaLida>> ListarEmpresas(CancellationToken cancelar);
    Task<bool> EmpresaExiste(int id, CancellationToken cancelar);
    Task<bool> RaizCadastrada(string raiz, CancellationToken cancelar);

    /// <summary>Empresa, estabelecimento matriz e a alocação de quem cadastrou, numa transação.</summary>
    Task<EmpresaLida> CriarEmpresa(NovaEmpresa nova, Usuario por, DateTimeOffset agora, CancellationToken cancelar);

    /// <summary>Mais recentes primeiro.</summary>
    Task<IReadOnlyList<ProjetoLido>> ListarProjetos(CancellationToken cancelar);
    Task<ProjetoLido?> BuscarProjeto(int id, CancellationToken cancelar);
    Task<bool> ProjetoRepetido(int empresaId, string frente, string nome, CancellationToken cancelar);
    Task<int> CriarProjeto(NovoProjeto novo, Usuario por, DateTimeOffset agora, CancellationToken cancelar);

    /// <summary>
    /// Grava uma linha no histórico. Quem chama decide o que fazer se falhar:
    /// o fato aconteceu, e perder a anotação dele é ruim, não fatal.
    /// </summary>
    Task RegistrarEvento(int projetoId, string tipo, string texto, object? dados, Usuario por, DateTimeOffset agora,
        CancellationToken cancelar);

    /// <summary>O nome e o período novos e o evento que os registra, numa transação.</summary>
    Task AlterarCadastro(int projetoId, string nome, DateOnly ini, DateOnly fim, string texto, object dados, Usuario por,
        DateTimeOffset agora, CancellationToken cancelar);

    /// <summary>As competências das EFD importadas no trabalho, com quantas EFD em cada.</summary>
    Task<IReadOnlyList<(DateOnly Competencia, int Efds)>> CompetenciasDaBase(int projetoId, CancellationToken cancelar);

    /// <summary>A escolha nova e o evento que a registra, numa transação.</summary>
    Task DefinirVendaAConsumidor(int projetoId, string valor, object dados, Usuario por, DateTimeOffset agora,
        CancellationToken cancelar);

    Task<OQueSeraApagado?> ResumirExclusao(int projetoId, CancellationToken cancelar);
    Task<IReadOnlyList<string>> PastasDeTrabalho(int projetoId, CancellationToken cancelar);

    /// <summary>Arquivos, execuções, lotes e o projeto, numa transação. O histórico cai em cascata no banco.</summary>
    Task ApagarTrabalho(int projetoId, CancellationToken cancelar);
}

public sealed record PastasApagadas(IReadOnlyList<string> Apagadas, IReadOnlyList<string> Recusadas);

public sealed class MotorIndisponivel(string motivo, Exception? causa = null)
    : Exception($"O motor do sistema não respondeu: {motivo}", causa);

/// <summary>
/// O canal interno com o motor Python. O disco é dele: o C# decide se a pessoa
/// pode, e o motor faz — e só dentro da pasta de trabalho que ele conhece.
/// </summary>
public interface IMotor
{
    Task<PastasApagadas> ApagarPastas(IReadOnlyList<string> pastas, CancellationToken cancelar);

    /// <summary>O que a pasta tem para este trabalho. O motor busca a raiz do CNPJ e o que já foi importado.</summary>
    /// <exception cref="MotorRecusou">pasta inexistente ou fora das permitidas (422), trabalho inexistente (404)</exception>
    Task<LoteInspecionado> InspecionarLote(int projetoId, string pasta, CancellationToken cancelar);

    /// <summary>A remessa enviada pela tela, repassada em fluxo: SPED de empresa grande passa de um GB.</summary>
    Task<System.Text.Json.Nodes.JsonObject> AnalisarRemessa(Stream corpo, string tipoDoConteudo, long? tamanho,
        CancellationToken cancelar);

    /// <summary>O motor confere se há o que fazer, cria a execução na fila e devolve o identificador.</summary>
    /// <exception cref="MotorRecusou">já em andamento (409), trabalho parado ou nada a fazer (422)</exception>
    Task<int> PedirExecucao(string etapa, int projetoId, int usuarioId, CancellationToken cancelar);

    /// <summary>Gera (ou reaproveita) a planilha a partir dos parquets e diz onde está.</summary>
    /// <exception cref="MotorRecusou">planilha ou formato desconhecido (404), não terminou (409), material apagado (410)</exception>
    Task<PlanilhaPronta> GerarPlanilha(int execucaoId, string etapa, string qual, string? modelos, string? classificacoes,
        string formato, CancellationToken cancelar);

    /// <summary>Pede para a rodada parar. Na fila, cancela na hora.</summary>
    /// <exception cref="MotorRecusou">não existe (404), já terminou (409), etapa sem cancelamento (422)</exception>
    Task CancelarExecucao(int execucaoId, int usuarioId, CancellationToken cancelar);

    /// <summary>Uma página do analítico da apuração do ICMS suportado.</summary>
    /// <exception cref="MotorRecusou">não é apuração (404), não terminou (409), material apagado (410), filtro inválido (422)</exception>
    Task<System.Text.Json.JsonElement> LinhasDoSuportado(int execucaoId, PedidoDeLinhas pedido, CancellationToken cancelar);

    /// <summary>A lista de fichas do razão.</summary>
    /// <exception cref="MotorRecusou">não é razão (404), não terminou (409), material apagado (410), recorte inválido (422)</exception>
    Task<System.Text.Json.JsonElement> FichasDoRazao(int execucaoId, PedidoDeFichas pedido, CancellationToken cancelar);

    /// <summary>As linhas de uma ficha do razão.</summary>
    Task<System.Text.Json.JsonElement> LinhasDoRazao(int execucaoId, PedidoDeFicha pedido, CancellationToken cancelar);

    /// <summary>O seletor de conta do razão contábil da ECD, que sai da quebra de SPED.</summary>
    /// <exception cref="MotorRecusou">não é quebra (404), não terminou (409), material apagado (410), recorte inválido (422)</exception>
    Task<System.Text.Json.JsonElement> ContasDoRazaoContabil(int execucaoId, PedidoDeContasContabeis pedido, CancellationToken cancelar);

    /// <summary>Os lançamentos de uma conta do razão contábil, em ordem de data.</summary>
    Task<System.Text.Json.JsonElement> LancamentosDoRazaoContabil(int execucaoId, PedidoDeLancamentos pedido, CancellationToken cancelar);

    /// <summary>Os estabelecimentos que aparecem no razão contábil, para o filtro da tela.</summary>
    /// <summary>O catálogo de colunas da planilha dos XML; não depende de execução.</summary>
    Task<System.Text.Json.JsonElement> CamposDoXml(CancellationToken cancelar);

    Task<System.Text.Json.JsonElement> EstabelecimentosDoRazaoContabil(int execucaoId, CancellationToken cancelar);

    /// <summary>O que há para escolher na 047, com o tamanho de cada escolha.</summary>
    /// <exception cref="MotorRecusou">não é apuração (404), não terminou (409), material apagado (410)</exception>
    Task<System.Text.Json.JsonElement> FiltrosDasSaidas(int execucaoId, RecorteDasSaidas recorte, CancellationToken cancelar);

    /// <summary>Uma página das linhas da 047, com os totais do recorte inteiro.</summary>
    Task<System.Text.Json.JsonElement> LinhasDasSaidas(int execucaoId, PedidoDasSaidas pedido, CancellationToken cancelar);

    /// <summary>A planilha da 047 recortada como a tela está mostrando.</summary>
    Task<PlanilhaPronta> PlanilhaDasSaidas(int execucaoId, PedidoDaPlanilhaDasSaidas pedido, CancellationToken cancelar);

    /// <summary>O que dá para extrair de uma quebra: registros, hierarquias e blocos.</summary>
    /// <exception cref="MotorRecusou">não é quebra (404), não terminou (409), material apagado (410)</exception>
    Task<System.Text.Json.JsonElement> AlvosDaQuebra(int execucaoId, CancellationToken cancelar);

    /// <summary>Extrai um registro ou hierarquia e devolve a planilha pronta.</summary>
    /// <exception cref="MotorRecusou">alvo sem leiaute (422), formato desconhecido (404), material apagado (410)</exception>
    Task<PlanilhaPronta> ExtrairDaQuebra(int execucaoId, PedidoDeExtracao pedido, CancellationToken cancelar);

    /// <summary>O filtro do crédito outorgado do trabalho. Trabalho sem filtro responde vazio.</summary>
    /// <exception cref="MotorRecusou">trabalho não existe (404)</exception>
    Task<System.Text.Json.JsonElement> FiltroDoCreditoOutorgado(int projetoId, CancellationToken cancelar);

    /// <summary>Grava o filtro e devolve como ficou — já normalizado pelo domínio.</summary>
    /// <exception cref="MotorRecusou">trabalho não existe (404)</exception>
    Task<System.Text.Json.JsonElement> GravarFiltroDoCreditoOutorgado(int projetoId, PedidoDeFiltroOutorgado pedido,
        int usuarioId, CancellationToken cancelar);

    /// <summary>Os produtos que o filtro capturou, agrupados.</summary>
    /// <exception cref="MotorRecusou">não é a etapa (404), não terminou (409), lista não guardada ou apagada (410)</exception>
    Task<System.Text.Json.JsonElement> ProdutosDoCreditoOutorgado(int execucaoId, PedidoDaListaOutorgada pedido,
        CancellationToken cancelar);

    /// <summary>As linhas de item da triagem, com as notas de origem.</summary>
    Task<System.Text.Json.JsonElement> ItensDoCreditoOutorgado(int execucaoId, PedidoDaListaOutorgada pedido,
        CancellationToken cancelar);

    /// <summary>
    /// A Ficha 3 editada à mão, repassada em fluxo, e o que ela muda em relação
    /// ao razão. O motor compara e devolve a proposta; **nada é gravado lá**.
    /// </summary>
    /// <exception cref="MotorRecusou">não é razão (404), não terminou (409), material apagado (410), arquivo ilegível (422)</exception>
    Task<System.Text.Json.JsonElement> ConferirPlanilhaDeCorrecoes(int execucaoId, Stream corpo, string tipoDoConteudo,
        long? tamanho, CancellationToken cancelar);

    /// <summary>As competências fechadas na apuração do período.</summary>
    /// <exception cref="MotorRecusou">não é apuração (404), não terminou (409), material apagado (410), recorte inválido (422)</exception>
    Task<System.Text.Json.JsonElement> CompetenciasApuradas(int execucaoId, PedidoDeCompetencias pedido, CancellationToken cancelar);

    /// <summary>Os arquivos digitais de uma geração.</summary>
    /// <exception cref="MotorRecusou">não é geração (404), não terminou (409), material apagado (410), recorte inválido (422)</exception>
    Task<System.Text.Json.JsonElement> ArquivosGerados(int execucaoId, PedidoDeArquivos pedido, CancellationToken cancelar);

    /// <summary>As ocorrências da pré-validação de um arquivo digital, gerado ou do cliente.</summary>
    Task<System.Text.Json.JsonElement> OcorrenciasDoArquivo(int execucaoId, PedidoDeOcorrencias pedido, CancellationToken cancelar);

    /// <summary>Os arquivos do cliente de uma pré-validação.</summary>
    /// <exception cref="MotorRecusou">não é pré-validação (404), não terminou (409), material apagado (410), recorte inválido (422)</exception>
    Task<System.Text.Json.JsonElement> ArquivosDoCliente(int execucaoId, PedidoDeArquivos pedido, CancellationToken cancelar);

    /// <summary>O de-para do trabalho: as propostas da última movimentação e as decisões da empresa.</summary>
    /// <exception cref="MotorRecusou">trabalho inexistente (404), sem movimentação (422), material apagado (410)</exception>
    Task<System.Text.Json.JsonElement> CandidatosDeDePara(int projetoId, CancellationToken cancelar);

    /// <summary>Os estabelecimentos de uma entrega montada.</summary>
    /// <exception cref="MotorRecusou">não é entrega (404), não terminou (409), material apagado (410), recorte inválido (422)</exception>
    Task<System.Text.Json.JsonElement> EstabelecimentosDaEntrega(int execucaoId, PedidoDeEstabelecimentos pedido, CancellationToken cancelar);
}

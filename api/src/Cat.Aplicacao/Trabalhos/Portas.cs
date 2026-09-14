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
    string Frente, string Nome, DateOnly CompetenciaIni, DateOnly CompetenciaFim, string Status,
    string? CriadoPor, int? CriadoPorId, string? Responsavel, int? ResponsavelId, int Comentarios,
    bool TemBase, IReadOnlyDictionary<string, string> UltimaSituacaoPorEtapa);

public sealed record NovoProjeto(
    int EmpresaId, string Frente, string Nome, DateOnly CompetenciaIni, DateOnly CompetenciaFim, string? Observacao);

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
}

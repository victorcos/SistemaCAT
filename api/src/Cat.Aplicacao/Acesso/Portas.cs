using Cat.Dominio.Acesso;

namespace Cat.Aplicacao.Acesso;

/// <summary>O que o caso de uso precisa do banco. A implementação vive na infraestrutura.</summary>
public interface IRepositorioDeUsuario
{
    Task<Usuario?> BuscarPorNome(string nomeDeUsuario, CancellationToken cancelar);
    Task<Usuario?> BuscarPorEmail(string email, CancellationToken cancelar);
    Task<Usuario?> BuscarPorId(int id, CancellationToken cancelar);

    /// <summary>Ativos primeiro, depois por nome de usuário — a ordem da tela de gestão.</summary>
    Task<IReadOnlyList<Usuario>> Listar(CancellationToken cancelar);

    /// <summary>
    /// Só papel de gestor, e só ativos. Dev fica de fora de propósito: conta
    /// técnica não substitui responsável pelo negócio.
    /// </summary>
    Task<int> ContarGestoresAtivos(CancellationToken cancelar);

    Task<bool> ExisteAlgum(CancellationToken cancelar);
    Task<string> ObterResumoDaSenha(int id, CancellationToken cancelar);

    Task<Usuario> Criar(NovoUsuario novo, CancellationToken cancelar);
    Task SalvarTentativa(Usuario usuario, CancellationToken cancelar);
    Task RegravarResumoDaSenha(int id, string novoResumo, CancellationToken cancelar);
    Task DefinirSenha(int id, string novoResumo, bool provisoria, CancellationToken cancelar);
    Task DefinirPapel(int id, Papel papel, CancellationToken cancelar);
    Task DefinirCargo(int id, Cargo cargo, CancellationToken cancelar);
    Task DefinirDados(int id, string nomeExibicao, string email, CancellationToken cancelar);
    Task DefinirSituacao(int id, bool ativo, CancellationToken cancelar);
    Task Desbloquear(int id, CancellationToken cancelar);
}

public sealed record NovoUsuario(
    string NomeDeUsuario, string Email, string NomeExibicao, string ResumoDaSenha,
    Papel Papel, Cargo Cargo, bool SenhaProvisoria);

public sealed record EmpresaParaAcesso(int Id, string RazaoSocial, string? Uf);

/// <summary>As alocações de pessoa a empresa. Nunca se apaga linha: encerra-se.</summary>
public interface IRepositorioDeAcesso
{
    /// <summary>Todas as empresas, em ordem de razão social.</summary>
    Task<IReadOnlyList<EmpresaParaAcesso>> ListarEmpresas(CancellationToken cancelar);

    /// <summary>Empresa alcançada hoje → desde quando.</summary>
    Task<IReadOnlyDictionary<int, DateTimeOffset>> Vigentes(int usuarioId, CancellationToken cancelar);

    /// <summary>Concede e encerra numa transação só: metade aplicada é pior que nada.</summary>
    Task Aplicar(int usuarioId, IReadOnlyCollection<int> conceder, IReadOnlyCollection<int> encerrar,
        Usuario por, DateTimeOffset agora, CancellationToken cancelar);
}

public interface IConferidorDeSenha
{
    bool Conferir(string senha, string resumoArmazenado);
    string Gerar(string senha);

    /// <summary>
    /// Resumo em formato antigo ou com parâmetros defasados. É o que permite
    /// endurecer os parâmetros no futuro sem forçar ninguém a trocar de senha.
    /// </summary>
    bool PrecisaRegravar(string resumoArmazenado);
}

/// <summary>O que o token carrega. Papel e empresas viajam, mas a fonte é o banco.</summary>
public sealed record ConteudoDoToken(int UsuarioId, string NomeDeUsuario, Papel Papel, IReadOnlyList<int> Empresas);

public sealed class TokenInvalido(string motivo) : Exception("Sessão inválida ou expirada.")
{
    public string Motivo { get; } = motivo;
}

public interface IEmissorDeToken
{
    (string Token, int ExpiraEmSegundos) Emitir(Usuario usuario);

    /// <exception cref="TokenInvalido">assinatura, validade ou conteúdo recusados</exception>
    Task<ConteudoDoToken> Ler(string token);
}

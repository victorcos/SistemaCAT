using Cat.Dominio.Acesso;

namespace Cat.Aplicacao.Acesso;

/// <summary>O que o caso de uso precisa do banco. A implementação vive na infraestrutura.</summary>
public interface IRepositorioDeUsuario
{
    Task<Usuario?> BuscarPorNome(string nomeDeUsuario, CancellationToken cancelar);
    Task<Usuario?> BuscarPorId(int id, CancellationToken cancelar);
    Task<string> ObterResumoDaSenha(int id, CancellationToken cancelar);
    Task SalvarTentativa(Usuario usuario, CancellationToken cancelar);
    Task RegravarResumoDaSenha(int id, string novoResumo, CancellationToken cancelar);
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

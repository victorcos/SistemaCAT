namespace Cat.Dominio.Acesso;

/// <summary>Recusa de acesso prevista pela regra, com a mensagem que a pessoa lê.</summary>
public abstract class ErroDeAcesso(string mensagem) : Exception(mensagem);

/// <summary>
/// Usuário ou senha errados. A mensagem é sempre a mesma, de propósito:
/// dizer "usuário não existe" entrega quais contas existem.
/// </summary>
public sealed class CredencialInvalida() : ErroDeAcesso("Usuário ou senha inválidos.");

public sealed class UsuarioInativo() : ErroDeAcesso("Usuário inativo. Procure um gestor.");

public sealed class UsuarioBloqueadoTemporariamente(int minutos)
    : ErroDeAcesso($"Muitas tentativas. Tente de novo em {minutos} {(minutos == 1 ? "minuto" : "minutos")}.")
{
    public int Minutos { get; } = minutos;
}

public sealed class UsuarioBloqueado(int tentativas)
    : ErroDeAcesso("Usuário bloqueado por excesso de tentativas. Procure um gestor.")
{
    public int Tentativas { get; } = tentativas;
}

/// <summary>
/// A pessoa não trabalha naquele assunto. Separada de <c>SemAcessoAEmpresa</c>
/// porque a recusa é de outra natureza e a mensagem tem de dizer qual: quem
/// esbarra nisto precisa saber que o caminho é pedir o segmento ao gestor, e não
/// que foi alocado na empresa errada.
/// </summary>
public sealed class SemAcessoAoSegmento(string segmento)
    : ErroDeAcesso($"Você não trabalha no segmento {segmento}. Peça acesso a um gestor.")
{
    public string Segmento { get; } = segmento;
}

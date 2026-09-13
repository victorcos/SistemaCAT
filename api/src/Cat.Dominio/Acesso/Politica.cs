using System.Globalization;
using System.Security.Cryptography;
using System.Text.RegularExpressions;

namespace Cat.Dominio.Acesso;

/// <summary>Recusa de uma regra de cadastro ou de gestão, com a mensagem que a pessoa lê.</summary>
public abstract class RecusaDeRegra(string mensagem) : Exception(mensagem);

/// <summary>Senha que não atende à política.</summary>
public sealed class SenhaFraca(string mensagem) : RecusaDeRegra(mensagem);

/// <summary>Dado de cadastro fora do formato (o <c>ValueError</c> do Python).</summary>
public sealed class DadoInvalido(string mensagem) : RecusaDeRegra(mensagem);

/// <summary>Impede o sistema de ficar sem quem administre.</summary>
public sealed class UltimoGestor(int restantes) : RecusaDeRegra(
    $"O sistema precisa de pelo menos {PoliticaDeAcesso.MinimoDeGestores} gestores " +
    "ativos. Promova outra pessoa antes de fazer esta alteração.")
{
    public int Restantes { get; } = restantes;
}

public sealed class NaoPodeAlterarSiMesmo(string acao) : RecusaDeRegra($"Você não pode {acao} a si mesmo.");

/// <summary>
/// As regras de cadastro, portadas de <c>dominio/acesso/usuario.py</c> com as
/// mesmas mensagens. Puras: nada de banco, e o sorteio da senha provisória é a
/// única coisa que não se repete.
/// </summary>
public static partial class PoliticaDeAcesso
{
    /// <summary>
    /// O sistema recusa ficar com menos de três gestores ativos. Com um só,
    /// férias, desligamento ou senha esquecida travam o sistema inteiro e não
    /// há quem destrave; com três, sempre sobram dois. É regra de domínio, não
    /// de tela, para valer em qualquer caminho.
    /// </summary>
    public const int MinimoDeGestores = 3;

    public const int TamanhoMinimoSenha = 10;

    // sem caractere ambíguo: quem recebe a senha provisória vai digitá-la
    // lendo de um bilhete ou de uma mensagem
    private const string AlfabetoProvisoria = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";

    /// <summary>
    /// Comprimento pesa mais que exigência de caractere especial, que só empurra
    /// para "Senha@123". Tamanho e alguma variedade. A ordem das checagens é a
    /// do Python, porque decide qual mensagem a pessoa lê primeiro.
    /// </summary>
    public static void ValidarSenha(string senha)
    {
        // o len() do Python conta caracteres, não unidades UTF-16: emoji conta um
        if (senha.EnumerateRunes().Count() < TamanhoMinimoSenha)
            throw new SenhaFraca($"A senha precisa de pelo menos {TamanhoMinimoSenha} caracteres.");
        if (senha.ToLowerInvariant() == senha || senha.ToUpperInvariant() == senha)
            throw new SenhaFraca("A senha precisa misturar maiúsculas e minúsculas.");
        if (!senha.Any(char.IsDigit))
            throw new SenhaFraca("A senha precisa de pelo menos um número.");
        if (senha.Trim() != senha)
            throw new SenhaFraca("A senha não pode começar nem terminar com espaço.");
    }

    /// <returns>o nome normalizado: sem espaço nas pontas e em minúsculas</returns>
    public static string ValidarNomeDeUsuario(string nome)
    {
        nome = nome.Trim().ToLowerInvariant();
        if (!NomeDeUsuario().IsMatch(nome))
            throw new DadoInvalido(
                "Nome de usuário deve ter de 3 a 40 caracteres, entre letras " +
                "minúsculas, números, ponto, hífen e sublinhado.");
        return nome;
    }

    /// <returns>o e-mail normalizado</returns>
    public static string ValidarEmail(string email)
    {
        email = email.Trim().ToLowerInvariant();
        if (!Email().IsMatch(email))
            throw new DadoInvalido("E-mail inválido.");
        return email;
    }

    public static string ValidarNomeDeExibicao(string nome)
    {
        nome = nome.Trim();
        if (nome.Length == 0)
            throw new DadoInvalido("O nome de exibição não pode ficar vazio.");
        return nome;
    }

    /// <summary>
    /// Senha de uso único, gerada pelo sistema. O gestor nunca escolhe a senha
    /// de ninguém: se escolhesse, passaria a saber a senha da pessoa, e toda a
    /// proteção do resumo perderia sentido na prática.
    /// </summary>
    public static string GerarSenhaProvisoria(int tamanho = 14)
    {
        while (true)
        {
            var candidata = new string(RandomNumberGenerator.GetItems<char>(AlfabetoProvisoria, tamanho));
            try
            {
                ValidarSenha(candidata);
                return candidata;
            }
            catch (SenhaFraca)
            {
                // sorteio sem maiúscula, minúscula ou número: tenta de novo
            }
        }
    }

    /// <summary>Chamado antes de desativar ou rebaixar um gestor.</summary>
    public static void GarantirMinimoDeGestores(int gestoresAtivosDepois)
    {
        if (gestoresAtivosDepois < MinimoDeGestores)
            throw new UltimoGestor(gestoresAtivosDepois);
    }

    // [a-z] em ASCII puro, como no Python: "acento_ç" é recusado
    [GeneratedRegex("^[a-z0-9._-]{3,40}$", RegexOptions.CultureInvariant)]
    private static partial Regex NomeDeUsuario();

    [GeneratedRegex(@"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$", RegexOptions.CultureInvariant)]
    private static partial Regex Email();
}

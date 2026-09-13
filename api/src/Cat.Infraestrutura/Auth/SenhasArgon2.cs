using System.Security.Cryptography;
using System.Text;
using Cat.Aplicacao.Acesso;
using Cat.Aplicacao.Log;
using Konscious.Security.Cryptography;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Cat.Infraestrutura.Auth;

public sealed class SenhaLonga() : ArgumentException($"A senha excede {SenhasArgon2.LimiteSenha} bytes.");

/// <summary>
/// Resumo de senha com Argon2id, conferindo byte a byte o que o
/// <c>argon2-cffi</c> do Python grava. Senha não é criptografada: resumo de mão
/// única, função lenta e cara em memória, sal por senha e pimenta fora do banco.
///
/// Compatibilidade exata é o que deixa migrar sem derrubar ninguém: resumo
/// gravado por um lado confere no outro. Os vetores gerados pelo Python ficam
/// em <c>tests/Cat.Compatibilidade.Testes</c>.
/// </summary>
public sealed class SenhasArgon2 : IConferidorDeSenha
{
    public const int LimiteSenha = 1024;
    private const int LimiteBcrypt = 72;

    // Os padrões do argon2-cffi 25, que seguem a RFC 9106. Mudar aqui sem mudar
    // lá faria cada login de um lado regravar o resumo que o outro acabou de gravar.
    public const int Memoria = 65536;   // KiB
    public const int Iteracoes = 3;
    public const int Vias = 4;
    public const int TamanhoResumo = 32;
    public const int TamanhoSal = 16;

    private readonly byte[] _pimenta;
    private readonly ILogger _log;

    public SenhasArgon2(string pimenta, ILogger<SenhasArgon2>? log = null)
    {
        _pimenta = Encoding.UTF8.GetBytes(pimenta ?? "");
        _log = log ?? (ILogger)NullLogger.Instance;
    }

    /// <summary>
    /// A pimenta entra antes do resumo, por HMAC-SHA256, e o que vai ao Argon2 é
    /// o <b>hexadecimal minúsculo</b> do HMAC — não os bytes. Detalhe que decide
    /// se alguém consegue entrar: o Python usa <c>.hexdigest()</c>.
    /// </summary>
    private byte[] Temperar(string senha)
    {
        if (_pimenta.Length == 0)
            return Encoding.UTF8.GetBytes(senha);
        var hmac = HMACSHA256.HashData(_pimenta, Encoding.UTF8.GetBytes(senha));
        return Encoding.UTF8.GetBytes(Convert.ToHexStringLower(hmac));
    }

    public string Gerar(string senha)
    {
        if (Encoding.UTF8.GetByteCount(senha) > LimiteSenha)
            throw new SenhaLonga();
        var parametros = new ParametrosArgon2("argon2id", 19, Memoria, Iteracoes, Vias,
            RandomNumberGenerator.GetBytes(TamanhoSal), new byte[TamanhoResumo]);
        return (parametros with { Resumo = Calcular(Temperar(senha), parametros) }).Codificar();
    }

    public bool Conferir(string senha, string resumoArmazenado)
    {
        if (string.IsNullOrEmpty(resumoArmazenado))
            return false;

        if (resumoArmazenado.StartsWith("$argon2", StringComparison.Ordinal))
        {
            if (!ParametrosArgon2.TentarLer(resumoArmazenado, out var p))
            {
                _log.Erro("resumo de senha ilegível no banco", new { formato = "argon2", erro = "InvalidHashError" });
                return false;
            }
            var calculado = Calcular(Temperar(senha), p);
            return CryptographicOperations.FixedTimeEquals(calculado, p.Resumo);
        }

        // formato antigo: bcrypt, gravado antes da migração e sem pimenta
        if (resumoArmazenado.StartsWith("$2", StringComparison.Ordinal))
        {
            try
            {
                var bytes = Encoding.UTF8.GetBytes(senha);
                var cortada = bytes.Length > LimiteBcrypt
                    ? Encoding.UTF8.GetString(bytes, 0, LimiteBcrypt)
                    : senha;
                return BCrypt.Net.BCrypt.Verify(cortada, resumoArmazenado);
            }
            catch (Exception erro) when (erro is ArgumentException or FormatException
                                             or BCrypt.Net.SaltParseException)
            {
                _log.Erro("resumo de senha ilegível no banco", new { formato = "bcrypt" });
                return false;
            }
        }

        _log.Erro("formato de resumo de senha desconhecido",
            new { prefixo = resumoArmazenado[..Math.Min(7, resumoArmazenado.Length)] });
        return false;
    }

    /// <summary>
    /// Mesma pergunta do <c>check_needs_rehash</c> do argon2-cffi: tipo, versão,
    /// memória, iterações, vias e tamanhos iguais aos atuais.
    /// </summary>
    public bool PrecisaRegravar(string resumoArmazenado)
    {
        if (!resumoArmazenado.StartsWith("$argon2", StringComparison.Ordinal))
            return true;
        if (!ParametrosArgon2.TentarLer(resumoArmazenado, out var p))
            return true;
        return p is not { Tipo: "argon2id", Versao: 19, Memoria: Memoria, Iteracoes: Iteracoes, Vias: Vias }
               || p.Sal.Length != TamanhoSal
               || p.Resumo.Length != TamanhoResumo;
    }

    private static byte[] Calcular(byte[] senhaTemperada, ParametrosArgon2 p)
    {
        using Argon2 argon = p.Tipo switch
        {
            "argon2id" => new Argon2id(senhaTemperada),
            "argon2i" => new Argon2i(senhaTemperada),
            _ => new Argon2d(senhaTemperada),
        };
        argon.Salt = p.Sal;
        argon.MemorySize = p.Memoria;
        argon.Iterations = p.Iteracoes;
        argon.DegreeOfParallelism = p.Vias;
        return argon.GetBytes(p.Resumo.Length);
    }
}

/// <summary>
/// O formato PHC que o argon2-cffi grava:
/// <c>$argon2id$v=19$m=65536,t=3,p=4$&lt;sal&gt;$&lt;resumo&gt;</c>, em base64 sem preenchimento.
/// </summary>
internal sealed record ParametrosArgon2(
    string Tipo, int Versao, int Memoria, int Iteracoes, int Vias, byte[] Sal, byte[] Resumo)
{
    public string Codificar() =>
        $"${Tipo}$v={Versao}$m={Memoria},t={Iteracoes},p={Vias}${Base64SemPreenchimento(Sal)}${Base64SemPreenchimento(Resumo)}";

    public static bool TentarLer(string texto, out ParametrosArgon2 parametros)
    {
        parametros = null!;
        // "", tipo, "v=19", "m=..,t=..,p=..", sal, resumo
        var partes = texto.Split('$');
        if (partes.Length != 6 || partes[0].Length != 0)
            return false;
        if (partes[1] is not ("argon2id" or "argon2i" or "argon2d"))
            return false;
        if (!partes[2].StartsWith("v=", StringComparison.Ordinal) || !int.TryParse(partes[2][2..], out var versao))
            return false;

        var valores = new Dictionary<string, int>();
        foreach (var par in partes[3].Split(','))
        {
            var kv = par.Split('=');
            if (kv.Length != 2 || !int.TryParse(kv[1], out var numero))
                return false;
            valores[kv[0]] = numero;
        }
        if (!valores.TryGetValue("m", out var m) || !valores.TryGetValue("t", out var t)
            || !valores.TryGetValue("p", out var p) || m <= 0 || t <= 0 || p <= 0)
            return false;

        if (!TentarBase64(partes[4], out var sal) || !TentarBase64(partes[5], out var resumo)
            || sal.Length == 0 || resumo.Length == 0)
            return false;

        parametros = new ParametrosArgon2(partes[1], versao, m, t, p, sal, resumo);
        return true;
    }

    private static string Base64SemPreenchimento(byte[] bytes) => Convert.ToBase64String(bytes).TrimEnd('=');

    private static bool TentarBase64(string texto, out byte[] bytes)
    {
        var completo = texto.PadRight(texto.Length + (4 - texto.Length % 4) % 4, '=');
        bytes = new byte[completo.Length];
        if (!Convert.TryFromBase64String(completo, bytes, out var escritos))
            return false;
        bytes = bytes[..escritos];
        return true;
    }
}

using System.Text.RegularExpressions;

namespace Cat.Dominio.Comum;

public sealed class CnpjInvalido(string valor, string motivo) : Exception($"CNPJ inválido ({motivo}): {valor}")
{
    public string Valor { get; } = valor;
    public string Motivo { get; } = motivo;
}

/// <summary>
/// CNPJ validado, portado de <c>dominio/comum/cnpj.py</c>.
///
/// Suporta os dois formatos: a Receita passou a emitir CNPJ <b>alfanumérico</b>
/// em 31/07/2026, e um validador que só aceite dígito recusaria empresa nova
/// legítima. Raiz (1 a 8) e ordem (9 a 12) aceitam letra maiúscula ou dígito;
/// os verificadores (13 e 14) são sempre numéricos. O dígito usa módulo 11
/// sobre o valor ASCII menos 48, então <c>0</c>..<c>9</c> valem 0..9 e o CNPJ
/// antigo dá o mesmo resultado nas duas regras.
/// </summary>
public sealed partial record Cnpj
{
    public const int Tamanho = 14;
    public const string OrdemMatriz = "0001";

    private static readonly int[] Pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    private static readonly int[] Pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];

    /// <summary>Sempre limpo e em maiúsculas.</summary>
    public string Valor { get; }

    public Cnpj(string bruto)
    {
        var limpo = Limpar(bruto);
        if (limpo.Length != Tamanho)
            throw new CnpjInvalido(bruto, $"precisa de {Tamanho} caracteres");
        if (!Valido().IsMatch(limpo))
            throw new CnpjInvalido(bruto, "os 12 primeiros aceitam letra ou dígito e os 2 últimos só dígito");
        // repetição de um só caractere passa no módulo 11 mas não existe
        if (limpo.Distinct().Count() == 1)
            throw new CnpjInvalido(bruto, "sequência repetida");
        if (DigitosVerificadores(limpo[..12]) != limpo[12..])
            throw new CnpjInvalido(bruto, "dígito verificador não confere");
        Valor = limpo;
    }

    /// <summary>Os 8 primeiros. Identifica o grupo, comum a todas as filiais.</summary>
    public string Raiz => Valor[..8];

    /// <summary>Posições 9 a 12. Diz qual estabelecimento é.</summary>
    public string Ordem => Valor[8..12];

    public bool EMatriz => Ordem == OrdemMatriz;

    public string Formatado => $"{Valor[..2]}.{Valor[2..5]}.{Valor[5..8]}/{Valor[8..12]}-{Valor[12..]}";

    public override string ToString() => Formatado;

    /// <summary>Tira pontuação e põe em maiúsculas, sem validar.</summary>
    public static string Limpar(string? bruto) => NaoAlfanumerico().Replace(bruto ?? "", "").ToUpperInvariant();

    /// <summary>Os dois dígitos a partir dos doze primeiros caracteres.</summary>
    public static string DigitosVerificadores(string baseDoze)
    {
        var d1 = Digito(baseDoze, Pesos1);
        var d2 = Digito(baseDoze + d1, Pesos2);
        return d1 + d2;
    }

    /// <summary>
    /// O CNPJ ou nada. Serve para campo que pode vir torto do banco: recusar a
    /// tela inteira por isso seria pior do que mostrar sem formatação.
    /// </summary>
    public static Cnpj? Tentar(string? bruto)
    {
        try
        {
            return bruto is null ? null : new Cnpj(bruto);
        }
        catch (CnpjInvalido)
        {
            return null;
        }
    }

    private static string Digito(string @base, int[] pesos)
    {
        var soma = @base.Select((c, i) => (c - 48) * pesos[i]).Sum();
        var resto = soma % 11;
        return resto < 2 ? "0" : (11 - resto).ToString();
    }

    [GeneratedRegex("^[0-9A-Z]{12}[0-9]{2}$")]
    private static partial Regex Valido();

    [GeneratedRegex("[^0-9A-Za-z]")]
    private static partial Regex NaoAlfanumerico();
}

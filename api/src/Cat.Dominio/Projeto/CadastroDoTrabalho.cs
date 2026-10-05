using Cat.Dominio.Acesso;

namespace Cat.Dominio.Projeto;

/// <summary>De quando é a base importada, e quantas EFD caem fora do período do trabalho.</summary>
public sealed record BaseDoTrabalho(int Efds, DateOnly? Primeira, DateOnly? Ultima, int ForaDoPeriodo);

public sealed class CadastroSemMudanca() : RecusaDeRegra("Nada mudou no cadastro do trabalho.");

/// <summary>
/// Nome e período do trabalho. Mudam — o trabalho da empresa 19 nasceu como 2025 e
/// a base que existia era de 2021 (16/09/2026) —, mas nunca calados: toda
/// mudança vira evento com o de e o para.
/// </summary>
public static class CadastroDoTrabalho
{
    public const int TamanhoMinimoDoNome = 2;

    private static DateOnly Mes(DateOnly d) => new(d.Year, d.Month, 1);

    /// <summary>A competência é mês: o dia gravado no cadastro não conta.</summary>
    public static bool ForaDoPeriodo(DateOnly competencia, DateOnly ini, DateOnly fim) =>
        Mes(competencia) < Mes(ini) || Mes(competencia) > Mes(fim);

    public static BaseDoTrabalho Resumir(IReadOnlyCollection<(DateOnly Competencia, int Efds)> base_, DateOnly ini, DateOnly fim) =>
        new(base_.Sum(b => b.Efds),
            base_.Count == 0 ? null : base_.Min(b => b.Competencia),
            base_.Count == 0 ? null : base_.Max(b => b.Competencia),
            base_.Where(b => ForaDoPeriodo(b.Competencia, ini, fim)).Sum(b => b.Efds));

    /// <summary>A frase da linha do tempo: só o que mudou.</summary>
    public static string Frase(string nomeDe, DateOnly iniDe, DateOnly fimDe, string nomePara, DateOnly iniPara, DateOnly fimPara)
    {
        var partes = new List<string>();
        if (nomeDe != nomePara)
            partes.Add($"nome «{nomeDe}» → «{nomePara}»");
        if (Mes(iniDe) != Mes(iniPara) || Mes(fimDe) != Mes(fimPara))
            partes.Add($"período {iniDe:MM/yyyy} a {fimDe:MM/yyyy} → {iniPara:MM/yyyy} a {fimPara:MM/yyyy}");
        return "Cadastro do trabalho: " + string.Join("; ", partes);
    }
}

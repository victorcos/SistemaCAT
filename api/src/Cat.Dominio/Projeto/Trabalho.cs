namespace Cat.Dominio.Projeto;

/// <summary>
/// As frentes de trabalho. A chave é gravada no banco; o rótulo é o que a tela mostra.
/// A ordem é a de <c>FRENTES</c> no Python, que a tela usa para montar a lista.
/// </summary>
public static class Frentes
{
    public static readonly IReadOnlyList<KeyValuePair<string, string>> Todas =
    [
        new("cat42", "CAT 42 — ressarcimento de ICMS-ST"),
        new("depara", "De-para de produto"),
        new("sped", "Quebra de SPED"),
        new("notafiscal", "Nota fiscal"),
    ];

    public static bool Existe(string? chave) => Todas.Any(f => f.Key == chave);

    /// <summary>Frente gravada que não está mais na lista aparece pela chave, não some.</summary>
    public static string Rotulo(string chave) =>
        Todas.FirstOrDefault(f => f.Key == chave).Value ?? chave;
}

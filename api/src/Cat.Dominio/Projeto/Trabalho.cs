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

/// <summary>
/// Em que pé o trabalho está, portado de <c>dominio/projeto/historico.py</c>.
/// A regra de mudar status é da fatia do histórico; aqui vem só o que o
/// cartão do projeto mostra.
/// </summary>
public static class StatusDoProjeto
{
    public const string EmAndamento = "em_andamento";

    /// <summary>Status desconhecido aparece como gravado, em vez de derrubar a listagem.</summary>
    public static string Rotulo(string valor) => valor switch
    {
        "em_andamento" => "Em andamento",
        "pausado" => "Pausado",
        "cancelado" => "Cancelado",
        "concluido" => "Concluído",
        _ => valor,
    };
}

/// <summary>
/// Os tipos de evento que esta fatia grava. O valor vai para o banco e o
/// histórico em Python lê: mudar um texto destes reescreve o passado.
/// </summary>
public static class TipoDeEvento
{
    public const string Criado = "criado";
    public const string Comentario = "comentario";
}

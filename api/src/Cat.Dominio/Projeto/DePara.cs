using System.Globalization;
using Cat.Dominio.Acesso;

namespace Cat.Dominio.Projeto;

/// <summary>Uma decisão do de-para, já conferida.</summary>
/// <param name="Cnpj">Vazio vale para todos os estabelecimentos da empresa.</param>
/// <param name="Fator">Quantidade na origem × fator = quantidade no destino.</param>
public sealed record DecisaoDeDePara(
    string Cnpj, string Origem, string Destino, decimal Fator, string Motivo, string Situacao,
    string? Confianca, string? Explicacao);

/// <summary>
/// O de-para de códigos: o mesmo produto escriturado com código diferente na
/// compra e na venda, em kit ou no marketplace. O motor propõe
/// (<c>cat/dominio/depara/candidatos.py</c>); quem escreve aprova ou recusa, e a
/// decisão vale para a empresa (decisão do Victor, 16/09/2026).
/// </summary>
public static class DePara
{
    public const string Aprovado = "aprovado";
    public const string Recusado = "recusado";
    public const int TamanhoMaximoDoCodigo = 60;
    public const int TamanhoMaximoDaExplicacao = 500;
    public const int DecisoesPorPedido = 5000;

    /// <summary>Os motivos que o motor usa, mais os de quem informa à mão.</summary>
    public static readonly IReadOnlySet<string> Motivos =
        new HashSet<string> { "gtin", "sufixo", "kit", "descricao", "cliente", "analista" };

    public static readonly IReadOnlySet<string> Confiancas = new HashSet<string> { "alta", "media" };

    public static DecisaoDeDePara Validar(string? cnpj, string? origem, string? destino, string? fator,
        string? motivo, string? situacao, string? confianca, string? explicacao)
    {
        var c = (cnpj ?? "").Trim();
        if (c.Length != 0 && (c.Length != 14 || !c.All(char.IsAsciiLetterOrDigit)))
            throw new DadoInvalido("O CNPJ do estabelecimento tem 14 caracteres, ou fica vazio para valer para todos.");
        var o = (origem ?? "").Trim();
        var d = (destino ?? "").Trim();
        if (o.Length == 0 || d.Length == 0)
            throw new DadoInvalido("Cada decisão precisa do código de origem e do código de destino.");
        if (o.Length > TamanhoMaximoDoCodigo || d.Length > TamanhoMaximoDoCodigo)
            throw new DadoInvalido($"Código com mais de {TamanhoMaximoDoCodigo} caracteres.");
        if (o == d)
            throw new DadoInvalido($"O código {o} não pode apontar para ele mesmo.");
        if (!decimal.TryParse(fator ?? "1", NumberStyles.Number, CultureInfo.InvariantCulture, out var f) || f <= 0 || f > 100_000)
            throw new DadoInvalido($"Fator inválido para {o}: é quantas unidades do destino cabem em uma da origem, maior que zero.");
        var m = (motivo ?? "").Trim();
        if (!Motivos.Contains(m))
            throw new DadoInvalido($"Motivo desconhecido: use um de {string.Join(", ", Motivos)}.");
        var s = (situacao ?? "").Trim();
        if (s is not (Aprovado or Recusado))
            throw new DadoInvalido("A decisão é aprovado ou recusado.");
        var conf = string.IsNullOrWhiteSpace(confianca) ? null : confianca.Trim();
        if (conf is not null && !Confiancas.Contains(conf))
            throw new DadoInvalido("Confiança é alta ou media.");
        var texto = string.IsNullOrWhiteSpace(explicacao) ? null : explicacao.Trim();
        if (texto is { Length: > TamanhoMaximoDaExplicacao })
            texto = texto[..TamanhoMaximoDaExplicacao];
        return new DecisaoDeDePara(c, o, d, f, m, s, conf, texto);
    }

    /// <summary>A frase do histórico.</summary>
    public static string Frase(IReadOnlyCollection<DecisaoDeDePara> decisoes)
    {
        var aprovadas = decisoes.Count(x => x.Situacao == Aprovado);
        var recusadas = decisoes.Count - aprovadas;
        var partes = new List<string>();
        if (aprovadas > 0) partes.Add($"{aprovadas} {(aprovadas == 1 ? "par aprovado" : "pares aprovados")}");
        if (recusadas > 0) partes.Add($"{recusadas} {(recusadas == 1 ? "par recusado" : "pares recusados")}");
        return $"De-para de códigos · {string.Join(", ", partes)}";
    }
}

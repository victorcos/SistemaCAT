using System.Globalization;
using Cat.Dominio.Acesso;

namespace Cat.Dominio.Projeto;

/// <summary>Uma correção à mão já conferida.</summary>
/// <param name="ValorAnterior">O que estava na tela quando alguém corrigiu — é o "antes" do histórico.</param>
public sealed record CorrecaoDoTrabalho(
    string Campo, string Valor, string Motivo, string Cnpj, string Codigo, string Documento,
    int? NumeroItem, string ValorAnterior)
{
    /// <summary>O alvo em uma linha, como o histórico mostra.</summary>
    public string Onde => Correcao.EhDaMercadoria(Campo)
        ? $"mercadoria {Codigo}"
        : $"documento {(Documento.Length == 44 ? "…" + Documento[^6..] : Documento)}, item {NumeroItem}";

    /// <summary>O antes e o depois, prontos para a linha do tempo.</summary>
    public string Frase =>
        $"{Correcao.Rotulo(Campo)} ({Onde}): {(ValorAnterior.Length == 0 ? "(vazio)" : ValorAnterior)} → {Valor}";
}

/// <summary>
/// O que uma pessoa pode mudar no que o sistema calculou — alíquota e redução da
/// mercadoria, enquadramento, quantidade, valor e ICMS de uma linha, e tirar ou
/// trazer de volta a linha da ficha.
///
/// A regra é a mesma do motor (<c>cat/dominio/cat42/correcao.py</c>), e as duas
/// implementações dizem a mesma coisa de propósito: aqui se recusa na porta, lá
/// se aplica no cálculo. O que **não** pode divergir é o que cada campo aceita —
/// por isso os limites estão escritos nos dois lados, com os mesmos números.
///
/// Correção é do **trabalho**, não da empresa: o de-para se herda porque o
/// código do fornecedor não muda de ano para ano; alíquota e enquadramento
/// mudam com a lei (decisão do Victor, 20/09/2026).
/// </summary>
public static class Correcao
{
    public const string Aliquota = "aliquota";
    public const string ReducaoBase = "reducao_base";
    public const string Enquadramento = "enquadramento";
    public const string Quantidade = "quantidade";
    public const string ValorItem = "valor_item";
    public const string IcmsSuportado = "icms_suportado";
    public const string Excluida = "excluida";

    public const int MotivoMinimo = 3;
    public const int MotivoMaximo = 500;
    public const int CorrecoesPorPedido = 5000;

    private static readonly Dictionary<string, string> Rotulos = new()
    {
        [Aliquota] = "Alíquota interna",
        [ReducaoBase] = "Redução de base (%)",
        [Enquadramento] = "Enquadramento legal",
        [Quantidade] = "Quantidade",
        [ValorItem] = "Valor do item (base do ICMS)",
        [IcmsSuportado] = "ICMS suportado",
        [Excluida] = "Fora da ficha",
    };

    private static readonly HashSet<string> DaMercadoria = [Aliquota, ReducaoBase];

    public static IReadOnlyCollection<string> Campos => Rotulos.Keys;

    public static bool EhDaMercadoria(string campo) => DaMercadoria.Contains(campo);

    public static string Rotulo(string campo) => Rotulos.GetValueOrDefault(campo, campo);

    public static CorrecaoDoTrabalho Validar(string? campo, string? valor, string? motivo, string? cnpj,
        string? codigo, string? documento, int? numeroItem, string? valorAnterior)
    {
        var c = (campo ?? "").Trim();
        if (!Rotulos.ContainsKey(c))
            throw new DadoInvalido($"Campo desconhecido: {campo}.");

        var razao = (motivo ?? "").Trim();
        if (razao.Length < MotivoMinimo)
            throw new DadoInvalido("Toda correção precisa de um motivo escrito — é o que a fiscalização vai ler.");
        if (razao.Length > MotivoMaximo)
            throw new DadoInvalido($"O motivo passa de {MotivoMaximo} caracteres.");

        var estabelecimento = (cnpj ?? "").Trim();
        if (estabelecimento.Length != 0 && (estabelecimento.Length != 14 || !estabelecimento.All(char.IsAsciiDigit)))
            throw new DadoInvalido("O CNPJ do estabelecimento tem 14 dígitos.");

        var mercadoria = (codigo ?? "").Trim();
        var doc = (documento ?? "").Trim();
        var item = numeroItem;
        if (EhDaMercadoria(c))
        {
            if (mercadoria.Length == 0)
                throw new DadoInvalido($"{Rotulo(c)} é da mercadoria: falta o código dela.");
            doc = "";
            item = null;
        }
        else
        {
            if (doc.Length == 0)
                throw new DadoInvalido($"{Rotulo(c)} é da linha: falta a chave ou o número do documento.");
            if (item is null)
                throw new DadoInvalido(
                    $"{Rotulo(c)} é da linha: falta o número do item no documento. " +
                    "Linha de relatório de PDV, que não tem item, não pode ser corrigida uma a uma.");
            if (item <= 0)
                throw new DadoInvalido("O número do item começa em 1.");
        }

        var texto = ValorValido(c, valor);
        var antes = (valorAnterior ?? "").Trim();
        if (antes.Length > MotivoMaximo)
            throw new DadoInvalido("O valor anterior informado é longo demais para ser um valor.");
        return new CorrecaoDoTrabalho(c, texto, razao, estabelecimento, mercadoria, doc, item, antes);
    }

    /// <summary>O valor como ele é gravado — texto, porque cada campo tem o seu tipo.</summary>
    private static string ValorValido(string campo, string? valor)
    {
        var bruto = (valor ?? "").Trim();
        if (campo == Excluida)
        {
            var resposta = bruto.ToLowerInvariant();
            if (resposta is "sim" or "true" or "1" or "s" or "x")
                return "sim";
            if (resposta is "nao" or "não" or "false" or "0" or "n" or "")
                return "nao";
            throw new DadoInvalido($"{Rotulo(campo)}: responda sim ou não, não '{valor}'.");
        }
        if (!decimal.TryParse(bruto.Replace(',', '.'), NumberStyles.Number, CultureInfo.InvariantCulture, out var numero))
            throw new DadoInvalido($"{Rotulo(campo)}: '{valor}' não é um número.");
        return campo switch
        {
            Enquadramento when numero != decimal.Truncate(numero) || numero is < 0 or > 4 =>
                throw new DadoInvalido("O enquadramento legal é um número de 0 a 4."),
            Enquadramento => ((int)numero).ToString(CultureInfo.InvariantCulture),
            Aliquota when numero <= 0 || numero > 100 =>
                throw new DadoInvalido("A alíquota vai de zero (exclusive) a 100."),
            ReducaoBase when numero < 0 || numero >= 100 =>
                throw new DadoInvalido("A redução de base vai de 0 a 100 (exclusive); 0 tira a redução."),
            Quantidade when numero <= 0 =>
                throw new DadoInvalido("A quantidade é maior que zero: o sinal quem dá é a espécie do movimento."),
            ValorItem or IcmsSuportado when numero < 0 =>
                throw new DadoInvalido($"{Rotulo(campo)} não pode ser negativo."),
            Aliquota or ReducaoBase => numero.ToString("0.0000", CultureInfo.InvariantCulture),
            _ => numero.ToString("0.000000", CultureInfo.InvariantCulture),
        };
    }
}

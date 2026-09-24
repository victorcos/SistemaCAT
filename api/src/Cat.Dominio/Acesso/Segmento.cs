namespace Cat.Dominio.Acesso;

/// <summary>
/// O que a pessoa toca dentro de um segmento. É o segundo nível da tela
/// inicial, e é ele que leva à lista de trabalhos.
/// </summary>
public sealed record Modulo(string Chave, string Rotulo, string Descricao);

/// <summary>Um segmento tributário: o primeiro nível da tela inicial.</summary>
public sealed record Segmento(string Chave, string Rotulo, string Descricao, IReadOnlyList<Modulo> Modulos);

/// <summary>
/// Os segmentos tributários da casa, e quem enxerga cada um.
///
/// **É uma terceira dimensão de acesso**, ortogonal às duas que já existiam:
/// <see cref="Papel"/> diz O QUE a pessoa pode fazer, a alocação diz SOBRE QUAIS
/// EMPRESAS, e o segmento diz EM QUE ASSUNTO. Um analista alocado na carteira
/// inteira e liberado só para PIS/COFINS não vê os trabalhos de ICMS — e o
/// contrário também vale.
///
/// **Gestor e dev enxergam todos** (decisão do Victor, 22/09/2026), pela mesma
/// razão que já ignoram o escopo de empresa: quem responde pela carteira não
/// pode depender de alguém liberá-lo assunto a assunto, e manutenção precisa
/// reproduzir problema em qualquer frente. Repare que a regra é do **papel**, e
/// não do cargo: cargo continua sendo informação organizacional, sem permissão
/// nenhuma — foi a escolha explícita ao desenhar esta tela.
///
/// **A reforma entra como módulo, não como segmento.** A CBS substitui
/// PIS/COFINS e o IBS substitui ICMS/ISS, então cada uma mora ao lado do tributo
/// que sucede: quem toca PIS/COFINS é quem vai tocar CBS, e a transição de 2027
/// a 2033 obriga a apurar os dois lado a lado por anos. Segmento separado para a
/// reforma partiria em dois exatamente a equipe que precisa ver os dois juntos.
/// </summary>
public static class Segmentos
{
    public const string PisCofins = "piscofins";
    public const string Icms = "icms";
    public const string IrpjCsll = "irpj_csll";

    public static readonly IReadOnlyList<Segmento> Todos =
    [
        new(PisCofins, "PIS/COFINS", "Apuração, créditos e reenquadramento das contribuições.",
        [
            new("piscofins", "PIS/COFINS", "Apuração pela EFD-Contribuições e revisão de CST."),
            new("cbs", "CBS", "A contribuição que substitui PIS/COFINS a partir de 2027."),
        ]),
        new(Icms, "ICMS", "Ressarcimento, substituição tributária e obrigações estaduais.",
        [
            new("icms", "ICMS", "CAT 42, ressarcimento de ST e apuração estadual."),
            new("ibs", "IBS", "O imposto que substitui ICMS e ISS na transição da reforma."),
        ]),
        new(IrpjCsll, "IRPJ/CSLL", "Lucro real, e-Lalur e e-Lacs pela ECF.",
        [
            // um módulo só: IRPJ e CSLL apuram juntos, mesma base e mesma ECF.
            // Segmento de um módulo pula a segunda tela e vai direto ao trabalho
            new("irpj_csll", "IRPJ/CSLL", "Apuração trimestral ou anual pela ECF."),
        ]),
    ];

    /// <summary>Módulo que saiu do catálogo aparece pela chave, em vez de sumir da frase.</summary>
    public static string RotuloDoModulo(string? chave) =>
        Todos.SelectMany(s => s.Modulos).FirstOrDefault(m => m.Chave == chave)?.Rotulo ?? chave ?? "";

    /// <summary>
    /// O que falta numa pasta que não serve ao trabalho. Fica aqui, junto do
    /// catálogo, porque é a frase que a pessoa lê quando a importação recusa —
    /// e ela precisa dizer o arquivo daquele tributo, não o da CAT 42.
    /// </summary>
    public static string FaltaNoLote(string? modulo) => modulo switch
    {
        PisCofins => "Falta a EFD-Contribuições, a ECD, a EFD ICMS/IPI ou o XML das notas.",
        IrpjCsll => "Falta a ECF ou a ECD.",
        _ => "Falta a EFD ICMS/IPI, o XML das notas ou o relatório gerencial.",
    };

    public static Segmento? Buscar(string? chave) => Todos.FirstOrDefault(s => s.Chave == chave);

    public static bool Existe(string? chave) => Buscar(chave) is not null;

    /// <summary>Segmento gravado que saiu da lista aparece pela chave, não some.</summary>
    public static string Rotulo(string chave) => Buscar(chave)?.Rotulo ?? chave;

    /// <summary>Só as chaves conhecidas, sem repetição e na ordem da lista.</summary>
    public static IReadOnlyList<string> Limpar(IEnumerable<string>? chaves)
    {
        var pedidos = (chaves ?? []).Select(c => (c ?? "").Trim().ToLowerInvariant()).ToHashSet();
        var desconhecido = pedidos.FirstOrDefault(c => !Existe(c));
        if (desconhecido is not null)
            throw new DadoInvalido($"Segmento desconhecido: {desconhecido}. Vale um de: " +
                                   $"{string.Join(", ", Todos.Select(s => s.Chave))}.");
        return Todos.Where(s => pedidos.Contains(s.Chave)).Select(s => s.Chave).ToList();
    }

    /// <summary>O que a pessoa enxerga. Gestor e dev enxergam tudo.</summary>
    public static IReadOnlyList<Segmento> De(Usuario usuario) =>
        usuario.Papel.EnxergaTodosOsSegmentos()
            ? Todos
            : Todos.Where(s => usuario.Segmentos.Contains(s.Chave)).ToList();

    public static bool PodeVer(Usuario usuario, string chave) =>
        usuario.Papel.EnxergaTodosOsSegmentos() || usuario.Segmentos.Contains(chave);

    /// <summary>
    /// Para onde a pessoa cai ao entrar, sem clique nenhum.
    ///
    /// Com mais de um segmento, a tela de segmentos — filtrada, mostrando só os
    /// dela. Com um só, pula essa tela: ela não escolheria nada ali. E se esse
    /// único segmento tiver um módulo só, pula as duas e vai ao trabalho.
    /// Nenhum segmento liberado devolve nulo, e a tela diz para procurar o gestor
    /// em vez de mostrar uma página vazia sem explicação.
    /// </summary>
    public static DestinoDeEntrada Entrada(Usuario usuario)
    {
        var meus = De(usuario);
        if (meus.Count == 0)
            return new DestinoDeEntrada(null, null);
        if (meus.Count > 1)
            return new DestinoDeEntrada(null, null, TodosOsSegmentos: true);
        var unico = meus[0];
        return unico.Modulos.Count == 1
            ? new DestinoDeEntrada(unico.Chave, unico.Modulos[0].Chave)
            : new DestinoDeEntrada(unico.Chave, null);
    }
}

/// <summary>
/// Onde a tela inicial deve parar. Tudo nulo e <c>TodosOsSegmentos</c> falso
/// significa que a pessoa não tem segmento nenhum liberado.
/// </summary>
public sealed record DestinoDeEntrada(string? Segmento, string? Modulo, bool TodosOsSegmentos = false);

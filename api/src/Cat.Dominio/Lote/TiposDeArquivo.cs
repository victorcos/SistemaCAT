using Cat.Dominio.Acesso;

namespace Cat.Dominio.Lote;

public sealed record TipoDeArquivo(string Valor, string Rotulo, string Grupo, bool AlimentaACat,
    IReadOnlyList<string> Modulos)
{
    /// <summary>Se o trabalho deste módulo lê o arquivo.</summary>
    public bool Alimenta(string? modulo) => Modulos.Contains(modulo ?? "");
}

/// <summary>
/// O que cada tipo de arquivo é, para a tela: rótulo, grupo e a que trabalho serve.
///
/// Quem <b>reconhece</b> o tipo de um arquivo é o motor, lendo o conteúdo
/// (<c>infraestrutura/arquivos/classificador.py</c>). Esta tabela só descreve o
/// valor que ele grava — e é a mesma de <c>dominio/lote.py</c>, conferida contra o
/// Python de verdade em <c>Cat.Compatibilidade.Testes</c>. Um tipo novo no motor
/// sem entrada aqui aparece como "Não reconhecido" em vez de sumir.
/// </summary>
public static class TiposDeArquivo
{
    public static readonly IReadOnlyList<TipoDeArquivo> Todos =
    [
        Novo("sped_icms_ipi", "EFD ICMS/IPI", Icms, PisCofins),
        Novo("sped_contribuicoes", "EFD Contribuições", PisCofins),
        Novo("sped_ecd", "ECD", PisCofins, IrpjCsll),
        Novo("sped_ecf", "ECF", IrpjCsll),
        Novo("sped_outro", "SPED de outro tipo"),
        Novo("xml_nfe", "XML de NF-e ou CF-e", Icms, PisCofins),
        Novo("xml_outro", "XML de outro documento"),
        Novo("xml_cancelamento", "Evento de cancelamento de NF-e", Icms),
        Novo("xml_compactado", "Zip de XML", Icms, PisCofins),
        Novo("gerencial_movimento", "Relatório de movimento", Icms),
        Novo("gerencial_inventario", "Relatório de inventário", Icms),
        Novo("gerencial_resumo", "Resumo por produto"),
        Novo("cat42_arquivo_digital", "Arquivo digital da CAT 42"),
        Novo("lista_de_canceladas", "Lista de notas canceladas", Icms),
        Novo("compactado", "Compactado"),
        Novo("nao_baixado", "Não baixado do OneDrive"),
        Novo("desconhecido", "Não reconhecido"),
    ];

    public static TipoDeArquivo Buscar(string valor) =>
        Todos.FirstOrDefault(t => t.Valor == valor) ?? Todos.Single(t => t.Valor == "desconhecido");

    private const string Icms = Segmentos.Icms;
    private const string PisCofins = Segmentos.PisCofins;
    private const string IrpjCsll = Segmentos.IrpjCsll;

    /// <summary>
    /// Útil é sempre em relação ao trabalho, nunca no absoluto. A EFD Contribuições
    /// e a ECD entram na mesma pasta o tempo todo e não servem à CAT 42 — PIS/COFINS
    /// e contabilidade não têm ICMS-ST —, mas são os arquivos dos trabalhos delas.
    /// A EFD ICMS/IPI serve a dois: é a base da CAT 42 e é dela que sai a exclusão
    /// do ICMS da base do PIS/COFINS.
    ///
    /// O mesmo mapa está em <c>dominio/lote.py</c>, conferido lado a lado em
    /// <c>Cat.Compatibilidade.Testes</c>.
    /// </summary>
    private static TipoDeArquivo Novo(string valor, string rotulo, params string[] modulos) =>
        new(valor, rotulo, Grupo(valor), modulos.Contains(Icms), modulos);

    private static string Grupo(string valor) =>
        valor.StartsWith("sped", StringComparison.Ordinal) ? "sped"
        : valor.StartsWith("xml", StringComparison.Ordinal) ? "xml"
        : valor.StartsWith("gerencial", StringComparison.Ordinal) ? "gerencial"
        : valor == "compactado" ? "compactado"
        : "outro";
}

namespace Cat.Dominio.Lote;

public sealed record TipoDeArquivo(string Valor, string Rotulo, string Grupo, bool AlimentaACat);

/// <summary>
/// O que cada tipo de arquivo é, para a tela: rótulo, grupo e se a CAT 42 o lê.
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
        Novo("sped_icms_ipi", "EFD ICMS/IPI", alimenta: true),
        Novo("sped_contribuicoes", "EFD Contribuições"),
        Novo("sped_ecd", "ECD"),
        Novo("sped_outro", "SPED de outro tipo"),
        Novo("xml_nfe", "XML de NF-e ou CF-e", alimenta: true),
        Novo("xml_outro", "XML de outro documento"),
        Novo("xml_cancelamento", "Evento de cancelamento de NF-e", alimenta: true),
        Novo("gerencial_movimento", "Relatório de movimento", alimenta: true),
        Novo("gerencial_inventario", "Relatório de inventário", alimenta: true),
        Novo("gerencial_resumo", "Resumo por produto"),
        Novo("cat42_arquivo_digital", "Arquivo digital da CAT 42"),
        Novo("lista_de_canceladas", "Lista de notas canceladas", alimenta: true),
        Novo("compactado", "Compactado"),
        Novo("nao_baixado", "Não baixado do OneDrive"),
        Novo("desconhecido", "Não reconhecido"),
    ];

    public static TipoDeArquivo Buscar(string valor) =>
        Todos.FirstOrDefault(t => t.Valor == valor) ?? Todos.Single(t => t.Valor == "desconhecido");

    /// <summary>
    /// A EFD Contribuições e a ECD entram na mesma pasta o tempo todo e não
    /// servem: PIS/COFINS e contabilidade não têm ICMS-ST. Aceitar sem distinguir
    /// faria o sistema dizer que a base está completa quando não está.
    /// </summary>
    private static TipoDeArquivo Novo(string valor, string rotulo, bool alimenta = false) =>
        new(valor, rotulo, Grupo(valor), alimenta);

    private static string Grupo(string valor) =>
        valor.StartsWith("sped", StringComparison.Ordinal) ? "sped"
        : valor.StartsWith("xml", StringComparison.Ordinal) ? "xml"
        : valor.StartsWith("gerencial", StringComparison.Ordinal) ? "gerencial"
        : valor == "compactado" ? "compactado"
        : "outro";
}

namespace Cat.Dominio.Projeto;

public enum SituacaoEtapa
{
    Concluida,
    EmAndamento,
    Pendente,
    /// <summary>Falta a etapa anterior.</summary>
    Bloqueada,
    /// <summary>Ainda não construída no sistema.</summary>
    NaoDisponivel,
}

public static class SituacoesDeEtapa
{
    /// <summary>O texto gravado e trocado com a tela, igual ao do Python.</summary>
    public static string Valor(this SituacaoEtapa s) => s switch
    {
        SituacaoEtapa.Concluida => "concluida",
        SituacaoEtapa.EmAndamento => "em_andamento",
        SituacaoEtapa.Pendente => "pendente",
        SituacaoEtapa.Bloqueada => "bloqueada",
        _ => "nao_disponivel",
    };

    public static string Rotulo(this SituacaoEtapa s) => s switch
    {
        SituacaoEtapa.Concluida => "Concluída",
        SituacaoEtapa.EmAndamento => "Em andamento",
        SituacaoEtapa.Pendente => "Pendente",
        SituacaoEtapa.Bloqueada => "Aguardando etapa anterior",
        _ => "Ainda não disponível",
    };
}

/// <param name="Implementada">
/// Falso enquanto a funcionalidade não existe. Mostrar a etapa mesmo assim é
/// deliberado: o usuário vê o caminho inteiro e sabe onde o trabalho está.
/// </param>
public sealed record DefinicaoEtapa(string Chave, string Nome, string Descricao, bool Implementada = false);

public sealed record EtapaDoProjeto(DefinicaoEtapa Definicao, SituacaoEtapa Situacao)
{
    /// <summary>Se vale a pena o usuário clicar.</summary>
    public bool Acessivel => Situacao is SituacaoEtapa.Concluida or SituacaoEtapa.EmAndamento or SituacaoEtapa.Pendente;
}

/// <summary>
/// As etapas do trabalho da CAT 42, na ordem em que existem, portadas de
/// <c>dominio/cat42/etapas.py</c>.
///
/// Conhecimento de domínio, não decoração de tela: a ordem vem do manual. Não
/// dá para montar o razão sem os movimentos, nem apurar ressarcimento sem o
/// razão, nem gerar o arquivo digital sem a apuração.
/// </summary>
public static class Etapas
{
    /// <summary>A ordem desta lista É a ordem do processo.</summary>
    public static readonly IReadOnlyList<DefinicaoEtapa> Todas =
    [
        new("importar", "Importar base de dados",
            "Apontar a pasta com a base do trabalho: EFD ICMS/IPI, XML das " +
            "notas e relatórios do ERP. O sistema identifica cada arquivo e " +
            "separa o que é de outra empresa. Pode voltar quantas vezes a " +
            "empresa mandar arquivo — o cadastro é que acontece uma vez só.",
            Implementada: true),
        new("conferencia", "Conferir documentos",
            "Cruzar o que a EFD escriturou (C100 e C800) com o XML e o " +
            "relatório do cliente. Sai daqui o que está na pasta e não foi " +
            "escriturado — que fica fora da análise — e o que foi escriturado " +
            "sem documento, que é o que se cobra do cliente.",
            Implementada: true),
        new("movimentos", "Extrair movimentos",
            "Ler os itens de cada documento (C170), o analítico (C190/C850), o " +
            "cadastro de item (0200) e o inventário (Bloco H), que dá o saldo " +
            "de abertura — cada movimento marcado pela conferência.",
            Implementada: true),
        new("st_suportado", "Apurar o ICMS suportado",
            "Determinar o imposto suportado de cada entrada. Quando o SPED e o " +
            "XML divergem, vale o XML — é o documento fiscal."),
        new("razao", "Montar o razão dos itens",
            "A Ficha 3: uma ficha por mercadoria, custo médio ponderado móvel, " +
            "entradas e devoluções antes das saídas no mesmo dia."),
        new("apuracao", "Apurar ressarcimento e complemento",
            "Confrontar o imposto suportado com o ICMS efetivo, por " +
            "enquadramento legal, e conferir o saldo final contra o inventário."),
        new("arquivo_digital", "Gerar o arquivo digital",
            "Montar os registros 0000 a 1200 no leiaute da CAT 42 e passar pela " +
            "pré-validação antes do envio à SEFAZ."),
        new("entrega", "Relatórios e entrega",
            "Planilhas de conferência por filial e competência, e o dossiê que " +
            "acompanha o pedido."),
    ];

    /// <summary>
    /// Monta o roteiro a partir do que já foi feito. Uma etapa fica bloqueada
    /// enquanto a anterior não concluiu, porque a ordem é de dependência real.
    /// </summary>
    public static IReadOnlyList<EtapaDoProjeto> Montar(IReadOnlySet<string> concluidas, string? emAndamento = null)
    {
        var saida = new List<EtapaDoProjeto>();
        var anteriorOk = true;
        foreach (var d in Todas)
        {
            var situacao =
                !d.Implementada ? SituacaoEtapa.NaoDisponivel
                : concluidas.Contains(d.Chave) ? SituacaoEtapa.Concluida
                : d.Chave == emAndamento ? SituacaoEtapa.EmAndamento
                : anteriorOk ? SituacaoEtapa.Pendente
                : SituacaoEtapa.Bloqueada;
            saida.Add(new EtapaDoProjeto(d, situacao));
            anteriorOk = anteriorOk && situacao == SituacaoEtapa.Concluida;
        }
        return saida;
    }

    /// <summary>
    /// Quantas concluídas de quantas já existem no sistema. O denominador
    /// ignora o que ainda não foi construído: "1 de 7" quando só três existem
    /// passaria a impressão errada de atraso.
    /// </summary>
    public static (int Feitas, int Totais) Progresso(IReadOnlyList<EtapaDoProjeto> etapas)
    {
        var disponiveis = etapas.Where(e => e.Definicao.Implementada).ToList();
        return (disponiveis.Count(e => e.Situacao == SituacaoEtapa.Concluida), disponiveis.Count);
    }
}

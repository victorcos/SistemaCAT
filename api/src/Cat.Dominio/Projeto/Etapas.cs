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
/// O catálogo de etapas e o roteiro de cada módulo tributário.
///
/// Conhecimento de domínio, não decoração de tela: a ordem vem do manual. Não
/// dá para montar o razão sem os movimentos, nem apurar ressarcimento sem o
/// razão, nem gerar o arquivo digital sem a apuração.
///
/// **Catálogo e roteiro são coisas diferentes** (22/09/2026, quando o sistema
/// passou a ter um módulo por tributo). <see cref="Todas"/> é tudo que existe;
/// <see cref="Roteiros"/> diz quais etapas cada módulo percorre e em que ordem.
/// Antes havia uma lista só, e ela era a da CAT 42 — um trabalho de PIS/COFINS
/// herdaria sete etapas de ICMS que nunca rodariam, e o cartão diria "0 de 7"
/// para sempre.
///
/// **Por que em código e não em tabela.** Uma etapa só existe se houver código
/// que a rode: o roteiro numa tabela permitiria apontar para uma etapa que
/// ninguém escreveu, e o erro só apareceria quando alguém clicasse. Aqui o
/// compilador cobra, e o teste abaixo cobra o resto.
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
            "Determinar o imposto suportado de cada entrada pela cascata de " +
            "quatro fontes — destacado na nota, informado pelo fornecedor, " +
            "reconstruído por base e alíquota, ou não apurável — e marcar de " +
            "onde veio cada valor. Quando o ERP e o XML divergem, vale o XML.",
            Implementada: true),
        new("razao", "Montar o razão dos itens",
            "A Ficha 3: uma ficha por estabelecimento e mercadoria com ST, custo " +
            "médio ponderado móvel, entradas e devoluções antes das saídas no mesmo " +
            "dia. As saídas sem item na EFD vêm do relatório do cliente.",
            Implementada: true),
        new("apuracao", "Apurar ressarcimento e complemento",
            "Fechar o período por estabelecimento e mês: ressarcimento a pedir e " +
            "complemento a recolher, separados, com os saldos de cada mercadoria e " +
            "a conferência contra o inventário. Só a competência sem pendência " +
            "segue para o arquivo digital.",
            Implementada: true),
        new("arquivo_digital", "Gerar o arquivo digital",
            "Um arquivo por estabelecimento de SP e por mês, com os registros 0000 a " +
            "1200 no leiaute da CAT 42, e a pré-validação que recompõe a Ficha 3 a " +
            "partir do próprio arquivo. Só a competência apta e sem erro vai para o " +
            "envio; as outras saem como prévia.",
            Implementada: true),
        new("entrega", "Relatórios e entrega",
            "O relatório executivo com todas as competências — prontas ou não, com o " +
            "que falta —, o dossiê de cada estabelecimento com o que vai à SEFAZ e o " +
            "manifesto com o SHA-256 de cada arquivo. Conclui quando um revisor ou " +
            "gestor aprova.",
            Implementada: true),

        // ---- PIS/COFINS: declaradas, ainda não construídas ----
        new("quebra_de_sped", "Quebra de SPED",
            "Indexar a EFD-Contribuições numa passada — contagem por registro e " +
            "posição em bytes de cada um — e extrair qualquer bloco sob demanda, sem " +
            "reler o arquivo. É o que permite consolidar C170, C190, M210 e os demais " +
            "de uma base de dezenas de milhões de linhas com memória constante. Dela saem a " +
            "Consulta de Entradas (037) e o razão contábil da ECD — o par que se confronta.",
            Implementada: true),
        new("apuracao_contribuicoes", "Apurar PIS/COFINS",
            "Os quadros da apuração por competência: receitas e bases por CST, CFOP e " +
            "natureza, ajustes, e o controle de créditos. Inclui a exclusão do ICMS da " +
            "base, que cruza a EFD-Contribuições com a EFD ICMS/IPI pelo documento e " +
            "pelo item.",
            Implementada: false),
    ];

    /// <summary>
    /// Qual módulo percorre quais etapas, na ordem. A chave é a do módulo em
    /// <see cref="Acesso.Segmentos"/>; o valor, chaves de <see cref="Todas"/>.
    ///
    /// Acrescentar funcionalidade é acrescentar a etapa ao catálogo e a chave
    /// dela aqui — nada mais. Etapa declarada e ainda não construída aparece
    /// como "ainda não disponível", que é deliberado: o usuário vê o caminho
    /// inteiro e sabe onde o trabalho está.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, IReadOnlyList<string>> Roteiros =
        new Dictionary<string, IReadOnlyList<string>>
        {
            ["icms"] = ["importar", "conferencia", "movimentos", "st_suportado", "razao",
                        "apuracao", "arquivo_digital", "entrega"],
            // o que vem do porte do Quebra de SPED e da Gestão padrão MA
            ["piscofins"] = ["importar", "quebra_de_sped", "apuracao_contribuicoes"],
            ["irpj_csll"] = ["importar"],
        };

    /// <summary>
    /// O roteiro do módulo. Módulo desconhecido cai no de ICMS, que é o de todo
    /// trabalho anterior a esta divisão — errar para o lado do que já funciona.
    /// </summary>
    public static IReadOnlyList<DefinicaoEtapa> Do(string? modulo)
    {
        var chaves = Roteiros.TryGetValue(modulo ?? "", out var r) ? r : Roteiros["icms"];
        return chaves.Select(c => Todas.First(d => d.Chave == c)).ToList();
    }

    /// <summary>
    /// As etapas que concluem com uma rodada do motor, de todos os módulos. É o
    /// filtro da consulta que lê a última situação de cada uma: ela não sabe de
    /// qual módulo é o trabalho, e listar demais não faz mal — listar de menos
    /// deixaria a etapa para sempre "pendente".
    /// </summary>
    public static readonly IReadOnlyList<string> DeProcessamento =
        Roteiros.Values.SelectMany(r => r).Distinct().Where(c => c != "importar").ToList();

    /// <summary>
    /// Monta o roteiro do módulo a partir do que já foi feito. Uma etapa fica
    /// bloqueada enquanto a anterior não concluiu: a ordem é de dependência real.
    /// </summary>
    public static IReadOnlyList<EtapaDoProjeto> Montar(string? modulo, IReadOnlySet<string> concluidas,
        string? emAndamento = null)
    {
        var saida = new List<EtapaDoProjeto>();
        var anteriorOk = true;
        foreach (var d in Do(modulo))
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

namespace Cat.Dominio.Projeto;

public enum SituacaoEtapa
{
    Concluida,
    EmAndamento,
    Pendente,
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
        _ => "nao_disponivel",
    };

    public static string Rotulo(this SituacaoEtapa s) => s switch
    {
        SituacaoEtapa.Concluida => "Concluída",
        SituacaoEtapa.EmAndamento => "Em andamento",
        SituacaoEtapa.Pendente => "Pendente",
        _ => "Ainda não disponível",
    };
}

/// <param name="Implementada">
/// Falso enquanto a funcionalidade não existe. Mostrar a funcionalidade mesmo
/// assim é deliberado: o usuário vê o caminho inteiro e sabe onde o trabalho
/// está.
/// </param>
/// <param name="Aba">
/// O rótulo curto da barra do trabalho. Uma ou duas palavras: "Arquivos",
/// "Quebras", "Apuração". O <paramref name="Nome"/> continua sendo a frase
/// inteira, que a tela usa no cabeçalho e no cartão. Vazio cai no Nome.
/// </param>
/// <param name="Conta">
/// Se entra no progresso do trabalho. Falso para a funcionalidade que **nunca
/// conclui** — o histórico é consulta, não tarefa. Sem isto o cartão diria
/// "3 de 6" para sempre, e a barra jamais chegaria ao fim com tudo pronto.
/// </param>
public sealed record DefinicaoEtapa(string Chave, string Nome, string Descricao,
    bool Implementada = false, string Aba = "", bool Conta = true)
{
    public string Rotulo => string.IsNullOrWhiteSpace(Aba) ? Nome : Aba;
}

public sealed record EtapaDoProjeto(DefinicaoEtapa Definicao, SituacaoEtapa Situacao)
{
    /// <summary>
    /// Se vale a pena o usuário clicar.
    ///
    /// Só o que não existe fica de fora. Falta de base **não** barra mais: a
    /// pessoa entra na funcionalidade e a tela diz o que falta, em vez de uma
    /// aba apagada que não explica nada.
    /// </summary>
    public bool Acessivel => Situacao is not SituacaoEtapa.NaoDisponivel;
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
            Implementada: true, Aba: "Arquivos"),
        new("conferencia", "Conferir documentos",
            "Cruzar o que a EFD escriturou (C100 e C800) com o XML e o " +
            "relatório do cliente. Sai daqui o que está na pasta e não foi " +
            "escriturado — que fica fora da análise — e o que foi escriturado " +
            "sem documento, que é o que se cobra do cliente.",
            Implementada: true, Aba: "Conferência"),
        new("movimentos", "Extrair movimentos",
            "Ler os itens de cada documento (C170), o analítico (C190/C850), o " +
            "cadastro de item (0200) e o inventário (Bloco H), que dá o saldo " +
            "de abertura — cada movimento marcado pela conferência.",
            Implementada: true, Aba: "Movimentos"),
        new("st_suportado", "Apurar o ICMS suportado",
            "Determinar o imposto suportado de cada entrada pela cascata de " +
            "quatro fontes — destacado na nota, informado pelo fornecedor, " +
            "reconstruído por base e alíquota, ou não apurável — e marcar de " +
            "onde veio cada valor. Quando o ERP e o XML divergem, vale o XML.",
            Implementada: true, Aba: "Suportado"),
        new("razao", "Montar o razão dos itens",
            "A Ficha 3: uma ficha por estabelecimento e mercadoria com ST, custo " +
            "médio ponderado móvel, entradas e devoluções antes das saídas no mesmo " +
            "dia. As saídas sem item na EFD vêm do relatório do cliente.",
            Implementada: true, Aba: "Razão"),
        new("apuracao", "Apurar ressarcimento e complemento",
            "Fechar o período por estabelecimento e mês: ressarcimento a pedir e " +
            "complemento a recolher, separados, com os saldos de cada mercadoria e " +
            "a conferência contra o inventário. Só a competência sem pendência " +
            "segue para o arquivo digital.",
            Implementada: true, Aba: "Apuração"),
        new("arquivo_digital", "Gerar o arquivo digital",
            "Um arquivo por estabelecimento de SP e por mês, com os registros 0000 a " +
            "1200 no leiaute da CAT 42, e a pré-validação que recompõe a Ficha 3 a " +
            "partir do próprio arquivo. Só a competência apta e sem erro vai para o " +
            "envio; as outras saem como prévia.",
            Implementada: true, Aba: "Arquivo digital"),
        new("entrega", "Relatórios e entrega",
            "O relatório executivo com todas as competências — prontas ou não, com o " +
            "que falta —, o dossiê de cada estabelecimento com o que vai à SEFAZ e o " +
            "manifesto com o SHA-256 de cada arquivo. Conclui quando um revisor ou " +
            "gestor aprova.",
            Implementada: true, Aba: "Entrega"),
        new("credito_outorgado", "Crédito outorgado",
            "Varre os XML de saída e separa, item a item, o que é produto " +
            "beneficiado pelo crédito outorgado. A **descrição manda** e a NCM " +
            "confirma: bater só a NCM não basta, porque a NCM é declarada pelo " +
            "emitente e erra, enquanto a descrição é o produto que o dono do " +
            "negócio reconhece. Não depende das etapas acima — lê os XML do " +
            "lote direto.",
            Implementada: true, Aba: "Outorgado"),

        // ---- PIS/COFINS ----
        new("quebra_de_sped", "Quebrar os SPED",
            "Abrir os arquivos: quantos de cada registro cada SPED tem, e o índice " +
            "com a posição em bytes de cada um — que é o que permite extrair " +
            "qualquer registro depois sem reler o arquivo. Numa base de dezenas de " +
            "milhões de linhas, é a diferença entre olhar um C170 em segundos e em " +
            "minutos.",
            Implementada: true, Aba: "Quebras"),
        new("apuracao_piscofins", "Apurar PIS/COFINS",
            "Monta as duas consultas do lado fiscal — a de Entradas (037) e a de " +
            "Saídas (047), item a item — e o razão da ECD, do lado contábil. A 047 " +
            "abre em tela própria, com filtro por competência, estabelecimento, CFOP " +
            "e CST, e o download sai do tamanho do filtro. O cruzamento com a " +
            "contabilidade é seu: casar partida contábil com item de nota exige " +
            "critério que muda de cliente para cliente, e um casamento automático " +
            "erraria calado. Marque as contas no razão, extraia, e compare.",
            Implementada: true, Aba: "Apuração"),
        new("apuracao_contribuicoes", "Gestão Fiscal",
            "Os quadros no padrão do MA: da EFD-Contribuições saem PIS e COFINS, nos " +
            "36 quadros; da ECF saem IRPJ e CSLL do Lucro Real. Receitas e bases por " +
            "CST, natureza dos créditos, ajustes e controle de saldos, competência a " +
            "competência.",
            Implementada: true, Aba: "Gestão"),
        new("exclusoes", "Exclusões da base",
            "O que sai da base de cálculo do PIS/COFINS antes de apurar. A " +
            "primeira tese são as próprias contribuições: a receita embute PIS e " +
            "COFINS, e a base de cada uma perde as duas. Sai grupo a grupo — " +
            "registro, CST e CFOP na competência —, e o cruzamento com a 037 " +
            "continua sendo do analista. Falta a do ICMS destacado (Tema 69, RE " +
            "574.706), que precisa da EFD ICMS/IPI do mesmo CNPJ e competência: o " +
            "campo do ICMS no C170 das Contribuições é facultativo, e metade dos " +
            "clientes o manda em branco.",
            Implementada: true, Aba: "Exclusões"),
        new("combustivel", "Crédito de ICMS sobre combustível",
            "O crédito de quem queima combustível como insumo. Lê a EFD ICMS/IPI do " +
            "lote, acha as compras, classifica cada item pela NCM e pela descrição, e " +
            "apura: no regime monofásico é litro × ad rem × fator de correção do " +
            "volume; na era da substituição tributária é base × alíquota interna do " +
            "estado, e sai marcado como estimativa, porque o arquivo do destinatário " +
            "não traz a base do ST. O que a tabela não cobre aparece na linha com o " +
            "motivo, fora do total — nunca como zero. Também confronta com o que o " +
            "cliente já creditou por ajuste no E111: o produto é auditar o crédito " +
            "tomado, não só achar crédito novo.",
            Implementada: false, Aba: "Combustível"),
        new("historico", "Histórico do trabalho",
            "Tudo o que aconteceu, em ordem: quem importou, quem rodou cada " +
            "etapa, o que cada rodada produziu, quem mudou o status e por quê. " +
            "É a resposta para \"por que este número é este\" três meses depois — " +
            "e é consulta, não tarefa: não entra no progresso.",
            Implementada: true, Aba: "Histórico", Conta: false),
        new("quebra_xml", "Quebrar os XML",
            "Abrir os XML das notas do lote item a item — NF-e, NFC-e e CF-e SAT, " +
            "soltos ou em zip. A planilha sai com as colunas que você escolher: " +
            "identificação, produto, descontos, ICMS, ST, PIS/COFINS, IPI e ISSQN. " +
            "É o item que a EFD não traz na saída própria, e o CST que o C170 " +
            "consolidado esconde.",
            Implementada: true, Aba: "Quebra XML"),
    ];

    /// <summary>
    /// Uma frente de trabalho dentro do módulo: a CAT 42, a CAT 207, o crédito
    /// outorgado, a quebra de XML. É o que se contrata e o que se entrega — e,
    /// na tela, é o card que se abre para ver as etapas dele.
    ///
    /// **Chama-se trilha, e não frente**, porque `frente` já é a coluna do
    /// projeto (<see cref="Frentes"/>), que classifica o trabalho inteiro: um
    /// trabalho de frente "cat42" percorre hoje a CAT 42 **e** o crédito
    /// outorgado. Dois nomes para conceitos diferentes valem mais que um nome
    /// para dois.
    ///
    /// **Importar é trilha própria, e não o começo das outras.** Até
    /// 30/09/2026 `importar` era a primeira etapa de cada trilha, e a base é
    /// mesmo a mesma para todas — quem importou para a CAT 42 já importou para
    /// o crédito outorgado. Só que isso obrigava a entrar numa frente de
    /// trabalho para subir arquivo: quem só queria mandar a base do cliente
    /// tinha de atravessar a Quebra de SPED, que não tem nada com isso. Pedido
    /// do Victor em 30/09/2026, e ele tem razão — subir arquivo não é uma etapa
    /// da quebra, é o que vem antes de todas.
    ///
    /// Agora ela é o **primeiro card de todo módulo**, com uma etapa só, e
    /// nenhuma outra trilha a lista. A dependência não se perdeu: continua
    /// cobrada por quem pode cobrá-la — o servidor, que recusa a etapa sem
    /// lote e diz o que falta — e o roteiro segue começando por ela.
    /// </summary>
    /// <param name="Sigla">o quadrado do card, como no hub: "C42", "OUT".</param>
    public sealed record Trilha(string Chave, string Rotulo, string Sigla, string Descricao,
        IReadOnlyList<string> Etapas);

    /// <summary>
    /// As frentes de trabalho de cada módulo, na ordem em que aparecem.
    ///
    /// **É daqui que sai o roteiro**, e não o contrário: assim nenhuma etapa
    /// fica sem card na tela, e acrescentar uma frente nova (CAT 207, quebra de
    /// XML) é acrescentar uma linha aqui com as chaves dela.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, IReadOnlyList<Trilha>> TrilhasPorModulo =
        new Dictionary<string, IReadOnlyList<Trilha>>
        {
            ["icms"] =
            [
                new("importar", "Importar arquivos", "BASE",
                    "Apontar a pasta com a base do trabalho e registrar o lote. É o que vem "
                    + "antes de todas as frentes, e por isso tem card próprio: subir arquivo "
                    + "não é etapa de nenhuma delas. Pode voltar quantas vezes a empresa "
                    + "mandar arquivo.",
                    ["importar"]),
                new("cat42", "CAT 42", "C42",
                    "Ressarcimento e complemento de ICMS-ST: da conferência dos documentos " +
                    "ao arquivo digital no leiaute da CAT 42 e à entrega. A ordem aqui é de " +
                    "dependência real — sem movimentos não há razão.",
                    ["conferencia", "movimentos", "st_suportado", "razao",
                     "apuracao", "arquivo_digital", "entrega"]),
                new("credito_outorgado", "Crédito outorgado", "OUT",
                    "Quais itens vendidos são produto beneficiado, pela descrição e pela NCM. " +
                    "Lê os XML do lote direto: não depende da CAT 42 nem de etapa nenhuma dela.",
                    ["credito_outorgado"]),
                new("quebra_xml", "Quebra de XML", "XML",
                    "Abrir os XML do lote item a item e levar para planilha as colunas que " +
                    "interessam. No ICMS é o item que a EFD não traz: NF-e de emissão própria " +
                    "e NFC-e vão à escrituração só com o analítico.",
                    ["quebra_xml"]),
                // Uma etapa só, por enquanto. A fila de revisão do classificador
                // — o revisor confirmando o que cada descrição é — será a
                // segunda, quando existir: hoje o classificador marca a linha
                // para revisão e quem revisa olha a planilha.
                new("combustivel", "Crédito de combustível", "CMB",
                    "Quanto de ICMS o cliente pode recuperar do combustível que queimou como " +
                    "insumo, e quanto ele já recuperou por conta própria. Lê a EFD ICMS/IPI " +
                    "direto: não depende da CAT 42 nem de etapa nenhuma dela.",
                    ["combustivel"]),
            ],
            // Cinco frentes, e não uma só com cinco etapas dentro. Até 28/09/2026
            // a quebra, a 037, as exclusões e a Gestão moravam num card chamado
            // "Apuração de PIS/COFINS" — e isso desfazia justamente a separação
            // que o Victor tinha pedido em 23/09: quebrar um SPED para olhar um
            // C170 não é apurar contribuição, e quem entra para quebrar não quer
            // atravessar a apuração para chegar lá.
            ["piscofins"] =
            [
                new("importar", "Importar arquivos", "BASE",
                    "Apontar a pasta com a base do trabalho e registrar o lote. É o que vem "
                    + "antes de todas as frentes, e por isso tem card próprio: subir arquivo "
                    + "não é etapa de nenhuma delas. Pode voltar quantas vezes a empresa "
                    + "mandar arquivo.",
                    ["importar"]),
                new("quebra_de_sped", "Quebra de SPED", "SPED",
                    "Abrir os SPED do lote: o que há dentro de cada arquivo, e a extração de " +
                    "qualquer registro ou hierarquia — o C170 com a nota que o contém, o M210 " +
                    "com o M200 — filtrando pelo bloco do leiaute.",
                    ["quebra_de_sped"]),
                new("piscofins", "Apuração de PIS/COFINS", "037",
                    "As duas pontas do fiscal — a Consulta de Entradas (037) e a de Saídas " +
                    "(047), item a item — e o razão da ECD, do lado contábil. A 047 abre em " +
                    "tela própria, com filtro por competência, CFOP e CST.",
                    ["apuracao_piscofins"]),
                new("exclusoes", "Exclusões da base", "EXC",
                    "O que sai da base de cálculo antes de apurar — a principal é o ICMS " +
                    "destacado, do Tema 69.",
                    ["exclusoes"]),
                new("apuracao_contribuicoes", "Gestão Fiscal", "GES",
                    "Os 36 quadros no padrão do MA: receitas e bases por CST, natureza dos " +
                    "créditos, ajustes e controle de saldos, competência a competência.",
                    ["apuracao_contribuicoes"]),
                new("quebra_xml", "Quebra de XML", "XML",
                    "Abrir os XML das notas do lote item a item, como a quebra faz com o SPED.",
                    ["quebra_xml"]),
            ],
            // a base, e mais nada: nenhuma frente de apuração construída ainda.
            // O card de importar aparece mesmo assim, porque é o que este
            // módulo faz hoje — e antes a tela dizia só "nenhuma frente
            // construída", sem caminho nenhum para subir arquivo
            ["irpj_csll"] =
            [
                new("importar", "Importar arquivos", "BASE",
                    "Apontar a pasta com a base do trabalho e registrar o lote. É o que vem "
                    + "antes de todas as frentes, e por isso tem card próprio: subir arquivo "
                    + "não é etapa de nenhuma delas. Pode voltar quantas vezes a empresa "
                    + "mandar arquivo.",
                    ["importar"]),
            ],
        };

    /// <summary>As frentes do módulo. Módulo desconhecido cai no de ICMS.</summary>
    public static IReadOnlyList<Trilha> TrilhasDo(string? modulo) =>
        TrilhasPorModulo.TryGetValue(modulo ?? "", out var t) ? t : TrilhasPorModulo["icms"];

    /// <summary>
    /// Qual módulo percorre quais etapas, na ordem. A chave é a do módulo em
    /// <see cref="Acesso.Segmentos"/>; o valor, chaves de <see cref="Todas"/>.
    ///
    /// **Derivado das trilhas**, e não escrito à mão: duas listas para a mesma
    /// verdade divergiriam no dia em que alguém mexesse numa, e o preço seria
    /// uma etapa que existe no roteiro e não aparece em card nenhum.
    ///
    /// `importar` abre todo roteiro e `historico` fecha todos: os dois são de
    /// qualquer trabalho, e não de uma frente. Etapa declarada e ainda não
    /// construída aparece como "ainda não disponível", que é deliberado: o
    /// usuário vê o caminho inteiro e sabe onde o trabalho está.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, IReadOnlyList<string>> Roteiros =
        TrilhasPorModulo.ToDictionary(
            p => p.Key,
            p => (IReadOnlyList<string>)
            [
                "importar",
                .. p.Value.SelectMany(t => t.Etapas).Where(c => c != "importar").Distinct(),
                "historico",
            ]);

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
        string? emAndamento = null) => Montar(Do(modulo), concluidas, emAndamento);

    /// <summary>
    /// O mesmo, sobre um roteiro dado em vez do roteiro de um módulo.
    ///
    /// Existe para que a regra da etapa **declarada e ainda não construída**
    /// continue testável. Ela vale desde sempre, mas só tinha como ser exercida
    /// enquanto houvesse alguma etapa por fazer — e em 23/09/2026 a última
    /// ficou pronta. Amarrar um teste de regra à existência de trabalho
    /// pendente é perdê-lo no dia em que o trabalho acaba.
    /// </summary>
    public static IReadOnlyList<EtapaDoProjeto> Montar(IEnumerable<DefinicaoEtapa> roteiro,
        IReadOnlySet<string> concluidas, string? emAndamento = null)
    {
        var saida = new List<EtapaDoProjeto>();
        foreach (var d in roteiro)
        {
            // nada trava mais: a funcionalidade abre e, faltando base, a tela
            // diz o que falta. A dependência real continua no servidor, que
            // recusa com a frase certa — e uma frase explica; uma aba apagada,
            // não. Ver DECISOES de 23/09/2026.
            var situacao =
                !d.Implementada ? SituacaoEtapa.NaoDisponivel
                : concluidas.Contains(d.Chave) ? SituacaoEtapa.Concluida
                : d.Chave == emAndamento ? SituacaoEtapa.EmAndamento
                : SituacaoEtapa.Pendente;
            saida.Add(new EtapaDoProjeto(d, situacao));
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
        var disponiveis = etapas.Where(e => e.Definicao.Implementada && e.Definicao.Conta).ToList();
        return (disponiveis.Count(e => e.Situacao == SituacaoEtapa.Concluida), disponiveis.Count);
    }
}

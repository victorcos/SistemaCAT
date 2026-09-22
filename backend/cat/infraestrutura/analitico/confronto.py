"""O confronto propriamente dito, em DuckDB.

Três listas saem daqui — pendentes, não escrituradas e conferidas —, e vão
para parquet em vez de para o banco: numa base desta casa a EFD tem centenas
de milhões de documentos, e qualquer uma delas pode ser milhões de linhas. O que vai para o Postgres é o resumo — números que a tela
mostra e que ficam registrados na execução.

**Nada sai da lista.** Documento cancelado, denegado, com numeração inutilizada
ou sem chave de acesso continua na pendência, marcado com o que é. A primeira
versão os excluía por serem improváveis de cobrar, e isso estava errado pelo
motivo que só aparece quando se pensa no ciclo inteiro: o trabalho não termina
na primeira rodada. O cliente manda o que faltava, a conferência roda de novo,
e o que tiver sido excluído nunca mais é olhado — some do controle sem ter sido
resolvido. Marcar é reversível; excluir não é.

O casamento é pela chave de acesso. Uma nota pode aparecer mais de uma vez na
EFD legitimamente: emitida por um estabelecimento e recebida por outro do mesmo
grupo são dois C100 da mesma chave. Por isso a lista é agrupada por chave —
pedir duas vezes o mesmo XML ao cliente é ruído. Documento sem chave não tem
como ser confrontado, então cada um vale por si e é rotulado `sem_chave`: não é
pendência resolvida nem por resolver, é pendência de conferência manual.
"""

from __future__ import annotations

import os
import shutil
from decimal import Decimal

import duckdb

from cat.config import obter_config

from cat.dominio.icms.cat42.conferencia import Fatia, Origem, ResumoDaConferencia
from cat.log import obter_log

log = obter_log(__name__)

ZERO = Decimal("0")

# Tabela 4.1.2: regular, extemporâneo e complementar. O resto é cancelado,
# denegado ou numeração inutilizada — a lista traz todos, e esta tupla só diz
# de quais se espera que exista documento a pedir.
SITUACOES_COM_DOCUMENTO = ("00", "01", "06", "07", "08")

ARQUIVO_NAO_ESCRITURADAS = "nao_escrituradas.parquet"
ARQUIVO_SEM_DOCUMENTO = "sem_documento.parquet"
ARQUIVO_CONFERIDOS = "conferidos.parquet"
BANCO_DO_CONFRONTO = "confronto.duckdb"

# quanto de disco não se toca. Encher a unidade de rascunho derruba o
# sistema operacional junto, não só esta execução.
FOLGA_DE_DISCO = 2 * 1000**3


def confrontar(efd: str, pasta: str, destino: str,
               anterior: str | None = None) -> ResumoDaConferencia:
    """Compara os dois parquets e grava as três listas.

    `anterior` é o `sem_documento.parquet` da rodada passada. Com ele, o resumo
    diz o que andou desde então: quantas pendências o cliente resolveu, quantas
    continuam e quantas apareceram. É o que dá sentido a rodar de novo.
    """
    os.makedirs(destino, exist_ok=True)
    nao_escrituradas = os.path.join(destino, ARQUIVO_NAO_ESCRITURADAS)
    sem_documento = os.path.join(destino, ARQUIVO_SEM_DOCUMENTO)
    conferidos = os.path.join(destino, ARQUIVO_CONFERIDOS)
    esperado = str(SITUACOES_COM_DOCUMENTO)

    con = _abrir(destino)
    try:
        # DuckDB não aceita parâmetro preparado em CREATE VIEW; o caminho entra
        # no texto, com as aspas simples dobradas
        con.execute("CREATE VIEW efd_bruta AS SELECT * FROM read_parquet("
                    f"'{_escapar(efd)}')")
        con.execute("CREATE VIEW pasta AS SELECT * FROM read_parquet("
                    f"'{_escapar(pasta)}') WHERE length(chave) = 44")
        con.execute("CREATE TABLE entregues AS "
                    "SELECT DISTINCT chave FROM pasta")

        # o agrupador é a chave quando ela existe; quando não existe, cada
        # documento vale por si, identificado pelo que a EFD tem dele
        con.execute("""
            CREATE VIEW efd AS
            SELECT *,
                   length(chave) = 44 AS tem_chave,
                   CASE WHEN length(chave) = 44 THEN chave
                        ELSE 'sem-chave:' || coalesce(cnpj, '') || ':'
                             || coalesce(modelo, '') || ':'
                             || coalesce(serie, '') || ':'
                             || coalesce(numero, '') || ':'
                             || coalesce(CAST(data AS VARCHAR), '')
                   END AS agrupador
            FROM efd_bruta
        """)

        # Tira PRIMEIRO o que já tem documento, agrupa só o que sobrou.
        #
        # Na ordem inversa — agrupar tudo e depois filtrar — o agrupamento
        # carrega a base inteira: numa empresa de 37,9 milhões de documentos
        # isso estourou 5,5 GB de memória e derrubou a execução depois de nove
        # minutos. E é trabalho jogado fora, porque numa base saudável a maior
        # parte dos documentos TEM o XML e sai do caminho aqui.
        # Pendente = não está entre os entregues. ANTI JOIN explícito, com a
        # tabela pequena (entregues) do lado da construção da dispersão.
        con.execute("""
            CREATE VIEW pendentes_cru AS
            SELECT e.* FROM efd e ANTI JOIN entregues p ON e.chave = p.chave
        """)

        partes = _uma_linha_por_chave(con, "pendentes_cru", destino, "pendentes")

        # junta, classifica e ordena — a partir dos dois parquets prontos, que
        # é uma varredura, não uma materialização
        con.execute(f"""
            COPY (
                SELECT *,
                       tem_chave AND situacao IN {esperado} AS espera_documento,
                       CASE
                         WHEN NOT tem_chave THEN 'sem_chave'
                         WHEN situacao NOT IN {esperado} THEN 'sem_documento_a_pedir'
                         ELSE 'a_cobrar'
                       END AS classificacao
                FROM read_parquet({_lista_sql(partes)})
                ORDER BY classificacao, cnpj, competencia
            ) TO '{_escapar(sem_documento)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        _apagar(partes)

        # ---- na EFD e com documento: o resultado positivo ----
        # "Possui nota e está na EFD — onde vejo?" precisa de lista, não só
        # de número: é o que segue para a apuração. Mesma forma da lista de
        # pendências (uma linha por chave, ocorrências contadas) mais de onde
        # veio o documento. Sem ORDER BY de propósito: numa base saudável
        # este é o lado GRANDE, e ordenar 37 milhões de linhas custou 6,4
        # min na lista de pendências — lá a classificação justifica, aqui não.
        con.execute("""
            CREATE VIEW conferidos_cru AS
            SELECT e.* FROM efd e SEMI JOIN entregues p ON e.chave = p.chave
        """)
        partes = _uma_linha_por_chave(con, "conferidos_cru", destino, "conferidos")
        # de qual arquivo veio o documento de cada chave. A pasta é o lado
        # pequeno; agrupar aqui é barato
        con.execute("""
            CREATE TABLE documentos AS
            SELECT chave, min(origem) AS origem, min(arquivo) AS arquivo
            FROM pasta GROUP BY chave
        """)
        con.execute(f"""
            COPY (
                SELECT c.*, d.origem, d.arquivo AS arquivo_do_documento
                FROM read_parquet({_lista_sql(partes)}) c
                JOIN documentos d ON d.chave = c.chave
            ) TO '{_escapar(conferidos)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        _apagar(partes)

        # ---- na pasta e fora da EFD: sai da análise ----
        con.execute(f"""
            COPY (
                SELECT p.chave, p.origem, p.arquivo
                FROM pasta p
                LEFT JOIN (SELECT DISTINCT chave FROM efd WHERE tem_chave) e
                       USING (chave)
                WHERE e.chave IS NULL
                ORDER BY p.chave
            ) TO '{_escapar(nao_escrituradas)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

        resumo = _resumir(con, nao_escrituradas, sem_documento, conferidos)
        if anterior and os.path.isfile(anterior):
            _comparar(con, anterior, sem_documento, resumo)
    finally:
        con.close()
        _limpar(destino)

    log.info(
        "confronto concluído",
        extra={"escriturados": resumo.escriturados,
               "conferidos": resumo.conferidos,
               "sem_documento": resumo.sem_documento,
               "espera_documento": resumo.sem_documento_cobravel,
               "sem_chave": resumo.sem_chave_na_efd,
               "nao_escrituradas": resumo.nao_escrituradas,
               "resolvidas": resumo.pendencias_resolvidas,
               "cobertura": round(resumo.cobertura, 4)},
    )
    return resumo


def _uma_linha_por_chave(con, fonte: str, destino: str,
                         rotulo: str) -> list[str]:
    """Reduz a view `fonte` a uma linha por agrupador, em dois parquets.

    Deduplicar SÓ o que se repete — e em COMANDOS SEPARADOS.

    Agrupar as dezesseis colunas do registro sobre dezenas de milhões de
    grupos não cabe em memória nem derramando: numa base de 37,9 milhões de
    documentos morreu em 3,7 GB. As chaves são quase todas únicas — o
    agrupamento fazia trabalho enorme para não juntar quase nada. Então os
    únicos atravessam em fluxo (ANTI JOIN com a tabela pequena dos
    repetidos) e só os repetidos passam pelo GROUP BY largo.

    E a forma importa tanto quanto a ideia. Uma primeira versão com os dois
    ramos numa UNION ALL e EXISTS correlacionados levou o DuckDB a
    materializar a fonte inteira (CTE de subplano comum, 26 GB de rascunho,
    sem terminar em 88 minutos). Cada ramo num COPY próprio relê 400 MB de
    parquet — segundos — em vez de materializar 38 milhões de linhas.
    Medido: as etapas em 1,5 min com 1,9 GB de rascunho.

    Devolve os dois caminhos; quem chama junta, acrescenta o que for seu e
    apaga com `_apagar`.
    """
    con.execute(f"""
        CREATE TABLE repetidos_{rotulo} AS
        SELECT agrupador FROM {fonte}
        GROUP BY agrupador HAVING count(*) > 1
    """)

    unicos = os.path.join(destino, f"_{rotulo}_unicos.parquet")
    repetidos = os.path.join(destino, f"_{rotulo}_repetidos.parquet")

    # os únicos atravessam sem agregar: uma passada, em fluxo
    con.execute(f"""
        COPY (
            SELECT p.agrupador, p.chave, p.tem_chave, p.modelo, p.situacao,
                   p.serie, p.numero, p.data, p.valor, p.participante,
                   p.operacao, p.emitente, p.cnpj, p.competencia,
                   p.arquivo AS arquivo_efd, 1::BIGINT AS ocorrencias
            FROM {fonte} p
            ANTI JOIN repetidos_{rotulo} r ON r.agrupador = p.agrupador
        ) TO '{_escapar(unicos)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    # só os repetidos — um conjunto pequeno — passam pelo GROUP BY largo
    con.execute(f"""
        COPY (
            SELECT agrupador,
                   any_value(chave)    AS chave,
                   bool_and(tem_chave) AS tem_chave,
                   min(modelo)         AS modelo,
                   min(situacao)       AS situacao,
                   any_value(serie)    AS serie,
                   any_value(numero)   AS numero,
                   min(data)           AS data,
                   max(valor)          AS valor,
                   any_value(participante) AS participante,
                   any_value(operacao)     AS operacao,
                   any_value(emitente)     AS emitente,
                   any_value(cnpj)         AS cnpj,
                   min(competencia)        AS competencia,
                   -- de qual arquivo saiu: é por onde se recomeça quando
                   -- alguém questiona uma linha meses depois
                   any_value(arquivo)      AS arquivo_efd,
                   count(*)                AS ocorrencias
            FROM {fonte} p
            SEMI JOIN repetidos_{rotulo} r ON r.agrupador = p.agrupador
            GROUP BY agrupador
        ) TO '{_escapar(repetidos)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    return [unicos, repetidos]


def _lista_sql(caminhos: list[str]) -> str:
    """Lista de caminhos como literal do read_parquet."""
    return "[" + ", ".join(f"'{_escapar(c)}'" for c in caminhos) + "]"


def _apagar(caminhos: list[str]) -> None:
    for caminho in caminhos:
        try:
            os.remove(caminho)
        except OSError:
            log.warning("não deu para apagar parquet intermediário",
                        extra={"arquivo": caminho})


def _abrir(destino: str):
    """Conexão do confronto: em ARQUIVO, com teto de memória e onde derramar.

    Banco em memória não tem para onde derramar quando a agregação não cabe na
    RAM — ele simplesmente morre com "Allocation failure". Aconteceu num
    confronto de 37,9 milhões de documentos: a agregação por chave estourou e a
    execução inteira caiu, levando junto a responsividade da API.

    As três configurações resolvem coisas diferentes:

    * banco em arquivo e `temp_directory` dão a DuckDB onde escrever o que não
      couber na memória;
    * `memory_limit` impede que ele tome a máquina de assalto — a API e o
      Postgres rodam ao lado;
    * `preserve_insertion_order` desligado é o que mais economiza memória em
      leitura e escrita de parquet grande, e aqui a ordem de entrada não
      significa nada: o que sai é ordenado por ORDER BY explícito.
    """
    con = duckdb.connect(os.path.join(destino, BANCO_DO_CONFRONTO))
    con.execute(f"SET temp_directory = '{_escapar(destino)}'")
    con.execute(f"SET memory_limit = '{obter_config().memoria_analitica}'")
    con.execute("SET preserve_insertion_order = false")
    if obter_config().threads_analiticas:
        con.execute(f"SET threads = {obter_config().threads_analiticas}")
    livre = shutil.disk_usage(destino).free
    # deixa uma folga: encher o disco de rascunho derruba mais coisa do
    # que esta execução
    teto = max(livre - FOLGA_DE_DISCO, FOLGA_DE_DISCO)
    con.execute(f"SET max_temp_directory_size = '{teto // 10**9}GB'")
    log.info("motor analítico aberto",
             extra={"destino": destino, "livre_gb": round(livre / 1e9, 1),
                    "teto_rascunho_gb": teto // 10**9,
                    "memoria": obter_config().memoria_analitica,
                    "threads": obter_config().threads_analiticas})
    return con


def _limpar(destino: str) -> None:
    """O banco do confronto é rascunho: o resultado está nos parquets."""
    caminho = os.path.join(destino, BANCO_DO_CONFRONTO)
    for alvo in (caminho, caminho + ".wal", caminho + ".tmp"):
        if os.path.isdir(alvo):
            shutil.rmtree(alvo, ignore_errors=True)
        elif os.path.isfile(alvo):
            try:
                os.remove(alvo)
            except OSError:
                log.warning("não deu para apagar o rascunho do confronto",
                            extra={"arquivo": alvo})


def _resumir(con, nao_escrituradas: str, sem_documento: str,
             conferidos: str) -> ResumoDaConferencia:
    """Os números do confronto, lidos dos parquets já escritos.

    `count(DISTINCT)` sobre dezenas de milhões de valores constrói uma tabela
    de dispersão que não derrama bem: numa base de 37,9 milhões de documentos
    ele passou de dez minutos e estourou a memória. Aqui as contagens saem
    das listas **já gravadas** — pendências e conferidos, uma linha por chave
    cada — numa varredura colunar, sem voltar à base.

    E `escriturados` não é contado: as pendências e os conferidos particionam
    o conjunto, então a soma dos dois é o total. Contar de novo seria pagar
    caro por um número que já se tem.

    A única contagem distinta do lado grande é a guarda de chave repetida na
    saída — `count(DISTINCT chave)` sobre uma coluna só, já escrita em parquet:
    uns 20 segundos em 37,9 milhões, e é o que impede cobrar o cliente em dobro
    sem ninguém perceber.
    """
    na_pasta = con.execute("SELECT count(*) FROM entregues").fetchone()[0]

    pendencias = _escapar(sem_documento)
    (faltando, valor_faltando, espera, sem_chave, repetidas,
     com_chave, chaves_distintas) = con.execute(f"""
        SELECT count(*), coalesce(sum(valor), 0),
               count(*) FILTER (WHERE espera_documento),
               count(*) FILTER (WHERE NOT tem_chave),
               count(*) FILTER (WHERE ocorrencias > 1),
               count(*) FILTER (WHERE tem_chave),
               count(DISTINCT chave) FILTER (WHERE tem_chave)
        FROM read_parquet('{pendencias}')
    """).fetchone()
    # Invariante da saída: uma linha por chave. Não é filtro — é conferência.
    # Se um dia der diferente, é defeito do pipeline, e tem de aparecer na
    # tela em vez de virar cobrança em dobro ao cliente. A tentação de
    # "deduplicar por número" foi medida e rejeitada: número se repete entre
    # emitentes diferentes e entre equipamentos SAT, e apagaria 10,9 milhões
    # de documentos legítimos numa base real.
    chaves_repetidas_na_saida = com_chave - chaves_distintas
    if chaves_repetidas_na_saida:
        log.error("a lista de pendências tem chave repetida — defeito do pipeline",
                  extra={"linhas_a_mais": chaves_repetidas_na_saida,
                         "arquivo": os.path.basename(sem_documento)})

    fora = con.execute(
        f"SELECT count(*) FROM read_parquet('{_escapar(nao_escrituradas)}')"
    ).fetchone()[0]

    # o lado positivo, do parquet já escrito: uma linha por chave
    com_documento, valor_conferido = con.execute(f"""
        SELECT count(*), coalesce(sum(valor), 0)
        FROM read_parquet('{_escapar(conferidos)}')
    """).fetchone()

    origens = [Origem(o) for (o,) in con.execute(
        "SELECT DISTINCT origem FROM pasta WHERE origem IS NOT NULL"
    ).fetchall() if o in {x.value for x in Origem}]

    positivos = _escapar(conferidos)
    por_modelo = _fatias(con, "modelo", pendencias, positivos, _modelo_rotulo)
    por_operacao = _fatias(
        con, "operacao", pendencias, positivos,
        lambda o: "Entrada" if o == "entrada" else "Saída")

    # como as pendências se dividem: o que se cobra, o que não tem documento a
    # pedir e o que precisa de conferência manual por não ter chave
    por_classificacao = [
        Fatia(rotulo=_CLASSIFICACAO.get(c, c), documentos=q, valor=_dec(v),
              codigo=c)
        for c, q, v in con.execute(f"""
            SELECT classificacao, count(*), coalesce(sum(valor), 0)
            FROM read_parquet('{pendencias}')
            GROUP BY classificacao ORDER BY 2 DESC
        """).fetchall()
    ]

    # o CNPJ do emitente está na própria chave, posições 7 a 20; não é preciso
    # abrir o XML de novo para saber de quem ele é. Distinto aqui é barato:
    # são poucas dezenas de estabelecimentos, e a tabela de dispersão é minúscula.
    estabelecimentos = [c for (c,) in con.execute(
        "SELECT DISTINCT cnpj FROM efd "
        "WHERE cnpj IS NOT NULL AND cnpj <> '' ORDER BY 1").fetchall()]
    emitentes = [c for (c,) in con.execute(
        "SELECT DISTINCT substr(chave, 7, 14) FROM entregues ORDER BY 1"
    ).fetchall() if c]

    return ResumoDaConferencia(
        escriturados=com_documento + faltando,
        conferidos=com_documento,
        nao_escrituradas=fora,
        sem_documento=faltando,
        sem_documento_cobravel=espera,
        documentos_na_pasta=na_pasta,
        valor_conferido=_dec(valor_conferido),
        valor_sem_documento=_dec(valor_faltando),
        sem_chave_na_efd=sem_chave,
        origens=origens,
        por_modelo=por_modelo,
        por_operacao=por_operacao,
        por_classificacao=por_classificacao,
        estabelecimentos_da_efd=estabelecimentos[:20],
        emitentes_na_pasta=emitentes[:20],
        pendencias_repetidas=repetidas,
        chaves_repetidas_na_lista=chaves_repetidas_na_saida,
    )


def _fatias(con, coluna: str, pendencias: str, positivos: str,
            rotular) -> list[Fatia]:
    """Recorte somando os dois lados: o que ficou pendente e o que conferiu.

    Somar as duas listas em vez de contar sobre a base inteira é o que mantém
    isto barato — cada lado é uma varredura de parquet, uma linha por chave.
    """
    pendentes = con.execute(f"""
        SELECT {coluna}, count(*), coalesce(sum(valor), 0)
        FROM read_parquet('{pendencias}') GROUP BY 1
    """).fetchall()
    conferidos = con.execute(f"""
        SELECT {coluna}, count(*), coalesce(sum(valor), 0)
        FROM read_parquet('{positivos}') GROUP BY 1
    """).fetchall()

    juntos: dict[str, tuple[int, Decimal]] = {}
    for codigo, quantos, valor in list(pendentes) + list(conferidos):
        q, v = juntos.get(codigo or "", (0, ZERO))
        juntos[codigo or ""] = (q + quantos, v + _dec(valor))
    return [
        Fatia(rotulo=rotular(c), documentos=q, valor=v, codigo=c)
        for c, (q, v) in sorted(juntos.items(), key=lambda kv: -kv[1][0])
    ]


def _comparar(con, anterior: str, atual: str,
              resumo: ResumoDaConferencia) -> None:
    """O que andou desde a rodada passada.

    É o que responde "o cliente mandou os documentos, e agora?". Resolvidas são
    as que saíram da pendência; novas são as que apareceram porque entrou EFD
    que antes não estava no lote.
    """
    resolvidas = con.execute(f"""
        SELECT count(*) FROM read_parquet('{_escapar(anterior)}') a
        LEFT JOIN read_parquet('{_escapar(atual)}') b USING (agrupador)
        WHERE b.agrupador IS NULL
    """).fetchone()[0]
    novas = con.execute(f"""
        SELECT count(*) FROM read_parquet('{_escapar(atual)}') b
        LEFT JOIN read_parquet('{_escapar(anterior)}') a USING (agrupador)
        WHERE a.agrupador IS NULL
    """).fetchone()[0]

    resumo.comparou = True
    resumo.pendencias_resolvidas = resolvidas
    resumo.pendencias_novas = novas
    resumo.pendencias_que_permanecem = resumo.sem_documento - novas


_MODELOS = {"01": "NF modelo 1/1-A", "04": "Nota Fiscal de Produtor",
            "06": "Conta de energia", "55": "NF-e", "57": "CT-e",
            "59": "CF-e-SAT", "65": "NFC-e"}

_CLASSIFICACAO = {
    "a_cobrar": "A cobrar do cliente",
    "sem_documento_a_pedir": "Cancelada, denegada ou inutilizada",
    "sem_chave": "Sem chave — conferir à mão",
}


def _modelo_rotulo(codigo: str) -> str:
    return _MODELOS.get(codigo, f"Modelo {codigo}")


def _dec(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(Decimal("0.01"))


def _escapar(caminho: str) -> str:
    """Caminho dentro de literal SQL. Windows usa contrabarra; aspas simples
    é o que precisa dobrar."""
    return caminho.replace("'", "''")

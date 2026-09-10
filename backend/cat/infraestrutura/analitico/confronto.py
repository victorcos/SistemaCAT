"""O confronto propriamente dito, em DuckDB.

Duas listas saem daqui, e vão para parquet em vez de para o banco: numa base
desta casa a EFD tem centenas de milhões de documentos, e a pendência pode ser
milhões de linhas. O que vai para o Postgres é o resumo — números que a tela
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
from decimal import Decimal

import duckdb

from cat.dominio.cat42.conferencia import Fatia, Origem, ResumoDaConferencia
from cat.log import obter_log

log = obter_log(__name__)

ZERO = Decimal("0")

# Tabela 4.1.2: regular, extemporâneo e complementar. O resto é cancelado,
# denegado ou numeração inutilizada — a lista traz todos, e esta tupla só diz
# de quais se espera que exista documento a pedir.
SITUACOES_COM_DOCUMENTO = ("00", "01", "06", "07", "08")

ARQUIVO_NAO_ESCRITURADAS = "nao_escrituradas.parquet"
ARQUIVO_SEM_DOCUMENTO = "sem_documento.parquet"


def confrontar(efd: str, pasta: str, destino: str,
               anterior: str | None = None) -> ResumoDaConferencia:
    """Compara os dois parquets e grava as duas listas de divergência.

    `anterior` é o `sem_documento.parquet` da rodada passada. Com ele, o resumo
    diz o que andou desde então: quantas pendências o cliente resolveu, quantas
    continuam e quantas apareceram. É o que dá sentido a rodar de novo.
    """
    os.makedirs(destino, exist_ok=True)
    nao_escrituradas = os.path.join(destino, ARQUIVO_NAO_ESCRITURADAS)
    sem_documento = os.path.join(destino, ARQUIVO_SEM_DOCUMENTO)
    esperado = str(SITUACOES_COM_DOCUMENTO)

    con = duckdb.connect()
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

        con.execute("""
            CREATE TABLE por_documento AS
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
                   -- alguém questiona uma linha da cobrança meses depois
                   any_value(arquivo)      AS arquivo_efd,
                   count(*)                AS ocorrencias
            FROM efd GROUP BY agrupador
        """)

        con.execute(f"""
            CREATE TABLE pendentes AS
            SELECT e.*,
                   e.tem_chave AND e.situacao IN {esperado} AS espera_documento,
                   CASE
                     WHEN NOT e.tem_chave THEN 'sem_chave'
                     WHEN e.situacao NOT IN {esperado} THEN 'sem_documento_a_pedir'
                     ELSE 'a_cobrar'
                   END AS classificacao
            FROM por_documento e
            LEFT JOIN entregues p USING (chave)
            WHERE p.chave IS NULL
        """)

        con.execute(f"""
            COPY (SELECT * FROM pendentes
                  ORDER BY classificacao, cnpj, competencia, data, numero)
            TO '{_escapar(sem_documento)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

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

        resumo = _resumir(con, nao_escrituradas)
        if anterior and os.path.isfile(anterior):
            _comparar(con, anterior, sem_documento, resumo)
    finally:
        con.close()

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


def _resumir(con, nao_escrituradas: str) -> ResumoDaConferencia:
    escriturados, sem_chave = con.execute("""
        SELECT count(*), count(*) FILTER (WHERE NOT tem_chave)
        FROM por_documento
    """).fetchone()
    na_pasta = con.execute("SELECT count(*) FROM entregues").fetchone()[0]

    faltando, valor_faltando, espera = con.execute("""
        SELECT count(*), coalesce(sum(valor), 0),
               count(*) FILTER (WHERE espera_documento)
        FROM pendentes
    """).fetchone()

    fora = con.execute(
        f"SELECT count(*) FROM read_parquet('{_escapar(nao_escrituradas)}')"
    ).fetchone()[0]

    conferidos, valor_conferido = con.execute("""
        SELECT count(*), coalesce(sum(e.valor), 0)
        FROM por_documento e
        JOIN entregues p USING (chave)
    """).fetchone()

    origens = [Origem(o) for (o,) in con.execute(
        "SELECT DISTINCT origem FROM pasta WHERE origem IS NOT NULL"
    ).fetchall() if o in {x.value for x in Origem}]

    por_modelo = [
        Fatia(rotulo=_modelo_rotulo(m), documentos=q, valor=_dec(v), codigo=m)
        for m, q, v in con.execute("""
            SELECT modelo, count(*), coalesce(sum(valor), 0)
            FROM por_documento GROUP BY modelo ORDER BY count(*) DESC
        """).fetchall()
    ]
    por_operacao = [
        Fatia(rotulo="Entrada" if o == "entrada" else "Saída",
              documentos=q, valor=_dec(v), codigo=o)
        for o, q, v in con.execute("""
            SELECT operacao, count(*), coalesce(sum(valor), 0)
            FROM por_documento GROUP BY operacao ORDER BY count(*) DESC
        """).fetchall()
    ]
    # como as pendências se dividem: o que se cobra, o que não tem documento a
    # pedir e o que precisa de conferência manual por não ter chave
    por_classificacao = [
        Fatia(rotulo=_CLASSIFICACAO.get(c, c), documentos=q, valor=_dec(v),
              codigo=c)
        for c, q, v in con.execute("""
            SELECT classificacao, count(*), coalesce(sum(valor), 0)
            FROM pendentes GROUP BY classificacao ORDER BY count(*) DESC
        """).fetchall()
    ]

    return ResumoDaConferencia(
        escriturados=escriturados,
        conferidos=conferidos,
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
    )


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

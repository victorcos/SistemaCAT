"""O confronto propriamente dito, em DuckDB.

Duas listas saem daqui, e vão para parquet em vez de para o banco: numa base
desta casa a EFD tem centenas de milhões de documentos, e a pendência pode ser
milhões de linhas. O que vai para o Postgres é o resumo — números que a tela
mostra e que ficam registrados na execução.

O casamento é pela chave de acesso. Uma nota pode aparecer mais de uma vez na
EFD legitimamente: emitida por um estabelecimento e recebida por outro do mesmo
grupo são dois C100 da mesma chave. Por isso a lista de cobrança é agrupada por
chave — pedir duas vezes o mesmo XML ao cliente é ruído.
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
# denegado ou numeração inutilizada — não há documento a pedir.
SITUACOES_COBRAVEIS = ("00", "01", "06", "07", "08")

ARQUIVO_NAO_ESCRITURADAS = "nao_escrituradas.parquet"
ARQUIVO_SEM_DOCUMENTO = "sem_documento.parquet"


def confrontar(efd: str, pasta: str, destino: str) -> ResumoDaConferencia:
    """Compara os dois parquets e grava as duas listas de divergência."""
    os.makedirs(destino, exist_ok=True)
    nao_escrituradas = os.path.join(destino, ARQUIVO_NAO_ESCRITURADAS)
    sem_documento = os.path.join(destino, ARQUIVO_SEM_DOCUMENTO)

    con = duckdb.connect()
    try:
        # DuckDB não aceita parâmetro preparado em CREATE VIEW; o caminho
        # entra no texto, com as aspas simples dobradas
        con.execute("CREATE VIEW efd_bruta AS SELECT * FROM read_parquet("
                    f"'{_escapar(efd)}')")
        con.execute("CREATE VIEW pasta AS SELECT * FROM read_parquet("
                    f"'{_escapar(pasta)}')")

        # sem chave não há confronto possível: nota modelo 1 e cupom antigo não
        # têm chave, e tratá-los como pendência mandaria o cliente atrás de algo
        # que nunca existiu
        con.execute("""
            CREATE VIEW efd AS
            SELECT * FROM efd_bruta WHERE length(chave) = 44
        """)

        sem_chave = con.execute(
            "SELECT count(*) FROM efd_bruta WHERE length(chave) <> 44"
        ).fetchone()[0]

        con.execute("""
            CREATE VIEW por_chave AS
            SELECT chave,
                   min(modelo)       AS modelo,
                   min(situacao)     AS situacao,
                   any_value(serie)  AS serie,
                   any_value(numero) AS numero,
                   min(data)         AS data,
                   max(valor)        AS valor,
                   any_value(participante) AS participante,
                   any_value(operacao)     AS operacao,
                   any_value(emitente)     AS emitente,
                   any_value(cnpj)         AS cnpj,
                   min(competencia)        AS competencia,
                   -- de qual arquivo saiu: é por onde se recomeça quando
                   -- alguém questiona uma linha da cobrança meses depois
                   any_value(arquivo)      AS arquivo_efd,
                   count(*)                AS ocorrencias
            FROM efd GROUP BY chave
        """)

        # ---- na EFD e sem documento: é o que se cobra ----
        con.execute(f"""
            COPY (
                SELECT e.*,
                       e.situacao IN {SITUACOES_COBRAVEIS} AS cobravel
                FROM por_chave e
                LEFT JOIN (SELECT DISTINCT chave FROM pasta) p USING (chave)
                WHERE p.chave IS NULL
                ORDER BY e.cnpj, e.competencia, e.data, e.numero
            ) TO '{_escapar(sem_documento)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

        # ---- na pasta e fora da EFD: sai da análise ----
        con.execute(f"""
            COPY (
                SELECT p.chave, p.origem, p.arquivo
                FROM pasta p
                LEFT JOIN (SELECT DISTINCT chave FROM efd) e USING (chave)
                WHERE e.chave IS NULL
                ORDER BY p.chave
            ) TO '{_escapar(nao_escrituradas)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

        resumo = _resumir(con, sem_chave, nao_escrituradas, sem_documento)
    finally:
        con.close()

    log.info(
        "confronto concluído",
        extra={"escriturados": resumo.escriturados,
               "conferidos": resumo.conferidos,
               "sem_documento": resumo.sem_documento,
               "cobravel": resumo.sem_documento_cobravel,
               "nao_escrituradas": resumo.nao_escrituradas,
               "cobertura": round(resumo.cobertura, 4)},
    )
    return resumo


def _resumir(con, sem_chave: int, nao_escrituradas: str,
             sem_documento: str) -> ResumoDaConferencia:
    escriturados = con.execute("SELECT count(*) FROM por_chave").fetchone()[0]
    na_pasta = con.execute(
        "SELECT count(DISTINCT chave) FROM pasta").fetchone()[0]

    faltando, valor_faltando, cobravel = con.execute(f"""
        SELECT count(*), coalesce(sum(valor), 0),
               count(*) FILTER (WHERE situacao IN {SITUACOES_COBRAVEIS})
        FROM read_parquet('{_escapar(sem_documento)}')
    """).fetchone()

    fora = con.execute(
        f"SELECT count(*) FROM read_parquet('{_escapar(nao_escrituradas)}')"
    ).fetchone()[0]

    conferidos, valor_conferido = con.execute("""
        SELECT count(*), coalesce(sum(e.valor), 0)
        FROM por_chave e
        JOIN (SELECT DISTINCT chave FROM pasta) p USING (chave)
    """).fetchone()

    origens = [Origem(o) for (o,) in con.execute(
        "SELECT DISTINCT origem FROM pasta WHERE origem IS NOT NULL"
    ).fetchall() if o in {x.value for x in Origem}]

    por_modelo = [
        Fatia(rotulo=_modelo_rotulo(m), documentos=q, valor=_dec(v), codigo=m)
        for m, q, v in con.execute("""
            SELECT modelo, count(*), coalesce(sum(valor), 0)
            FROM por_chave GROUP BY modelo ORDER BY count(*) DESC
        """).fetchall()
    ]
    por_operacao = [
        Fatia(rotulo="Entrada" if o == "entrada" else "Saída",
              documentos=q, valor=_dec(v), codigo=o)
        for o, q, v in con.execute("""
            SELECT operacao, count(*), coalesce(sum(valor), 0)
            FROM por_chave GROUP BY operacao ORDER BY count(*) DESC
        """).fetchall()
    ]

    return ResumoDaConferencia(
        escriturados=escriturados,
        conferidos=conferidos,
        nao_escrituradas=fora,
        sem_documento=faltando,
        sem_documento_cobravel=cobravel,
        documentos_na_pasta=na_pasta,
        valor_conferido=_dec(valor_conferido),
        valor_sem_documento=_dec(valor_faltando),
        sem_chave_na_efd=sem_chave,
        origens=origens,
        por_modelo=por_modelo,
        por_operacao=por_operacao,
    )


_MODELOS = {"01": "NF modelo 1/1-A", "04": "Nota Fiscal de Produtor",
            "06": "Conta de energia", "55": "NF-e", "57": "CT-e",
            "59": "CF-e-SAT", "65": "NFC-e"}


def _modelo_rotulo(codigo: str) -> str:
    return _MODELOS.get(codigo, f"Modelo {codigo}")


def _dec(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(Decimal("0.01"))


def _escapar(caminho: str) -> str:
    """Caminho dentro de literal SQL. Windows usa contrabarra; aspas simples
    é o que precisa dobrar."""
    return caminho.replace("'", "''")

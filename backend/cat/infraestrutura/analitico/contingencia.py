"""As notas não escrituradas e a multa de cada item, em DuckDB.

Roda dentro da consolidação da etapa 3, na mesma conexão: usa as tabelas
`xml_itens` e `canceladas` que ela já montou.

Nota não escriturada é XML **do estabelecimento** (emitente ou destinatário é
um CNPJ que tem EFD no projeto), **emitido num mês que tem EFD** desse
estabelecimento, **sem a chave na EFD dele** e **não cancelado na SEFAZ**. O
mês sem EFD fica de fora: ali não se sabe se a nota foi escriturada. A nota
entre dois estabelecimentos do projeto conta para cada lado que não a
escriturou.

O lado grande é a EFD (`documentos.parquet`); as chaves do XML vão do lado da
construção, como na marca da conferência.
"""

from __future__ import annotations

from cat.dominio.cat42.contingencia import (
    FUNDAMENTO_ENTRADA,
    FUNDAMENTO_SAIDA,
    PERCENTUAL_ENTRADA,
    PERCENTUAL_SAIDA,
)
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_CONTINGENCIA = "contingencia.parquet"


def montar_contingencia(con, documentos: str, destino: str) -> None:
    """Grava `contingencia.parquet`, um item por linha. `documentos` e `destino`
    chegam já escapados para o texto do SQL."""
    con.execute(f"""
        CREATE TABLE periodos_da_efd AS
        SELECT DISTINCT cnpj, competencia FROM read_parquet('{documentos}')
    """)
    # cada nota, de cada lado que é estabelecimento do projeto e tem EFD no mês
    con.execute("""
        CREATE TABLE xml_dos_estabelecimentos AS
        SELECT DISTINCT l.cnpj, l.chave
        FROM (SELECT DISTINCT chave, emitente AS cnpj, emissao FROM xml_itens
              UNION
              SELECT DISTINCT chave, destinatario AS cnpj, emissao FROM xml_itens) l
        SEMI JOIN periodos_da_efd p
               ON p.cnpj = l.cnpj AND p.competencia = date_trunc('month', l.emissao)
    """)
    con.execute(f"""
        CREATE TABLE xml_escriturados AS
        SELECT DISTINCT d.cnpj, d.chave FROM read_parquet('{documentos}') d
        SEMI JOIN xml_dos_estabelecimentos k ON k.cnpj = d.cnpj AND k.chave = d.chave
    """)
    con.execute(f"""
        COPY (
            WITH ausentes AS (
                SELECT k.* FROM xml_dos_estabelecimentos k
                ANTI JOIN xml_escriturados e ON e.cnpj = k.cnpj AND e.chave = k.chave
                ANTI JOIN canceladas c ON c.chave = k.chave
            ),
            itens AS (
                SELECT a.cnpj, x.*,
                       CASE WHEN (x.emitente = a.cnpj) = (x.tipo = '1')
                            THEN 'saida' ELSE 'entrada' END AS operacao
                FROM ausentes a JOIN xml_itens x ON x.chave = a.chave
            )
            SELECT cnpj, CAST(date_trunc('month', emissao) AS DATE) AS competencia, emissao,
                   operacao, modelo, numero_documento, serie, chave, emitente, destinatario,
                   numero_item, codigo, descricao, ncm, cfop, cst_icms, valor, valor_icms,
                   CASE operacao WHEN 'entrada' THEN coalesce(valor, 0)
                                 ELSE coalesce(valor_icms, 0) END AS base_da_multa,
                   CASE operacao WHEN 'entrada' THEN {PERCENTUAL_ENTRADA}
                                 ELSE {PERCENTUAL_SAIDA} END::DECIMAL(5, 2) AS percentual,
                   round(CASE operacao WHEN 'entrada' THEN coalesce(valor, 0) * {PERCENTUAL_ENTRADA}
                                       ELSE coalesce(valor_icms, 0) * {PERCENTUAL_SAIDA} END / 100,
                         2)::DECIMAL(18, 2) AS multa,
                   CASE operacao WHEN 'entrada' THEN '{FUNDAMENTO_ENTRADA}'
                                 ELSE '{FUNDAMENTO_SAIDA}' END AS fundamento,
                   arquivo
            FROM itens
            ORDER BY cnpj, operacao, emissao, chave, numero_item
        ) TO '{destino}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)


def resumir_contingencia(con, parquet: str) -> dict:
    """Documentos, valores e multa por operação, e a multa por ano."""
    (entradas, saidas, valor_entradas, icms_saidas, multa_entradas, multa_saidas) = con.execute(f"""
        SELECT count(DISTINCT (cnpj, chave)) FILTER (WHERE operacao = 'entrada'),
               count(DISTINCT (cnpj, chave)) FILTER (WHERE operacao = 'saida'),
               coalesce(sum(valor) FILTER (WHERE operacao = 'entrada'), 0),
               coalesce(sum(valor_icms) FILTER (WHERE operacao = 'saida'), 0),
               coalesce(sum(multa) FILTER (WHERE operacao = 'entrada'), 0),
               coalesce(sum(multa) FILTER (WHERE operacao = 'saida'), 0)
        FROM read_parquet('{parquet}')
    """).fetchone()
    por_ano = con.execute(f"""
        SELECT CAST(year(emissao) AS VARCHAR), count(DISTINCT (cnpj, chave)), coalesce(sum(multa), 0)
        FROM read_parquet('{parquet}') GROUP BY 1 ORDER BY 1
    """).fetchall()
    log.info("contingência das não escrituradas", extra={
        "entradas": entradas, "saidas": saidas,
        "multa_entradas": str(multa_entradas), "multa_saidas": str(multa_saidas)})
    return {"entradas": entradas, "saidas": saidas, "valor_entradas": valor_entradas,
            "icms_saidas": icms_saidas, "multa_entradas": multa_entradas,
            "multa_saidas": multa_saidas, "por_ano": por_ano}

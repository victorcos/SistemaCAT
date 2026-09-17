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

A base da multa é a do XML; o item sem ela busca a nota mais próxima do mesmo
produto (estabelecimento, operação e código) entre todos os XML do
estabelecimento — escriturados ou não, fora os cancelados e as devoluções —, e
leva dela o valor por unidade. A regra está em `cat.dominio.cat42.contingencia`.
"""

from __future__ import annotations

from cat.dominio.cat42.contingencia import (
    BASE_DA_NOTA_ANTERIOR,
    BASE_DA_NOTA_POSTERIOR,
    BASE_DO_XML,
    FUNDAMENTO_ENTRADA,
    FUNDAMENTO_SAIDA,
    PERCENTUAL_ENTRADA,
    PERCENTUAL_SAIDA,
    SEM_REFERENCIA,
)
from cat.dominio.cat42.enquadramento import CFOP_DEVOLUCAO
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
    # todo XML do estabelecimento, de cada lado, com a base que o XML traz: é
    # de onde sai a nota vizinha do item que não traz
    con.execute("""
        CREATE TABLE xml_por_estabelecimento AS
        SELECT l.cnpj, x.*,
               CASE WHEN (x.emitente = l.cnpj) = (x.tipo = '1') THEN 'saida' ELSE 'entrada' END AS operacao,
               CASE WHEN (x.emitente = l.cnpj) = (x.tipo = '1') THEN x.valor_icms ELSE x.valor END AS base_do_xml
        FROM (SELECT DISTINCT chave, emitente AS cnpj FROM xml_itens
              UNION
              SELECT DISTINCT chave, destinatario AS cnpj FROM xml_itens) l
        SEMI JOIN (SELECT DISTINCT cnpj FROM periodos_da_efd) e ON e.cnpj = l.cnpj
        ANTI JOIN canceladas c ON c.chave = l.chave
        JOIN xml_itens x ON x.chave = l.chave
    """)
    con.execute("""
        CREATE TABLE contingencia_itens AS
        WITH ausentes AS (
            SELECT k.* FROM xml_dos_estabelecimentos k
            ANTI JOIN xml_escriturados e ON e.cnpj = k.cnpj AND e.chave = k.chave
            ANTI JOIN canceladas c ON c.chave = k.chave
        )
        SELECT x.* FROM xml_por_estabelecimento x
        SEMI JOIN ausentes a ON a.cnpj = x.cnpj AND a.chave = x.chave
    """)
    # a nota mais próxima do mesmo produto que traz a base; no empate, a anterior
    devolucoes = ", ".join(f"'{c}'" for c in sorted(CFOP_DEVOLUCAO))
    con.execute(f"""
        CREATE TABLE referencias AS
        WITH precisa AS (
            SELECT cnpj, chave, numero_item, operacao, codigo, emissao FROM contingencia_itens
            WHERE coalesce(base_do_xml, 0) <= 0
        ),
        com_base AS (
            SELECT cnpj, operacao, codigo, chave, numero_item, emissao,
                   round(CAST(base_do_xml AS DOUBLE) / CAST(quantidade AS DOUBLE), 6)::DECIMAL(18, 6) AS unitario
            FROM xml_por_estabelecimento
            WHERE coalesce(base_do_xml, 0) > 0 AND coalesce(quantidade, 0) > 0
              -- a devolução carrega o valor da operação de origem, não o desta
              AND replace(coalesce(cfop, ''), '.', '') NOT IN ({devolucoes})
              AND (cnpj, operacao, codigo) IN (SELECT (cnpj, operacao, codigo) FROM precisa)
        )
        SELECT p.cnpj, p.chave, p.numero_item, r.chave AS chave_de_referencia,
               r.emissao AS emissao_de_referencia, r.unitario AS unitario_de_referencia
        FROM precisa p
        JOIN com_base r ON r.cnpj = p.cnpj AND r.operacao = p.operacao AND r.codigo = p.codigo
                       AND r.chave <> p.chave
        QUALIFY row_number() OVER (
            PARTITION BY p.cnpj, p.chave, p.numero_item
            ORDER BY abs(date_diff('day', r.emissao, p.emissao)), r.emissao > p.emissao,
                     r.chave, r.numero_item) = 1
    """)
    con.execute(f"""
        COPY (
            WITH com_base AS (
                SELECT i.*, r.chave_de_referencia, r.emissao_de_referencia, r.unitario_de_referencia,
                       CASE WHEN coalesce(i.base_do_xml, 0) > 0 THEN '{BASE_DO_XML}'
                            WHEN r.unitario_de_referencia IS NULL THEN '{SEM_REFERENCIA}'
                            WHEN r.emissao_de_referencia <= i.emissao THEN '{BASE_DA_NOTA_ANTERIOR}'
                            ELSE '{BASE_DA_NOTA_POSTERIOR}' END AS origem_da_base,
                       CASE WHEN coalesce(i.base_do_xml, 0) > 0 THEN i.base_do_xml
                            WHEN r.unitario_de_referencia IS NULL THEN 0
                            ELSE round(r.unitario_de_referencia * coalesce(i.quantidade, 0), 2)
                       END::DECIMAL(18, 2) AS base_da_multa
                FROM contingencia_itens i
                LEFT JOIN referencias r ON r.cnpj = i.cnpj AND r.chave = i.chave AND r.numero_item = i.numero_item
            )
            SELECT cnpj, CAST(date_trunc('month', emissao) AS DATE) AS competencia, emissao,
                   operacao, modelo, numero_documento, serie, chave, emitente, destinatario,
                   numero_item, codigo, descricao, ncm, cfop, cst_icms, quantidade, valor, valor_icms,
                   origem_da_base, unitario_de_referencia, chave_de_referencia, emissao_de_referencia,
                   base_da_multa,
                   CASE operacao WHEN 'entrada' THEN {PERCENTUAL_ENTRADA}
                                 ELSE {PERCENTUAL_SAIDA} END::DECIMAL(5, 2) AS percentual,
                   round(base_da_multa * CASE operacao WHEN 'entrada' THEN {PERCENTUAL_ENTRADA}
                                                       ELSE {PERCENTUAL_SAIDA} END / 100,
                         2)::DECIMAL(18, 2) AS multa,
                   CASE operacao WHEN 'entrada' THEN '{FUNDAMENTO_ENTRADA}'
                                 ELSE '{FUNDAMENTO_SAIDA}' END AS fundamento,
                   arquivo
            FROM com_base
            ORDER BY cnpj, operacao, emissao, chave, numero_item
        ) TO '{destino}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)


def resumir_contingencia(con, parquet: str) -> dict:
    """Documentos, valores e multa por operação, e a multa por ano."""
    (entradas, saidas, valor_entradas, icms_saidas, multa_entradas, multa_saidas,
     de_nota_vizinha, sem_referencia) = con.execute(f"""
        SELECT count(DISTINCT (cnpj, chave)) FILTER (WHERE operacao = 'entrada'),
               count(DISTINCT (cnpj, chave)) FILTER (WHERE operacao = 'saida'),
               coalesce(sum(base_da_multa) FILTER (WHERE operacao = 'entrada'), 0),
               coalesce(sum(base_da_multa) FILTER (WHERE operacao = 'saida'), 0),
               coalesce(sum(multa) FILTER (WHERE operacao = 'entrada'), 0),
               coalesce(sum(multa) FILTER (WHERE operacao = 'saida'), 0),
               count(*) FILTER (WHERE origem_da_base IN ('{BASE_DA_NOTA_ANTERIOR}', '{BASE_DA_NOTA_POSTERIOR}')),
               count(*) FILTER (WHERE origem_da_base = '{SEM_REFERENCIA}')
        FROM read_parquet('{parquet}')
    """).fetchone()
    por_ano = con.execute(f"""
        SELECT CAST(year(emissao) AS VARCHAR), count(DISTINCT (cnpj, chave)), coalesce(sum(multa), 0)
        FROM read_parquet('{parquet}') GROUP BY 1 ORDER BY 1
    """).fetchall()
    log.info("contingência das não escrituradas", extra={
        "entradas": entradas, "saidas": saidas,
        "multa_entradas": str(multa_entradas), "multa_saidas": str(multa_saidas),
        "itens_com_base_de_nota_vizinha": de_nota_vizinha, "itens_sem_referencia": sem_referencia})
    return {"entradas": entradas, "saidas": saidas, "valor_entradas": valor_entradas,
            "icms_saidas": icms_saidas, "multa_entradas": multa_entradas,
            "multa_saidas": multa_saidas, "por_ano": por_ano,
            "de_nota_vizinha": de_nota_vizinha, "sem_referencia": sem_referencia}

"""Consolidar os parquets da extração de movimentos e resumir, em DuckDB.

Duas coisas, a partir do que `movimentos.py` gravou:

1. **o cadastro que vale** — o 0200 se repete a cada período; fica, por
   estabelecimento e código, o do período mais recente (`itens.parquet`);
2. **os movimentos prontos para o razão** — cada C170/C810 com a descrição,
   NCM e CEST do cadastro, e com a **classificação da conferência**: conferido,
   pendente ou sem chave. Ordenados por estabelecimento, item e data, que é a
   ordem em que a ficha se lê (`movimentos.parquet`).

## O item do XML

Quando a etapa leu XML (`itens_do_xml.parquet`), ele entra de duas formas:

* **completa o documento escriturado sem item** — a NF-e de saída própria, a
  NFC-e e o CF-e, que vão à EFD só com o analítico. O documento é o da EFD
  (estabelecimento, operação, data, participante); o item é o do XML
  (`registro` = ``XML``, `fonte_item` = ``xml``). Só documento regular:
  cancelado e denegado não têm operação a completar;
* **ao lado do C170 que já existe** — pelo número do item, confirmado pela
  quantidade ou pelo valor; sem nenhum dos dois, só em nota de um item só. A
  contagem de itens igual não basta: na Advertising, nota com os itens em outra
  ordem no C170 levava o GTIN de um produto para o código de outro. O valor sozinho não serve: na Advertising o C170 grava o custo com ST
  e IPI embutidos (15.044,19) e o XML, a mercadoria (10.465,92). Os valores do
  XML vão em colunas próprias (`valor_st_xml`, `retido_xml`...) e vencem na
  apuração do suportado; os da EFD ficam como vieram.

Na entrada de terceiros completada pelo XML, o CFOP do XML é o de quem vendeu
(5.401): vale o CFOP do analítico do documento quando ele é um só, e senão o
do XML com o primeiro dígito virado para o lado de quem recebeu (1.401).

## Canceladas na SEFAZ

Com `chaves_canceladas.parquet` (evento de cancelamento ou lista de chaves), o
documento que a EFD traz como válido e está cancelado na SEFAZ sai da
movimentação — o C170 e o item do XML —, e o resumo conta quantos documentos
e movimentos saíram. O documento continua em `documentos.parquet`: é a
escrituração como veio, e é ela que se retifica.

## Não escrituradas

O XML do estabelecimento, de mês com EFD, que a EFD dele não tem e que não está
cancelado vai para `contingencia.parquet`, item a item, com a multa do art. 527
do RICMS/SP — sem SELIC. A regra está em `contingencia.py`.

A marca da conferência é a única junção contra o lado grande, e é feita
pelo lado pequeno de propósito: a lista de conferidos de uma base saudável
tem dezenas de milhões de chaves, mas os movimentos com item são só as
entradas — poucos milhões de chaves distintas. Primeiro se reduz a lista de
conferidos a essas chaves (SEMI JOIN, com as chaves dos movimentos do lado
da construção), e só então se marca cada linha.

Mesmas regras do confronto para não estourar memória: conexão em arquivo com
`temp_directory`, `memory_limit` e `preserve_insertion_order` desligado. As
contagens do resumo saem dos parquets já gravados, uma varredura cada.
"""

from __future__ import annotations

import os
from decimal import Decimal

from cat.dominio.cat42.conferencia import Fatia
from cat.dominio.cat42.movimentacao import ResumoDaMovimentacao
from cat.infraestrutura.analitico.canceladas import ARQUIVO_CHAVES_CANCELADAS, ESQUEMA_CHAVES_CANCELADAS
from cat.infraestrutura.analitico.confronto import SITUACOES_COM_DOCUMENTO, _abrir, _escapar, _limpar
from cat.infraestrutura.analitico.contingencia import (
    ARQUIVO_CONTINGENCIA,
    montar_contingencia,
    resumir_contingencia,
)
from cat.infraestrutura.analitico.itens_do_xml import ARQUIVO_ITENS_DO_XML, ESQUEMA_ITENS_DO_XML
from cat.infraestrutura.analitico.movimentos import (  # noqa: F401
    ARQUIVO_ANALITICO,
    ARQUIVO_CONVERSOES_DA_EFD,
    ARQUIVO_DOCUMENTOS,
    ARQUIVO_INVENTARIO,
    ARQUIVO_ITENS_DA_EFD,
    ARQUIVO_MOVIMENTOS_BRUTOS,
)
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_ITENS = "itens.parquet"
ARQUIVO_MOVIMENTOS = "movimentos.parquet"
ARQUIVO_CONVERSOES = "conversoes.parquet"

_MODELOS = {"01": "NF modelo 1/1-A", "55": "NF-e", "59": "CF-e-SAT", "65": "NFC-e",
            "57": "CT-e", "04": "NF de Produtor"}
_CLASSIFICACAO = {
    "conferido": "Documento conferido",
    "pendente": "Documento pendente na conferência",
    "sem_chave": "Sem chave — conferir à mão",
    "nao_conferido": "Sem conferência",
}

# o que o XML acrescenta a cada movimento. Vazio quando não há XML do documento
# ou quando o item do XML não é o mesmo do C170
_COLUNAS_DO_XML = """
    x.arquivo AS arquivo_xml, x.codigo AS codigo_xml, x.gtin AS gtin_xml,
    x.descricao AS descricao_xml, x.ncm AS ncm_xml, x.cest AS cest_xml,
    x.unidade AS unidade_xml, x.quantidade AS quantidade_xml,
    x.valor_icms AS valor_icms_xml, x.bc_st AS bc_st_xml, x.valor_st AS valor_st_xml,
    x.fcp_st AS fcp_st_xml, x.retido_informado AS retido_xml,
    x.consumidor_final AS consumidor_final_xml
"""

# o primeiro dígito do CFOP, do lado de quem emitiu para o de quem recebeu
_VIRAR_CFOP = """
    CASE WHEN d.operacao = 'entrada' THEN
              CASE substr(x.cfop, 1, 1) WHEN '5' THEN '1' WHEN '6' THEN '2' WHEN '7' THEN '3'
                   ELSE substr(x.cfop, 1, 1) END
         ELSE CASE substr(x.cfop, 1, 1) WHEN '1' THEN '5' WHEN '2' THEN '6' WHEN '3' THEN '7'
                   ELSE substr(x.cfop, 1, 1) END
    END || substr(x.cfop, 2)
"""


def consolidar(destino: str, conferidos: str | None) -> ResumoDaMovimentacao:
    """Grava `itens`, `movimentos` e `analitico` finais e devolve o resumo."""
    p = lambda nome: _escapar(os.path.join(destino, nome))  # noqa: E731
    con = _abrir(destino)
    try:
        _preparar_xml(con, destino, p)
        # 1. o cadastro mais recente por estabelecimento e código
        con.execute(f"""
            COPY (
                SELECT * FROM read_parquet('{p(ARQUIVO_ITENS_DA_EFD)}')
                QUALIFY row_number() OVER (
                    PARTITION BY cnpj, codigo
                    ORDER BY competencia DESC NULLS LAST, arquivo DESC) = 1
            ) TO '{p(ARQUIVO_ITENS)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

        # 1b. o fator de conversão (0220) mais recente por estabelecimento,
        # código e unidade — o cadastro muda de período para período, e vale
        # o último, como no 0200
        if os.path.isfile(os.path.join(destino, ARQUIVO_CONVERSOES_DA_EFD)):
            con.execute(f"""
                COPY (
                    SELECT cnpj, codigo, upper(trim(unidade)) AS unidade, fator, competencia
                    FROM read_parquet('{p(ARQUIVO_CONVERSOES_DA_EFD)}')
                    QUALIFY row_number() OVER (
                        PARTITION BY cnpj, codigo, upper(trim(unidade))
                        ORDER BY competencia DESC NULLS LAST, arquivo DESC) = 1
                ) TO '{p(ARQUIVO_CONVERSOES)}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """)

        # 2. os movimentos com cadastro e com a marca da conferência.
        # A lista de conferidos é uma linha por chave; sem ela, ninguém é
        # marcado e o resumo avisa.
        if conferidos and os.path.isfile(conferidos):
            # as chaves dos movimentos (lado pequeno) contra a lista de
            # conferidos (lado grande): o que sobra é o que se marca
            con.execute("""
                CREATE TABLE chaves_dos_movimentos AS
                SELECT DISTINCT chave FROM movimentos_juntos
                WHERE length(chave) = 44
            """)
            con.execute(f"""
                CREATE TABLE conferidos AS
                SELECT k.chave FROM chaves_dos_movimentos k
                SEMI JOIN read_parquet('{_escapar(conferidos)}') c ON c.chave = k.chave
            """)
            classificacao = """
                CASE WHEN length(m.chave) <> 44 THEN 'sem_chave'
                     WHEN c.chave IS NOT NULL THEN 'conferido'
                     ELSE 'pendente' END"""
            juncao = "LEFT JOIN conferidos c ON c.chave = m.chave"
            usada = True
        else:
            classificacao = "'nao_conferido'"
            juncao = ""
            usada = False
        # sem 0200, a descrição, o código de barras, o NCM e o CEST vêm do XML;
        # `cadastro_da_efd` continua dizendo quem não está no cadastro
        con.execute(f"""
            COPY (
                SELECT m.*,
                       CASE WHEN i.codigo IS NULL THEN m.descricao_xml ELSE i.descricao END AS descricao,
                       CASE WHEN i.codigo IS NULL THEN m.gtin_xml ELSE i.codigo_barras END AS codigo_barras,
                       CASE WHEN i.codigo IS NULL THEN m.ncm_xml ELSE i.ncm END AS ncm,
                       CASE WHEN i.codigo IS NULL THEN m.cest_xml ELSE i.cest END AS cest,
                       i.unidade AS unidade_cadastro,
                       i.codigo IS NOT NULL AS cadastro_da_efd,
                       {classificacao} AS classificacao
                FROM movimentos_juntos m
                LEFT JOIN read_parquet('{p(ARQUIVO_ITENS)}') i
                       ON i.cnpj = m.cnpj AND i.codigo = m.codigo
                {juncao}
                ORDER BY m.cnpj, m.codigo, m.data, m.numero_documento, m.numero_item
            ) TO '{p(ARQUIVO_MOVIMENTOS)}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

        # 3. as notas do XML que a EFD não escriturou, com a multa de cada item
        montar_contingencia(con, p(ARQUIVO_DOCUMENTOS), p(ARQUIVO_CONTINGENCIA))

        try:
            os.remove(os.path.join(destino, ARQUIVO_MOVIMENTOS_BRUTOS))
        except OSError:
            log.warning("não deu para apagar parquet intermediário",
                        extra={"arquivo": ARQUIVO_MOVIMENTOS_BRUTOS})

        resumo = _resumir(con, p, usada)
        _resumir_xml(con, p, resumo)
        _resumir_contingencia(con, p, resumo)
    finally:
        con.close()
        _limpar(destino)

    log.info("movimentos consolidados",
             extra={"documentos": resumo.documentos,
                    "com_item": resumo.documentos_com_item,
                    "saidas_sem_item": resumo.saidas_sem_item,
                    "movimentos": resumo.movimentos,
                    "itens": resumo.itens_cadastrados,
                    "sem_cadastro": resumo.itens_sem_cadastro,
                    "inventarios": resumo.inventarios})
    return resumo


def _preparar_xml(con, destino: str, p) -> None:
    """Monta `movimentos_juntos`: os C170/C810 com o XML ao lado, mais os itens
    que o XML traz para o documento escriturado sem item, menos o cancelado na SEFAZ."""
    if os.path.isfile(os.path.join(destino, ARQUIVO_CHAVES_CANCELADAS)):
        con.execute(f"CREATE TABLE canceladas AS SELECT DISTINCT chave FROM read_parquet('{p(ARQUIVO_CHAVES_CANCELADAS)}')")
    else:
        con.register("canceladas_vazio", ESQUEMA_CHAVES_CANCELADAS.empty_table())
        con.execute("CREATE TABLE canceladas AS SELECT DISTINCT chave FROM canceladas_vazio")
        con.unregister("canceladas_vazio")
    if os.path.isfile(os.path.join(destino, ARQUIVO_ITENS_DO_XML)):
        con.execute(f"CREATE TABLE xml_itens AS SELECT * FROM read_parquet('{p(ARQUIVO_ITENS_DO_XML)}')")
    else:
        con.register("xml_vazio", ESQUEMA_ITENS_DO_XML.empty_table())
        con.execute("CREATE TABLE xml_itens AS SELECT * FROM xml_vazio")
        con.unregister("xml_vazio")
    situacoes = ", ".join(f"'{s}'" for s in SITUACOES_COM_DOCUMENTO)
    con.execute("CREATE TABLE xml_chaves AS SELECT DISTINCT chave FROM xml_itens")
    con.execute(f"""
        CREATE TABLE docs_do_xml AS
        SELECT d.* FROM read_parquet('{p(ARQUIVO_DOCUMENTOS)}') d
        SEMI JOIN xml_chaves k ON k.chave = d.chave
        WHERE d.itens = 0 AND d.situacao IN ({situacoes})
    """)
    con.execute(f"""
        CREATE TABLE cfop_do_analitico AS
        SELECT a.cnpj, a.chave, min(replace(a.cfop, '.', '')) AS cfop
        FROM read_parquet('{p(ARQUIVO_ANALITICO)}') a
        SEMI JOIN docs_do_xml d ON d.cnpj = a.cnpj AND d.chave = a.chave AND d.emitente = 'terceiros'
        GROUP BY a.cnpj, a.chave HAVING count(DISTINCT replace(a.cfop, '.', '')) = 1
    """)
    con.execute("CREATE TABLE xml_contagem AS SELECT chave, count(*) AS itens FROM xml_itens GROUP BY chave")
    con.execute(f"""
        CREATE TABLE efd_contagem AS
        SELECT m.cnpj, m.chave, count(*) AS itens FROM read_parquet('{p(ARQUIVO_MOVIMENTOS_BRUTOS)}') m
        SEMI JOIN xml_contagem k ON k.chave = m.chave
        GROUP BY m.cnpj, m.chave
    """)
    con.execute(f"""
        CREATE VIEW movimentos_com_xml AS
        SELECT m.*, 'efd' AS fonte_item, {_COLUNAS_DO_XML}
        FROM read_parquet('{p(ARQUIVO_MOVIMENTOS_BRUTOS)}') m
        LEFT JOIN efd_contagem ce ON ce.cnpj = m.cnpj AND ce.chave = m.chave
        LEFT JOIN xml_contagem cx ON cx.chave = m.chave
        LEFT JOIN xml_itens x
               ON x.chave = m.chave AND x.numero_item = m.numero_item
              AND (abs(x.quantidade - m.quantidade) <= 0.001 OR abs(x.valor - m.valor) <= 0.01
                   OR (ce.itens = 1 AND cx.itens = 1))
        UNION ALL BY NAME
        SELECT d.cnpj, d.competencia, d.arquivo, d.chave, d.modelo, d.situacao,
               d.numero_documento, d.serie, d.data, d.operacao, d.emitente, d.participante,
               'XML' AS registro, x.numero_item, x.codigo,
               x.descricao AS descricao_complementar, x.quantidade, x.unidade, x.valor,
               x.desconto, '0' AS ind_mov, x.cst_icms,
               CASE WHEN d.emitente = 'terceiros' THEN coalesce(ca.cfop, {_VIRAR_CFOP})
                    ELSE x.cfop END AS cfop,
               x.bc_icms, x.aliq_icms, x.valor_icms, x.bc_st, x.aliq_st, x.valor_st,
               'xml' AS fonte_item, {_COLUNAS_DO_XML}
        FROM docs_do_xml d
        JOIN xml_itens x ON x.chave = d.chave
        LEFT JOIN cfop_do_analitico ca ON ca.cnpj = d.cnpj AND ca.chave = d.chave
        -- as colunas das contagens não entram: são só do lado da EFD
    """)
    # a nota cancelada na SEFAZ não tem operação: sai da movimentação e fica
    # contada — aqui, antes que o intermediário da EFD seja apagado
    con.execute("""
        CREATE TABLE canceladas_contadas AS
        SELECT count(DISTINCT (m.cnpj, m.chave)) AS documentos, count(*) AS movimentos
        FROM movimentos_com_xml m SEMI JOIN canceladas c ON c.chave = m.chave
    """)
    con.execute("""
        CREATE VIEW movimentos_juntos AS
        SELECT m.* FROM movimentos_com_xml m ANTI JOIN canceladas c ON c.chave = m.chave
    """)


def _resumir_xml(con, p, r: ResumoDaMovimentacao) -> None:
    """O que o XML completou, casou e deixou de fora; e o que saiu por cancelado."""
    r.chaves_canceladas = con.execute("SELECT count(*) FROM canceladas").fetchone()[0]
    (r.documentos_cancelados_na_sefaz, r.movimentos_cancelados) = con.execute(
        "SELECT documentos, movimentos FROM canceladas_contadas").fetchone()
    (r.saidas_completadas_pelo_xml, r.entradas_completadas_pelo_xml) = con.execute("""
        SELECT count(*) FILTER (WHERE operacao = 'saida'), count(*) FILTER (WHERE operacao = 'entrada')
        FROM (SELECT DISTINCT cnpj, chave, operacao FROM docs_do_xml
              WHERE chave IN (SELECT chave FROM xml_itens)
                AND chave NOT IN (SELECT chave FROM canceladas))
    """).fetchone()
    # do parquet final: o intermediário da EFD, em que a view se apoia, já foi apagado
    (r.movimentos_do_xml, r.itens_pareados_com_xml, r.itens_sem_par_no_xml) = con.execute(f"""
        SELECT count(*) FILTER (WHERE fonte_item = 'xml'),
               count(*) FILTER (WHERE fonte_item = 'efd' AND codigo_xml IS NOT NULL),
               count(*) FILTER (WHERE fonte_item = 'efd' AND codigo_xml IS NULL
                                  AND chave IN (SELECT chave FROM xml_chaves))
        FROM read_parquet('{p(ARQUIVO_MOVIMENTOS)}')
    """).fetchone()


def _resumir_contingencia(con, p, r: ResumoDaMovimentacao) -> None:
    c = resumir_contingencia(con, p(ARQUIVO_CONTINGENCIA))
    r.nao_escrituradas_entradas, r.nao_escrituradas_saidas = c["entradas"], c["saidas"]
    r.valor_nao_escriturado_entradas = _dec(c["valor_entradas"])
    r.icms_nao_escriturado_saidas = _dec(c["icms_saidas"])
    r.multa_nao_escrituradas_entradas = _dec(c["multa_entradas"])
    r.multa_nao_escrituradas_saidas = _dec(c["multa_saidas"])
    r.contingencia_por_ano = [Fatia(rotulo=ano, documentos=n, valor=_dec(v), codigo=ano)
                              for ano, n, v in c["por_ano"]]


def _resumir(con, p, conferencia_usada: bool) -> ResumoDaMovimentacao:
    r = ResumoDaMovimentacao(conferencia_usada=conferencia_usada)

    docs = p(ARQUIVO_DOCUMENTOS)
    (r.documentos, r.documentos_com_item, r.entradas_sem_item,
     r.entradas_proprias_sem_item, r.saidas_sem_item, arquivos) = con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE itens > 0),
               count(*) FILTER (WHERE operacao = 'entrada' AND itens = 0
                                  AND emitente = 'terceiros'),
               count(*) FILTER (WHERE operacao = 'entrada' AND itens = 0
                                  AND emitente = 'propria'),
               count(*) FILTER (WHERE operacao = 'saida' AND itens = 0),
               count(DISTINCT arquivo)
        FROM read_parquet('{docs}')
    """).fetchone()
    r.arquivos = arquivos
    r.estabelecimentos = [c for (c,) in con.execute(
        f"SELECT DISTINCT cnpj FROM read_parquet('{docs}') "
        "WHERE cnpj IS NOT NULL AND cnpj <> '' ORDER BY 1").fetchall()]
    r.saidas_sem_item_por_modelo = [
        Fatia(rotulo=_MODELOS.get(m, f"Modelo {m}"), documentos=n, valor=_dec(v),
              codigo=m)
        for m, n, v in con.execute(f"""
            SELECT modelo, count(*), coalesce(sum(valor), 0)
            FROM read_parquet('{docs}') WHERE operacao = 'saida' AND itens = 0
            GROUP BY 1 ORDER BY 2 DESC, 1
        """).fetchall()
    ]

    # o analítico diz quanto dessas saídas é CST 60: mercadoria com ST retida,
    # exatamente o que o razão precisa por item e a EFD não detalha
    valor, valor_st = con.execute(f"""
        SELECT coalesce(sum(valor_operacao), 0),
               coalesce(sum(valor_operacao) FILTER (WHERE right(cst_icms, 2) = '60'), 0)
        FROM read_parquet('{p(ARQUIVO_ANALITICO)}')
        WHERE operacao = 'saida' AND NOT tem_item
    """).fetchone()
    r.valor_saidas_sem_item, r.valor_saidas_sem_item_st = _dec(valor), _dec(valor_st)

    mov = p(ARQUIVO_MOVIMENTOS)
    (r.movimentos, r.movimentos_entrada, r.movimentos_saida, v_ent, v_sai, st,
     r.itens_movimentados, r.itens_sem_cadastro) = con.execute(f"""
        SELECT count(*),
               count(*) FILTER (WHERE operacao = 'entrada'),
               count(*) FILTER (WHERE operacao = 'saida'),
               coalesce(sum(valor) FILTER (WHERE operacao = 'entrada'), 0),
               coalesce(sum(valor) FILTER (WHERE operacao = 'saida'), 0),
               coalesce(sum(valor_st) FILTER (WHERE operacao = 'entrada'), 0),
               count(DISTINCT codigo),
               count(DISTINCT codigo) FILTER (WHERE NOT cadastro_da_efd)
        FROM read_parquet('{mov}')
    """).fetchone()
    r.valor_entradas, r.valor_saidas, r.st_nas_entradas = _dec(v_ent), _dec(v_sai), _dec(st)

    r.por_cst = [
        Fatia(rotulo=f"CST {c}", documentos=n, valor=_dec(v), codigo=c)
        for c, n, v in con.execute(f"""
            SELECT cst_icms, count(*), coalesce(sum(valor), 0)
            FROM read_parquet('{mov}') WHERE operacao = 'entrada'
            GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 12
        """).fetchall()
    ]
    r.por_classificacao = [
        Fatia(rotulo=_CLASSIFICACAO.get(c, c), documentos=n, valor=_dec(v), codigo=c)
        for c, n, v in con.execute(f"""
            SELECT classificacao, count(*), coalesce(sum(valor), 0)
            FROM read_parquet('{mov}') GROUP BY 1 ORDER BY 2 DESC, 1
        """).fetchall()
    ]

    r.itens_cadastrados = con.execute(
        f"SELECT count(*) FROM read_parquet('{p(ARQUIVO_ITENS)}')").fetchone()[0]

    r.inventarios, r.itens_em_estoque, valor = con.execute(f"""
        SELECT count(DISTINCT (cnpj, data_inventario)), count(*),
               coalesce(sum(valor), 0)
        FROM read_parquet('{p(ARQUIVO_INVENTARIO)}')
    """).fetchone()
    r.valor_em_estoque = _dec(valor)
    return r


def _dec(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(Decimal("0.01"))

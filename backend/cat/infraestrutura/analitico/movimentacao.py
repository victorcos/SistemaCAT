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
  contagem de itens igual não basta: na empresa 04, nota com os itens em outra
  ordem no C170 levava o GTIN de um produto para o código de outro. O valor sozinho não serve: na empresa 04 o C170 grava o custo com ST
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
import time
from decimal import Decimal

from cat.dominio.icms.cat42.conferencia import Fatia
from cat.dominio.icms.cat42.movimentacao import ResumoDaMovimentacao
from cat.infraestrutura.analitico.canceladas import ARQUIVO_CHAVES_CANCELADAS, ESQUEMA_CHAVES_CANCELADAS
from cat.infraestrutura.analitico.confronto import SITUACOES_COM_DOCUMENTO, _abrir, _escapar, _limpar
from cat.infraestrutura.analitico.contingencia import (
    ARQUIVO_CONTINGENCIA,
    montar_contingencia,
    resumir_contingencia,
)
from cat.infraestrutura.analitico.itens_do_relatorio import (
    ARQUIVO_ITENS_DO_RELATORIO,
    ESQUEMA_ITENS_DO_RELATORIO,
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
# (coluna em `xml_itens`, nome na saída). É uma lista e não SQL escrito à mão
# porque as colunas saem de duas formas — cruas na perna do XML e condicionais
# na perna da EFD —, e duas listas escritas à mão divergiriam no dia em que
# alguém acrescentasse uma coluna numa só.
_DO_XML = (
    ("arquivo", "arquivo_xml"), ("codigo", "codigo_xml"), ("gtin", "gtin_xml"),
    ("descricao", "descricao_xml"), ("ncm", "ncm_xml"), ("cest", "cest_xml"),
    ("unidade", "unidade_xml"), ("quantidade", "quantidade_xml"),
    ("valor_icms", "valor_icms_xml"), ("bc_st", "bc_st_xml"), ("valor_st", "valor_st_xml"),
    ("base_do_item", "base_do_item_xml"), ("aliquota_efetiva", "aliquota_efetiva_xml"),
    ("reducao_declarada", "reducao_declarada_xml"),
    ("fcp_st", "fcp_st_xml"), ("retido_informado", "retido_xml"),
    ("consumidor_final", "consumidor_final_xml"),
)
_COLUNAS_DO_XML = ",\n    ".join(f"x.{coluna} AS {nome}" for coluna, nome in _DO_XML)

# O que o relatório do cliente acrescenta ao movimento que ele completou.
#
# **Colunas próprias, e não as do XML.** A tentação era reaproveitar
# `descricao_xml` e `ncm_xml` — o `consolidar` já as usa quando o 0200 não tem
# o código. Mas elas querem dizer "o que o XML declarou", e o de-para decide
# por isso: `gtin_xml` vale como prova porque é o fornecedor dizendo, na nota
# autorizada, qual é o código de barras. O que o ERP do cliente diz é outra
# coisa, de outra força. Misturar as duas seria dar ao campo digitado no
# cadastro do cliente o peso de um documento fiscal.
_DO_RELATORIO = (
    ("descricao", "descricao_relatorio"), ("ncm", "ncm_relatorio"),
    ("gtin", "gtin_relatorio"), ("arquivo", "arquivo_relatorio"),
)
_COLUNAS_DO_RELATORIO = ",\n    ".join(f"r.{coluna} AS {nome}" for coluna, nome in _DO_RELATORIO)

# O que decide se o item do XML cola no C170: o número do item casa, e a
# quantidade ou o valor confirmam — ou, sem nenhum dos dois, a nota tem um item
# só nos dois lados.
#
# **Isto fica FORA da cláusula ON, de propósito.** O DuckDB não extrai as
# igualdades quando o ON é `(eq AND eq) AND (OR ...)`: o EXPLAIN mostrava
# `BLOCKWISE_NL_JOIN` de 10.107.934 x 1.053.058 linhas — laço aninhado, 10¹³
# comparações, que na empresa 12 não terminou em 3h19 a 400% de CPU e sem
# escrever um byte. Com a igualdade sozinha no ON o plano vira `HASH_JOIN`, e a
# condição decide aqui se o item vale ou se as colunas do XML saem nulas.
#
# Seguro porque `(chave, numero_item)` é ÚNICO em `xml_itens` — conferido:
# 1.053.058 linhas para 1.053.058 pares distintos —, então o join não
# multiplica linha e nular a coluna dá o mesmo resultado que não casar.
_O_ITEM_COLA = """(abs(x.quantidade - m.quantidade) <= 0.001
         OR abs(x.valor - m.valor) <= 0.01
         OR (m._itens_na_efd = 1 AND m._itens_no_xml = 1))"""

# O número do item não basta. Quem recebe escritura a nota com a numeração DELA:
# na transferência entre filiais de uma empresa de varejo (2026), a EFD da loja
# trazia o item 1 como o lava-roupa e o XML do CD como o alvejante, e o XML ainda
# tinha itens que a EFD não escriturou. Casando só pelo número, 442 mil entradas
# de transferência ficavam sem o XML — e com elas o retido que o XML informa.
# Também o fornecedor que informa o GTIN da caixa (DUN-14) e escritura em unidades
# não casava: nem número, nem quantidade, nem valor.
#
# Por isso a cascata, cada critério só para o que o anterior deixou livre, e só
# quando o par é ÚNICO dos dois lados dentro da chave (um movimento, um item):
#
# 1. código — só na nota da própria empresa (mesma raiz do CNPJ na chave): ali o
#    código do XML é o do cadastro. Em nota de fornecedor o código é o dele, e uma
#    coincidência com o nosso não prova nada;
# 2. número do item, confirmado por quantidade ou valor (a regra de sempre);
# 3. GTIN, pelos 12 dígitos do meio: o EAN-13 e o DUN-14 da caixa dele coincidem aí;
# 4. valor do item.
#
# Cada critério é uma igualdade, para o DuckDB resolver por hash join (ver acima o
# preço de um OR na cláusula ON).
_CRITERIOS_DO_PAR = (
    ("codigo", "x.codigo = e.codigo", "e.mesma_empresa"),
    ("numero", "x.numero_item = e.numero_item", None),
    ("gtin", "x.gtin12 = e.gtin12", "e.gtin12 IS NOT NULL"),
    ("valor", "x.centavos = e.centavos", None),
)
_GTIN12 = """CASE WHEN regexp_full_match(ltrim(trim({0}), '0'), '[0-9]{{7,14}}')
    THEN substr(lpad(ltrim(trim({0}), '0'), 14, '0'), 2, 12) END"""

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
        # sem 0200, a descrição, o código de barras, o NCM e o CEST vêm do XML
        # e, se o XML não tiver, do relatório do cliente — nessa ordem, que é a
        # da força da prova: documento autorizado antes do que o ERP diz.
        # `cadastro_da_efd` continua dizendo quem não está no cadastro.
        #
        # Na empresa 17 isto não é detalhe: o 0200 só lista o item que o
        # arquivo referencia, e a saída dela vai à EFD sem item — o código que
        # só vende não aparece em cadastro nenhum, e sem esta queda a ficha
        # dele sairia sem nome e sem NCM.
        con.execute(f"""
            COPY (
                SELECT m.*,
                       CASE WHEN i.codigo IS NULL
                            THEN coalesce(m.descricao_xml, m.descricao_relatorio)
                            ELSE i.descricao END AS descricao,
                       CASE WHEN i.codigo IS NULL
                            THEN coalesce(m.gtin_xml, m.gtin_relatorio)
                            ELSE i.codigo_barras END AS codigo_barras,
                       CASE WHEN i.codigo IS NULL
                            THEN coalesce(m.ncm_xml, m.ncm_relatorio)
                            ELSE i.ncm END AS ncm,
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
        _resumir_relatorio(con, p, resumo)
        _resumir_contingencia(con, p, resumo)
    finally:
        con.close()
        _limpar(destino)

    log.info("movimentos consolidados",
             extra={"documentos": resumo.documentos,
                    "com_item": resumo.documentos_com_item,
                    "saidas_sem_item": resumo.saidas_sem_item,
                    "completadas_pelo_relatorio": resumo.saidas_completadas_pelo_relatorio,
                    "movimentos_do_relatorio": resumo.movimentos_do_relatorio,
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
    _preparar_relatorio(con, destino, p)
    con.execute("CREATE TABLE xml_contagem AS SELECT chave, count(*) AS itens FROM xml_itens GROUP BY chave")
    con.execute(f"""
        CREATE TABLE efd_contagem AS
        SELECT m.cnpj, m.chave, count(*) AS itens FROM read_parquet('{p(ARQUIVO_MOVIMENTOS_BRUTOS)}') m
        SEMI JOIN xml_contagem k ON k.chave = m.chave
        GROUP BY m.cnpj, m.chave
    """)
    # **Tabela, e não view.** Esta junção é consumida três vezes no
    # `consolidar`: a contagem de canceladas logo abaixo, as
    # `chaves_dos_movimentos` e o COPY que grava `movimentos.parquet`. Como
    # view, ela era recalculada em cada uma delas — e o `LEFT JOIN xml_itens`
    # tem um OR sobre `ce.itens`/`cx.itens`, colunas de outros dois joins, o
    # que impede o DuckDB de resolver como hash join limpo.
    #
    # Na base da empresa 12 (44,6 milhões de documentos, 79 estabelecimentos),
    # a PRIMEIRA das três passadas não terminou em duas horas: 400% de CPU,
    # memória colada no teto de 4 GB e nenhum byte escrito. Materializar paga
    # a junção uma vez, e as duas leituras seguintes são varredura de tabela.
    # **As contagens entram como COLUNA do movimento, antes do join.** Elas são
    # usadas na condição do `LEFT JOIN xml_itens`, e enquanto vinham de dois
    # outros joins (`ce`, `cx`) o OR referenciava três relações ao mesmo tempo —
    # o DuckDB não podia usar a igualdade `(chave, numero_item)` como hash join
    # e caía em laço aninhado.
    #
    # Medido na empresa 12: 10.107.934 movimentos contra 1.053.058 itens de XML,
    # com `(chave, numero_item)` ÚNICO do lado do XML e só 847.013 movimentos
    # com chave que existe lá. Um hash join nesses números é questão de
    # segundos; o laço aninhado seria 10¹³ comparações, e de fato não terminou
    # em 3h19 — 400% de CPU e nenhum byte escrito. Com a contagem já na tabela,
    # o OR só fala de `m` e de `x`, e o plano volta a ser hash join.
    comeco = time.time()
    con.execute(f"""
        CREATE TABLE movimentos_contados AS
        SELECT m.*, ce.itens AS _itens_na_efd, cx.itens AS _itens_no_xml,
               row_number() OVER () AS _id
        FROM read_parquet('{p(ARQUIVO_MOVIMENTOS_BRUTOS)}') m
        LEFT JOIN efd_contagem ce ON ce.cnpj = m.cnpj AND ce.chave = m.chave
        LEFT JOIN xml_contagem cx ON cx.chave = m.chave
    """)
    log.info("movimentos com as contagens ao lado",
             extra={"segundos": round(time.time() - comeco, 1)})

    comeco = time.time()
    _parear_com_o_xml(con, p)
    log.info("itens da EFD pareados com o XML",
             extra={"por_criterio": dict(con.execute(
                 "SELECT por, count(*) FROM pares_xml GROUP BY 1").fetchall()),
                    "segundos": round(time.time() - comeco, 1)})

    comeco = time.time()
    con.execute(f"""
        CREATE TABLE movimentos_com_xml AS
        SELECT m.* EXCLUDE (_itens_na_efd, _itens_no_xml, _id),
               'efd' AS fonte_item, {_COLUNAS_DO_XML}
        FROM movimentos_contados m
        LEFT JOIN pares_xml px ON px._id = m._id
        LEFT JOIN xml_itens x ON x.chave = m.chave AND x.numero_item = px.numero_item_xml
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
        UNION ALL BY NAME
        -- o item que o relatório do cliente completou. Mesma porta do XML, e
        -- depois dele na fila: `docs_do_relatorio` já exclui o que o XML cobre.
        --
        -- **O CFOP entra como está, sem virar o primeiro dígito.** O do XML é
        -- de quem emitiu — numa compra, o 5.401 do fornecedor, que do lado de
        -- quem recebe é 1.401. O do relatório é do ERP do próprio cliente: já
        -- é o CFOP dele. Virar seria trocar entrada por saída.
        SELECT d.cnpj, d.competencia, d.arquivo, d.chave, d.modelo, d.situacao,
               d.numero_documento, d.serie, d.data, d.operacao, d.emitente, d.participante,
               'RELATORIO' AS registro, r.numero_item, r.codigo,
               r.descricao AS descricao_complementar, r.quantidade, r.unidade, r.valor,
               '0' AS ind_mov, r.cst_icms, r.cfop,
               r.bc_icms, r.aliq_icms, r.valor_icms, r.bc_st, r.valor_st,
               'relatorio' AS fonte_item, {_COLUNAS_DO_RELATORIO}
        FROM docs_do_relatorio d
        JOIN rel_itens r ON r.chave = d.chave
    """)
    linhas = con.execute("SELECT count(*) FROM movimentos_com_xml").fetchone()[0]
    log.info("movimentos com XML materializados",
             extra={"linhas": linhas, "segundos": round(time.time() - comeco, 1)})

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


def _preparar_relatorio(con, destino: str, p) -> None:
    """`rel_itens` e `docs_do_relatorio`: o item do relatório do cliente, e o
    documento que ele completa.

    Duas decisões ficam aqui:

    **Uma cópia por chave, escolhida em SQL.** O cliente reexporta, e o mesmo
    documento vem em dois arquivos — na empresa 17, 3,3 milhões de chaves
    repetidas entre os 217 relatórios e a remessa de 13/11. Somar os dois
    dobraria a quantidade vendida de cada item. Fica o arquivo de nome menor,
    que é critério estável: a escolha não muda entre duas rodadas da mesma
    base. Em memória isto seria um `set` de 13,8 milhões de chaves, mais de
    1,5 GB; aqui o DuckDB derrama em disco.

    **Só documento escriturado sem item, e só o que o XML não cobre.** O
    relatório não cria documento: quem diz o que foi escriturado é a EFD.
    E quando os dois têm o mesmo documento vale o XML, que é o que a SEFAZ
    autorizou — o relatório é o que o ERP diz.
    """
    caminho = os.path.join(destino, ARQUIVO_ITENS_DO_RELATORIO)
    if os.path.isfile(caminho):
        con.execute(f"""
            CREATE TABLE rel_fonte AS
            SELECT chave, min(arquivo) AS arquivo
            FROM read_parquet('{_escapar(caminho)}') GROUP BY chave
        """)
        con.execute(f"""
            CREATE TABLE rel_itens AS
            SELECT r.* FROM read_parquet('{_escapar(caminho)}') r
            SEMI JOIN rel_fonte f ON f.chave = r.chave AND f.arquivo = r.arquivo
        """)
    else:
        con.register("rel_vazio", ESQUEMA_ITENS_DO_RELATORIO.empty_table())
        con.execute("CREATE TABLE rel_itens AS SELECT * FROM rel_vazio")
        con.unregister("rel_vazio")
    situacoes = ", ".join(f"'{s}'" for s in SITUACOES_COM_DOCUMENTO)
    con.execute("CREATE TABLE rel_chaves AS SELECT DISTINCT chave FROM rel_itens")
    con.execute(f"""
        CREATE TABLE docs_do_relatorio AS
        SELECT d.* FROM read_parquet('{p(ARQUIVO_DOCUMENTOS)}') d
        SEMI JOIN rel_chaves k ON k.chave = d.chave
        ANTI JOIN xml_chaves x ON x.chave = d.chave
        WHERE d.itens = 0 AND d.situacao IN ({situacoes})
    """)
    log.info("itens do relatório preparados", extra={
        "itens": con.execute("SELECT count(*) FROM rel_itens").fetchone()[0],
        "chaves": con.execute("SELECT count(*) FROM rel_chaves").fetchone()[0],
        "documentos_completados": con.execute(
            "SELECT count(*) FROM docs_do_relatorio").fetchone()[0]})


def _resumir_relatorio(con, p, r: ResumoDaMovimentacao) -> None:
    """O que o relatório do cliente completou — separado do que o XML completou."""
    (r.relatorio_itens, r.relatorio_chaves) = con.execute(
        "SELECT count(*), count(DISTINCT chave) FROM rel_itens").fetchone()
    (r.saidas_completadas_pelo_relatorio, r.entradas_completadas_pelo_relatorio) = con.execute("""
        SELECT count(*) FILTER (WHERE operacao = 'saida'),
               count(*) FILTER (WHERE operacao = 'entrada')
        FROM docs_do_relatorio""").fetchone()
    r.movimentos_do_relatorio = con.execute(
        "SELECT count(*) FROM movimentos_juntos WHERE fonte_item = 'relatorio'").fetchone()[0]


def _parear_com_o_xml(con, p) -> None:
    """Grava `pares_xml(_id, numero_item_xml, por)`: qual item do XML vai ao lado
    de cada C170/C810, pela cascata de `_CRITERIOS_DO_PAR`.

    O par é por estabelecimento: na transferência a mesma chave está na EFD de quem
    enviou e na de quem recebeu, e o mesmo item do XML vale para as duas.
    """
    con.execute(f"""
        CREATE TABLE gtin_do_cadastro AS
        SELECT cnpj, codigo, {_GTIN12.format('arg_max(codigo_barras, competencia)')} AS gtin12
        FROM read_parquet('{p(ARQUIVO_ITENS_DA_EFD)}')
        WHERE coalesce(codigo_barras, '') <> ''
        GROUP BY cnpj, codigo
    """)
    con.execute("""
        CREATE TABLE efd_com_xml AS
        SELECT m._id, m.cnpj, m.chave, m.codigo, m.numero_item, m.quantidade, m.valor,
               m._itens_na_efd, m._itens_no_xml, round(m.valor * 100)::BIGINT AS centavos,
               g.gtin12, substr(m.chave, 7, 8) = substr(m.cnpj, 1, 8) AS mesma_empresa
        FROM movimentos_contados m
        LEFT JOIN gtin_do_cadastro g ON g.cnpj = m.cnpj AND g.codigo = m.codigo
        WHERE m._itens_no_xml IS NOT NULL
    """)
    con.execute(f"""
        CREATE TABLE xml_para_parear AS
        SELECT chave, numero_item, codigo, quantidade, valor,
               round(valor * 100)::BIGINT AS centavos, {_GTIN12.format('gtin')} AS gtin12
        FROM xml_itens
    """)
    con.execute("CREATE TABLE pares_xml (_id BIGINT, numero_item_xml INTEGER, por VARCHAR)")
    con.execute("CREATE TABLE xml_usados (cnpj VARCHAR, chave VARCHAR, numero_item INTEGER)")
    for por, igual, filtro in _CRITERIOS_DO_PAR:
        if por == "numero":
            filtro = _O_ITEM_COLA.replace("m.", "e.")
        # livres dos dois lados: o movimento ainda sem par, o item do XML ainda não
        # usado por este estabelecimento
        con.execute(f"""
            CREATE OR REPLACE TABLE candidatos AS
            SELECT e._id, e.cnpj, e.chave, x.numero_item
            FROM efd_com_xml e
            JOIN xml_para_parear x ON x.chave = e.chave AND {igual}
            WHERE e._id NOT IN (SELECT _id FROM pares_xml)
              AND (e.cnpj, e.chave, x.numero_item) NOT IN (SELECT (cnpj, chave, numero_item) FROM xml_usados)
              {f"AND {filtro}" if filtro else ""}
        """)
        con.execute(f"""
            INSERT INTO pares_xml
            SELECT c._id, any_value(c.numero_item), '{por}'
            FROM candidatos c
            WHERE c._id IN (SELECT _id FROM candidatos GROUP BY _id HAVING count(*) = 1)
              AND (c.cnpj, c.chave, c.numero_item) IN (
                  SELECT (cnpj, chave, numero_item) FROM candidatos
                  GROUP BY cnpj, chave, numero_item HAVING count(*) = 1)
            GROUP BY c._id
        """)
        con.execute(f"""
            INSERT INTO xml_usados
            SELECT e.cnpj, e.chave, px.numero_item_xml FROM pares_xml px
            JOIN efd_com_xml e ON e._id = px._id WHERE px.por = '{por}'
        """)
    con.execute("DROP TABLE candidatos")


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
    r.contingencia_itens_de_nota_vizinha = c["de_nota_vizinha"]
    r.contingencia_itens_sem_referencia = c["sem_referencia"]


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

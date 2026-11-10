"""Os candidatos a de-para, a partir da movimentação da etapa 3.

A regra de quem é o mesmo produto está em `cat.dominio.depara.candidatos`.
Aqui se junta, por estabelecimento e código, o que ela precisa: quanto entrou,
quanto saiu, o estoque de abertura, a descrição, o NCM e os GTINs — do 0200 e
do XML, que no distribuidor é onde o código de barras aparece.

Devolução não conta como entrada nem como saída: a devolução de venda não é de
onde o estoque veio, e a de compra não é venda. Vai à parte, porque ainda é
movimento da ficha — o que decide se juntar dois códigos conserta alguma.

O GTIN vem do 0200 e do XML **do próprio código** (a saída que o XML trouxe).
O do XML pareado com o C170 não entra: o código ali é o do fornecedor, e um
pareamento fora de ordem basta para ligar dois produtos diferentes.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pyarrow.parquet as pq

from cat.dominio.icms.cat42.enquadramento import CFOP_DEVOLUCAO, CFOP_TRANSFERENCIA
from cat.dominio.depara.candidatos import ItemParaCasar, Par, propor
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_ITENS, ARQUIVO_MOVIMENTOS
from cat.infraestrutura.analitico.movimentos import ARQUIVO_INVENTARIO
from cat.infraestrutura.analitico.suportado import _escapar, _leitura
from cat.log import obter_log

log = obter_log(__name__)

# o XML pareado ao C170 conta como o mesmo produto do cadastro? Mesmo capítulo
# de NCM, alguma palavra de 3+ letras em comum, ou cadastro sem descrição
_PALAVRAS = "regexp_extract_all(lower(strip_accents(coalesce({}, ''))), '[a-z]{{3,}}')"
_XML_COMBINA_COM_O_CADASTRO = (
    "(coalesce(descricao, '') = '' OR descricao_xml IS NULL"
    " OR (length(ncm_xml) >= 2 AND left(ncm_xml, 2) = left(ncm, 2))"
    f" OR len(list_intersect({_PALAVRAS.format('descricao_xml')}, {_PALAVRAS.format('descricao')})) > 0)")


def itens_para_casar(pasta_movimentos: str) -> dict[str, list[ItemParaCasar]]:
    """Por estabelecimento, cada código com o que se sabe dele."""
    movimentos = os.path.join(pasta_movimentos, ARQUIVO_MOVIMENTOS)
    if not os.path.isfile(movimentos):
        raise FileNotFoundError(f"{ARQUIVO_MOVIMENTOS} não está em {pasta_movimentos}: rode a etapa 3 antes.")
    colunas = pq.read_schema(movimentos).names
    tem_xml = "fonte_item" in colunas
    proprio = "coalesce(cadastro_da_efd, true)" if "cadastro_da_efd" in colunas else "true"
    # o código de barras do 0200; sem cadastro, o que o consolidar trouxe do XML — só vale na linha do próprio XML
    gtins = (f"list(codigo_barras) FILTER (WHERE {proprio} OR fonte_item = 'xml')" if tem_xml
             else "list(codigo_barras)")
    # **o GTIN que o documento declarou, separado do que o cadastro diz.** São
    # provas de força diferente: o do cadastro é um campo que alguém digitou
    # uma vez — na empresa 04 ele apontava o GTIN de outro produto, e um GTIN
    # sozinho juntava seis itens num. O do XML é o fornecedor dizendo, na nota,
    # qual é o código de barras daquele item. Quando o mesmo GTIN aparece no
    # XML dos dois lados, são dois documentos independentes concordando.
    #
    # **O do XML pareado com o C170 só entra quando o XML combina com o
    # cadastro do código**: mesmo capítulo de NCM ou alguma palavra em comum na
    # descrição. Na empresa 29 o código do creme de leite recebeu, numa
    # entrada, o XML do milho verde (pareamento fora de ordem), e o GTIN do
    # milho ligou os dois. Descartar todo GTIN pareado não serve: lá o 0200
    # quase não tem código de barras, e 167 de 168 pares de GTIN — os certos
    # também — vinham por esse caminho. A conferência derrubou 52 pares
    # errados e nenhum certo.
    if "gtin_xml" not in colunas:
        gtins_do_xml = "[]::VARCHAR[]"
    elif tem_xml and {"descricao_xml", "ncm_xml", "descricao", "ncm"} <= set(colunas):
        gtins_do_xml = f"list(ltrim(gtin_xml, '0')) FILTER (WHERE fonte_item = 'xml' OR {_XML_COMBINA_COM_O_CADASTRO})"
    else:
        gtins_do_xml = "list(ltrim(gtin_xml, '0'))"
    tem_data = "data" in colunas
    tem_valor = "valor" in colunas
    devolucoes = ", ".join(f"'{c}'" for c in sorted(CFOP_DEVOLUCAO))
    transferencias = ", ".join(f"'{c}'" for c in sorted(CFOP_TRANSFERENCIA))
    sem_devolucao = f"replace(cfop, '.', '') NOT IN ({devolucoes})"
    # as semanas em que o código vendeu e comprou: troca de código não convive,
    # dois produtos convivem (`candidatos.SEMANAS_QUE_PROVAM_CONVIVENCIA`)
    semanas = (f"""list(DISTINCT CAST(date_trunc('week', data) AS DATE)) FILTER (WHERE operacao = 'saida' AND {sem_devolucao}) AS semanas_com_saida,
                   list(DISTINCT CAST(date_trunc('week', data) AS DATE)) FILTER (WHERE operacao = 'entrada' AND {sem_devolucao}) AS semanas_com_entrada"""
               if tem_data else "[]::DATE[] AS semanas_com_saida, []::DATE[] AS semanas_com_entrada")
    # custo da entrada e preço da **venda**: a transferência sai a preço de
    # custo (80% das saídas em nota da empresa 29), e no preço ela esconde o kit errado
    valores = (f"""sum(valor - coalesce(desconto, 0)) FILTER (WHERE operacao = 'entrada' AND {sem_devolucao}) AS valor_entradas,
                   sum(valor - coalesce(desconto, 0)) FILTER (WHERE operacao = 'saida' AND {sem_devolucao}
                        AND replace(cfop, '.', '') NOT IN ({transferencias})) AS valor_vendas,
                   sum(quantidade) FILTER (WHERE operacao = 'saida' AND {sem_devolucao}
                        AND replace(cfop, '.', '') NOT IN ({transferencias})) AS quantidade_vendas"""
               if tem_valor else "NULL AS valor_entradas, NULL AS valor_vendas, NULL AS quantidade_vendas")
    inventario = os.path.join(pasta_movimentos, ARQUIVO_INVENTARIO)
    itens = os.path.join(pasta_movimentos, ARQUIVO_ITENS)

    con = _leitura(pasta_movimentos)
    try:
        con.execute(f"""
            CREATE TABLE mov AS
            SELECT cnpj, codigo,
                   sum(quantidade) FILTER (WHERE operacao = 'entrada'
                        AND replace(cfop, '.', '') NOT IN ({devolucoes})) AS entradas,
                   sum(quantidade) FILTER (WHERE operacao = 'saida'
                        AND replace(cfop, '.', '') NOT IN ({devolucoes})) AS saidas,
                   sum(quantidade) FILTER (WHERE operacao = 'entrada'
                        AND replace(cfop, '.', '') IN ({devolucoes})) AS devolucoes_de_venda,
                   sum(quantidade) FILTER (WHERE operacao = 'saida'
                        AND replace(cfop, '.', '') IN ({devolucoes})) AS devolucoes_de_compra,
                   any_value(descricao) AS descricao, any_value(ncm) AS ncm,
                   list_distinct({gtins}) AS gtins,
                   list_distinct({gtins_do_xml}) AS gtins_do_xml,
                   {semanas},
                   {valores}
            FROM read_parquet('{_escapar(movimentos)}')
            GROUP BY cnpj, codigo
        """)
        if os.path.isfile(inventario):
            con.execute(f"""
                CREATE TABLE estoque AS
                SELECT cnpj, codigo, sum(quantidade) AS quantidade
                FROM read_parquet('{_escapar(inventario)}')
                WHERE data_inventario = (SELECT min(data_inventario) FROM read_parquet('{_escapar(inventario)}'))
                GROUP BY cnpj, codigo
            """)
        else:
            con.execute("CREATE TABLE estoque (cnpj VARCHAR, codigo VARCHAR, quantidade DECIMAL(20, 5))")
        # o código que só tem estoque (sem movimento no período) não tem `m`:
        # ligar o cadastro por `m` deixava esse código **sem descrição**, e
        # descrição vazia passa como compatível — na execução 227 o sufixo
        # ligava "FIO PARALELO" (só estoque) a "CABO FLEXIVEL" e, em corrente,
        # joelho de PVC a argamassa
        cadastro = (f"LEFT JOIN read_parquet('{_escapar(itens)}') i"
                    f" ON i.cnpj = coalesce(m.cnpj, e.cnpj) AND i.codigo = coalesce(m.codigo, e.codigo)"
                    if os.path.isfile(itens) else "")
        linhas = con.execute(f"""
            SELECT coalesce(m.cnpj, e.cnpj), coalesce(m.codigo, e.codigo),
                   coalesce({"i.descricao, " if cadastro else ""}m.descricao, ''),
                   coalesce({"i.ncm, " if cadastro else ""}m.ncm, ''),
                   coalesce(m.gtins, []), coalesce(m.gtins_do_xml, []),
                   coalesce(m.entradas, 0), coalesce(m.saidas, 0),
                   coalesce(e.quantidade, 0), coalesce(m.devolucoes_de_venda, 0),
                   coalesce(m.devolucoes_de_compra, 0),
                   coalesce(m.semanas_com_saida, []), coalesce(m.semanas_com_entrada, []),
                   m.valor_entradas, m.valor_vendas, m.quantidade_vendas
            FROM mov m
            FULL JOIN estoque e ON e.cnpj = m.cnpj AND e.codigo = m.codigo
            {cadastro}
            ORDER BY 1, 2
        """).fetchall()
    finally:
        con.close()

    por_estabelecimento: dict[str, list[ItemParaCasar]] = {}
    for (cnpj, codigo, descricao, ncm, gtins, gtins_do_xml, entradas, saidas,
         estoque, dev_venda, dev_compra, sem_saida, sem_entrada,
         valor_entradas, valor_vendas, qtd_vendas) in linhas:
        por_estabelecimento.setdefault(cnpj, []).append(ItemParaCasar(
            codigo=codigo, descricao=descricao, ncm=ncm,
            gtins=frozenset(g for g in gtins if g),
            gtins_do_xml=frozenset(g for g in gtins_do_xml if g),
            entradas=Decimal(entradas or 0),
            saidas=Decimal(saidas or 0), estoque_inicial=Decimal(estoque or 0),
            devolucoes_de_venda=Decimal(dev_venda or 0), devolucoes_de_compra=Decimal(dev_compra or 0),
            semanas_com_saida=frozenset(s for s in sem_saida if s),
            semanas_com_entrada=frozenset(s for s in sem_entrada if s),
            custo_unitario=_unitario(valor_entradas, entradas),
            preco_de_venda=_unitario(valor_vendas, qtd_vendas)))
    return por_estabelecimento


def _unitario(valor, quantidade) -> Decimal | None:
    """Valor ÷ quantidade, ou None quando não há os dois positivos."""
    if not valor or not quantidade or valor <= 0 or quantidade <= 0:
        return None
    return Decimal(valor) / Decimal(quantidade)


def candidatos(pasta_movimentos: str) -> dict[str, list[Par]]:
    """Os pares propostos, por estabelecimento."""
    propostos = {}
    for cnpj, itens in itens_para_casar(pasta_movimentos).items():
        pares = propor(itens)
        if pares:
            propostos[cnpj] = pares
        log.info("candidatos a de-para", extra={"cnpj": cnpj, "codigos": len(itens), "pares": len(pares)})
    return propostos

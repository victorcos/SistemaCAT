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

from cat.dominio.cat42.enquadramento import CFOP_DEVOLUCAO
from cat.dominio.depara.candidatos import ItemParaCasar, Par, propor
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_ITENS, ARQUIVO_MOVIMENTOS
from cat.infraestrutura.analitico.movimentos import ARQUIVO_INVENTARIO
from cat.infraestrutura.analitico.suportado import _escapar, _leitura
from cat.log import obter_log

log = obter_log(__name__)


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
    devolucoes = ", ".join(f"'{c}'" for c in sorted(CFOP_DEVOLUCAO))
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
                   list_distinct({gtins}) AS gtins
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
        cadastro = (f"LEFT JOIN read_parquet('{_escapar(itens)}') i ON i.cnpj = m.cnpj AND i.codigo = m.codigo"
                    if os.path.isfile(itens) else "")
        linhas = con.execute(f"""
            SELECT coalesce(m.cnpj, e.cnpj), coalesce(m.codigo, e.codigo),
                   coalesce({"i.descricao, " if cadastro else ""}m.descricao, ''),
                   coalesce({"i.ncm, " if cadastro else ""}m.ncm, ''),
                   coalesce(m.gtins, []), coalesce(m.entradas, 0), coalesce(m.saidas, 0),
                   coalesce(e.quantidade, 0), coalesce(m.devolucoes_de_venda, 0),
                   coalesce(m.devolucoes_de_compra, 0)
            FROM mov m
            FULL JOIN estoque e ON e.cnpj = m.cnpj AND e.codigo = m.codigo
            {cadastro}
            ORDER BY 1, 2
        """).fetchall()
    finally:
        con.close()

    por_estabelecimento: dict[str, list[ItemParaCasar]] = {}
    for cnpj, codigo, descricao, ncm, gtins, entradas, saidas, estoque, dev_venda, dev_compra in linhas:
        por_estabelecimento.setdefault(cnpj, []).append(ItemParaCasar(
            codigo=codigo, descricao=descricao, ncm=ncm,
            gtins=frozenset(g for g in gtins if g), entradas=Decimal(entradas or 0),
            saidas=Decimal(saidas or 0), estoque_inicial=Decimal(estoque or 0),
            devolucoes_de_venda=Decimal(dev_venda or 0), devolucoes_de_compra=Decimal(dev_compra or 0)))
    return por_estabelecimento


def candidatos(pasta_movimentos: str) -> dict[str, list[Par]]:
    """Os pares propostos, por estabelecimento."""
    propostos = {}
    for cnpj, itens in itens_para_casar(pasta_movimentos).items():
        pares = propor(itens)
        if pares:
            propostos[cnpj] = pares
        log.info("candidatos a de-para", extra={"cnpj": cnpj, "codigos": len(itens), "pares": len(pares)})
    return propostos

"""A leitura dos códigos para o de-para (`itens_para_casar`): o GTIN do XML
pareado, as semanas, o custo e o preço de venda."""

from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.infraestrutura.analitico.depara import itens_para_casar
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_MOVIMENTOS

CNPJ = "00000000000191"
MILHO = "7897517209391"


def linha(codigo, operacao, cfop, quantidade, valor, data, descricao, ncm, fonte="efd",
          gtin_xml=None, descricao_xml=None, ncm_xml=None, codigo_barras=None):
    return dict(cnpj=CNPJ, codigo=codigo, operacao=operacao, cfop=cfop, quantidade=Decimal(quantidade),
                valor=Decimal(valor), desconto=Decimal(0), data=data, descricao=descricao, ncm=ncm,
                fonte_item=fonte, cadastro_da_efd=True, codigo_barras=codigo_barras, gtin_xml=gtin_xml,
                descricao_xml=descricao_xml, ncm_xml=ncm_xml)


def gravar(pasta, linhas):
    tabela = pa.Table.from_pylist(linhas, schema=pa.schema([
        ("cnpj", pa.string()), ("codigo", pa.string()), ("operacao", pa.string()), ("cfop", pa.string()),
        ("quantidade", pa.decimal128(20, 5)), ("valor", pa.decimal128(18, 2)), ("desconto", pa.decimal128(18, 2)),
        ("data", pa.date32()), ("descricao", pa.string()), ("ncm", pa.string()), ("fonte_item", pa.string()),
        ("cadastro_da_efd", pa.bool_()), ("codigo_barras", pa.string()), ("gtin_xml", pa.string()),
        ("descricao_xml", pa.string()), ("ncm_xml", pa.string())]))
    pq.write_table(tabela, str(pasta / ARQUIVO_MOVIMENTOS))


def itens(pasta):
    return {i.codigo: i for i in itens_para_casar(str(pasta))[CNPJ]}


def test_xml_pareado_de_outro_produto_nao_da_gtin(tmp_path):
    """Empresa 29: o C170 do creme de leite recebeu o XML do milho verde."""
    gravar(tmp_path, [
        linha("S1", "entrada", "1102", 10, 30, date(2021, 10, 4), "Cr Leite Tp 200g Italac", "04022930",
              gtin_xml=MILHO, descricao_xml="MILHO VERDE LA 170G FUGINI", ncm_xml="20058000"),
        linha("S1", "saida", "5102", 5, 25, date(2021, 10, 5), "Cr Leite Tp 200g Italac", "04022930", fonte="xml"),
    ])
    assert itens(tmp_path)["S1"].gtins_do_xml == frozenset()


def test_xml_pareado_do_mesmo_produto_da_gtin(tmp_path):
    """Pelo capítulo do NCM, ou por uma palavra em comum na descrição."""
    gravar(tmp_path, [
        linha("M1", "entrada", "1102", 10, 30, date(2021, 10, 4), "Milho Verde Fugini 170g Vapor Lt", "20079910",
              gtin_xml=MILHO, descricao_xml="MILHO VERDE LA 170G FUGINI", ncm_xml="20058000"),
        linha("M2", "entrada", "1102", 10, 30, date(2021, 10, 4), "Milho Fugini 170g", "11111111",
              gtin_xml="0" + MILHO, descricao_xml="MILHO VERDE LA 170G FUGINI", ncm_xml="20058000"),
    ])
    lidos = itens(tmp_path)
    assert lidos["M1"].gtins_do_xml == {MILHO}
    assert lidos["M2"].gtins_do_xml == {MILHO}


def test_semanas_custo_e_preco_sem_transferencia(tmp_path):
    gravar(tmp_path, [
        linha("A", "entrada", "1102", 10, 50, date(2021, 10, 4), "ARROZ 5KG", "10063021"),
        linha("A", "entrada", "1102", 10, 70, date(2021, 10, 13), "ARROZ 5KG", "10063021"),
        linha("A", "saida", "5102", 4, 40, date(2021, 10, 6), "ARROZ 5KG", "10063021"),
        # transferência sai a custo: não entra no preço de venda
        linha("A", "saida", "5152", 100, 600, date(2021, 10, 20), "ARROZ 5KG", "10063021"),
        # devolução não é compra nem venda
        linha("A", "entrada", "1202", 1, 999, date(2021, 10, 27), "ARROZ 5KG", "10063021"),
    ])
    a = itens(tmp_path)["A"]
    assert a.custo_unitario == Decimal(6)
    assert a.preco_de_venda == Decimal(10)
    assert a.semanas_com_entrada == {date(2021, 10, 4), date(2021, 10, 11)}
    assert a.semanas_com_saida == {date(2021, 10, 4), date(2021, 10, 18)}

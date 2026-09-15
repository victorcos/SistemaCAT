"""Os leitores de item da EFD, contra linhas reais.

Cada linha aqui foi copiada de um arquivo verdadeiro desta casa (Sulamericana
e Advertising), com a contagem de campos conferida. Se um leiaute mudar de
versão, é aqui que aparece — antes de deslocar quantidade para valor em
milhões de linhas.
"""

from datetime import date
from decimal import Decimal

from cat.dominio.sped.itens import (
    LEITORES,
    PREFIXOS_DE_ITENS,
    ler_0200,
    ler_0220,
    ler_c170,
    ler_c190,
    ler_c810,
    ler_c850,
    ler_h005,
    ler_h010,
)

# reais, reduzidos onde não importa
L_0200 = "|0200|1000144|Iog Vidativa 160g 0% Gord Desnat Ameixa|7898194090401||CX|00|04031000||04||18|1702200|"
L_C170 = ("|C170|1|1050           08|GRECIN TONS DE GRISALHO|1352|PC|18947,77|0|1|870|1403|300"
          "|0|0|0|0|0|0||||0|0|0|||||||||||||1103010001|0|")
L_C170_COM_ST = ("|C170|3|537861|Abobora P/Doce Kg Frac|20,5|KG|87,65|1,5|0|010|1403|5909"
                 "|87,65|18|15,78|120,4|18|5,89||49||0|0|0||0|0|0|0|0||0|0|0|0|0|1.1.20.01.90.0001|0|")
L_C190 = "|C190|040|1949|0|550,67|0|0|0|0|0|0||"
L_C190_ST = "|C190|010|1403|18|87,65|87,65|15,78|120,4|5,89|0|0||"
L_C850 = "|C850|060|5405|0|36,2|0|0||"
L_H005 = "|H005|31032021|2807100,79|01|"
L_H010 = "|H010|1000144|CX|81|1,19|96,39|0|||1.1.20.01.01|96,39|"


def campos(linha: str) -> list[str]:
    return linha.split("|")


class TestCadastro:
    def test_0200_real(self):
        i = ler_0200(campos(L_0200))
        assert i.codigo == "1000144"
        assert i.descricao.startswith("Iog Vidativa")
        assert i.codigo_barras == "7898194090401"
        assert i.unidade == "CX"
        assert i.tipo_item == "00"
        assert i.ncm == "04031000"
        assert i.cod_gen == "04"
        assert i.aliq_icms == Decimal("18")
        assert i.cest == "1702200"


class TestConversao:
    def test_0220_fator_multiplica_para_a_unidade_do_inventario(self):
        c = ler_0220(campos("|0220|CX|12,000000|7891000100103|"))
        assert c.unidade == "CX" and c.fator == Decimal("12")

    def test_0220_esta_entre_os_registros_lidos(self):
        assert b"|0220|" in PREFIXOS_DE_ITENS and "0220" in LEITORES


class TestItemDeDocumento:
    def test_c170_real_sem_st(self):
        m = ler_c170(campos(L_C170))
        assert m.registro == "C170"
        assert m.numero == 1
        # o código vem com espaços internos no arquivo real; fica como está
        assert m.codigo == "1050           08"
        assert m.quantidade == Decimal("1352")
        assert m.unidade == "PC"
        assert m.valor == Decimal("18947.77")
        assert m.ind_mov == "1"
        assert m.cst_icms == "870"
        assert m.cfop == "1403"
        assert m.valor_st == Decimal("0")

    def test_c170_com_icms_e_st(self):
        m = ler_c170(campos(L_C170_COM_ST))
        assert m.numero == 3
        assert m.quantidade == Decimal("20.5")
        assert m.desconto == Decimal("1.5")
        assert m.cst_icms == "010"
        assert (m.bc_icms, m.aliq_icms, m.valor_icms) == (
            Decimal("87.65"), Decimal("18"), Decimal("15.78"))
        assert (m.bc_st, m.aliq_st, m.valor_st) == (
            Decimal("120.4"), Decimal("18"), Decimal("5.89"))

    def test_c810_do_manual(self):
        m = ler_c810(campos("|C810|2|537861|3|UN|12,9|060|5405|"))
        assert m.registro == "C810"
        assert (m.numero, m.codigo, m.quantidade, m.unidade) == (2, "537861", Decimal("3"), "UN")
        assert m.valor == Decimal("12.9")
        assert (m.cst_icms, m.cfop) == ("060", "5405")


class TestAnalitico:
    def test_c190_real(self):
        a = ler_c190(campos(L_C190))
        assert a.registro == "C190"
        assert (a.cst_icms, a.cfop) == ("040", "1949")
        assert a.valor_operacao == Decimal("550.67")

    def test_c190_com_st(self):
        a = ler_c190(campos(L_C190_ST))
        assert a.aliq_icms == Decimal("18")
        assert (a.bc_icms, a.valor_icms) == (Decimal("87.65"), Decimal("15.78"))
        assert (a.bc_st, a.valor_st) == (Decimal("120.4"), Decimal("5.89"))

    def test_c850_real_nao_tem_st(self):
        a = ler_c850(campos(L_C850))
        assert a.registro == "C850"
        assert (a.cst_icms, a.cfop) == ("060", "5405")
        assert a.valor_operacao == Decimal("36.2")
        assert a.valor_st == Decimal("0")


class TestInventario:
    def test_h005_real(self):
        h = ler_h005(campos(L_H005))
        assert h.data == date(2021, 3, 31)
        assert h.valor_total == Decimal("2807100.79")
        assert h.motivo == "01"

    def test_h010_real(self):
        e = ler_h010(campos(L_H010))
        assert e.codigo == "1000144"
        assert e.unidade == "CX"
        assert e.quantidade == Decimal("81")
        assert e.valor_unitario == Decimal("1.19")
        assert e.valor == Decimal("96.39")
        assert e.ind_prop == "0"
        assert e.cod_cta == "1.1.20.01.01"


def test_todo_prefixo_tem_leitor():
    for prefixo in PREFIXOS_DE_ITENS:
        assert prefixo.decode().strip("|") in LEITORES

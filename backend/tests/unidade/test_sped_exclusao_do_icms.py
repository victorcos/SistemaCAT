"""A exclusão do ICMS da base do PIS/COFINS — o Tema 69, relatório 903.

Este é o primeiro motor desta casa que **calcula** em vez de copiar: o 037 e a
047 medem se sabemos ler o arquivo, este mede se sabemos dizer quanto o cliente
tem a receber. Errar aqui não some numa coluna, vira um pedido de restituição
errado.

A amostra carrega as regras que o dado real ensinou:

- os **quatro filtros** que decidem quem entra — CFOP de venda ou de devolução
  de venda, ICMS destacado, base de PIS/COFINS e contribuição paga;
- a nota **cuja base já excluiu o ICMS**, que aparece com exclusão zero em vez
  de sumir: quem apurou certo precisa ver que foi conferido;
- o **rateio** do frete/seguro/despesas, repartido pelo valor do item sobre a
  soma de **todos** os itens da nota, inclusive os que não entram;
- a última nota de um bloco `C010`, que é do estabelecimento que **termina**
  ali — foi assim que 61 linhas saíram com o CNPJ da filial seguinte.

As linhas são montadas por nome de campo, nunca contando barras.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cat.infraestrutura.sped.exclusao_do_icms import (
    DEVOLUCAO_DE_FATURAMENTO,
    FATURAMENTO,
    exclusoes_do_icms,
)
from cat.infraestrutura.sped.registros import CAMPOS

MATRIZ = "11222333000181"
FILIAL = "11222333000262"

# o mês da restituição usado na amostra
ATE = "2026-09"


def reg(nome: str, **campos: str) -> str:
    valores = [campos.get(c, "") for c in CAMPOS[nome]]
    valores[0] = nome
    return "|" + "|".join(valores) + "|"


def c170(**campos: str) -> str:
    """Um item de venda tributada, com o que quase todos têm preenchido."""
    padrao = {
        "CFOP": "5102", "CST_PIS": "01", "CST_COFINS": "01",
        "ALIQ_PIS_PERC": "1,6500", "ALIQ_COFINS_PERC": "7,6000",
    }
    return reg("C170", **(padrao | campos))


EFD = "\n".join([
    reg("0000", COD_VER="006", TIPO_ESCRIT="0", DT_INI="01102022", DT_FIN="31102022",
        NOME="COMERCIO DO TESTE LTDA", CNPJ=MATRIZ, UF="MG", COD_MUN="3106200",
        IND_NAT_PJ="0", IND_ATIV="0"),

    # ---- bloco C da MATRIZ ---------------------------------------------
    reg("C010", CNPJ=MATRIZ),

    # nota com frete e despesa para ratear: 100,00 sobre 1.000,00 de itens.
    # O item 3 não entra no relatório, mas continua no denominador
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="1001", CHV_NFE="31" + "1" * 42, DT_DOC="03102022",
        DT_E_S="03102022", VL_DOC="1100,00", VL_MERC="1000,00", VL_FRT="60,00",
        VL_SEG="15,00", VL_OUT_DA="25,00"),
    # entra: venda, com ICMS, base e contribuição
    c170(NUM_ITEM="1", COD_ITEM="SKU1", VL_ITEM="500,00", VL_BC_ICMS="500,00",
         ALIQ_ICMS="18,00", VL_ICMS="90,00", VL_BC_PIS="500,00", VL_PIS="8,25",
         VL_BC_COFINS="500,00", VL_COFINS="38,00"),
    # entra, e a base DELE já excluiu o ICMS: 300 + 30 de rateio - 54 = 276
    c170(NUM_ITEM="2", COD_ITEM="SKU2", VL_ITEM="300,00", VL_BC_ICMS="300,00",
         ALIQ_ICMS="18,00", VL_ICMS="54,00", VL_BC_PIS="276,00", VL_PIS="4,55",
         VL_BC_COFINS="276,00", VL_COFINS="20,98"),
    # não entra: CST 04, monofásico — sem contribuição paga
    c170(NUM_ITEM="3", COD_ITEM="SKU3", VL_ITEM="200,00", VL_BC_ICMS="200,00",
         ALIQ_ICMS="18,00", VL_ICMS="36,00", CST_PIS="04", CST_COFINS="04",
         ALIQ_PIS_PERC="0,0000", ALIQ_COFINS_PERC="0,0000", VL_BC_PIS="0,00",
         VL_PIS="0,00", VL_BC_COFINS="0,00", VL_COFINS="0,00"),

    # nota só com o que não entra
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="1002", CHV_NFE="31" + "2" * 42, DT_DOC="04102022",
        DT_E_S="04102022", VL_DOC="400,00", VL_MERC="400,00"),
    # CFOP de transferência: não é receita
    c170(NUM_ITEM="1", COD_ITEM="SKU1", CFOP="5152", VL_ITEM="100,00",
         VL_BC_ICMS="100,00", ALIQ_ICMS="18,00", VL_ICMS="18,00", VL_BC_PIS="100,00",
         VL_PIS="1,65", VL_BC_COFINS="100,00", VL_COFINS="7,60"),
    # venda sem ICMS destacado: não há o que excluir
    c170(NUM_ITEM="2", COD_ITEM="SKU2", VL_ITEM="100,00", VL_BC_ICMS="0,00",
         ALIQ_ICMS="0,00", VL_ICMS="0,00", VL_BC_PIS="100,00", VL_PIS="1,65",
         VL_BC_COFINS="100,00", VL_COFINS="7,60"),
    # venda com ICMS mas sem base de PIS/COFINS
    c170(NUM_ITEM="3", COD_ITEM="SKU3", VL_ITEM="200,00", VL_BC_ICMS="200,00",
         ALIQ_ICMS="18,00", VL_ICMS="36,00", CST_PIS="06", CST_COFINS="06",
         ALIQ_PIS_PERC="0,0000", ALIQ_COFINS_PERC="0,0000", VL_BC_PIS="0,00",
         VL_PIS="0,00", VL_BC_COFINS="0,00", VL_COFINS="0,00"),

    # devolução de venda: entra, e sai marcada como tal
    reg("C100", IND_OPER="0", IND_EMIT="1", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="1003", CHV_NFE="31" + "3" * 42, DT_DOC="05102022",
        DT_E_S="05102022", VL_DOC="100,00", VL_MERC="100,00"),
    c170(NUM_ITEM="1", COD_ITEM="SKU1", CFOP="1202", VL_ITEM="100,00",
         VL_BC_ICMS="100,00", ALIQ_ICMS="18,00", VL_ICMS="18,00", VL_BC_PIS="100,00",
         VL_PIS="1,65", VL_BC_COFINS="100,00", VL_COFINS="7,60"),

    # ---- a ÚLTIMA nota da matriz, colada no C010 da filial --------------
    # é este documento que o buffer do rateio segurava quando o CNPJ trocava
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="1004", CHV_NFE="31" + "4" * 42, DT_DOC="06102022",
        DT_E_S="06102022", VL_DOC="200,00", VL_MERC="200,00"),
    c170(NUM_ITEM="1", COD_ITEM="SKU1", VL_ITEM="200,00", VL_BC_ICMS="200,00",
         ALIQ_ICMS="18,00", VL_ICMS="36,00", VL_BC_PIS="200,00", VL_PIS="3,30",
         VL_BC_COFINS="200,00", VL_COFINS="15,20"),

    # ---- bloco C da FILIAL ---------------------------------------------
    reg("C010", CNPJ=FILIAL),
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="2001", CHV_NFE="41" + "5" * 42, DT_DOC="07102022",
        DT_E_S="07102022", VL_DOC="150,00", VL_MERC="150,00"),
    c170(NUM_ITEM="1", COD_ITEM="SKU9", VL_ITEM="150,00", VL_BC_ICMS="150,00",
         ALIQ_ICMS="12,00", VL_ICMS="18,00", VL_BC_PIS="150,00", VL_PIS="2,48",
         VL_BC_COFINS="150,00", VL_COFINS="11,40"),
    "|9999|30|",
    "",
])


@pytest.fixture
def arquivo(tmp_path):
    caminho = tmp_path / "contribuicoes.txt"
    caminho.write_bytes(EFD.encode("cp1252"))
    return str(caminho)


@pytest.fixture
def linhas(arquivo):
    return list(exclusoes_do_icms(arquivo, "cp1252", ATE))


def uma(linhas, **igual):
    achadas = [linha for linha in linhas
               if all(getattr(linha, campo) == valor for campo, valor in igual.items())]
    assert len(achadas) == 1, f"{len(achadas)} linhas casam com {igual}"
    return achadas[0]


class TestQuemEntra:
    def test_so_as_cinco_que_passam_nos_quatro_filtros(self, linhas):
        assert [(linha.numero_do_documento, linha.numero_do_item) for linha in linhas] == [
            ("1001", "1"), ("1001", "2"), ("1003", "1"), ("1004", "1"), ("2001", "1")]

    def test_transferencia_fica_de_fora(self, linhas):
        assert not [linha for linha in linhas if linha.cfop == "5152"]

    def test_venda_sem_icms_destacado_fica_de_fora(self, linhas):
        """Sem ICMS na nota não há o que excluir da base."""
        assert not [linha for linha in linhas if linha.numero_do_documento == "1002"]

    def test_devolucao_de_venda_entra_marcada(self, linhas):
        assert uma(linhas, numero_do_documento="1003").cfop_faturamento == (
            DEVOLUCAO_DE_FATURAMENTO)

    def test_venda_sai_marcada_como_faturamento(self, linhas):
        assert uma(linhas, numero_do_documento="1004").cfop_faturamento == FATURAMENTO


class TestOEstabelecimento:
    def test_a_ultima_nota_do_bloco_e_de_quem_termina_ali(self, linhas):
        """O C010 da filial não pode levar a nota que a matriz deixou no buffer."""
        assert uma(linhas, numero_do_documento="1004").cnpj == MATRIZ

    def test_a_nota_da_filial_e_da_filial(self, linhas):
        assert uma(linhas, numero_do_documento="2001").cnpj == FILIAL


class TestORateio:
    def test_reparte_pelo_valor_do_item_sobre_todos_os_itens(self, linhas):
        """100,00 de frete+seguro+despesa sobre 1.000,00 de itens.

        O item 3 não entra no relatório e continua no denominador: o frete foi
        pago pela nota inteira.
        """
        assert uma(linhas, numero_do_documento="1001",
                   numero_do_item="1").rateio == "50.00"
        assert uma(linhas, numero_do_documento="1001",
                   numero_do_item="2").rateio == "30.00"

    def test_nota_sem_frete_nao_rateia_nada(self, linhas):
        assert uma(linhas, numero_do_documento="1004").rateio == "0"


class TestAConta:
    def test_a_base_recalculada_sai_do_proprio_item(self, linhas):
        """valor - desconto + rateio - ICMS: 500 - 0 + 50 - 90."""
        linha = uma(linhas, numero_do_documento="1001", numero_do_item="1")
        assert linha.base_recalculada == "460.00"
        assert linha.base_stf == "410.00"          # base - ICMS
        assert linha.diferenca_da_base == "90.00"  # o ICMS que se exclui

    def test_pis_e_cofins_saem_da_base_stf(self, linhas):
        linha = uma(linhas, numero_do_documento="1001", numero_do_item="1")
        assert linha.pis_stf == "6.77"            # 410,00 x 1,65%
        assert linha.cofins_stf == "31.16"        # 410,00 x 7,60%
        assert linha.diferenca_do_pis == "1.48"   # 8,25 - 6,77
        assert linha.diferenca_da_cofins == "6.84"

    def test_a_selic_corrige_a_diferenca(self, linhas):
        """10/2022 corrigida até 09/2026: 47,24% — a acumulada da tabela."""
        linha = uma(linhas, numero_do_documento="1001", numero_do_item="1")
        assert linha.selic_acumulada == "47.24"
        assert linha.selic_sobre_o_pis == "0.70"       # 1,48 x 47,24%
        assert linha.total_do_pis_a_recuperar == "2.18"

    def test_quem_ja_excluiu_aparece_com_exclusao_zero(self, linhas):
        """A linha existe, e o crédito é zero. Sumir esconderia a conferência."""
        linha = uma(linhas, numero_do_documento="1001", numero_do_item="2")
        assert linha.base == linha.base_recalculada == "276.00"
        assert linha.base_stf == "0"
        assert linha.diferenca_do_pis == "0"
        assert Decimal(linha.total_a_recuperar_atualizado) == 0

    def test_o_total_soma_pis_e_cofins_corrigidos(self, linhas):
        linha = uma(linhas, numero_do_documento="2001")
        esperado = (Decimal(linha.total_do_pis_a_recuperar)
                    + Decimal(linha.total_da_cofins_a_recuperar))
        assert Decimal(linha.total_a_recuperar_atualizado) == esperado

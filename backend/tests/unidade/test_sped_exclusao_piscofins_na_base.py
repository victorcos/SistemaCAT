"""As próprias contribuições fora da base, item a item — o relatório 680.

A quarta tese da família e a maior: 3.568.362 linhas no arquivo de referência do
MA, conferidas 100% nas 35 colunas. A amostra carrega as regras que **o dado
real ensinou**, e cada uma delas custou uma rodada inteira de conferência:

- os **quatro ramos**, e o que cada um tem: só o `C100/C170` traz ICMS, desconto
  e rateio; o `C100/C175` traz só o desconto; o `A100/A170` e o `F100` não trazem
  nenhum dos três — **nem quando o leiaute tem o campo**. Escrever zero no lugar
  do vazio divergia em 71.837 linhas de uma competência só;
- o **rateio** do frete/seguro/despesas no C170, repartido pelo valor do item
  sobre a soma de **todos** os itens da nota, inclusive os que não entram. São 10
  linhas não-zero em 3,5 milhões, e é por elas que o documento é guardado;
- o **F100 somado por dia**: ele não tem documento, modelo nem item que
  distingam duas linhas suas, e o MA emite uma só. Somar reduziu 841 linhas
  nossas às 334 dele;
- o **sentido do registro sem CFOP**, que vem do `IND_OPER` e não de suposição:
  F100 de aquisição e serviço contratado ficam fora. Tratá-los como faturamento
  trazia CST 50 — crédito, que só existe na entrada — para dentro da tese;
- **tributada basta, paga não é exigido**: a linha de R$ 0,06 com CST 01 e
  alíquota cheia recolhe R$ 0,00 por arredondamento, e o MA a traz;
- a última nota de um bloco `C010`, que é do estabelecimento que **termina** ali,
  e a última do arquivo, que não tem outra depois para fechá-la.

As linhas são montadas por nome de campo, nunca contando barras.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cat.infraestrutura.sped.exclusao_piscofins_na_base import (
    RAMO_A170,
    RAMO_C170,
    RAMO_C175,
    RAMO_F100,
    exclusoes_do_piscofins,
)
from cat.infraestrutura.sped.registros import CAMPOS
from cat.infraestrutura.sped.tabelas.tab_cfop_receita import (
    DEVOLUCAO_DE_FATURAMENTO,
    FATURAMENTO,
    classificacao_do_cfop,
)

MATRIZ = "11222333000181"
FILIAL = "11222333000262"

ATE = "2026-09"

# a Selic entra por fora: 50% deixa a conferência da correção à vista — o que
# volta vira metade de si mesmo, e um erro de centavo não se esconde
SELIC = {"2022-10": Decimal("50")}


def reg(nome: str, **campos: str) -> str:
    valores = [campos.get(c, "") for c in CAMPOS[nome]]
    valores[0] = nome
    return "|" + "|".join(valores) + "|"


def c170(**campos: str) -> str:
    """Um item de venda tributada, com o que quase todos têm preenchido."""
    padrao = {"CFOP": "5102", "CST_PIS": "01", "CST_COFINS": "01",
              "ALIQ_PIS_PERC": "1,6500", "ALIQ_COFINS_PERC": "7,6000"}
    return reg("C170", **(padrao | campos))


def c175(**campos: str) -> str:
    padrao = {"CFOP": "5102", "CST_PIS": "01", "CST_COFINS": "01",
              "ALIQ_PIS": "1,6500", "ALIQ_COFINS": "7,6000"}
    return reg("C175", **(padrao | campos))


def f100(**campos: str) -> str:
    padrao = {"IND_OPER": "1", "CST_PIS": "01", "CST_COFINS": "01",
              "ALIQ_PIS": "1,6500", "ALIQ_COFINS": "7,6000"}
    return reg("F100", **(padrao | campos))


EFD = "\n".join([
    reg("0000", COD_VER="006", TIPO_ESCRIT="0", DT_INI="01102022", DT_FIN="31102022",
        NOME="COMERCIO DO TESTE LTDA", CNPJ=MATRIZ, UF="MG", COD_MUN="3106200",
        IND_NAT_PJ="0", IND_ATIV="0"),
    reg("0140", COD_EST="001", NOME="MATRIZ", CNPJ=MATRIZ, UF="MG", IE="111",
        COD_MUN="3106200"),
    reg("0200", COD_ITEM="SKU1", DESCR_ITEM="ARROZ 5KG", UNID_INV="PC",
        TIPO_ITEM="00", COD_NCM="10063021"),
    reg("0200", COD_ITEM="SKU2", DESCR_ITEM="FEIJAO 1KG", UNID_INV="PC",
        TIPO_ITEM="00", COD_NCM="07133319"),
    reg("0200", COD_ITEM="SRV1", DESCR_ITEM="PRESTACAO DE SERVICO", UNID_INV="UN",
        TIPO_ITEM="09"),
    reg("0140", COD_EST="002", NOME="FILIAL", CNPJ=FILIAL, UF="MG", IE="222",
        COD_MUN="3106200"),
    reg("0200", COD_ITEM="SKU1", DESCR_ITEM="ARROZ 5KG DA FILIAL", UNID_INV="PC",
        TIPO_ITEM="00", COD_NCM="10063021"),

    # ---- bloco C da MATRIZ ---------------------------------------------
    reg("C010", CNPJ=MATRIZ),

    # nota com frete, seguro e despesa: 100,00 a ratear sobre 1.000,00 de itens.
    # O item 3 não entra no relatório e **continua no denominador**
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="1001", CHV_NFE="31" + "1" * 42, DT_DOC="03102022",
        DT_E_S="03102022", VL_DOC="1100,00", VL_MERC="1000,00", VL_FRT="60,00",
        VL_SEG="15,00", VL_OUT_DA="25,00"),
    c170(NUM_ITEM="1", COD_ITEM="SKU1", VL_ITEM="500,00", VL_DESC="0,00",
         VL_BC_ICMS="500,00", ALIQ_ICMS="18,00", VL_ICMS="90,00",
         VL_BC_PIS="500,00", VL_PIS="8,25", VL_BC_COFINS="500,00", VL_COFINS="38,00"),
    c170(NUM_ITEM="2", COD_ITEM="SKU2", VL_ITEM="300,00", VL_DESC="10,00",
         VL_BC_ICMS="300,00", ALIQ_ICMS="18,00", VL_ICMS="54,00",
         VL_BC_PIS="300,00", VL_PIS="4,95", VL_BC_COFINS="300,00", VL_COFINS="22,80"),
    # remessa para industrialização: não é receita, e sai pelo CFOP
    c170(NUM_ITEM="3", COD_ITEM="SKU1", CFOP="5924", VL_ITEM="200,00",
         VL_BC_PIS="200,00", VL_PIS="3,30", VL_BC_COFINS="200,00", VL_COFINS="15,20"),

    # devolução de venda: entra com o CST de crédito que tiver
    reg("C100", IND_OPER="0", IND_EMIT="1", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="2001", CHV_NFE="31" + "2" * 42, DT_DOC="04102022",
        DT_E_S="04102022", VL_DOC="100,00", VL_MERC="100,00"),
    c170(NUM_ITEM="1", COD_ITEM="SKU1", CFOP="1411", CST_PIS="50", CST_COFINS="50",
         VL_ITEM="100,00", VL_DESC="0,00", VL_ICMS="18,00",
         VL_BC_PIS="100,00", VL_PIS="1,65", VL_BC_COFINS="100,00", VL_COFINS="7,60"),

    # NFC-e: o analítico C175 não tem item, nem ICMS, nem rateio
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_MOD="65", COD_SIT="00", SER="1",
        NUM_DOC="3001", CHV_NFE="31" + "3" * 42, DT_DOC="05102022", DT_E_S="05102022",
        VL_DOC="100,06", VL_MERC="100,06"),
    c175(VL_OPR="100,00", VL_DESC="0,00", VL_BC_PIS="100,00", VL_PIS="1,65",
         VL_BC_COFINS="100,00", VL_COFINS="7,60"),
    # tributada, e recolhe zero nas duas por arredondamento: o MA a traz
    c175(VL_OPR="0,06", VL_DESC="0,00", VL_BC_PIS="0,06", VL_PIS="0,00",
         VL_BC_COFINS="0,06", VL_COFINS="0,00"),

    # ---- bloco C da FILIAL --------------------------------------------
    # o C010 fecha o documento anterior: sem isso a nota 3001 sairia com o CNPJ
    # da filial, que foi como 61 linhas saíram erradas no 903
    reg("C010", CNPJ=FILIAL),
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="4001", CHV_NFE="31" + "4" * 42, DT_DOC="06102022",
        DT_E_S="06102022", VL_DOC="200,00", VL_MERC="200,00"),
    c170(NUM_ITEM="1", COD_ITEM="SKU1", VL_ITEM="200,00", VL_DESC="0,00",
         VL_ICMS="36,00", VL_BC_PIS="200,00", VL_PIS="3,30",
         VL_BC_COFINS="200,00", VL_COFINS="15,20"),

    # ---- o resumo diário do SAT-CF-e ------------------------------------
    # O C860 vale para os C870 que vierem depois, como o C100 para os C170.
    # "Número Documento" é o DOC_INIC — medido contra o gabarito do MA em
    # 07/10/2026: das 51 combinações de (data, número), o DOC_INIC explica 51,
    # o NR_SAT nenhuma e o DOC_FIM nenhuma
    reg("C860", COD_MOD="59", NR_SAT="900111", DT_DOC="20102022",
        DOC_INIC="5500", DOC_FIM="5620"),
    reg("C870", COD_ITEM="SKU1", CFOP="5102", VL_ITEM="200,00", VL_DESC="0,00",
        CST_PIS="01", VL_BC_PIS="200,00", ALIQ_PIS_PERC="1,6500", VL_PIS="3,30",
        CST_COFINS="01", VL_BC_COFINS="200,00", ALIQ_COFINS_PERC="7,6000",
        VL_COFINS="15,20"),
    # CST 06 (alíquota zero): não há contribuição, logo não há o que excluir
    reg("C870", COD_ITEM="SKU2", CFOP="5102", VL_ITEM="80,00", VL_DESC="0,00",
        CST_PIS="06", VL_BC_PIS="0", ALIQ_PIS_PERC="0", VL_PIS="0",
        CST_COFINS="06", VL_BC_COFINS="0", ALIQ_COFINS_PERC="0", VL_COFINS="0"),

    # ---- bloco A: serviço prestado e serviço contratado -----------------
    reg("A010", CNPJ=MATRIZ),
    # prestado: entra. O A170 tem VL_DESC no leiaute, e o MA o deixa em branco
    reg("A100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_SIT="00", SER="A",
        NUM_DOC="55", DT_DOC="07102022", DT_EXE_SERV="07102022", VL_DOC="1000,00",
        VL_ISS="50,00"),
    reg("A170", NUM_ITEM="1", COD_ITEM="SRV1", VL_ITEM="1000,00", VL_DESC="20,00",
        CST_PIS="01", VL_BC_PIS="1000,00", ALIQ_PIS="1,6500", VL_PIS="16,50",
        CST_COFINS="01", VL_BC_COFINS="1000,00", ALIQ_COFINS="7,6000",
        VL_COFINS="76,00"),
    # contratado: é crédito, não receita. Fica fora, e o CST 50 diz por quê
    reg("A100", IND_OPER="0", IND_EMIT="1", COD_PART="C01", COD_SIT="00", SER="A",
        NUM_DOC="66", DT_DOC="08102022", DT_EXE_SERV="08102022", VL_DOC="900,00"),
    reg("A170", NUM_ITEM="1", COD_ITEM="SRV1", VL_ITEM="900,00", CST_PIS="50",
        VL_BC_PIS="900,00", ALIQ_PIS="1,6500", VL_PIS="14,85", CST_COFINS="50",
        VL_BC_COFINS="900,00", ALIQ_COFINS="7,6000", VL_COFINS="68,40"),

    # ---- bloco F: demais documentos, somados por dia -------------------
    reg("F010", CNPJ=MATRIZ),
    f100(DT_OPER="31102022", VL_OPER="1000,00", VL_BC_PIS="1000,00", VL_PIS="16,50",
         VL_BC_COFINS="1000,00", VL_COFINS="76,00"),
    f100(DT_OPER="31102022", VL_OPER="500,00", VL_BC_PIS="500,00", VL_PIS="8,25",
         VL_BC_COFINS="500,00", VL_COFINS="38,00"),
    # outro dia: linha própria, e não se soma com as de cima
    f100(DT_OPER="15102022", VL_OPER="200,00", VL_BC_PIS="200,00", VL_PIS="3,30",
         VL_BC_COFINS="200,00", VL_COFINS="15,20"),
    # aquisição: fica fora, e o CST 50 diz por quê
    f100(IND_OPER="0", DT_OPER="31102022", VL_OPER="9999,00", CST_PIS="50",
         CST_COFINS="50", VL_BC_PIS="9999,00", VL_PIS="164,98",
         VL_BC_COFINS="9999,00", VL_COFINS="759,92"),

    "|9999|40|",
    "",
])


@pytest.fixture(scope="module")
def linhas(tmp_path_factory):
    caminho = tmp_path_factory.mktemp("680") / "contribuicoes.txt"
    caminho.write_bytes(EFD.encode("cp1252"))
    return list(exclusoes_do_piscofins(str(caminho), "cp1252", ATE, acumulada=SELIC))


@pytest.fixture(scope="module")
def por_chave(linhas):
    """As linhas por (registro, documento, item) — a ordem de saída não é a do arquivo.

    O C170 sai quando a nota fecha e o F100 só no fim do arquivo; indexar pelo
    que identifica a linha é o que deixa o teste medir a regra e não a ordem.

    **O ramo sem item se identifica pelo valor.** Dois C175 da mesma NFC-e não
    têm número de item que os separe — é por não ter nada disso que o F100 acaba
    somado por dia.
    """
    return {(l.registro, l.numero_do_documento,
             l.numero_do_item or l.valor_do_item): l for l in linhas}


class TestQuemEntra:
    def test_so_as_linhas_de_receita_saem(self, linhas, por_chave):
        """Dez linhas: duas do 1001, a devolução, os dois C175, a filial, o
        serviço prestado, dois F100 (um por dia) e **um C870**.

        O segundo C870 tem CST 06 — alíquota zero — e por isso não entra: não
        há contribuição embutida, logo não há o que excluir.
        """
        assert len(linhas) == 10
        assert len(por_chave) == 10, "duas linhas disputaram a mesma identidade"

    def test_o_cfop_fora_da_receita_fica_de_fora(self, por_chave):
        """A remessa para industrialização tem contribuição apurada e não entra."""
        assert (RAMO_C170, "1001", "3") not in por_chave

    def test_a_devolucao_de_venda_entra_com_o_cst_de_credito(self, por_chave):
        linha = por_chave[(RAMO_C170, "2001", "1")]

        assert linha.cfop_faturamento == DEVOLUCAO_DE_FATURAMENTO
        assert linha.cst == "50"

    def test_tributada_que_recolhe_zero_entra(self, por_chave):
        """R$ 0,06 com CST 01: as duas contribuições arredondam para zero."""
        tributada = [l for l in por_chave.values()
                     if l.registro == RAMO_C175 and l.valor_do_item == "0.06"]

        assert len(tributada) == 1
        assert tributada[0].pis == "0.00"
        assert tributada[0].aliquota_do_pis == "1.6500"

    def test_o_servico_contratado_fica_fora(self, por_chave):
        """O A100 de IND_OPER 0 é crédito: a nota 66 não aparece."""
        assert (RAMO_A170, "66", "1") not in por_chave
        assert (RAMO_A170, "55", "1") in por_chave

    def test_o_f100_de_aquisicao_fica_fora(self, linhas):
        """Sem CFOP para perguntar, o IND_OPER é quem diz o sentido."""
        assert not [l for l in linhas if l.registro == RAMO_F100 and l.cst == "50"]


class TestOCfopQueCompoeReceita:
    """Quais CFOP a tese reconhece como faturamento — e por que importa.

    Até 06/10/2026 `classificacao_do_cfop` perguntava a natureza da operação
    **sem passar a descrição do CFOP**. Sem ela, `tab_cfop_natureza_operacao`
    só sabe responder pelos 21 CFOP da tabela medida, e desses apenas **seis**
    são venda. Resultado: num cliente industrial, o 5101 e o 6101 — venda de
    produção do próprio estabelecimento — caíam inteiros em "CFOP fora da
    receita", e a tese saía esvaziada.

    O relatório 047 nunca teve o problema, porque sempre passou a descrição
    (`sped/saidas.py::_da_operacao`): era o mesmo classificador respondendo
    diferente conforme quem perguntava.

    Estes testes prendem os dois lados — o que passou a entrar e, sobretudo, o
    que **não pode** entrar junto.
    """

    def test_a_venda_de_producao_propria_entra(self):
        """O CFOP central da indústria. É o que estava faltando."""
        assert classificacao_do_cfop("5101") == FATURAMENTO
        assert classificacao_do_cfop("6101") == FATURAMENTO

    def test_as_outras_vendas_da_familia_tambem(self):
        for cfop in ("5103", "5104", "5105", "5109", "5110", "5116", "5117"):
            assert classificacao_do_cfop(cfop) == FATURAMENTO, cfop

    def test_o_cfop_do_ecf_continua_fora(self):
        """**OBS 2 do MA.** O X929 é a nota que duplica um cupom já registrado
        no ECF. Entrar aqui contaria a mesma receita duas vezes."""
        for cfop in ("5929", "6929", "1929", "2929"):
            assert classificacao_do_cfop(cfop) == "", cfop

    def test_a_tabela_medida_vence_a_descricao(self):
        """O 5209 começa com "Devol" e o MA o classifica como **Transferência**,
        pela natureza da operação original. É a exceção que faz a tabela medida
        existir — ver `tab_cfop_natureza_operacao`. Se a descrição passasse na
        frente dela, esta devolução viraria receita."""
        assert classificacao_do_cfop("5209") == ""

    def test_devolucao_de_compra_nao_e_devolucao_de_venda(self):
        """Estorno de uma entrada, não de uma receita: não compõe faturamento."""
        assert classificacao_do_cfop("5202") == ""
        assert classificacao_do_cfop("1202") == DEVOLUCAO_DE_FATURAMENTO

    def test_remessa_e_transferencia_seguem_fora(self):
        for cfop in ("5901", "5910", "5152", "5949"):
            assert classificacao_do_cfop(cfop) == "", cfop


class TestOResumoDiarioDoSat:
    """O ramo C860/C870, que faltava até 07/10/2026.

    **Por que faltava doía.** Numa base de varejo o C870 era dois terços do
    crédito — R$ 4.572.159,48 de R$ 6,85 milhões. O consolidado o somava, o
    detalhe por item não o alcançava, e as duas frentes da mesma tese
    divergiam em 70,81%. Quem comparava os dois números concluía que um estava
    errado; nenhum estava, faltava ramo.

    **O mapeamento foi medido, não suposto** — ver `_do_c870`.
    """

    @pytest.fixture
    def do_sat(self, por_chave):
        # o ramo não tem número de item, então a chave cai no valor — ver
        # o docstring de `por_chave`
        return por_chave[("C860/C870", "5500", "200.00")]

    def test_o_numero_do_documento_e_o_DOC_INIC(self, do_sat):
        """Das três candidatas do C860 — NR_SAT, DOC_INIC e DOC_FIM — só o
        DOC_INIC explica o gabarito: 51 de 51 pares contra zero das outras."""
        assert do_sat.numero_do_documento == "5500"

    def test_o_modelo_e_a_data_vem_do_C860(self, do_sat):
        assert do_sat.modelo == "59"
        assert do_sat.data_do_documento == "20/10/2022"

    def test_o_ramo_nao_tem_item_nem_icms_nem_rateio(self, do_sat):
        """A ausência é do **ramo**, não do campo: o C870 não traz nenhum dos
        três. Escrever zero no lugar do vazio divergiria do MA — ver `_do_ramo`."""
        assert do_sat.numero_do_item == ""
        assert do_sat.icms == ""
        assert do_sat.rateio == ""

    def test_o_item_traz_codigo_descricao_e_valores(self, do_sat):
        assert do_sat.codigo_do_item == "SKU1"
        assert do_sat.valor_do_item == "200.00"
        assert do_sat.cfop == "5102"

    def test_a_descricao_vem_do_cadastro_do_estabelecimento_certo(self, do_sat):
        """O C860/C870 do exemplo está no bloco da **filial**, e o SKU1 dela se
        chama diferente do da matriz. O ramo segue o `C010` aberto, como os
        outros — se seguisse a matriz, a planilha mostraria o produto errado
        num cliente com cadastro divergente entre estabelecimentos."""
        assert do_sat.cnpj == FILIAL
        assert do_sat.descricao_do_item == "ARROZ 5KG DA FILIAL"

    def test_a_base_nova_perde_as_duas_contribuicoes(self, do_sat):
        """A regra da tese, igual para todos os ramos: 200 − (3,30 + 15,20)."""
        assert do_sat.base_do_pis == "200.00"
        assert do_sat.base_do_pis_stf == "181.50"
        assert do_sat.base_da_cofins_stf == "181.50"

    def test_o_cst_sem_incidencia_nao_entra(self, por_chave):
        """O segundo C870 é CST 06. Sem contribuição, não há o que excluir."""
        assert ("C860/C870", "5500", "80.00") not in por_chave


class TestAConta:
    def test_a_base_de_cada_uma_perde_as_duas(self, por_chave):
        """500,00 − 8,25 − 38,00 = 453,75, e é a mesma base nas duas."""
        linha = por_chave[(RAMO_C170, "1001", "1")]

        assert linha.base_do_pis == "500.00"
        assert linha.base_do_pis_stf == "453.75"
        assert linha.base_da_cofins_stf == "453.75"

    def test_o_que_volta_e_a_diferenca_corrigida(self, por_chave):
        """453,75 × 1,65% = 7,49 e × 7,6% = 34,49; a Selic de 50% sobre cada."""
        linha = por_chave[(RAMO_C170, "1001", "1")]

        assert linha.pis_stf == "7.49"
        assert linha.diferenca_do_pis == "0.76"
        assert linha.selic_sobre_o_pis == "0.38"
        assert linha.total_do_pis_a_recuperar == "1.14"
        assert linha.cofins_stf == "34.49"
        assert linha.diferenca_da_cofins == "3.51"
        assert linha.selic_sobre_a_cofins == "1.76"
        assert linha.total_da_cofins_a_recuperar == "5.27"
        assert linha.total_a_recuperar_atualizado == "6.41"

    def test_a_selic_acumulada_sai_na_linha(self, linhas):
        assert {l.selic_acumulada for l in linhas} == {"50"}


class TestOQueCadaRamoTem:
    def test_o_c170_traz_icms_desconto_e_rateio(self, por_chave):
        linha = por_chave[(RAMO_C170, "1001", "2")]

        assert linha.icms == "54.00"
        assert linha.desconto == "10.00"
        assert linha.rateio == "30.00"

    def test_o_c175_traz_so_o_desconto(self, por_chave):
        linha = por_chave[(RAMO_C175, "3001", "100.00")]

        assert linha.desconto == "0.00"
        assert linha.icms == "", "o C175 não tem ICMS no leiaute"
        assert linha.rateio == ""

    def test_o_c175_nao_tem_item(self, por_chave):
        linha = por_chave[(RAMO_C175, "3001", "100.00")]

        assert (linha.numero_do_item, linha.codigo_do_item,
                linha.descricao_do_item) == ("", "", "")

    def test_o_a170_nao_traz_nenhum_dos_tres(self, por_chave):
        """Tem `VL_DESC` no leiaute, preenchido com 20,00 — e o MA o deixa vazio."""
        linha = por_chave[(RAMO_A170, "55", "1")]

        assert (linha.desconto, linha.icms, linha.rateio) == ("", "", "")

    def test_o_f100_nao_traz_nenhum_dos_tres(self, linhas):
        for linha in [l for l in linhas if l.registro == RAMO_F100]:
            assert (linha.desconto, linha.icms, linha.rateio) == ("", "", "")

    def test_o_registro_sem_cfop_escreve_o_sentido(self, por_chave, linhas):
        """O MA escreve "S" na coluna do CFOP, e classifica como faturamento."""
        do_servico = por_chave[(RAMO_A170, "55", "1")]
        do_f100 = next(l for l in linhas if l.registro == RAMO_F100)

        assert (do_servico.cfop, do_servico.cfop_faturamento) == ("S", FATURAMENTO)
        assert (do_f100.cfop, do_f100.cfop_faturamento) == ("S", FATURAMENTO)


class TestORateio:
    def test_reparte_pelo_valor_do_item_sobre_a_nota_inteira(self, por_chave):
        """60 + 15 + 25 = 100, sobre 1.000,00 de itens: 10% de cada um."""
        assert por_chave[(RAMO_C170, "1001", "1")].rateio == "50.00"
        assert por_chave[(RAMO_C170, "1001", "2")].rateio == "30.00"

    def test_o_item_fora_da_tese_continua_no_denominador(self, por_chave):
        """Os 200,00 do item 3 não saem no relatório e dividem o frete.

        Se o denominador fossem só os itens que entram — 800,00 —, o item 1
        levaria 62,50 em vez de 50,00. O frete foi pago pela nota inteira.
        """
        assert por_chave[(RAMO_C170, "1001", "1")].rateio != "62.50"

    def test_nota_sem_frete_tem_rateio_zero_e_nao_vazio(self, por_chave):
        """Zero é número aqui: o C170 **tem** a coluna, e o MA escreve 0,00."""
        assert por_chave[(RAMO_C170, "2001", "1")].rateio == "0"


class TestOF100SomadoPorDia:
    def test_duas_linhas_do_mesmo_dia_viram_uma(self, linhas):
        """1.000,00 + 500,00 = 1.500,00, com as contribuições somadas também."""
        do_dia = [l for l in linhas
                  if l.registro == RAMO_F100 and l.data_do_documento == "31/10/2022"]

        assert len(do_dia) == 1
        assert do_dia[0].valor_do_item == "1500.00"
        assert do_dia[0].pis == "24.75"
        assert do_dia[0].cofins == "114.00"
        # 1.500,00 − 24,75 − 114,00 = 1.361,25
        assert do_dia[0].base_do_pis_stf == "1361.25"

    def test_dia_diferente_e_linha_diferente(self, linhas):
        do_f100 = [l for l in linhas if l.registro == RAMO_F100]

        assert len(do_f100) == 2
        assert {l.data_do_documento for l in do_f100} == {"15/10/2022", "31/10/2022"}

    def test_o_f100_nao_tem_documento_modelo_nem_item(self, linhas):
        linha = next(l for l in linhas if l.registro == RAMO_F100)

        assert (linha.numero_do_documento, linha.modelo, linha.chave,
                linha.numero_do_item) == ("", "", "", "")


class TestOEstabelecimentoDaLinha:
    def test_a_ultima_nota_do_bloco_e_de_quem_termina_ali(self, por_chave):
        """A nota 3001 é da MATRIZ, e o C010 seguinte não pode levá-la embora."""
        assert por_chave[(RAMO_C175, "3001", "100.00")].cnpj == MATRIZ

    def test_a_nota_da_filial_sai_com_o_cnpj_da_filial(self, por_chave):
        linha = por_chave[(RAMO_C170, "4001", "1")]

        assert linha.cnpj == FILIAL
        assert linha.descricao_do_item == "ARROZ 5KG DA FILIAL", (
            "a descrição veio do cadastro do outro estabelecimento")

    def test_a_ultima_nota_do_arquivo_sai(self, por_chave):
        """Ninguém vem depois dela para fechá-la: quem fecha é o fim do arquivo."""
        assert (RAMO_C170, "4001", "1") in por_chave

    def test_a_descricao_vem_do_cadastro_do_estabelecimento(self, por_chave):
        assert por_chave[(RAMO_C170, "1001", "2")].descricao_do_item == "FEIJAO 1KG"
        assert por_chave[(RAMO_A170, "55", "1")].descricao_do_item == (
            "PRESTACAO DE SERVICO")


class TestAsColunasDoRelatorio:
    def test_a_competencia_e_a_do_cabecalho_e_nao_a_do_documento(self, linhas):
        """O MA escreve o primeiro dia do período da escrituração, em toda linha."""
        assert {l.periodo for l in linhas} == {"01/10/2022"}

    def test_a_data_do_documento_sai_no_formato_do_relatorio(self, por_chave):
        assert por_chave[(RAMO_C170, "1001", "1")].data_do_documento == "03/10/2022"

"""A Consulta de Saídas (047): os quatro ramos, e as regras que só o dado real
ensinou.

A amostra tem **matriz e filial com o mesmo código de item significando coisas
diferentes** — porque é isso que quebra quem trata o 0200 como uma tabela só
por arquivo. Na EFD-Contribuições o cadastro pende do 0140, e o arquivo de
referência tinha 134 códigos repetidos entre dois estabelecimentos em uma só
competência.

Tem também as duas metades da regra da nota cancelada: a nota fiscal sem filho
rende uma linha, a NFC-e sem filho não rende nenhuma.

As linhas são montadas **por nome de campo**, nunca contando barras: já houve
teste nesta casa que passou pelo motivo errado porque o CST caiu na coluna do
valor.
"""

import pytest

from cat.infraestrutura.sped.registros import CAMPOS
from cat.infraestrutura.sped.saidas import (
    RAMO_A170,
    RAMO_C170,
    RAMO_C175,
    RAMO_F100,
    Contagem,
    colunas_da_saida,
    saidas,
)

MATRIZ = "11222333000181"
FILIAL = "11222333000262"


def reg(nome: str, **campos: str) -> str:
    valores = [campos.get(c, "") for c in CAMPOS[nome]]
    valores[0] = nome
    return "|" + "|".join(valores) + "|"


EFD = "\n".join([
    reg("0000", COD_VER="006", TIPO_ESCRIT="0", DT_INI="01062021", DT_FIN="30062021",
        NOME="COMERCIO DO TESTE LTDA", CNPJ=MATRIZ, UF="MG", COD_MUN="3106200",
        IND_NAT_PJ="0", IND_ATIV="0"),

    # ---- o cadastro da MATRIZ (MG) --------------------------------------
    reg("0140", COD_EST="001", NOME="MATRIZ", CNPJ=MATRIZ, UF="MG", IE="111",
        COD_MUN="3106200"),
    reg("0150", COD_PART="C01", NOME="CLIENTE PAULISTA", COD_PAIS="1058",
        CNPJ="99888777000166", COD_MUN="3550308"),
    # SKU1 na matriz é xampu, e tem código de barra
    reg("0200", COD_ITEM="SKU1", DESCR_ITEM="XAMPU 350ML", COD_BARRA="7890000000017",
        UNID_INV="UN", TIPO_ITEM="00", COD_NCM="33051000"),
    # SKU2 é o caso oposto: aqui, que é o primeiro cadastro do arquivo, ele NÃO
    # tem código de barra
    reg("0200", COD_ITEM="SKU2", DESCR_ITEM="SABONETE 90G", UNID_INV="UN",
        TIPO_ITEM="00", COD_NCM="34011190"),

    # ---- o cadastro da FILIAL (PR): o MESMO código, outro produto -------
    reg("0140", COD_EST="002", NOME="FILIAL CURITIBA", CNPJ=FILIAL, UF="PR", IE="222",
        COD_MUN="4106902"),
    reg("0150", COD_PART="C01", NOME="CLIENTE MINEIRO", COD_PAIS="1058",
        CNPJ="55444333000199", COD_MUN="3106200"),
    # sem COD_MUN: o 0150 não traz UF, e sem município não há de onde tirá-la
    reg("0150", COD_PART="C02", NOME="CLIENTE SEM MUNICIPIO", COD_PAIS="1058",
        CNPJ="44333222000155"),
    # SKU1 na filial é carne, e NÃO tem código de barra
    reg("0200", COD_ITEM="SKU1", DESCR_ITEM="COXAO MOLE KG", UNID_INV="KG",
        TIPO_ITEM="00", COD_NCM="02013000"),
    # SKU2 aqui tem código de barra — e é o segundo cadastro do arquivo
    reg("0200", COD_ITEM="SKU2", DESCR_ITEM="ARROZ 5KG", COD_BARRA="7890000000024",
        UNID_INV="PC", TIPO_ITEM="00", COD_NCM="10063021"),

    # ---- bloco C da MATRIZ ---------------------------------------------
    reg("C010", CNPJ=MATRIZ),
    # venda interestadual, com item
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="5001", CHV_NFE="31" + "0" * 42, DT_DOC="01062021",
        DT_E_S="01062021", VL_DOC="1000,00", VL_DESC="10,00", VL_MERC="900,00",
        VL_FRT="50,00", VL_SEG="7,00", VL_OUT_DA="3,00"),
    reg("C170", NUM_ITEM="1", COD_ITEM="SKU1", DESCR_COMPL="XAMPU GRANDE", QTD="10,000",
        UNID="UN", VL_ITEM="900,00", VL_DESC="10,00", CFOP="6102", VL_ICMS="108,00",
        VL_ICMS_ST="0,00", VL_IPI="0,00", CST_PIS="01", VL_BC_PIS="900,00",
        ALIQ_PIS_PERC="1,6500", VL_PIS="14,85", CST_COFINS="01", VL_BC_COFINS="900,00",
        ALIQ_COFINS_PERC="7,6000", VL_COFINS="68,40", COD_CTA="3.1.1"),
    reg("C170", NUM_ITEM="2", COD_ITEM="SKU2", QTD="1,000", UNID="UN", VL_ITEM="100,00",
        CFOP="6102", CST_PIS="01", VL_BC_PIS="100,00", ALIQ_PIS_PERC="1,6500",
        VL_PIS="1,65", CST_COFINS="01", VL_BC_COFINS="100,00",
        ALIQ_COFINS_PERC="7,6000", VL_COFINS="7,60", COD_CTA="3.1.1"),
    # compra: entrada não entra na 047
    reg("C100", IND_OPER="0", IND_EMIT="1", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="9001", DT_DOC="02062021", VL_DOC="500,00"),
    reg("C170", NUM_ITEM="1", COD_ITEM="SKU1", DESCR_COMPL="ENTRADA NAO ENTRA",
        VL_ITEM="500,00", CFOP="1102"),
    # nota fiscal cancelada, sem filho: rende a linha do documento
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_MOD="55", COD_SIT="02", SER="1",
        NUM_DOC="5002", CHV_NFE="31" + "1" * 42),
    # NFC-e com o analítico por CFOP
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_MOD="65", COD_SIT="00", SER="9",
        NUM_DOC="7001", CHV_NFE="31" + "2" * 42, DT_DOC="03062021", DT_E_S="03062021",
        VL_DOC="250,00", VL_DESC="0,00", VL_MERC="250,00", VL_FRT="0,00",
        VL_OUT_DA="0,00"),
    reg("C175", CFOP="5102", VL_OPR="150,00", VL_DESC="0,00", CST_PIS="01",
        VL_BC_PIS="150,00", ALIQ_PIS="1,6500", VL_PIS="2,48", CST_COFINS="01",
        VL_BC_COFINS="150,00", ALIQ_COFINS="7,6000", VL_COFINS="11,40", COD_CTA="3.1.1"),
    reg("C175", CFOP="5405", VL_OPR="100,00", VL_DESC="0,00", CST_PIS="04",
        VL_BC_PIS="0,00", ALIQ_PIS="0,0000", VL_PIS="0,00", CST_COFINS="04",
        VL_BC_COFINS="0,00", ALIQ_COFINS="0,0000", VL_COFINS="0,00", COD_CTA="3.1.1"),
    # NFC-e cancelada, sem filho: NÃO rende linha
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_MOD="65", COD_SIT="05", SER="9",
        NUM_DOC="7002"),

    # ---- bloco C da FILIAL: mesmo SKU1, outro produto -------------------
    reg("C010", CNPJ=FILIAL),
    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="5003", CHV_NFE="41" + "3" * 42, DT_DOC="04062021",
        DT_E_S="04062021", VL_DOC="80,00", VL_MERC="80,00"),
    reg("C170", NUM_ITEM="1", COD_ITEM="SKU1", QTD="2,000", UNID="KG", VL_ITEM="80,00",
        CFOP="5949", CST_PIS="01", VL_BC_PIS="80,00", ALIQ_PIS_PERC="1,6500",
        VL_PIS="1,32", CST_COFINS="01", VL_BC_COFINS="80,00",
        ALIQ_COFINS_PERC="7,6000", VL_COFINS="6,08", COD_CTA="3.1.2"),

    reg("C100", IND_OPER="1", IND_EMIT="0", COD_PART="C02", COD_MOD="55", COD_SIT="00",
        SER="1", NUM_DOC="5004", CHV_NFE="41" + "4" * 42, DT_DOC="05062021",
        DT_E_S="05062021", VL_DOC="30,00", VL_MERC="30,00"),
    reg("C170", NUM_ITEM="1", COD_ITEM="SKU1", QTD="1,000", UNID="KG", VL_ITEM="30,00",
        CFOP="5949", CST_PIS="01", VL_BC_PIS="30,00", ALIQ_PIS_PERC="1,6500",
        VL_PIS="0,50", CST_COFINS="01", VL_BC_COFINS="30,00",
        ALIQ_COFINS_PERC="7,6000", VL_COFINS="2,28", COD_CTA="3.1.2"),

    # ---- um ramo que a 047 ainda não cobre ------------------------------
    reg("C400", COD_MOD="2D", ECF_MOD="ECF", ECF_FAB="ABC", ECF_CX="001"),

    # ---- bloco A: nota de serviço, da FILIAL ---------------------------
    reg("A010", CNPJ=FILIAL),
    reg("A100", IND_OPER="1", IND_EMIT="0", COD_PART="C01", COD_SIT="00", SER="A",
        NUM_DOC="301", DT_DOC="05062021", DT_EXE_SERV="05062021", VL_DOC="500,00",
        VL_DESC="0,00"),
    reg("A170", NUM_ITEM="1", COD_ITEM="SKU1", VL_ITEM="500,00", CST_PIS="01",
        VL_BC_PIS="500,00", ALIQ_PIS="1,6500", VL_PIS="8,25", CST_COFINS="01",
        VL_BC_COFINS="500,00", ALIQ_COFINS="7,6000", VL_COFINS="38,00", COD_CTA="3.3.1"),
    # serviço tomado: não é saída
    reg("A100", IND_OPER="0", COD_PART="C01", NUM_DOC="302", DT_DOC="06062021",
        VL_DOC="90,00"),
    reg("A170", NUM_ITEM="1", COD_ITEM="SKU1", DESCR_COMPL="ENTRADA NAO ENTRA",
        VL_ITEM="90,00"),

    # ---- bloco F: demais documentos, da MATRIZ -------------------------
    reg("F010", CNPJ=MATRIZ),
    reg("F100", IND_OPER="1", COD_PART="C01", COD_ITEM="SKU1", DT_OPER="20062021",
        VL_OPER="250,00", CST_PIS="01", VL_BC_PIS="250,00", ALIQ_PIS="1,6500",
        VL_PIS="4,13", CST_COFINS="01", VL_BC_COFINS="250,00", ALIQ_COFINS="7,6000",
        VL_COFINS="19,00", COD_CTA="3.4.1"),
    reg("F100", IND_OPER="0", COD_PART="C01", COD_ITEM="SKU1", DT_OPER="21062021",
        VL_OPER="99,00", DESC_DOC_OPER="ENTRADA NAO ENTRA"),
    "|9999|44|",
    "",
])


@pytest.fixture
def arquivo(tmp_path):
    caminho = tmp_path / "contribuicoes.txt"
    caminho.write_bytes(EFD.encode("cp1252"))
    return str(caminho)


@pytest.fixture
def linhas(arquivo):
    return list(saidas(arquivo, "cp1252"))


def uma(linhas, **igual):
    """A única linha que casa com o que se pediu. Zero ou duas é erro."""
    achadas = [l for l in linhas
               if all(getattr(l, campo) == valor for campo, valor in igual.items())]
    assert len(achadas) == 1, f"{len(achadas)} linhas casam com {igual}"
    return achadas[0]


class TestOsQuatroRamos:
    def test_todos_os_ramos_aparecem(self, linhas):
        assert {l.registros for l in linhas} == {RAMO_C170, RAMO_C175, RAMO_A170, RAMO_F100}

    def test_so_saida_entra(self, linhas):
        assert all("ENTRADA NAO ENTRA" not in (l.descricao_complementar or "")
                   for l in linhas)
        # a compra do C100, o serviço tomado do A100 e o F100 de entrada sumiram
        assert [l.numero_do_documento for l in linhas if l.registros == RAMO_A170] == ["301"]
        assert len([l for l in linhas if l.registros == RAMO_F100]) == 1

    def test_a_planilha_tem_as_53_colunas(self):
        assert len(colunas_da_saida()) == 53


class TestOCadastroEDoEstabelecimento:
    """O 0200 e o 0150 pendem do 0140, e não do arquivo."""

    def test_o_mesmo_codigo_e_outro_produto_na_filial(self, linhas):
        da_matriz = uma(linhas, numero_do_documento="5001", numero_do_item="1")
        da_filial = uma(linhas, numero_do_documento="5003")
        assert da_matriz.codigo_do_item == da_filial.codigo_do_item == "SKU1"
        assert da_matriz.descricao_do_item == "XAMPU 350ML"
        assert da_filial.descricao_do_item == "COXAO MOLE KG"
        assert da_matriz.ncm == "33051000"
        assert da_filial.ncm == "02013000"

    def test_o_mesmo_codigo_e_outro_participante_na_filial(self, linhas):
        assert uma(linhas, numero_do_documento="5001", numero_do_item="1").nome_do_participante == "CLIENTE PAULISTA"
        assert uma(linhas, numero_do_documento="5003").nome_do_participante == "CLIENTE MINEIRO"

    def test_campo_vazio_se_completa_com_o_primeiro_do_arquivo(self, linhas):
        """O coxão não tem código de barra; o MA escreve o do xampu, que é o
        primeiro cadastro de SKU1 no arquivo. Ver `sped/cadastro.py`: é
        replicação do gabarito, e está marcada lá como tal."""
        assert uma(linhas, numero_do_documento="5003").codigo_de_barra == "7890000000017"

    def test_e_o_primeiro_do_arquivo_mesmo_estando_vazio(self, linhas):
        """SKU2 não tem código de barra na matriz, que é o primeiro cadastro, e
        tem na filial. A linha da matriz sai **em branco**.

        É esta a diferença entre "o primeiro" e "o primeiro não vazio", e ela
        vale 22 linhas de divergência numa competência do gabarito."""
        assert uma(linhas, numero_do_item="2").codigo_de_barra == ""
        assert uma(linhas, numero_do_item="2").descricao_do_item == "SABONETE 90G"


class TestAUfTrocaDeLado:
    def test_estabelecimento_primeiro_participante_depois(self, linhas):
        """Na saída a origem somos nós: MG/SP, e não SP/MG como na 037."""
        assert uma(linhas, numero_do_documento="5001", numero_do_item="1").uf_origem_destino == "MG/SP"
        assert uma(linhas, numero_do_documento="5003").uf_origem_destino == "PR/MG"

    def test_uma_ponta_so_nao_e_par(self, linhas):
        """Sem a UF do participante, a coluna fica vazia — nunca "PR/".

        O cliente C02 está cadastrado sem município, e o 0150 não traz UF: não
        há de onde tirá-la. As duas pontas ou nenhuma — foi a última das
        7.784.121 linhas do gabarito a divergir.
        """
        sem_municipio = uma(linhas, numero_do_documento="5004")
        assert sem_municipio.nome_do_participante == "CLIENTE SEM MUNICIPIO"
        assert sem_municipio.uf_origem_destino == ""


class TestANaturezaEOFaturamento:
    def test_venda_traz_faturamento(self, linhas):
        venda = uma(linhas, numero_do_documento="5001", numero_do_item="1")
        assert (venda.natureza, venda.faturamento) == ("Venda", "Faturamento")

    def test_outras_saidas_nao_traz(self, linhas):
        outra = uma(linhas, numero_do_documento="5003")
        assert (outra.natureza, outra.faturamento) == ("Outras saídas/prestações", "")

    def test_sem_cfop_nao_ha_natureza(self, linhas):
        servico = uma(linhas, registros=RAMO_A170)
        assert (servico.cfop, servico.natureza, servico.faturamento) == ("", "", "")


class TestANotaCancelada:
    def test_nota_fiscal_sem_filho_rende_a_linha_do_documento(self, linhas):
        cancelada = uma(linhas, numero_do_documento="5002")
        assert cancelada.registros == RAMO_C170
        assert (cancelada.situacao, cancelada.modelo) == ("02", "55")
        assert cancelada.chave == "31" + "1" * 42
        # o leiaute não deixa escriturar mais que isso, e o relatório não inventa
        assert (cancelada.numero_do_item, cancelada.valor_do_item, cancelada.cfop) == ("", "", "")

    def test_nfce_sem_filho_nao_rende_nada(self, linhas):
        assert not [l for l in linhas if l.numero_do_documento == "7002"]


class TestOAnaliticoDaNfce:
    def test_uma_linha_por_cfop_sem_item_e_sem_participante(self, linhas):
        do_cupom = [l for l in linhas if l.registros == RAMO_C175]
        assert [l.cfop for l in do_cupom] == ["5102", "5405"]
        for linha in do_cupom:
            # o C175 não tem COD_ITEM, e a NFC-e não tem participante
            assert (linha.codigo_do_item, linha.descricao_do_item, linha.ncm) == ("", "", "")
            assert (linha.quantidade, linha.unidade, linha.numero_do_item) == ("", "", "")
            assert (linha.codigo_do_participante, linha.nome_do_participante) == ("", "")
            # mas as colunas do documento vêm do C100, como na nota fiscal
            assert linha.chave == "31" + "2" * 42
            assert linha.valor_do_documento == "250,00"

    def test_o_valor_do_item_vem_do_vl_opr(self, linhas):
        assert uma(linhas, registros=RAMO_C175, cfop="5102").valor_do_item == "150,00"


class TestOQueONaoCobertoDiz:
    def test_o_c400_e_contado_e_nao_lido(self, arquivo):
        contagem = Contagem()
        linhas = list(saidas(arquivo, "cp1252", contagem))
        assert contagem.nao_cobertos == {"C400": 1}
        assert contagem.linhas == len(linhas)
        assert contagem.por_ramo[RAMO_C175] == 2


class TestOsCamposDoDocumento:
    def test_seguro_e_outras_despesas_saem_do_c100(self, linhas):
        nota = uma(linhas, numero_do_documento="5001", numero_do_item="1")
        assert (nota.frete, nota.seguro, nota.outras_despesas) == ("50,00", "7,00", "3,00")

    def test_vazio_continua_vazio(self, linhas):
        """A filial não escriturou frete: a coluna fica em branco, não "0,00"."""
        assert uma(linhas, numero_do_documento="5003").frete == ""

"""Extrair registro e hierarquia do SPED, consolidados dos arquivos do trabalho.

O que se cobra aqui é o que a quebra sozinha não entregava: pegar o registro
que o analista pediu, de todos os arquivos, com as colunas do leiaute — e, na
hierarquia, com o pai que o SPED só amarra pela posição.

Dois arquivos, de competências diferentes, para que a consolidação apareça: uma
linha do primeiro e uma do segundo no mesmo parquet, cada uma dizendo de onde
veio.
"""

from __future__ import annotations

from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.quebra_de_sped import quebrar
from cat.infraestrutura.sped.registros import CAMPOS
from cat.infraestrutura.analitico.registros_do_sped import (
    AlvoDesconhecido,
    Recorte,
    colunas_do_alvo,
    disponiveis,
    extrair,
)

CNPJ = "11222333000181"

def reg(nome: str, **campos: str) -> str:
    """Uma linha de SPED montada **por nome de campo**, na ordem do leiaute.

    Contar barras à mão é como se escreve um teste que passa pelo motivo
    errado: na primeira versão deste arquivo o CST do PIS caiu na coluna do
    valor, e o filtro "passou" testando outra coisa.
    """
    valores = [campos.get(c, "") for c in CAMPOS[nome]]
    valores[0] = nome
    return "|" + "|".join(valores) + "|"


def sped(competencia_ini: str, competencia_fim: str) -> str:
    """Uma EFD-Contribuições curtinha: duas notas com itens, consolidação de
    entradas com PIS e COFINS, cupom SAT e o bloco M."""
    return "\n".join([
        reg("0000", COD_VER="006", TIPO_ESCRIT="0", DT_INI=competencia_ini,
            DT_FIN=competencia_fim, NOME="EMPRESA DO TESTE", CNPJ=CNPJ, UF="SP",
            COD_MUN="3550308", IND_NAT_PJ="0", IND_ATIV="0"),
        reg("0140", COD_EST="001", NOME="FILIAL UM", CNPJ=CNPJ, UF="SP",
            IE="123456789012", COD_MUN="3550308"),
        reg("0150", COD_PART="F001", NOME="FORNECEDOR ALFA", COD_PAIS="1058",
            CNPJ="99888777000166"),
        reg("0200", COD_ITEM="P01", DESCR_ITEM="PAO FRANCES", UNID_INV="UN",
            TIPO_ITEM="00", COD_NCM="19059090"),
        reg("0200", COD_ITEM="P02", DESCR_ITEM="LEITE INTEGRAL 1L", UNID_INV="UN",
            TIPO_ITEM="00", COD_NCM="04012010"),
        reg("0400", COD_NAT="N01", DESCR_NAT="VENDA DE MERCADORIA"),
        reg("0500", COD_CTA="31010001", NOME_CTA="CLIENTES", COD_NAT_CC="01"),
        reg("C010", CNPJ=CNPJ, IND_ESCRI="0"),
        reg("C100", IND_OPER="0", IND_EMIT="1", COD_PART="F001", COD_MOD="55",
            COD_SIT="00", SER="001", NUM_DOC="123",
            CHV_NFE="35210511222333000181550010000001231000000001",
            DT_DOC="04062021", DT_E_S="04062021", VL_DOC="100,00", VL_MERC="100,00"),
        reg("C170", NUM_ITEM="1", COD_ITEM="P01", DESCR_COMPL="PAO FRANCES",
            QTD="10", UNID="UN", VL_ITEM="30,00", CFOP="5102", COD_NAT="N01",
            CST_PIS="01", VL_BC_PIS="30,00", ALIQ_PIS="1,65", VL_PIS="0,50",
            CST_COFINS="01", VL_BC_COFINS="30,00", ALIQ_COFINS="7,60",
            VL_COFINS="2,28"),
        reg("C170", NUM_ITEM="2", COD_ITEM="P02", DESCR_COMPL="LEITE INTEGRAL",
            QTD="5", UNID="UN", VL_ITEM="70,00", CFOP="5102", COD_NAT="N01",
            CST_PIS="01", VL_BC_PIS="70,00", ALIQ_PIS="1,65", VL_PIS="1,16",
            CST_COFINS="01", VL_BC_COFINS="70,00", ALIQ_COFINS="7,60",
            VL_COFINS="5,32"),
        reg("C100", IND_OPER="0", IND_EMIT="1", COD_PART="F001", COD_MOD="55",
            COD_SIT="00", SER="001", NUM_DOC="124",
            CHV_NFE="35210511222333000181550010000001241000000002",
            DT_DOC="05062021", DT_E_S="05062021", VL_DOC="50,00", VL_MERC="50,00"),
        reg("C170", NUM_ITEM="1", COD_ITEM="P01", DESCR_COMPL="PAO FRANCES",
            QTD="20", UNID="UN", VL_ITEM="50,00", CFOP="5102", COD_NAT="N01",
            CST_PIS="01", VL_BC_PIS="50,00", ALIQ_PIS="1,65", VL_PIS="0,83",
            CST_COFINS="01", VL_BC_COFINS="50,00", ALIQ_COFINS="7,60",
            VL_COFINS="3,80"),
        reg("C190", COD_MOD="55", DT_INI=competencia_ini, DT_FIN=competencia_fim,
            COD_ITEM="P01", COD_NCM="19059090", VL_TOT_ITEM="100,00"),
        reg("C191", COD_PART="F001", CST_PIS="01", CFOP="1102", VL_ITEM="100,00",
            VL_BC_PIS="100,00", ALIQ_PIS_PERC="1,65", VL_PIS="1,65",
            COD_CTA="31010001"),
        reg("C191", COD_PART="F001", CST_PIS="50", CFOP="1102", VL_ITEM="40,00",
            VL_BC_PIS="40,00", ALIQ_PIS_PERC="1,65", VL_PIS="0,66",
            COD_CTA="31010001"),
        reg("C195", COD_PART="F001", CST_COFINS="01", CFOP="1102", VL_ITEM="100,00",
            VL_BC_COFINS="100,00", ALIQ_COFINS_PERC="7,60", VL_COFINS="7,60",
            COD_CTA="31010001"),
        reg("C195", COD_PART="F001", CST_COFINS="50", CFOP="1102", VL_ITEM="40,00",
            VL_BC_COFINS="40,00", ALIQ_COFINS_PERC="7,60", VL_COFINS="3,04",
            COD_CTA="31010001"),
        # a NFC-e e o analítico dela: sem item, uma linha por CFOP e CST
        reg("C100", IND_OPER="1", IND_EMIT="0", COD_MOD="65", COD_SIT="00",
            SER="002", NUM_DOC="900",
            CHV_NFE="35210511222333000181650010000009001000000009",
            DT_DOC="06062021", DT_E_S="06062021", VL_DOC="25,00", VL_MERC="25,00"),
        reg("C175", CFOP="5102", VL_OPR="25,00", CST_PIS="01", VL_BC_PIS="25,00",
            ALIQ_PIS="1,6500", VL_PIS="0,41", CST_COFINS="01", VL_BC_COFINS="25,00",
            ALIQ_COFINS="7,6000", VL_COFINS="1,90", COD_CTA="31010001"),
        # serviços, que têm bloco e abridor próprios
        reg("A010", CNPJ=CNPJ),
        reg("A100", IND_OPER="1", IND_EMIT="0", COD_PART="F001", COD_SIT="00",
            NUM_DOC="7", DT_DOC="07062021", DT_EXE_SERV="07062021", VL_DOC="500,00",
            IND_PGTO="0", VL_BC_PIS="500,00", VL_PIS="8,25",
            VL_BC_COFINS="500,00", VL_COFINS="38,00"),
        reg("A170", NUM_ITEM="1", COD_ITEM="S01", DESCR_COMPL="FRETE CONTRATADO",
            VL_ITEM="500,00", CST_PIS="01", VL_BC_PIS="500,00", ALIQ_PIS="1,6500",
            VL_PIS="8,25", CST_COFINS="01", VL_BC_COFINS="500,00",
            ALIQ_COFINS="7,6000", VL_COFINS="38,00", COD_CTA="41010001"),
        reg("C860", COD_MOD="59", NR_SAT="900001", DT_DOC="04062021",
            DOC_INIC="1", DOC_FIM="9"),
        reg("C870", COD_ITEM="P01", CFOP="5102", VL_ITEM="12,00", CST_PIS="01",
            VL_BC_PIS="12,00", ALIQ_PIS_PERC="1,65", VL_PIS="0,20",
            CST_COFINS="01", VL_BC_COFINS="12,00", ALIQ_COFINS_PERC="7,60",
            VL_COFINS="0,91", COD_CTA="31010001"),
        reg("M200", VL_TOT_CONT_NC_PER="10,00"),
        reg("M210", COD_CONT="01", VL_REC_BRT="1000,00", VL_BC_CONT="1000,00",
            ALIQ_PIS="1,65", VL_CONT_APUR="16,50"),
        reg("M220", IND_AJ="0", VL_AJ="1,50", COD_AJ="CODAJ", NUM_DOC="DOC-1",
            DESCR_AJ="ajuste de teste", DT_REF="01062021"),
    ]) + "\n"


@pytest.fixture(scope="module")
def quebrado(tmp_path_factory):
    """Dois SPED quebrados: é a pasta da execução que a extração lê."""
    base = tmp_path_factory.mktemp("registros")
    arquivos = []
    for ini, fim, nome in (("01062021", "30062021", "efd_062021.txt"),
                           ("01072021", "31072021", "efd_072021.txt")):
        caminho = base / nome
        caminho.write_bytes(sped(ini, fim).encode("cp1252"))
        arquivos.append(str(caminho))
    destino = str(base / "execucao")
    quebrar(arquivos, [], destino)
    return destino


def _linhas(caminho):
    return pq.read_table(caminho).to_pylist()


class TestOQueDaParaExtrair:
    def test_lista_registro_e_hierarquia_com_a_contagem(self, quebrado):
        d = disponiveis(quebrado)
        por_alvo = {l["alvo"]: l for l in d["linhas"]}

        # três C170 por arquivo, dois arquivos
        assert por_alvo["C170"]["quantidade"] == 6
        assert por_alvo["C170"]["hierarquia"] is False
        assert por_alvo["C100+C170"]["hierarquia"] is True
        assert por_alvo["C100+C170"]["quantidade"] == 6
        assert d["sem_indice"] == 0

    def test_a_hierarquia_sem_folha_no_arquivo_nao_e_oferecida(self, quebrado):
        """O pai sem folha não gera linha: oferecer seria prometer planilha vazia."""
        alvos = {l["alvo"] for l in disponiveis(quebrado)["linhas"]}

        assert "M200+M210" in alvos          # tem M210
        assert "M500+M505" not in alvos      # não tem M505

    def test_os_blocos_saem_para_a_tela_filtrar(self, quebrado):
        d = disponiveis(quebrado)

        # o bloco A entrou com as notas de serviço, em 29/09/2026
        assert set(d["blocos"]) == {"0", "A", "C", "M"}
        assert d["rotulos_dos_blocos"]["C"].startswith("Bloco C")
        assert {l["bloco"] for l in d["linhas"] if l["alvo"] == "C170"} == {"C"}


class TestORegistroSozinho:
    def test_sai_com_as_colunas_do_leiaute_e_a_origem(self, quebrado, tmp_path):
        caminho = extrair(quebrado, "C170")
        linhas = _linhas(caminho)

        assert len(linhas) == 6
        assert linhas[0]["REG"] == "C170"
        assert linhas[0]["COD_ITEM"] == "P01"
        assert linhas[0]["VL_ITEM"] == "30,00"
        # a identificação do arquivo vai em toda linha
        assert linhas[0]["arquivo"] == "efd_062021.txt"
        assert linhas[0]["cnpj"] == CNPJ
        assert {l["competencia"] for l in linhas} == {"2021-06", "2021-07"}

    def test_registro_sem_leiaute_e_recusado_dizendo_o_que_vale(self, quebrado):
        with pytest.raises(AlvoDesconhecido) as erro:
            extrair(quebrado, "Z999")

        assert "não é registro com leiaute" in str(erro.value)


class TestAHierarquia:
    def test_a_folha_sai_com_o_pai_que_o_sped_amarra_pela_posicao(self, quebrado):
        caminho = extrair(quebrado, "C100+C170")
        linhas = _linhas(caminho)

        assert len(linhas) == 6
        primeira = linhas[0]
        # o item, e a nota a que ele pertence
        assert primeira["C170_COD_ITEM"] == "P01"
        assert primeira["C100_NUM_DOC"] == "123"
        assert primeira["C100_VL_DOC"] == "100,00"
        # o terceiro item do arquivo é da segunda nota, e o pai acompanha
        assert linhas[2]["C100_NUM_DOC"] == "124"
        assert linhas[2]["C170_VL_ITEM"] == "50,00"

    def test_o_cadastro_entra_por_codigo_e_nao_por_posicao(self, quebrado):
        linhas = _linhas(extrair(quebrado, "C100+C170"))

        pao = next(l for l in linhas if l["C170_COD_ITEM"] == "P01")
        leite = next(l for l in linhas if l["C170_COD_ITEM"] == "P02")
        assert pao["0200_DESCR_ITEM"] == "PAO FRANCES"
        assert pao["0200_COD_NCM"] == "19059090"
        assert leite["0200_DESCR_ITEM"] == "LEITE INTEGRAL 1L"
        # o participante vem do C100, que é o pai — e não da folha
        assert pao["0150_NOME"] == "FORNECEDOR ALFA"

    def test_o_prefixo_impede_o_pai_e_a_folha_de_se_atropelarem(self, quebrado):
        colunas = colunas_do_alvo("C100+C170")

        assert "C100_VL_DOC" in colunas
        assert "C170_VL_ITEM" in colunas
        # os dois têm CHV_NFE/COD_ITEM parecidos; nenhum nome nu sobrevive
        assert "VL_ITEM" not in colunas
        assert colunas[:4] == ["arquivo", "cnpj", "empresa", "competencia"]

    def test_hierarquia_de_tres_niveis_carrega_os_dois_pais(self, quebrado):
        linhas = _linhas(extrair(quebrado, "M200+M210+M220"))

        assert len(linhas) == 2
        assert linhas[0]["M220_COD_AJ"] == "CODAJ"
        assert linhas[0]["M210_COD_CONT"] == "01"
        assert linhas[0]["M200_VL_TOT_CONT_NC_PER"] == "10,00"

    def test_o_cupom_sat_sai_com_a_maquina_e_o_item(self, quebrado):
        linhas = _linhas(extrair(quebrado, "C860+C870"))

        assert len(linhas) == 2
        assert linhas[0]["C870_COD_ITEM"] == "P01"
        assert linhas[0]["C860_NR_SAT"] == "900001"
        assert linhas[0]["0200_DESCR_ITEM"] == "PAO FRANCES"


# ---------------------------------------------------------------------------
# o par PIS+COFINS, o catálogo deduplicado e o recorte
# ---------------------------------------------------------------------------
class TestOParPisCofins:
    def test_c191_e_c195_saem_na_mesma_linha_pareados_por_posicao(self, quebrado):
        """É o leiaute do Sistema MA: um C190 traz todos os C191 e depois todos
        os C195, na mesma ordem, e é contra o par que se confere."""
        linhas = _linhas(extrair(quebrado, "C190+C191+C195"))

        # duas linhas por arquivo (dois CST), dois arquivos
        assert len(linhas) == 4
        primeira = linhas[0]
        assert primeira["C191_CST_PIS"] == "01"
        assert primeira["C195_CST_COFINS"] == "01"
        assert primeira["C191_VL_PIS"] == "1,65"
        assert primeira["C195_VL_COFINS"] == "7,60"
        # o pai e o cadastro acompanham
        assert primeira["C190_COD_ITEM"] == "P01"
        assert primeira["0200_DESCR_ITEM"] == "PAO FRANCES"
        # o segundo par é o do CST 50
        assert linhas[1]["C191_CST_PIS"] == "50"
        assert linhas[1]["C195_CST_COFINS"] == "50"

    def test_o_plano_de_contas_entra_pelo_cod_cta(self, quebrado):
        linhas = _linhas(extrair(quebrado, "C190+C191+C195"))

        assert linhas[0]["0500_COD_CTA"] == "31010001"
        assert linhas[0]["0500_NOME_CTA"] == "CLIENTES"


class TestOCatalogoDeItens:
    def test_o_0200_sai_uma_vez_so_e_nao_uma_por_mes(self, quebrado):
        """O 0200 é redeclarado inteiro em todo arquivo mensal: sem dedup, 59
        competências devolvem o catálogo 59 vezes."""
        linhas = _linhas(extrair(quebrado, "0140+0200"))

        assert len(linhas) == 2                      # P01 e P02, e não 4
        assert {l["0200_COD_ITEM"] for l in linhas} == {"P01", "P02"}
        # fica a ocorrência mais recente: o último arquivo lido
        assert {l["competencia"] for l in linhas} == {"2021-07"}


class TestOsCadastrosDoC170:
    def test_a_natureza_e_o_estabelecimento_entram_junto(self, quebrado):
        linhas = _linhas(extrair(quebrado, "C100+C170"))

        assert linhas[0]["0140_NOME"] == "FILIAL UM"
        assert linhas[0]["0400_DESCR_NAT"] == "VENDA DE MERCADORIA"


class TestORecorte:
    def test_sem_recorte_sai_tudo(self, quebrado):
        assert len(_linhas(extrair(quebrado, "C170"))) == 6

    def test_periodo_pula_o_arquivo_inteiro_sem_abrir(self, quebrado):
        linhas = _linhas(extrair(quebrado, "C170", Recorte(de="2021-07-01")))

        assert {l["competencia"] for l in linhas} == {"2021-07"}
        assert len(linhas) == 3

    def test_cnpj_que_nao_existe_devolve_lista_vazia(self, quebrado):
        assert _linhas(extrair(quebrado, "C170", Recorte(cnpjs=frozenset({"99999999"})))) == []

    def test_cst_acha_a_coluna_pelo_sufixo_sem_lista_de_nomes(self, quebrado):
        """`CST_PIS` acha `C170_CST_PIS` na hierarquia e `CST_PIS` no registro
        simples — sem que ninguém mantenha os nomes possíveis escritos."""
        na_hierarquia = _linhas(extrair(quebrado, "C100+C170", Recorte(cst_pis=frozenset({"01"}))))
        no_simples = _linhas(extrair(quebrado, "C170", Recorte(cst_pis=frozenset({"01"}))))

        assert len(na_hierarquia) == 6
        assert len(no_simples) == 6
        assert _linhas(extrair(quebrado, "C170", Recorte(cst_pis=frozenset({"99"})))) == []

    def test_descricao_casa_por_pedaco_em_qualquer_coluna_de_descricao(self, quebrado):
        linhas = _linhas(extrair(quebrado, "C100+C170", Recorte(descricao=("leite",))))

        assert len(linhas) == 2
        assert {l["C170_COD_ITEM"] for l in linhas} == {"P02"}

    def test_valor_minimo_compara_como_numero_e_nao_como_texto(self, quebrado):
        """"70,00" > "50,00" como texto por acaso; "8,00" > "50,00" não."""
        linhas = _linhas(extrair(quebrado, "C170", Recorte(vl_item_min=Decimal("50"))))

        assert sorted(l["VL_ITEM"] for l in linhas) == ["50,00", "50,00", "70,00", "70,00"]

    def test_intervalo_de_data_do_documento(self, quebrado):
        linhas = _linhas(extrair(quebrado, "C100+C170", Recorte(doc_de="2021-06-05")))

        # a nota 123 é de 04/06 e a 124 de 05/06; do arquivo de julho, nenhuma
        assert {l["C100_NUM_DOC"] for l in linhas} == {"124"}

    def test_cada_recorte_tem_o_seu_parquet(self, quebrado):
        """Pedir o C170 de um CNPJ e depois o de outro não pode servir o
        primeiro arquivo para o segundo."""
        inteiro = extrair(quebrado, "C170")
        recortado = extrair(quebrado, "C170", Recorte(cst_pis=frozenset({"01"})))

        assert inteiro != recortado


# ---------------------------------------------------------------------------
# o leiaute que muda de tamanho
# ---------------------------------------------------------------------------
class TestOLeiauteQueMudou:
    """Cinco leiautes estavam errados, e o erro só apareceu ao medir contra
    arquivo real (três competências da DMINAS, 29/09/2026). O que se fixa aqui
    é a **quantidade de campos**: ela é o que o arquivo confirma, e um campo a
    mais ou a menos desloca tudo o que vem depois sem erro nenhum."""

    def test_as_quantidades_batem_com_o_arquivo_real(self):
        esperado = {"0000": 14, "0140": 9, "0150": 13, "0200": 12, "0400": 3,
                    "0500": 9, "C010": 3, "C100": 29, "C170": 37, "C175": 18,
                    "A010": 2, "A100": 21, "A170": 18,
                    "M200": 13, "M210": 16, "M610": 16, "F100": 19}

        assert {r: len(CAMPOS[r]) for r in esperado} == esperado

    def test_o_m210_antigo_nao_desloca_a_aliquota(self):
        """Até 2018 o M210 tinha 13 campos; em 2019 ganhou três ajustes de base
        **no meio**. Ler o antigo com o leiaute novo põe a alíquota na coluna do
        ajuste — dois números de duas casas, e ninguém percebe."""
        from cat.infraestrutura.sped.registros import campos_de  # noqa: PLC0415

        antigo = campos_de("M210", 13)
        novo = campos_de("M210", 16)

        assert antigo[4] == "ALIQ_PIS"
        assert novo[4] == "VL_AJUS_ACRES_BC"
        assert novo[7] == "ALIQ_PIS"
        # o antigo é o novo menos os três ajustes de base: mesmos nomes, mesma ordem
        assert list(antigo) == [c for c in novo
                                if c not in ("VL_AJUS_ACRES_BC", "VL_AJUS_REDUC_BC",
                                             "VL_BC_CONT_AJUS")]

    def test_registro_de_tamanho_desconhecido_cai_no_leiaute_da_tabela(self):
        from cat.infraestrutura.sped.registros import campos_de  # noqa: PLC0415

        assert campos_de("C170", 37) == CAMPOS["C170"]
        assert campos_de("C170", 99) == CAMPOS["C170"]
        assert campos_de("ZZZZ", 5) == ()


# ---------------------------------------------------------------------------
# o que o 047 percorre: a NFC-e e o serviço
# ---------------------------------------------------------------------------
class TestOAnaliticoDaNfce:
    def test_o_c175_sai_com_a_nota_e_sem_item(self, quebrado):
        """O C175 é o analítico da NFC-e: uma linha por CFOP e CST, sem item.
        Numa base de varejo ele é quatro de cada cinco linhas do 047."""
        linhas = _linhas(extrair(quebrado, "C100+C175"))

        assert len(linhas) == 2
        assert linhas[0]["C100_COD_MOD"] == "65"
        assert linhas[0]["C100_NUM_DOC"] == "900"
        assert linhas[0]["C175_CFOP"] == "5102"
        assert linhas[0]["C175_VL_OPR"] == "25,00"
        assert linhas[0]["C175_CST_PIS"] == "01"
        assert linhas[0]["C175_VL_COFINS"] == "1,90"
        # não há item para casar: o C175 não tem COD_ITEM
        assert "0200_DESCR_ITEM" not in linhas[0]

    def test_o_bloco_a_tem_abridor_proprio(self, quebrado):
        """O A010 abre o bloco de serviços, como o C010 abre o de mercadorias:
        sem ele, a nota de serviço sairia pendurada no estabelecimento errado."""
        linhas = _linhas(extrair(quebrado, "A100+A170"))

        assert len(linhas) == 2
        assert linhas[0]["A010_CNPJ"] == CNPJ
        assert linhas[0]["A100_NUM_DOC"] == "7"
        assert linhas[0]["A170_COD_ITEM"] == "S01"
        assert linhas[0]["A170_VL_ITEM"] == "500,00"
        assert linhas[0]["0150_NOME"] == "FORNECEDOR ALFA"

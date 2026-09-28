"""Extrair registro e hierarquia do SPED, consolidados dos arquivos do trabalho.

O que se cobra aqui é o que a quebra sozinha não entregava: pegar o registro
que o analista pediu, de todos os arquivos, com as colunas do leiaute — e, na
hierarquia, com o pai que o SPED só amarra pela posição.

Dois arquivos, de competências diferentes, para que a consolidação apareça: uma
linha do primeiro e uma do segundo no mesmo parquet, cada uma dizendo de onde
veio.
"""

from __future__ import annotations

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.quebra_de_sped import quebrar
from cat.infraestrutura.analitico.registros_do_sped import (
    AlvoDesconhecido,
    colunas_do_alvo,
    disponiveis,
    extrair,
)

CNPJ = "11222333000181"

CABECALHO = ("|0000|006|0|||01062021|30062021|EMPRESA DO TESTE|"
             f"{CNPJ}|SP|3550308||0|0|")


def sped(competencia_ini: str, competencia_fim: str) -> str:
    """Uma EFD-Contribuições curtinha: duas notas, itens, cupom SAT e o bloco M."""
    return "\n".join([
        ("|0000|006|0|||" + competencia_ini + "|" + competencia_fim +
         f"|EMPRESA DO TESTE|{CNPJ}|SP|3550308||0|0|"),
        "|0140|001|FILIAL UM|" + CNPJ + "|SP|123456789012|3550308|||",
        "|0150|F001|FORNECEDOR ALFA|1058|99888777000166||||||||",
        "|0200|P01|PAO FRANCES|||UN|00|19059090|||||",
        "|0200|P02|LEITE INTEGRAL 1L|||UN|00|04012010|||||",
        "|C010|" + CNPJ + "|0|",
        "|C100|0|1|F001|55|00|001|123|35210511222333000181550010000001231000000001"
        "|04062021|04062021|100,00|0|0|0|100,00|9|0|0|0|0|0|0|0|0|0|0|0|0|",
        "|C170|1|P01|PAO FRANCES|10|UN|30,00|0|0|000|5102|||||||||||||01|30,00|1,65|0,50|"
        "||||01|30,00|7,60|2,28|||",
        "|C170|2|P02|LEITE INTEGRAL|5|UN|70,00|0|0|000|5102|||||||||||||01|70,00|1,65|1,16|"
        "||||01|70,00|7,60|5,32|||",
        "|C100|0|1|F001|55|00|001|124|35210511222333000181550010000001241000000002"
        "|05062021|05062021|50,00|0|0|0|50,00|9|0|0|0|0|0|0|0|0|0|0|0|0|",
        "|C170|1|P01|PAO FRANCES|20|UN|50,00|0|0|000|5102|||||||||||||01|50,00|1,65|0,83|"
        "||||01|50,00|7,60|3,80|||",
        "|C860|59|900001|04062021|1|9|",
        "|C870|P01|5102|12,00|0,00|01|12,00|1,65|0,20|01|12,00|7,60|0,91|31010001|",
        "|M200|10,00|0|0|0|10,00|0|0|0|10,00|0|0|0|",
        "|M210|01|1000,00|1000,00|0|1000,00|1,65|16,50|0|0|16,50|0|0|16,50|",
        "|M220|0|1,50|CODAJ|DOC-1|ajuste de teste|01062021|",
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

        assert set(d["blocos"]) == {"0", "C", "M"}
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

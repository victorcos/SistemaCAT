"""O bloco M: a apuração das contribuições e os ajustes dela.

A amostra tem as duas contribuições, para provar que PIS e COFINS são espelhos
e que uma função só lê os dois. E tem o caso que estraga a leitura ingênua: dois
M210 debaixo do mesmo M200, cada um com o seu ajuste — o M220 do segundo não
pode sair carregando o M210 do primeiro.
"""

import pytest

from cat.infraestrutura.sped.apuracao import (
    CADEIAS,
    CONTRIBUICAO,
    CadeiaDesconhecida,
    cadeia,
    colunas_da_cadeia,
    espelho_de,
)
from cat.infraestrutura.sped.registros import nomes_dos_campos

EFD = """|0000|006|0|||01062021|30062021|COMERCIO DO TESTE LTDA|11222333000181|SP|3550308||00|2|
|M100|101|0|10000,00|1,6500||||0,00|0,00|0,00|165,00|0|165,00|0,00|
|M105|01|50|10000,00|0,00|10000,00|10000,00|||1|
|M110|0|15,00|01|DOC1|AJUSTE DE CREDITO|30062021|
|M200|330,00|165,00|0,00|165,00|0,00|0,00|165,00|0,00|0,00|0,00|0,00|165,00|
|M210|01|20000,00|20000,00|1,6500|||330,00|10,00|0,00|0,00|330,00|0|330,00|0,00|
|M220|0|10,00|02|DOC2|AJUSTE DA CONTRIBUICAO A MAIOR|30062021|
|M210|02|5000,00|5000,00|0,6500|||32,50|0,00|5,00|0,00|32,50|0|32,50|0,00|
|M220|1|5,00|03|DOC3|AJUSTE DA CONTRIBUICAO A MENOR|30062021|
|M500|101|0|10000,00|7,6000||||0,00|0,00|0,00|760,00|0|760,00|0,00|
|M505|01|50|10000,00|0,00|10000,00|10000,00|||1|
|M600|1520,00|760,00|0,00|760,00|0,00|0,00|760,00|0,00|0,00|0,00|0,00|760,00|
|M610|01|20000,00|20000,00|7,6000|||1520,00|0,00|0,00|0,00|1520,00|0|1520,00|0,00|
|M620|0|20,00|04|DOC4|AJUSTE COFINS|30062021|
|9999|15|
"""


@pytest.fixture
def arquivo(tmp_path):
    caminho = tmp_path / "contribuicoes.txt"
    caminho.write_bytes(EFD.encode("cp1252"))
    return str(caminho)


class TestACadeia:
    def test_o_detalhe_carrega_a_contribuicao_do_periodo(self, arquivo):
        linhas = list(cadeia(arquivo, "cp1252", "M210"))

        assert len(linhas) == 2
        assert [l["M210_COD_CONT"] for l in linhas] == ["01", "02"]
        assert [l["M210_VL_CONT_APU"] for l in linhas] == ["330,00", "32,50"]
        # o M200 é o mesmo nas duas: é a consolidação do período
        assert {l["M200_VL_TOT_CONT_REC"] for l in linhas} == {"165,00"}

    def test_o_ajuste_sai_com_os_dois_niveis_acima(self, arquivo):
        linhas = list(cadeia(arquivo, "cp1252", "M220"))

        assert len(linhas) == 2
        assert [l["M220_DESCR_AJ"] for l in linhas] == [
            "AJUSTE DA CONTRIBUICAO A MAIOR", "AJUSTE DA CONTRIBUICAO A MENOR"]

    def test_o_ajuste_acompanha_o_detalhe_certo_e_nao_o_primeiro(self, arquivo):
        """Dois M210 no mesmo M200: cada M220 é do seu, não do que veio antes."""
        linhas = list(cadeia(arquivo, "cp1252", "M220"))

        assert [l["M210_COD_CONT"] for l in linhas] == ["01", "02"]
        assert [l["M210_VL_CONT_APU"] for l in linhas] == ["330,00", "32,50"]

    def test_a_base_do_credito_sai_com_o_credito(self, arquivo):
        linhas = list(cadeia(arquivo, "cp1252", "M105"))

        assert len(linhas) == 1
        assert linhas[0]["M105_NAT_BC_CRED"] == "01"
        assert linhas[0]["M100_COD_CRED"] == "101"
        assert linhas[0]["M100_VL_CRED_DISP"] == "165,00"


class TestOEspelhoDaCofins:
    def test_a_mesma_funcao_le_pis_e_cofins(self, arquivo):
        pis = list(cadeia(arquivo, "cp1252", "M210"))
        cofins = list(cadeia(arquivo, "cp1252", "M610"))

        assert pis[0]["M210_ALIQ_PIS"] == "1,6500"
        assert cofins[0]["M610_ALIQ_COFINS"] == "7,6000"
        assert cofins[0]["M600_VL_TOT_CONT_REC"] == "760,00"

    @pytest.mark.parametrize("pis, cofins", [
        ("M105", "M505"), ("M110", "M510"), ("M210", "M610"), ("M220", "M620")])
    def test_toda_cadeia_de_pis_tem_a_gemea_na_cofins(self, pis, cofins):
        assert espelho_de(pis) == cofins
        assert espelho_de(cofins) == pis
        # a estrutura é a mesma; só os nomes dos valores mudam
        assert len(CADEIAS[pis]) == len(CADEIAS[cofins])

    def test_a_contribuicao_de_cada_cadeia_fica_dita(self):
        assert CONTRIBUICAO["M210"] == "PIS/PASEP"
        assert CONTRIBUICAO["M610"] == "COFINS"
        assert set(CONTRIBUICAO) == set(CADEIAS)


class TestOQueFalta:
    def test_pai_ausente_sai_em_branco_em_vez_de_a_linha_sumir(self, tmp_path):
        """Bloco truncado existe; perder o ajuste seria perder valor apurado."""
        truncado = tmp_path / "truncado.txt"
        truncado.write_bytes(
            "|M210|01|100,00|100,00|1,6500|||1,65||||||||".encode("cp1252"))

        linhas = list(cadeia(str(truncado), "cp1252", "M210"))

        assert len(linhas) == 1
        assert linhas[0]["M210_COD_CONT"] == "01"
        assert linhas[0]["M200_VL_TOT_CONT_REC"] == ""

    def test_registro_que_o_modulo_nao_conhece_diz_o_que_conhece(self, arquivo):
        with pytest.raises(CadeiaDesconhecida, match="M210"):
            list(cadeia(arquivo, "cp1252", "M999"))

    def test_arquivo_sem_o_bloco_m_nao_devolve_nada(self, tmp_path):
        vazio = tmp_path / "so_bloco_c.txt"
        vazio.write_bytes("|C010|11222333000181|0|".encode("cp1252"))
        assert list(cadeia(str(vazio), "cp1252", "M210")) == []


class TestContrato:
    @pytest.mark.parametrize("folha", sorted(CADEIAS))
    def test_toda_cadeia_tem_leiaute_para_cada_registro(self, folha):
        for registro in CADEIAS[folha]:
            assert nomes_dos_campos(registro), f"{registro} não está na tabela de registros"

    @pytest.mark.parametrize("folha", ["M210", "M220", "M610", "M105"])
    def test_as_colunas_sao_conhecidas_antes_de_ler(self, folha, arquivo):
        colunas = colunas_da_cadeia(folha)
        linha = next(iter(cadeia(arquivo, "cp1252", folha)))
        assert set(linha) == set(colunas)
        assert colunas[-1].startswith(f"{folha}_")

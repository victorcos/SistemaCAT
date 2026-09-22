"""O caminho consolidado da EFD-Contribuições: C180/C190 com os filhos casados.

O que estes testes protegem é a armadilha do leiaute: os filhos **não vêm
intercalados**. Vêm todos os de PIS e só depois todos os de COFINS, e o
casamento é por posição. Quem supuser 1:1:1 na leitura sequencial — que é a
suposição natural — soma o PIS de um CFOP com o COFINS de outro, sem erro
nenhum aparecer.
"""

import pytest

from cat.infraestrutura.sped.consolidado import (
    ADQUIRIDAS,
    EMITIDAS,
    colunas_do_consolidado,
    grupos_consolidados,
)

# Duas mercadorias adquiridas, cada uma com dois CFOP. Repare na ordem dentro de
# cada grupo: C191, C191, C195, C195 — nunca alternados.
EFD = """|0000|006|0|||01062021|30062021|COMERCIO DO TESTE LTDA|11222333000181|SP|3550308||00|2|
|0200|SKU1|XAMPU 350ML||||00|33051000|||||
|0200|SKU2|SABONETE 90G||||00|34011190|||||
|0500|01062021|01|A|3|3.1.1|COMPRAS DE MERCADORIA||
|0500|01062021|01|A|3|4.2.2|DEVOLUCAO DE COMPRA||
|C010|11222333000181|0|
|C190|55|01062021|30062021|SKU1|33051000||1000,00|
|C191|F01|50|1102|600,00|0,00|600,00|1,6500|||9,90|3.1.1|
|C191|F01|50|1202|400,00|0,00|400,00|1,6500|||6,60|4.2.2|
|C195|F01|50|1102|600,00|0,00|600,00|7,6000|||45,60|3.1.1|
|C195|F01|50|1202|400,00|0,00|400,00|7,6000|||30,40|4.2.2|
|C190|55|01062021|30062021|SKU2|34011190||500,00|
|C191|F01|50|1102|500,00|0,00|500,00|1,6500|||8,25|3.1.1|
|C195|F01|50|1102|500,00|0,00|500,00|7,6000|||38,00|3.1.1|
|9999|15|
"""

EMITIDAS_EFD = """|0000|006|0|||01062021|30062021|COMERCIO DO TESTE LTDA|11222333000181|SP|3550308||00|2|
|0200|SKU1|XAMPU 350ML||||00|33051000|||||
|C010|11222333000181|0|
|C180|55|01062021|30062021|SKU1|33051000||2000,00|
|C181|01|5102|2000,00|0,00|2000,00|1,6500|||33,00|3.1.1|
|C185|01|5102|2000,00|0,00|2000,00|7,6000|||152,00|3.1.1|
|9999|7|
"""


@pytest.fixture
def adquiridas(tmp_path):
    caminho = tmp_path / "contribuicoes.txt"
    caminho.write_bytes(EFD.encode("cp1252"))
    return str(caminho)


@pytest.fixture
def emitidas(tmp_path):
    caminho = tmp_path / "emitidas.txt"
    caminho.write_bytes(EMITIDAS_EFD.encode("cp1252"))
    return str(caminho)


class TestOCasamentoDosFilhos:
    def test_pis_e_cofins_casam_pela_posicao_e_nao_pela_ordem_de_leitura(self, adquiridas):
        linhas = list(grupos_consolidados(adquiridas, "cp1252", ADQUIRIDAS))

        assert len(linhas) == 3
        # o primeiro grupo tem dois CFOP; cada linha tem de fechar o MESMO CFOP
        # dos dois lados — é isto que a suposição 1:1:1 quebraria
        for linha in linhas:
            assert linha["C191_CFOP"] == linha["C195_CFOP"]
        assert [l["C191_CFOP"] for l in linhas] == ["1102", "1202", "1102"]
        assert [l["C191_VL_PIS"] for l in linhas] == ["9,90", "6,60", "8,25"]
        assert [l["C195_VL_COFINS"] for l in linhas] == ["45,60", "30,40", "38,00"]

    def test_cada_linha_carrega_o_pai_a_mercadoria_e_a_conta(self, adquiridas):
        primeira = next(iter(grupos_consolidados(adquiridas, "cp1252", ADQUIRIDAS)))

        assert primeira["C190_COD_ITEM"] == "SKU1"
        assert primeira["C190_VL_TOT_ITEM"] == "1000,00"
        assert primeira["0200_COD_NCM"] == "33051000"
        assert primeira["C010_CNPJ"] == "11222333000181"
        # o plano de contas vem pelo COD_CTA do filho
        assert primeira["0500_NOME_CTA"] == "COMPRAS DE MERCADORIA"

    def test_a_conta_acompanha_o_cfop_da_linha(self, adquiridas):
        linhas = list(grupos_consolidados(adquiridas, "cp1252", ADQUIRIDAS))
        assert linhas[1]["C191_CFOP"] == "1202"
        assert linhas[1]["0500_NOME_CTA"] == "DEVOLUCAO DE COMPRA"

    def test_o_grupo_troca_quando_o_pai_troca(self, adquiridas):
        linhas = list(grupos_consolidados(adquiridas, "cp1252", ADQUIRIDAS))
        assert [l["C190_COD_ITEM"] for l in linhas] == ["SKU1", "SKU1", "SKU2"]

    def test_o_ultimo_grupo_sai_mesmo_sem_pai_depois_dele(self, adquiridas):
        """O grupo fecha no próximo pai — ou no fim do arquivo."""
        linhas = list(grupos_consolidados(adquiridas, "cp1252", ADQUIRIDAS))
        assert linhas[-1]["C190_COD_ITEM"] == "SKU2"


class TestListasDesiguais:
    def test_lado_que_falta_sai_em_branco_em_vez_de_a_linha_sumir(self, tmp_path):
        """Perder a linha seria perder valor apurado."""
        torto = tmp_path / "torto.txt"
        torto.write_bytes(
            ("|C010|11222333000181|0|" + chr(10)
             + "|C190|55|01062021|30062021|SKU1|33051000||100,00|" + chr(10)
             + "|C191|F01|50|1102|100,00|0,00|100,00|1,6500|||1,65|3.1.1|" + chr(10)
             + "|C191|F01|50|1202|50,00|0,00|50,00|1,6500|||0,82|3.1.1|" + chr(10)
             + "|C195|F01|50|1102|100,00|0,00|100,00|7,6000|||7,60|3.1.1|").encode("cp1252"))

        linhas = list(grupos_consolidados(str(torto), "cp1252", ADQUIRIDAS))

        assert len(linhas) == 2
        assert linhas[1]["C191_VL_PIS"] == "0,82"
        assert linhas[1]["C195_VL_COFINS"] == ""


class TestOsDoisGrupos:
    def test_as_emitidas_usam_c180_com_os_mesmos_campos(self, emitidas):
        linhas = list(grupos_consolidados(emitidas, "cp1252", EMITIDAS))

        assert len(linhas) == 1
        assert linhas[0]["C180_COD_ITEM"] == "SKU1"
        assert linhas[0]["C181_CST_PIS"] == "01"
        assert linhas[0]["C185_VL_COFINS"] == "152,00"
        # a venda consolidada não diz para quem se vendeu
        assert "C181_COD_PART" not in linhas[0]

    def test_a_aquisicao_sabe_de_quem_se_comprou(self, adquiridas):
        primeira = next(iter(grupos_consolidados(adquiridas, "cp1252", ADQUIRIDAS)))
        assert primeira["C191_COD_PART"] == "F01"

    def test_procurar_c180_num_arquivo_so_de_c190_nao_inventa_linha(self, adquiridas):
        assert list(grupos_consolidados(adquiridas, "cp1252", EMITIDAS)) == []


class TestContrato:
    @pytest.mark.parametrize("qual", [ADQUIRIDAS, EMITIDAS])
    def test_as_colunas_sao_conhecidas_antes_de_ler(self, qual, adquiridas, emitidas):
        arquivo = adquiridas if qual is ADQUIRIDAS else emitidas
        colunas = colunas_do_consolidado(qual)
        linha = next(iter(grupos_consolidados(arquivo, "cp1252", qual)))
        assert set(linha) == set(colunas)

    def test_os_dois_grupos_tem_o_mesmo_leiaute_de_pai(self):
        from cat.infraestrutura.sped.registros import nomes_dos_campos
        assert nomes_dos_campos("C180") == nomes_dos_campos("C190")

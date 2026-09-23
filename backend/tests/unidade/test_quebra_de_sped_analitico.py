"""A quebra: abrir os SPED e dizer o que há dentro.

O que sai daqui é o inventário — que arquivos entraram, que registros cada um
tem e quantos de cada. A **Consulta de Entradas** e o **razão** saíram desta
rodada em 23/09/2026 e têm teste próprio, em `test_piscofins_analitico.py`.
"""

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.quebra_de_sped import (
    ARQUIVO_DAS_CONTAGENS,
    ARQUIVO_DOS_ARQUIVOS,
    QuebraCancelada,
    quebrar,
    serializar,
)

CONTRIBUICOES = """|0000|006|0|||01062021|30062021|COMERCIO DO TESTE LTDA|11222333000181|SP|3550308||00|2|
|0140|001|MATRIZ|11222333000181|SP|111|3550308||||
|0150|F01|FORNECEDOR ALFA|1058|99888777000166||111|3304557||||||
|0200|SKU1|XAMPU 350ML||||00|33051000||||||
|0500|01062021|01|A|3|3.1.1|COMPRAS DE MERCADORIA||
|C010|11222333000181|0|
|C100|0|1|F01|55|00|1|1001|35210611222333000181550010000010011000010017|01062021|02062021|1000,00||||900,00||||||||||||||
|C170|1|SKU1||10,000|UN|500,00||0|000|1102|N01|500,00|18,00|90,00||||0||||||50|500,00|1,6500|||8,25|50|500,00|7,6000|||38,00|3.1.1|
|9999|9|
"""

ECD = """|0000|LECD|0||01062021|30062021|COMERCIO DO TESTE LTDA|11222333000181|SP|111|3550308||||
|I050|01062021|01|A|3|3.1.1|3|CAIXA|
|I200|1|10062021|1000,00|N||
|I250|3.1.1||1000,00|D|1|001|RECEBIMENTO|C09||
|I250|3.1.1||400,00|C|1|002|PAGAMENTO|C09||
|9999|6|
"""


@pytest.fixture
def base(tmp_path):
    contrib = tmp_path / "contribuicoes.txt"
    contrib.write_bytes(CONTRIBUICOES.encode("cp1252"))
    ecd = tmp_path / "ecd.txt"
    ecd.write_bytes(ECD.encode("cp1252"))
    return str(contrib), str(ecd), str(tmp_path / "saida")


def _ler(pasta: str, nome: str) -> list[dict]:
    return pq.read_table(f"{pasta}/{nome}").to_pylist()


class TestOQueFoiLido:
    def test_cada_arquivo_vira_uma_linha_com_o_que_tem_dentro(self, base):
        contrib, ecd, destino = base

        quebrar([contrib], [ecd], destino)

        arquivos = {a["tipo"]: a for a in _ler(destino, ARQUIVO_DOS_ARQUIVOS)}
        assert arquivos["contribuicoes"]["itens"] == 1
        assert arquivos["contribuicoes"]["empresa"] == "COMERCIO DO TESTE LTDA"
        assert arquivos["ecd"]["contas"] == 1
        assert arquivos["ecd"]["partidas"] == 2
        assert all(not a["erro"] for a in arquivos.values())

    def test_a_contagem_por_registro_sai_por_arquivo(self, base):
        contrib, ecd, destino = base

        quebrar([contrib], [ecd], destino)

        contagens = _ler(destino, ARQUIVO_DAS_CONTAGENS)
        por_registro = {c["registro"]: c["quantidade"] for c in contagens}
        assert por_registro["C170"] == 1
        assert por_registro["C100"] == 1
        # a ECD não tem contagem por registro como a EFD; o que ela tem de
        # contável são os dois blocos que importam — um lançamento com duas
        # partidas, que é a partida dobrada de sempre
        assert por_registro["I200"] == 1
        assert por_registro["I250"] == 2

    def test_o_resumo_conta_os_dois_tipos_de_arquivo(self, base):
        contrib, ecd, destino = base

        resumo = quebrar([contrib], [ecd], destino)

        assert (resumo.contribuicoes, resumo.ecd, resumo.arquivos) == (1, 1, 2)
        assert resumo.estabelecimentos == ["11222333000181"]
        assert resumo.competencias == ["2021-06"]
        assert resumo.registros > 0


class TestOQueDaErrado:
    def test_arquivo_ilegivel_nao_derruba_a_rodada_e_fica_anotado(self, tmp_path):
        torto = tmp_path / "nao_e_ecd.txt"
        torto.write_bytes("|0000|LECD|0||01062021|30062021|X|11222333000181|SP|".encode("cp1252"))
        destino = str(tmp_path / "saida")

        resumo = quebrar([], [str(torto)], destino)

        assert resumo.ilegiveis == 1
        assert resumo.arquivos == 0
        assert "I050" in resumo.avisos[0]
        # a linha do arquivo sai mesmo assim, dizendo o que houve: sumir da
        # lista seria a pessoa procurar por que o total não fecha
        assert _ler(destino, ARQUIVO_DOS_ARQUIVOS)[0]["erro"]

    def test_trabalho_sem_arquivo_nenhum_produz_parquet_legivel(self, tmp_path):
        destino = str(tmp_path / "saida")

        resumo = quebrar([], [], destino)

        assert resumo.arquivos == 0
        # os parquets existem e têm esquema: a etapa seguinte não precisa saber
        # a diferença entre "vazio" e "não rodou"
        assert _ler(destino, ARQUIVO_DOS_ARQUIVOS) == []
        assert _ler(destino, ARQUIVO_DAS_CONTAGENS) == []

    def test_cancelar_interrompe_antes_do_arquivo_seguinte(self, base):
        contrib, ecd, destino = base
        with pytest.raises(QuebraCancelada):
            quebrar([contrib], [ecd], destino, deve_parar=lambda: True)


class TestOResumoSerializado:
    def test_o_resumo_vai_inteiro_para_o_historico(self, base):
        contrib, ecd, destino = base

        serializado = serializar(quebrar([contrib], [ecd], destino))

        assert serializado["versao"] == 2
        assert serializado["arquivos"] == 2
        assert serializado["competencias"] == ["2021-06"]
        # o que saiu daqui não pode reaparecer no resumo
        assert "entradas" not in serializado
        assert "linhas_do_razao" not in serializado

"""A apuração de PIS/COFINS: o par que se confronta.

A Consulta de Entradas de um lado, o razão contábil do outro — e os dois saindo
da mesma rodada, sobre a mesma base, sem ninguém precisar juntar depois.

Era parte da quebra até 23/09/2026. A quebra abre os arquivos; esta confronta o
fiscal com o contábil.
"""

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.escrita import LeituraCancelada
from cat.infraestrutura.analitico.piscofins import (
    ARQUIVO_DAS_ENTRADAS,
    ARQUIVO_DO_RAZAO,
    confrontar,
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


class TestOParQueSeConfronta:
    def test_a_mesma_rodada_produz_as_entradas_e_o_razao(self, base):
        contrib, ecd, destino = base

        resumo = confrontar([contrib], [ecd], destino)

        assert resumo.entradas == 1
        assert resumo.linhas_do_razao == 2
        entradas = _ler(destino, ARQUIVO_DAS_ENTRADAS)
        razao = _ler(destino, ARQUIVO_DO_RAZAO)
        assert entradas[0]["numero_do_documento"] == "1001"
        assert entradas[0]["nome_do_participante"] == "FORNECEDOR ALFA"
        assert [l["historico"] for l in razao] == ["RECEBIMENTO", "PAGAMENTO"]
        # o saldo corre no razão: 1000 a débito, 400 a crédito
        assert [l["saldo"] for l in razao] == ["1000.00", "600.00"]

    def test_o_resumo_conta_os_dois_lados(self, base):
        contrib, ecd, destino = base

        resumo = confrontar([contrib], [ecd], destino)

        assert (resumo.contribuicoes, resumo.ecd, resumo.arquivos) == (1, 1, 2)
        assert resumo.estabelecimentos == ["11222333000181"]
        assert resumo.competencias == ["2021-06"]
        assert sum(resumo.por_ramo.values()) == 1


class TestUmLadoSo:
    def test_sem_ecd_sai_a_037_e_o_razao_fica_vazio(self, base):
        contrib, _, destino = base

        resumo = confrontar([contrib], [], destino)

        assert resumo.entradas == 1
        assert resumo.linhas_do_razao == 0
        # o parquet existe mesmo vazio: quem lê não precisa saber a diferença
        assert _ler(destino, ARQUIVO_DO_RAZAO) == []

    def test_sem_efd_sai_o_razao_e_a_037_fica_vazia(self, base):
        _, ecd, destino = base

        resumo = confrontar([], [ecd], destino)

        assert resumo.linhas_do_razao == 2
        assert resumo.entradas == 0
        assert _ler(destino, ARQUIVO_DAS_ENTRADAS) == []


class TestOQueDaErrado:
    def test_ecd_ilegivel_vira_aviso_e_nao_derruba(self, tmp_path):
        torto = tmp_path / "nao_e_ecd.txt"
        torto.write_bytes("|0000|LECD|0||01062021|30062021|X|11222333000181|SP|".encode("cp1252"))
        destino = str(tmp_path / "saida")

        resumo = confrontar([], [str(torto)], destino)

        assert resumo.ilegiveis == 1
        assert resumo.arquivos == 0
        assert "I050" in resumo.avisos[0]

    def test_cancelar_interrompe_antes_do_arquivo_seguinte(self, base):
        contrib, ecd, destino = base
        with pytest.raises(LeituraCancelada):
            confrontar([contrib], [ecd], destino, deve_parar=lambda: True)


class TestOResumoSerializado:
    def test_o_resumo_vai_inteiro_para_o_historico(self, base):
        contrib, ecd, destino = base

        serializado = serializar(confrontar([contrib], [ecd], destino))

        assert serializado["versao"] == 1
        assert serializado["entradas"] == 1
        assert serializado["linhas_do_razao"] == 2
        assert serializado["competencias"] == ["2021-06"]

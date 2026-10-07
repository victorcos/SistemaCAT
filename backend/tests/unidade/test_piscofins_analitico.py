"""A apuração de PIS/COFINS: o par que se confronta.

A Consulta de Entradas de um lado, o razão contábil do outro — e os dois saindo
da mesma rodada, sobre a mesma base, sem ninguém precisar juntar depois. Desde
29/09/2026 sai junto a **Consulta de Saídas (047)**, da mesma EFD.

Era parte da quebra até 23/09/2026. A quebra abre os arquivos; esta confronta o
fiscal com o contábil.
"""

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.escrita import LeituraCancelada
from cat.infraestrutura.analitico.piscofins import (
    ARQUIVO_DAS_ENTRADAS,
    ARQUIVO_DAS_SAIDAS,
    ARQUIVO_DO_RAZAO,
    confrontar,
    fonte_do_razao,
    partes_do_razao,
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
|C100|1|0|F01|55|00|1|2001|35210611222333000181550010000020011000020015|03062021|03062021|700,00||||700,00||||||||||||||
|C170|1|SKU1||5,000|UN|700,00||0|000|5102|N01|700,00|18,00|126,00||||0||||||01|700,00|1,6500|||11,55|01|700,00|7,6000|||53,20|3.1.1|
|C400|2D|ECF|ABC|001|
|9999|12|
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


class TestAsEcdEmParalelo:
    """As ECD lidas em processos paralelos, uma parte do razão por arquivo.

    **Por que existe.** Medido em 07/10/2026 numa base de 60 ECD e 294 GB: a
    leitura é Python puro em um núcleo — `readline` a 6 µs, que é buffer e não
    disco, contra ~80 µs por linha montando campo, dicionário, `Decimal` e
    objeto. A rodada ficou 15,6 h em 32 arquivos usando 79% de **um**
    processador, com o resto da máquina parado.

    O que estes testes cobram é o que a paralelização não pode quebrar: a mesma
    saída, lida pelos mesmos lugares. O razão deixou de ser um arquivo e passou
    a poder ser uma pasta de partes — e **execução antiga não se regrava**, então
    quem lê tem de aceitar as duas formas.
    """

    def test_duas_ecd_produzem_o_mesmo_que_uma_de_cada_vez(self, base, tmp_path,
                                                           monkeypatch):
        """A prova que importa: paralelo e serial dão a mesma coisa."""
        from cat.infraestrutura.analitico import piscofins

        contrib, ecd, _ = base
        outra = tmp_path / "ecd2.txt"
        outra.write_bytes(ECD.encode("cp1252"))

        from cat.config import obter_config

        serial = str(tmp_path / "serial")
        monkeypatch.setenv("CAT_PROCESSOS_DE_ECD", "1")
        obter_config.cache_clear()
        r1 = confrontar([contrib], [ecd, str(outra)], serial)

        paralelo = str(tmp_path / "paralelo")
        monkeypatch.setenv("CAT_PROCESSOS_DE_ECD", "2")
        obter_config.cache_clear()
        r2 = confrontar([contrib], [ecd, str(outra)], paralelo)
        obter_config.cache_clear()

        # **sem isto o teste passaria sem exercitar nada**: o caminho paralelo
        # grava uma parte por ECD, o serial grava um arquivo só. É a forma em
        # disco que prova por onde a rodada foi
        assert len(partes_do_razao(serial)) == 1
        assert len(partes_do_razao(paralelo)) == 2, (
            "a rodada caiu no caminho serial e o teste não provaria nada")

        assert r1.linhas_do_razao == r2.linhas_do_razao == 4
        assert r1.ecd == r2.ecd == 2
        # a soma das partes é a mesma lista, qualquer que seja a forma
        def tudo(pasta):
            linhas = []
            for parte in partes_do_razao(pasta):
                linhas += pq.read_table(parte).to_pylist()
            return sorted((l["conta"], l["historico"], l["saldo"]) for l in linhas)
        assert tudo(serial) == tudo(paralelo)

    def test_o_razao_de_uma_execucao_antiga_continua_sendo_achado(self, base):
        """Arquivo único: é o que todas as rodadas até 07/10/2026 gravaram."""
        contrib, ecd, destino = base
        confrontar([contrib], [ecd], destino)

        fonte = fonte_do_razao(destino)

        assert fonte is not None and fonte.endswith(ARQUIVO_DO_RAZAO)
        assert partes_do_razao(destino) == [fonte]

    def test_sem_ecd_nenhuma_nao_ha_razao_e_isso_e_dito(self, tmp_path):
        """`None` é diferente de "um razão vazio": quem lê precisa distinguir
        para dizer "rode de novo" em vez de mostrar zero linhas."""
        assert fonte_do_razao(str(tmp_path)) is None
        assert partes_do_razao(str(tmp_path)) == []


class TestOParQueSeConfronta:
    def test_a_mesma_rodada_produz_as_entradas_e_o_razao(self, base):
        contrib, ecd, destino = base

        resumo = confrontar([contrib], [ecd], destino)

        assert resumo.entradas == 1
        assert resumo.saidas == 1
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
        # **a competência vem do cabeçalho, não da linha de entrada.** Arquivo
        # sem entrada nenhuma — uma locadora cuja EFD só tem nota de serviço —
        # sumia da contagem, e a tela dizia "4 competências" de uma base que
        # cobre 44. E o CNPJ entra pelos catorze dígitos: o `str` do Cnpj sai
        # com máscara, e misturar as duas formas listava o mesmo
        # estabelecimento duas vezes
        assert len(resumo.estabelecimentos) == 1, "o mesmo CNPJ em dois formatos"
        assert sum(resumo.por_ramo.values()) == 1
        assert sum(resumo.por_ramo_das_saidas.values()) == 1
        # o C400 é saída, existe no arquivo e a 047 ainda não o monta: tem de
        # aparecer contado, e não sumir
        assert resumo.nao_cobertos == {"C400": 1}
        assert serializar(resumo)["nao_cobertos"] == {"C400": 1}

    def test_a_047_sai_do_mesmo_arquivo_e_traz_so_a_saida(self, base):
        contrib, ecd, destino = base

        confrontar([contrib], [ecd], destino)

        saidas = _ler(destino, ARQUIVO_DAS_SAIDAS)
        assert [l["numero_do_documento"] for l in saidas] == ["2001"]
        assert saidas[0]["cfop"] == "5102"
        # na saída a origem somos nós: SP do estabelecimento, RJ do participante
        assert saidas[0]["uf_origem_destino"] == "SP/RJ"
        assert (saidas[0]["natureza"], saidas[0]["faturamento"]) == ("Venda", "Faturamento")


class TestUmLadoSo:
    def test_sem_ecd_sai_a_037_e_o_razao_fica_vazio(self, base):
        contrib, _, destino = base

        resumo = confrontar([contrib], [], destino)

        assert (resumo.entradas, resumo.saidas) == (1, 1)
        assert resumo.linhas_do_razao == 0
        # o parquet existe mesmo vazio: quem lê não precisa saber a diferença
        assert _ler(destino, ARQUIVO_DO_RAZAO) == []

    def test_sem_efd_sai_o_razao_e_a_037_fica_vazia(self, base):
        _, ecd, destino = base

        resumo = confrontar([], [ecd], destino)

        assert resumo.linhas_do_razao == 2
        assert (resumo.entradas, resumo.saidas) == (0, 0)
        assert _ler(destino, ARQUIVO_DAS_ENTRADAS) == []
        assert _ler(destino, ARQUIVO_DAS_SAIDAS) == []


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

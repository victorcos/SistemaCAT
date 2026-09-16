"""A contingência das notas não escrituradas, na etapa 3.

A EFD é a de `test_movimentos`, de maio de 2021. Na pasta: uma entrada e uma
saída que ela não tem, uma devolução emitida pelo próprio estabelecimento, e o
que não é contingência — a nota escriturada, a de julho (mês sem EFD), a de
outra empresa e a cancelada na SEFAZ.
"""

from __future__ import annotations

from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.canceladas import ler_chaves_canceladas
from cat.infraestrutura.analitico.contingencia import ARQUIVO_CONTINGENCIA
from cat.infraestrutura.analitico.itens_do_xml import extrair_itens_do_xml
from cat.infraestrutura.analitico.movimentacao import consolidar
from cat.infraestrutura.analitico.movimentos import extrair_movimentos
from cat.infraestrutura.planilhas.movimentacao import gerar_contingencia
from tests.unidade.test_itens_do_xml import ICMS00, ICMS60, det, nfe
from tests.unidade.test_movimentos import (
    C100_ENTRADA, C170_1, C170_2, C170_SEM_CADASTRO, C190_ENTRADA, C190_ENTRADA_60,
    CABECALHO, CHAVE_ENTRADA, CNPJ, CONV_A_FD, ITEM_A_V2, ITEM_B, escrever,
)

D = Decimal
FORNECEDOR = "99888777000166"
CHAVE_COMPRA = "41210599888777000166550010000007771000000011"
CHAVE_VENDA = "41210511517841000278550010000008881000000012"
CHAVE_DEVOLUCAO = "41210511517841000278550010000009991000000013"
CHAVE_JULHO = "41210799888777000166550010000001111000000014"
CHAVE_DE_OUTROS = "41210599888777000166550010000002221000000015"
CHAVE_CANCELADA = "41210511517841000278550010000003331000000016"


def em_julho(xml: bytes) -> bytes:
    return xml.replace(b"2021-05-01", b"2021-07-02")


@pytest.fixture
def pasta(tmp_path):
    efd = escrever(tmp_path, "efd_2021_05.txt", [
        CABECALHO, ITEM_A_V2, CONV_A_FD, ITEM_B,
        C100_ENTRADA, C170_1, C170_2, C170_SEM_CADASTRO, C190_ENTRADA, C190_ENTRADA_60,
    ])
    arquivos = {
        "compra.xml": nfe(CHAVE_COMPRA, det(1, "F1", "5405", "1", "100.00", ICMS60)
                          + det(2, "F2", "5102", "1", "50.00", ICMS00)),
        "venda.xml": nfe(CHAVE_VENDA, det(1, "1000144", "5102", "2", "200.00", ICMS00), emit=CNPJ),
        "devolucao.xml": nfe(CHAVE_DEVOLUCAO, det(1, "1000144", "1202", "1", "30.00", ICMS60),
                             tp="0", emit=CNPJ),
        "escriturada.xml": nfe(CHAVE_ENTRADA, det(1, "FORN-1", "5405", "10", "100.00", ICMS60)),
        "julho.xml": em_julho(nfe(CHAVE_JULHO, det(1, "F1", "5405", "1", "10.00", ICMS60))),
        "de_outros.xml": nfe(CHAVE_DE_OUTROS, det(1, "F1", "5405", "1", "10.00", ICMS60))
                         .replace(f"<dest><CNPJ>{CNPJ}".encode(), b"<dest><CNPJ>55444333000122"),
        "cancelada.xml": nfe(CHAVE_CANCELADA, det(1, "1000144", "5102", "1", "80.00", ICMS00), emit=CNPJ),
    }
    xmls = []
    for nome, conteudo in sorted(arquivos.items()):
        (tmp_path / nome).write_bytes(conteudo)
        xmls.append(str(tmp_path / nome))
    (tmp_path / "canceladas.txt").write_text(CHAVE_CANCELADA)
    destino = str(tmp_path / "saida")
    extrair_movimentos([efd], destino)
    extrair_itens_do_xml(xmls, destino)
    ler_chaves_canceladas([str(tmp_path / "canceladas.txt")], destino)
    resumo = consolidar(destino, None)
    linhas = pq.read_table(f"{destino}/{ARQUIVO_CONTINGENCIA}").to_pylist()
    return destino, resumo, linhas


class TestQuemEntra:
    def test_so_o_do_estabelecimento_no_mes_com_efd_fora_da_efd_e_nao_cancelado(self, pasta):
        _, _, linhas = pasta
        assert sorted({l["chave"] for l in linhas}) == sorted([CHAVE_COMPRA, CHAVE_VENDA, CHAVE_DEVOLUCAO])
        assert {l["cnpj"] for l in linhas} == {CNPJ}

    def test_a_operacao_e_a_do_estabelecimento(self, pasta):
        _, _, linhas = pasta
        operacao = {l["chave"]: l["operacao"] for l in linhas}
        assert operacao == {CHAVE_COMPRA: "entrada", CHAVE_VENDA: "saida", CHAVE_DEVOLUCAO: "entrada"}


class TestMulta:
    def test_entrada_paga_dez_por_cento_do_valor_e_saida_setenta_e_cinco_do_icms(self, pasta):
        _, _, linhas = pasta
        multa = {(l["chave"], l["numero_item"]): (l["base_da_multa"], l["percentual"], l["multa"])
                 for l in linhas}
        assert multa == {
            (CHAVE_COMPRA, 1): (D("100.00"), D("10.00"), D("10.00")),
            (CHAVE_COMPRA, 2): (D("50.00"), D("10.00"), D("5.00")),
            (CHAVE_VENDA, 1): (D("9.00"), D("75.00"), D("6.75")),
            (CHAVE_DEVOLUCAO, 1): (D("30.00"), D("10.00"), D("3.00")),
        }
        venda = next(l for l in linhas if l["chave"] == CHAVE_VENDA)
        assert venda["fundamento"].startswith("RICMS/SP art. 527, I, b")

    def test_o_resumo_soma_sem_selic(self, pasta):
        _, resumo, _ = pasta
        assert (resumo.nao_escrituradas_entradas, resumo.nao_escrituradas_saidas) == (2, 1)
        assert (resumo.valor_nao_escriturado_entradas, resumo.icms_nao_escriturado_saidas) == (
            D("180.00"), D("9.00"))
        assert (resumo.multa_nao_escrituradas_entradas, resumo.multa_nao_escrituradas_saidas) == (
            D("18.00"), D("6.75"))
        assert [(f.rotulo, f.documentos, f.valor) for f in resumo.contingencia_por_ano] == [
            ("2021", 3, D("24.75"))]
        assert any("R$ 24,75" in a and "sem SELIC" in a for a in resumo.avisos)


class TestPlanilha:
    def test_nota_a_nota(self, pasta, tmp_path):
        destino, _, _ = pasta
        assert gerar_contingencia(f"{destino}/{ARQUIVO_CONTINGENCIA}", str(tmp_path / "c.xlsx")) == 4


def test_sem_xml_nao_ha_contingencia(tmp_path):
    efd = escrever(tmp_path, "efd.txt", [CABECALHO, ITEM_A_V2, CONV_A_FD, ITEM_B, C100_ENTRADA, C170_1, C190_ENTRADA])
    destino = str(tmp_path / "saida")
    extrair_movimentos([efd], destino)
    resumo = consolidar(destino, None)
    assert pq.read_metadata(f"{destino}/{ARQUIVO_CONTINGENCIA}").num_rows == 0
    assert (resumo.nao_escrituradas_entradas, resumo.multa_nao_escrituradas_saidas) == (0, D("0.00"))

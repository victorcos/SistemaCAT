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
CHAVE_VENDA = "41210544000002000237550010000008881000000016"
CHAVE_DEVOLUCAO = "41210544000002000237550010000009991000000015"
CHAVE_JULHO = "41210799888777000166550010000001111000000014"
CHAVE_DE_OUTROS = "41210599888777000166550010000002221000000015"
CHAVE_CANCELADA = "41210544000002000237550010000003331000000010"


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


# ---------------------------------------------------------------------------
# a base que o XML não traz: a da nota mais próxima do mesmo produto
# ---------------------------------------------------------------------------
def emitida_em(xml: bytes, dia: str) -> bytes:
    return xml.replace(b"2021-05-01", dia.encode())


def icms00(valor: str) -> str:
    return (f"<ICMS00><orig>0</orig><CST>00</CST><vBC>{valor}</vBC><pICMS>18.00</pICMS>"
            f"<vICMS>{valor}</vICMS></ICMS00>")


def chave(n: int, emitente: str = CNPJ) -> str:
    return f"4121{'05'}{emitente}550010000{n:05d}1{n:07d}"[:44].ljust(44, "0")


@pytest.fixture
def vizinhas(tmp_path):
    efd = escrever(tmp_path, "efd_2021_05.txt", [CABECALHO, ITEM_A_V2, CONV_A_FD, ITEM_B,
                                                 C100_ENTRADA, C170_1, C190_ENTRADA])
    arquivos = {
        # vendas com ICMS de A1: 10 un. com 18,00 no dia 3 e 10 un. com 30,00 no dia 20
        "venda_dia03.xml": emitida_em(nfe(chave(101), det(1, "A1", "5102", "10", "100.00", icms00("18.00")),
                                          emit=CNPJ), "2021-05-03"),
        "venda_dia20.xml": emitida_em(nfe(chave(102), det(1, "A1", "5102", "10", "100.00", icms00("30.00")),
                                          emit=CNPJ), "2021-05-20"),
        # remessas sem ICMS: dia 10 (mais perto da do dia 3), dia 18 (mais perto da do dia 20)
        "remessa_dia10.xml": emitida_em(nfe(chave(103), det(1, "A1", "5949", "4", "40.00", ICMS60), emit=CNPJ),
                                        "2021-05-10"),
        "remessa_dia18.xml": emitida_em(nfe(chave(104), det(1, "A1", "5949", "5", "50.00", ICMS60), emit=CNPJ),
                                        "2021-05-18"),
        # ZZ não tem nota nenhuma com ICMS
        "remessa_sem_par.xml": emitida_em(nfe(chave(105), det(1, "ZZ", "5949", "1", "10.00", ICMS60), emit=CNPJ),
                                          "2021-05-10"),
        # entrada de valor zero (bonificação): o valor por unidade da compra do mesmo código
        "compra.xml": emitida_em(nfe(chave(106, "99888777000166"), det(1, "F9", "1403", "2", "20.00", ICMS60)),
                                 "2021-05-05"),
        "bonificacao.xml": emitida_em(nfe(chave(107, "99888777000166"), det(1, "F9", "1910", "3", "0.00", ICMS60)),
                                      "2021-05-06"),
    }
    xmls = []
    for nome, conteudo in sorted(arquivos.items()):
        (tmp_path / nome).write_bytes(conteudo)
        xmls.append(str(tmp_path / nome))
    destino = str(tmp_path / "saida")
    extrair_movimentos([efd], destino)
    extrair_itens_do_xml(xmls, destino)
    resumo = consolidar(destino, None)
    linhas = {l["chave"]: l for l in pq.read_table(f"{destino}/{ARQUIVO_CONTINGENCIA}").to_pylist()}
    return resumo, linhas


class TestBaseDaNotaVizinha:
    def test_com_icms_no_xml_vale_o_xml(self, vizinhas):
        _, linhas = vizinhas
        venda = linhas[chave(101)]
        assert (venda["origem_da_base"], venda["base_da_multa"], venda["multa"]) == ("xml", D("18.00"), D("13.50"))

    def test_sem_icms_leva_o_unitario_da_nota_mais_proxima(self, vizinhas):
        _, linhas = vizinhas
        dia10, dia18 = linhas[chave(103)], linhas[chave(104)]
        # dia 10: a do dia 3 (7 dias) ganha da do dia 20 (10 dias) -> 1,80 × 4
        assert (dia10["origem_da_base"], dia10["unitario_de_referencia"], dia10["base_da_multa"],
                dia10["multa"], dia10["chave_de_referencia"]) == (
            "nota anterior", D("1.800000"), D("7.20"), D("5.40"), chave(101))
        # dia 18: a do dia 20 (2 dias) -> 3,00 × 5
        assert (dia18["origem_da_base"], dia18["base_da_multa"], dia18["multa"]) == (
            "nota posterior", D("15.00"), D("11.25"))

    def test_sem_nota_do_produto_fica_com_base_zero(self, vizinhas):
        _, linhas = vizinhas
        sem = linhas[chave(105)]
        assert (sem["origem_da_base"], sem["base_da_multa"], sem["multa"]) == ("sem referência", D("0.00"), D("0.00"))

    def test_entrada_de_valor_zero_leva_o_valor_por_unidade(self, vizinhas):
        _, linhas = vizinhas
        bonificacao = linhas[chave(107, "99888777000166")]
        assert (bonificacao["origem_da_base"], bonificacao["base_da_multa"], bonificacao["multa"]) == (
            "nota anterior", D("30.00"), D("3.00"))

    def test_o_resumo_conta_e_avisa(self, vizinhas):
        resumo, _ = vizinhas
        assert (resumo.contingencia_itens_de_nota_vizinha, resumo.contingencia_itens_sem_referencia) == (3, 1)
        assert resumo.icms_nao_escriturado_saidas == D("18.00") + D("30.00") + D("7.20") + D("15.00")
        assert any("nota mais próxima" in a for a in resumo.avisos)


def test_empate_de_datas_fica_com_a_anterior_e_depois_a_chave(tmp_path):
    efd = escrever(tmp_path, "efd.txt", [CABECALHO, ITEM_A_V2, CONV_A_FD, ITEM_B, C100_ENTRADA, C170_1, C190_ENTRADA])
    arquivos = {
        "antes.xml": emitida_em(nfe(chave(201), det(1, "B1", "5102", "1", "10.00", icms00("2.00")), emit=CNPJ),
                                "2021-05-08"),
        "depois.xml": emitida_em(nfe(chave(202), det(1, "B1", "5102", "1", "10.00", icms00("5.00")), emit=CNPJ),
                                 "2021-05-12"),
        "remessa.xml": emitida_em(nfe(chave(203), det(1, "B1", "5949", "2", "20.00", ICMS60), emit=CNPJ),
                                  "2021-05-10"),
    }
    xmls = []
    for nome, conteudo in arquivos.items():
        (tmp_path / nome).write_bytes(conteudo)
        xmls.append(str(tmp_path / nome))
    destino = str(tmp_path / "saida")
    extrair_movimentos([efd], destino)
    extrair_itens_do_xml(xmls, destino)
    consolidar(destino, None)
    linha = next(l for l in pq.read_table(f"{destino}/{ARQUIVO_CONTINGENCIA}").to_pylist() if l["chave"] == chave(203))
    assert (linha["origem_da_base"], linha["base_da_multa"]) == ("nota anterior", D("4.00"))


def test_devolucao_nao_serve_de_referencia(tmp_path):
    """A devolução de compra (5.411) carrega o valor da compra, não o da venda."""
    efd = escrever(tmp_path, "efd.txt", [CABECALHO, ITEM_A_V2, CONV_A_FD, ITEM_B, C100_ENTRADA, C170_1, C190_ENTRADA])
    arquivos = {
        "devolucao.xml": emitida_em(nfe(chave(301), det(1, "C1", "5411", "1", "10.00", icms00("1.00")), emit=CNPJ),
                                    "2021-05-10"),
        "venda.xml": emitida_em(nfe(chave(302), det(1, "C1", "6108", "1", "10.00", icms00("4.00")), emit=CNPJ),
                                "2021-05-25"),
        "remessa.xml": emitida_em(nfe(chave(303), det(1, "C1", "5949", "2", "20.00", ICMS60), emit=CNPJ),
                                  "2021-05-10"),
    }
    xmls = []
    for nome, conteudo in arquivos.items():
        (tmp_path / nome).write_bytes(conteudo)
        xmls.append(str(tmp_path / nome))
    destino = str(tmp_path / "saida")
    extrair_movimentos([efd], destino)
    extrair_itens_do_xml(xmls, destino)
    consolidar(destino, None)
    linha = next(l for l in pq.read_table(f"{destino}/{ARQUIVO_CONTINGENCIA}").to_pylist() if l["chave"] == chave(303))
    assert (linha["origem_da_base"], linha["chave_de_referencia"], linha["base_da_multa"]) == (
        "nota posterior", chave(302), D("8.00"))

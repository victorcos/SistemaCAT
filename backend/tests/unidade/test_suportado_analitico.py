"""A apuração do ICMS suportado ponta a ponta, sobre parquet de verdade.

O que se prova aqui é a junção: o item de CST 60 que a EFD zera precisa sair
com valor quando o relatório do cliente informa, e precisa sair marcado como
"informado pelo fornecedor" — não como se estivesse na nota.
"""

from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cat.dominio.cat42.suportado import Fonte
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_ITENS, ARQUIVO_MOVIMENTOS
from cat.infraestrutura.analitico.suportado import (
    ARQUIVO_RETIDO,
    ARQUIVO_SUPORTADO,
    ESQUEMA_RETIDO,
    apurar,
    fatias_por_fonte,
)

CNPJ = "11517841000278"
CHAVE_A = "4" * 44
CHAVE_B = "5" * 44
CHAVE_C = "6" * 44


def d(v: str) -> Decimal:
    return Decimal(v)


def escrever_movimentos(pasta, linhas: list[dict]) -> None:
    esquema = pa.schema([
        ("cnpj", pa.string()), ("competencia", pa.date32()),
        ("chave", pa.string()), ("codigo", pa.string()),
        ("cst_icms", pa.string()), ("operacao", pa.string()),
        ("quantidade", pa.decimal128(18, 5)),
        ("valor_icms", pa.decimal128(18, 2)),
        ("valor_st", pa.decimal128(18, 2)),
        ("bc_st", pa.decimal128(18, 2)),
    ])
    colunas = {c: [l.get(c) for l in linhas] for c in esquema.names}
    pq.write_table(pa.Table.from_pydict(colunas, schema=esquema),
                   str(pasta / ARQUIVO_MOVIMENTOS))


def escrever_retido(pasta, linhas: list[tuple[str, str, str]]) -> None:
    """Usa o esquema do próprio módulo, e não uma cópia.

    Uma cópia com duas casas escondeu o defeito que derrubou a extração real:
    o teste gravava o que o módulo não gravaria."""
    pq.write_table(pa.Table.from_pydict({
        "chave": [c for c, _, _ in linhas],
        "codigo": [k for _, k, _ in linhas],
        "informado": [d(v) for _, _, v in linhas],
    }, schema=ESQUEMA_RETIDO), str(pasta / ARQUIVO_RETIDO))


def escrever_cadastro(pasta, linhas: list[tuple[str, str, str]]) -> None:
    esquema = pa.schema([("cnpj", pa.string()), ("codigo", pa.string()),
                         ("aliq_icms", pa.decimal128(9, 4))])
    pq.write_table(pa.Table.from_pydict({
        "cnpj": [c for c, _, _ in linhas],
        "codigo": [k for _, k, _ in linhas],
        "aliq_icms": [d(a) for _, _, a in linhas],
    }, schema=esquema), str(pasta / ARQUIVO_ITENS))


def movimento(**kw) -> dict:
    base = {"cnpj": CNPJ, "competencia": date(2021, 5, 1), "chave": CHAVE_A,
            "codigo": "117110", "cst_icms": "060", "operacao": "entrada",
            "quantidade": d("1.00000"), "valor_icms": d("0.00"),
            "valor_st": d("0.00"), "bc_st": d("0.00")}
    base.update(kw)
    return base


def ler_saida(pasta) -> list[dict]:
    return pq.read_table(str(pasta / ARQUIVO_SUPORTADO)).to_pylist()


class TestSemRelatorio:
    def test_cst60_sozinho_fica_sem_apurar(self, tmp_path):
        """O retrato de hoje sem o relatório do cliente: a EFD não tem."""
        escrever_movimentos(tmp_path, [movimento()])
        resumo = apurar(str(tmp_path))
        assert resumo.itens == 1
        assert resumo.itens_apurados == 0
        assert resumo.por_fonte[Fonte.NAO_APURAVEL] == 1
        linha = ler_saida(tmp_path)[0]
        assert linha["fonte"] == "nao_apuravel"
        assert "CST 60" in linha["motivo"]

    def test_destacado_na_entrada_apura_sem_relatorio(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(cst_icms="010", valor_icms=d("18.00"), valor_st=d("9.00")),
        ])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_total == d("27.00")
        assert resumo.por_fonte[Fonte.DOCUMENTO] == 1
        assert ler_saida(tmp_path)[0]["suportado"] == d("27.00")

    def test_saida_nao_entra_na_apuracao(self, tmp_path):
        """Saída consome o suportado, não o traz."""
        escrever_movimentos(tmp_path, [
            movimento(operacao="saida", cst_icms="060"),
            movimento(operacao="entrada", cst_icms="010",
                      valor_icms=d("1.00"), valor_st=d("1.00")),
        ])
        assert apurar(str(tmp_path)).itens == 1


class TestComRelatorio:
    def test_o_relatorio_fecha_o_buraco_do_cst60(self, tmp_path):
        """O ponto da etapa: o que a EFD zera, o cliente informa."""
        escrever_movimentos(tmp_path, [movimento()])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "4.75")])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_total == d("4.75")
        assert resumo.por_fonte[Fonte.INFORMADO_PELO_FORNECEDOR] == 1
        assert resumo.cobertura == 1.0
        assert ler_saida(tmp_path)[0]["fonte"] == "informado_pelo_fornecedor"

    def test_o_valor_informado_nao_se_disfarca_de_documento(self, tmp_path):
        """A procedência é o que separa pedido sustentável de chute."""
        escrever_movimentos(tmp_path, [movimento()])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "4.75")])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_documental == d("4.75")
        assert resumo.por_fonte[Fonte.DOCUMENTO] == 0

    def test_a_juncao_e_por_chave_E_codigo(self, tmp_path):
        """Chave igual e código diferente não casa: uma nota tem muitos itens,
        e casar só pela chave daria o imposto de um item a outro."""
        escrever_movimentos(tmp_path, [
            movimento(codigo="117110"),
            movimento(codigo="999999"),
        ])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "4.75")])
        resumo = apurar(str(tmp_path))
        assert resumo.por_fonte[Fonte.INFORMADO_PELO_FORNECEDOR] == 1
        assert resumo.por_fonte[Fonte.NAO_APURAVEL] == 1

    def test_nota_diferente_nao_casa(self, tmp_path):
        escrever_movimentos(tmp_path, [movimento(chave=CHAVE_B)])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "4.75")])
        assert apurar(str(tmp_path)).itens_apurados == 0

    def test_destaque_na_nota_vence_o_informado(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(cst_icms="010", valor_icms=d("18.00"), valor_st=d("9.00")),
        ])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "999.00")])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_total == d("27.00")
        assert resumo.por_fonte[Fonte.DOCUMENTO] == 1


class TestPrecisao:
    """O relatório do cliente traz ICMS com quatro casas.

    Um esquema de duas casas não grava esse valor: o pyarrow recusa a
    gravação inteira. Foi o que derrubou a primeira extração de 2021, depois
    de treze minutos de leitura.
    """

    def test_valor_com_quatro_casas_sobrevive(self, tmp_path):
        escrever_movimentos(tmp_path, [movimento()])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "2.3341")])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_total == d("2.3341")
        assert ler_saida(tmp_path)[0]["suportado"] == d("2.334100")

    def test_soma_de_centavos_nao_se_perde(self, tmp_path):
        """Arredondar item a item desloca o total em base grande."""
        escrever_movimentos(tmp_path, [
            movimento(chave=CHAVE_A), movimento(chave=CHAVE_B),
            movimento(chave=CHAVE_C),
        ])
        escrever_retido(tmp_path, [(CHAVE_A, "117110", "0.3333"),
                                   (CHAVE_B, "117110", "0.3333"),
                                   (CHAVE_C, "117110", "0.3333")])
        assert apurar(str(tmp_path)).valor_total == d("0.9999")


class TestReconstrucao:
    def test_base_e_aliquota_do_cadastro_reconstroem(self, tmp_path):
        escrever_movimentos(tmp_path, [movimento(bc_st=d("150.00"))])
        escrever_cadastro(tmp_path, [(CNPJ, "117110", "18.0000")])
        resumo = apurar(str(tmp_path))
        assert resumo.valor_total == d("27.00")
        assert resumo.por_fonte[Fonte.BASE_E_ALIQUOTA] == 1
        assert resumo.valor_documental == Decimal(0), "reconstrução não é documento"

    def test_sem_cadastro_nao_reconstroi(self, tmp_path):
        escrever_movimentos(tmp_path, [movimento(bc_st=d("150.00"))])
        assert apurar(str(tmp_path)).itens_apurados == 0


class TestResumoParaATela:
    def test_as_fatias_so_trazem_fonte_que_ocorreu(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(cst_icms="010", valor_icms=d("18.00"), valor_st=d("9.00")),
            movimento(chave=CHAVE_B),
        ])
        escrever_retido(tmp_path, [(CHAVE_B, "117110", "5.00")])
        fatias = fatias_por_fonte(apurar(str(tmp_path)))
        codigos = {f["codigo"] for f in fatias}
        assert codigos == {"documento", "informado_pelo_fornecedor"}
        assert all(f["rotulo"] for f in fatias)

    def test_cobertura_e_fracao_documental(self, tmp_path):
        escrever_movimentos(tmp_path, [
            movimento(cst_icms="010", valor_icms=d("18.00"), valor_st=d("9.00")),
            movimento(chave=CHAVE_B, bc_st=d("100.00")),
            movimento(chave=CHAVE_C),
        ])
        escrever_cadastro(tmp_path, [(CNPJ, "117110", "18.0000")])
        resumo = apurar(str(tmp_path))
        assert resumo.itens == 3
        assert resumo.itens_apurados == 2
        assert round(resumo.cobertura, 4) == round(2 / 3, 4)
        assert resumo.valor_total == d("45.00")        # 27 + 18
        assert resumo.valor_documental == d("27.00")


class TestOrdemDasEtapas:
    def test_sem_movimentacao_a_apuracao_recusa_e_diz_o_que_falta(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="movimentação"):
            apurar(str(tmp_path))

"""O fechamento do período sobre a Ficha 3 gravada, com a conta à mão.

Loja A (SP), mercadoria X:

    abertura ..................... 2 un
    10/01 entrada ................ saldo 12 un, R$ 60
    20/01 saída, enq. 1 .......... saldo 7 un, R$ 35; ressarcimento 10,00
    05/02 saída, enq. 1 .......... saldo 3 un, R$ 15; ressarcimento 4,00

Mercadoria Y, retirada por estoque negativo, sai em fevereiro e não soma.
Loja B é do Paraná e tem saída de enquadramento 4, com confronto pendente.
"""

from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cat.infraestrutura.analitico.apuracao import (
    ARQUIVO_APURACAO,
    ARQUIVO_SALDOS,
    apurar,
    competencias,
    serializar,
)
from cat.infraestrutura.analitico.razao import (
    ARQUIVO_CONFERENCIA_INVENTARIO,
    ARQUIVO_FICHA3,
    ARQUIVO_FICHAS,
    ESQUEMA_FICHA3,
    ESQUEMA_FICHAS,
)
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada

A = "11111111000191"
B = "22222222000180"


def d(v) -> Decimal:
    return Decimal(str(v))


def linha(**kw) -> dict:
    base = {"cnpj": A, "codigo": "X", "numero": 1, "data": date(2021, 1, 10),
            "especie": "saida", "devolucao": False, "cfop": "5405", "documento": "doc",
            "origem": "relatorio", "enquadramento": 1, "enquadramento_indefinido": False,
            "ficha_retirada": False, "unidade_origem": "", "fator_conversao": d(1),
            "unidade_sem_fator": False, "quantidade": d(-1), "icms_suportado": d(-5),
            "valor_unitario_usado": d(5), "icms_efetivo": d(5), "saldo_quantidade": d(7),
            "saldo_unitario": d(5), "saldo_valor": d(35), "ressarcimento": d(0),
            "complemento": d(0)}
    return {**base, **kw}


def ficha(**kw) -> dict:
    base = {"cnpj": A, "uf": "SP", "codigo": "X", "descricao": "Item", "linhas": 2,
            "abertura_quantidade": d(2), "abertura_sem_valor": True, "entradas": d(10),
            "saidas": d(9), "saldo_quantidade": d(3), "saldo_valor": d(15),
            "ressarcimento": d(14), "complemento": d(0), "ficou_negativo": False,
            "retirada": False, "saidas_sem_aliquota": 0, "saidas_indefinidas": 0,
            "linhas_sem_fator": 0}
    return {**base, **kw}


@pytest.fixture
def razao(tmp_path):
    pasta = tmp_path / "razao"
    pasta.mkdir()
    pq.write_table(pa.Table.from_pylist([
        linha(numero=1, data=date(2021, 1, 10), especie="entrada", enquadramento=None,
              quantidade=d(10), icms_suportado=d(60), icms_efetivo=None,
              saldo_quantidade=d(12), saldo_valor=d(60)),
        linha(numero=2, data=date(2021, 1, 20), ressarcimento=d(10),
              saldo_quantidade=d(7), saldo_valor=d(35)),
        linha(numero=3, data=date(2021, 2, 5), ressarcimento=d(4), icms_efetivo=d(2),
              saldo_quantidade=d(3), saldo_valor=d(15)),
        # ficha retirada: sai em fevereiro e não soma
        linha(numero=1, codigo="Y", data=date(2021, 2, 8), ficha_retirada=True,
              ressarcimento=d(100), saldo_quantidade=d(-1), saldo_valor=d(-5)),
        # outra loja, enquadramento 4: confronto pendente
        linha(numero=1, cnpj=B, codigo="Z", enquadramento=4, icms_efetivo=None,
              saldo_quantidade=d(5), saldo_valor=d(25)),
    ], schema=ESQUEMA_FICHA3), str(pasta / ARQUIVO_FICHA3))
    pq.write_table(pa.Table.from_pylist([
        ficha(),
        ficha(codigo="Y", retirada=True, ficou_negativo=True, abertura_quantidade=d(0),
              ressarcimento=d(100), saldo_quantidade=d(-1), saldo_valor=d(-5)),
        ficha(cnpj=B, uf="PR", codigo="Z", abertura_quantidade=d(0), ressarcimento=d(0),
              saldo_quantidade=d(5), saldo_valor=d(25)),
    ], schema=ESQUEMA_FICHAS), str(pasta / ARQUIVO_FICHAS))
    pq.write_table(pa.table({
        "cnpj": [A, A, B], "codigo": ["X", "X", "Z"],
        "data_inventario": [date(2021, 1, 31), date(2021, 2, 28), date(2021, 1, 31)],
        "saldo_ficha": [d(7), d(3), d(5)], "inventario": [d(7), d(90), d(5)],
        "diferenca": [d(0), d(-87), d(0)],
        "situacao": ["bate", "divergente", "bate"],
    }), str(pasta / ARQUIVO_CONFERENCIA_INVENTARIO))
    return str(pasta)


@pytest.fixture
def apurado(razao, tmp_path):
    destino = tmp_path / "apuracao"
    destino.mkdir()
    resumo = apurar(razao, str(destino), uf_por_cnpj={A: "SP", B: "PR"})
    return destino, resumo


def linhas_de(destino, arquivo) -> list[dict]:
    return pq.read_table(str(destino / arquivo)).to_pylist()


class TestFechamento:
    def test_uma_linha_por_estabelecimento_e_mes(self, apurado):
        destino, r = apurado
        chaves = [(l["cnpj"], l["competencia"]) for l in linhas_de(destino, ARQUIVO_APURACAO)]
        assert sorted(chaves) == [(A, "2021-01"), (A, "2021-02"), (B, "2021-01")]
        assert r.competencias == 3 and r.estabelecimentos == 2

    def test_ressarcimento_e_complemento_nao_se_misturam(self, apurado):
        _, r = apurado
        assert r.ressarcimento == d(14)            # 10 em janeiro, 4 em fevereiro
        assert r.complemento == 0
        assert r.credito_operacao_propria == 0     # art. 271 preparado e zerado

    def test_ficha_retirada_nao_soma(self, apurado):
        destino, _ = apurado
        fev = next(l for l in linhas_de(destino, ARQUIVO_APURACAO) if l["competencia"] == "2021-02")
        assert fev["ressarcimento"] == d(4) and fev["fichas_retiradas"] == 1

    def test_so_o_que_esta_limpo_e_apto(self, apurado):
        destino, r = apurado
        por_mes = {(l["cnpj"], l["competencia"]): l for l in linhas_de(destino, ARQUIVO_APURACAO)}
        assert por_mes[(A, "2021-01")]["apta"] and por_mes[(A, "2021-01")]["motivos"] == ""
        assert por_mes[(A, "2021-02")]["motivos"] == "ficha_retirada,diverge_do_inventario"
        assert por_mes[(B, "2021-01")]["motivos"] == "fora_de_sp,confronto_pendente"
        assert r.aptas == 1
        # o que dá para pedir hoje é só o da competência limpa
        assert r.ressarcimento_apto == d(10)
        assert r.estabelecimentos_aptos == 0       # a loja A tem fevereiro travado


class TestSaldosDoRegistro1050:
    def test_o_saldo_inicial_do_mes_e_o_final_do_anterior(self, apurado):
        destino, _ = apurado
        saldos = {(l["cnpj"], l["competencia"], l["codigo"]): l
                  for l in linhas_de(destino, ARQUIVO_SALDOS)}
        janeiro = saldos[(A, "2021-01", "X")]
        fevereiro = saldos[(A, "2021-02", "X")]
        # no primeiro mês da mercadoria, o inicial é a abertura do inventário
        assert janeiro["qtd_ini"] == d(2) and janeiro["icms_tot_ini"] == 0
        assert janeiro["qtd_fim"] == d(7) and janeiro["icms_tot_fim"] == d(35)
        assert fevereiro["qtd_ini"] == d(7) and fevereiro["icms_tot_ini"] == d(35)
        assert fevereiro["qtd_fim"] == d(3) and fevereiro["icms_tot_fim"] == d(15)

    def test_a_ficha_retirada_fica_marcada_no_saldo(self, apurado):
        destino, r = apurado
        y = next(l for l in linhas_de(destino, ARQUIVO_SALDOS) if l["codigo"] == "Y")
        assert y["retirada"] and r.saldos == 4


class TestATela:
    def test_recortes_e_motivos_legiveis(self, apurado):
        destino, _ = apurado
        assert competencias(str(destino), so="aptas")["total"] == 1
        assert competencias(str(destino), so="bloqueadas")["total"] == 2
        assert competencias(str(destino), so="fora_de_sp")["total"] == 1
        bloqueada = competencias(str(destino), so="ficha_retirada")["linhas"][0]
        assert [m["codigo"] for m in bloqueada["motivos"]] == ["ficha_retirada", "diverge_do_inventario"]
        assert bloqueada["motivos"][0]["o_que_fazer"]
        assert competencias(str(destino), busca="2021-01")["total"] == 2

    def test_recorte_desconhecido_e_recusado(self, apurado):
        destino, _ = apurado
        with pytest.raises(ValueError):
            competencias(str(destino), so="tudo")

    def test_resumo_para_o_banco(self, apurado):
        _, r = apurado
        s = serializar(r)
        assert s["ressarcimento"] == "14.00" and s["ressarcimento_apto"] == "10.00"
        assert [m["competencia"] for m in s["por_competencia"]] == ["2021-01", "2021-02"]
        assert {m["codigo"] for m in s["por_motivo"]} == {
            "fora_de_sp", "ficha_retirada", "confronto_pendente", "diverge_do_inventario"}


class TestCancelar:
    def test_cancelar_nao_deixa_apuracao_pela_metade(self, razao, tmp_path):
        destino = tmp_path / "cancelado"
        destino.mkdir()
        with pytest.raises(ApuracaoCancelada):
            apurar(razao, str(destino), deve_parar=lambda: True)
        assert not (destino / ARQUIVO_APURACAO).exists()
        assert not (destino / ARQUIVO_SALDOS).exists()

    def test_sem_razao_recusa_e_diz_o_que_falta(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="razão"):
            apurar(str(tmp_path), str(tmp_path))

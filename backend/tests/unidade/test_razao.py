"""Razão do item — a Ficha 3 em código.

Cada teste aqui corresponde a uma exigência do manual da CAT 42. Quando um
falhar, o que quebrou foi a norma, não uma preferência de implementação.
"""

from datetime import date
from decimal import Decimal

import pytest

from cat.dominio.cat42.razao import (
    Especie,
    EnquadramentoLegal,
    Movimento,
    MovimentoInvalido,
    RazaoDoItem,
    ResumoDoRazao,
    SaldoInicial,
)

D = Decimal
DIA = date(2025, 1, 10)


def entrada(qtd, icms, quando=DIA, **t):
    return Movimento(data=quando, especie=Especie.ENTRADA, quantidade=D(qtd),
                     icms_suportado=D(icms), **t)


def saida(qtd, quando=DIA, enq=EnquadramentoLegal.DEMAIS_SAIDAS, efetivo=None, **t):
    return Movimento(data=quando, especie=Especie.SAIDA, quantidade=D(qtd),
                     enquadramento=enq,
                     icms_efetivo=D(efetivo) if efetivo is not None else None, **t)


def razao(*movimentos, inicial=None):
    r = RazaoDoItem("ITEM-1", inicial)
    r.lancar_varios(movimentos)
    return r.apurar()


class TestCustoMedioPonderadoMovel:
    """O método exigido no item 2.2."""

    def test_entrada_unica_define_o_unitario(self):
        l = razao(entrada(10, 20))
        assert l[0].saldo_quantidade == D(10)
        assert l[0].saldo_unitario == D(2)

    def test_duas_entradas_ponderam(self):
        """10 a 2,00 mais 10 a 4,00 dá 20 a 3,00 — média, não a última."""
        l = razao(entrada(10, 20), entrada(10, 40, ordem_na_fonte=1))
        assert l[-1].saldo_quantidade == D(20)
        assert l[-1].saldo_unitario == D(3)

    def test_saida_usa_o_unitario_do_saldo_anterior(self):
        """Coluna 14: o unitário vem da linha imediatamente anterior."""
        l = razao(entrada(10, 30), saida(4, ordem_na_fonte=1))
        assert l[1].valor_unitario_usado == D(3)
        assert l[1].icms_suportado == D(-12)

    def test_saida_nao_muda_o_unitario(self):
        l = razao(entrada(10, 30), saida(4, ordem_na_fonte=1))
        assert l[1].saldo_unitario == D(3)
        assert l[1].saldo_quantidade == D(6)
        assert l[1].saldo_valor == D(18)

    def test_entrada_depois_de_saida_repondera(self):
        l = razao(
            entrada(10, 30),
            saida(5, ordem_na_fonte=1),
            entrada(5, 5, quando=date(2025, 1, 11)),
        )
        # sobram 5 a 3,00 = 15, mais 5 a 1,00 = 5 -> 10 unidades, 20,00
        assert l[-1].saldo_quantidade == D(10)
        assert l[-1].saldo_unitario == D(2)


class TestOrdemDentroDoDia:
    """"as entradas e devoluções antes das saídas" — item 2.2."""

    def test_entrada_lancada_depois_ainda_vem_antes_da_saida(self):
        """A ordem de lançamento não pode mudar o resultado."""
        pela_ordem_certa = razao(entrada(10, 30), saida(10, ordem_na_fonte=1))
        na_ordem_torta = razao(saida(10, ordem_na_fonte=1), entrada(10, 30))
        assert [x.saldo_valor for x in pela_ordem_certa] == [
            x.saldo_valor for x in na_ordem_torta
        ]

    def test_sem_a_regra_o_custo_medio_sairia_diferente(self):
        """Prova de que a ordem importa: com a entrada do dia contada, a saída
        leva 3,00; sem ela, levaria o unitário antigo."""
        l = razao(
            entrada(10, 10),                                   # 1,00 cada
            entrada(10, 50, ordem_na_fonte=1),                 # sobe a média
            saida(1, ordem_na_fonte=2),
        )
        assert l[-1].valor_unitario_usado == D(3)

    def test_abertura_vem_antes_de_tudo(self):
        m = Movimento(data=DIA, especie=Especie.ABERTURA, quantidade=D(5),
                      icms_suportado=D(10), ordem_na_fonte=9)
        l = razao(saida(1), m)
        assert l[0].movimento.especie is Especie.ABERTURA

    def test_dias_diferentes_seguem_a_data(self):
        l = razao(
            entrada(5, 5, quando=date(2025, 1, 20)),
            entrada(5, 15, quando=date(2025, 1, 10)),
        )
        assert [x.data for x in l] == [date(2025, 1, 10), date(2025, 1, 20)]


class TestDevolucao:
    """"lançamento nas mesmas colunas da origem, com sinal negativo" — 3.3.6."""

    def test_devolucao_de_entrada_tira_do_estoque(self):
        l = razao(entrada(10, 30), entrada(4, 12, devolucao=True, ordem_na_fonte=1))
        assert l[-1].saldo_quantidade == D(6)
        assert l[-1].saldo_valor == D(18)

    def test_devolucao_de_saida_devolve_ao_estoque(self):
        l = razao(
            entrada(10, 30),
            saida(4, ordem_na_fonte=1),
            saida(4, devolucao=True, quando=date(2025, 1, 11)),
        )
        assert l[-1].saldo_quantidade == D(10)
        assert l[-1].saldo_valor == D(30)

    def test_devolucao_nao_apura_ressarcimento(self):
        """Colunas 25 e 26: "exceto nas devoluções de saída"."""
        l = razao(
            entrada(10, 100),
            saida(2, devolucao=True, enq=EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO,
                  efetivo=1, ordem_na_fonte=1),
        )
        assert l[-1].ressarcimento == D(0)
        assert l[-1].complemento == D(0)

    def test_quantidade_negativa_e_recusada(self):
        """Devolução se marca em `devolucao`, não com sinal na quantidade."""
        with pytest.raises(MovimentoInvalido, match="devolução"):
            Movimento(data=DIA, especie=Especie.SAIDA, quantidade=D(-1))


class TestApuracao:
    def test_ressarcimento_e_a_diferenca_positiva(self):
        l = razao(
            entrada(10, 100),                       # 10,00 por unidade
            saida(1, enq=EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO,
                  efetivo=4, ordem_na_fonte=1),
        )
        assert l[-1].ressarcimento == D(6)
        assert l[-1].complemento == D(0)

    def test_diferenca_negativa_no_enquadramento_2_nao_vira_complemento(self):
        """O manual só prevê complemento a partir da coluna 15, que é o
        enquadramento 1. Foi o que a gente havia interpretado errado."""
        l = razao(
            entrada(10, 10),                        # 1,00 por unidade
            saida(1, enq=EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO,
                  efetivo=5, ordem_na_fonte=1),
        )
        assert l[-1].ressarcimento == D(0)
        assert l[-1].complemento == D(0)

    def test_diferenca_negativa_no_enquadramento_1_vira_complemento(self):
        l = razao(
            entrada(10, 10),
            saida(1, enq=EnquadramentoLegal.CONSUMIDOR_FINAL,
                  efetivo=5, ordem_na_fonte=1),
        )
        assert l[-1].complemento == D(4)
        assert l[-1].ressarcimento == D(0)

    def test_enquadramento_zero_nunca_apura(self):
        l = razao(
            entrada(10, 100),
            saida(1, enq=EnquadramentoLegal.DEMAIS_SAIDAS, efetivo=1,
                  ordem_na_fonte=1),
        )
        assert l[-1].ressarcimento == D(0)

    def test_sem_valor_de_confronto_nao_apura(self):
        """Sem o ICMS efetivo não há o que confrontar; inventar daria número
        errado com aparência de certo."""
        l = razao(
            entrada(10, 100),
            saida(1, enq=EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO,
                  ordem_na_fonte=1),
        )
        assert l[-1].ressarcimento == D(0)

    def test_confronto_muda_conforme_o_enquadramento(self):
        assert EnquadramentoLegal.CONSUMIDOR_FINAL.confronta_com_saida
        assert EnquadramentoLegal.ISENCAO_OU_NAO_INCIDENCIA.confronta_com_saida
        assert not EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO.confronta_com_saida
        assert not EnquadramentoLegal.OUTRO_ESTADO.confronta_com_saida


class TestSaldoInicial:
    def test_transcricao_do_periodo_anterior(self):
        """Item 3.3.1: o saldo vem da mesma ficha do período anterior."""
        l = razao(saida(2), inicial=SaldoInicial(D(10), D(50)))
        assert l[0].valor_unitario_usado == D(5)
        assert l[0].saldo_quantidade == D(8)
        assert l[0].saldo_valor == D(40)

    def test_ficha_sem_movimento_nao_gera_linha(self):
        assert razao(inicial=SaldoInicial(D(10), D(50))) == []


class TestEstoqueZerado:
    def test_zerar_limpa_o_valor(self):
        """Sem isto, resto de arredondamento fica preso no estoque e volta a
        aparecer na próxima entrada."""
        l = razao(entrada(3, 10), saida(3, ordem_na_fonte=1))
        assert l[-1].saldo_quantidade == D(0)
        assert l[-1].saldo_valor == D(0)
        assert l[-1].saldo_unitario == D(0)

    def test_saida_sem_estoque_usa_unitario_zero(self):
        l = razao(saida(1))
        assert l[0].valor_unitario_usado == D(0)
        assert l[0].icms_suportado == D(0)


class TestItemSemStEmEstoque:
    def test_baixa_de_item_sem_st_nao_gera_ressarcimento(self):
        """Foi o caso de 236 mil linhas na BOA: item com suportado zerado."""
        l = razao(
            entrada(10, 0),
            saida(1, enq=EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO,
                  efetivo=0, ordem_na_fonte=1),
        )
        assert l[-1].ressarcimento == D(0)
        assert l[-1].icms_suportado == D(0)


class TestResumo:
    def test_totais(self):
        l = razao(
            entrada(10, 100),
            saida(1, enq=EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO,
                  efetivo=4, ordem_na_fonte=1),
            saida(1, enq=EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO,
                  efetivo=4, ordem_na_fonte=2),
        )
        r = ResumoDoRazao.de("ITEM-1", l)
        assert r.linhas == 3
        assert r.ressarcimento == D(12)
        assert r.saldo_quantidade == D(8)

"""Razão do item — a Ficha 3 em código.

Cada teste aqui corresponde a uma exigência do manual da CAT 42. Quando um
falhar, o que quebrou foi a norma, não uma preferência de implementação.
"""

from datetime import date
from decimal import Decimal

import pytest

from cat.dominio.icms.cat42.razao import (
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
        """Foi o caso de 236 mil linhas na empresa 17: item com suportado zerado."""
        l = razao(
            entrada(10, 0),
            saida(1, enq=EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO,
                  efetivo=0, ordem_na_fonte=1),
        )
        assert l[-1].ressarcimento == D(0)
        assert l[-1].icms_suportado == D(0)


class TestFichaComoElaVemDoCliente:
    """A sequência que a Ficha 3 de um cliente real traz, do começo ao fim.

    Confrontado em 14/09/2026 contra a Ficha 3 já calculada da IRMAOS EMPRESA_17, uma
    filial e um mês: 10.741 itens, 550.862 linhas, saldo e ressarcimento
    batendo em 100% delas e diferença de R$ 0,00 no total. Este teste guarda o
    formato daquela conferência para que ela não precise ser refeita à mão.
    """

    def test_abertura_baixa_entrada_e_saidas(self):
        """O padrão mais comum: estoque aberto, baixa que consome tudo,
        entrada nova e vendas em seguida."""
        razao = RazaoDoItem("970310", SaldoInicial(Decimal("72"), Decimal("180.00")))
        # baixa de estoque: enquadramento 2, confronta com o ICMS da ENTRADA
        razao.lancar(Movimento(
            data=date(2021, 1, 5), especie=Especie.SAIDA, quantidade=Decimal("72"),
            enquadramento=EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO,
            icms_efetivo=Decimal("80.00"), cfop="5927", ordem_na_fonte=0))
        razao.lancar(Movimento(
            data=date(2021, 1, 10), especie=Especie.ENTRADA,
            quantidade=Decimal("60"), icms_suportado=Decimal("150.00"),
            cfop="1409", ordem_na_fonte=1))
        for i in range(3):
            razao.lancar(Movimento(
                data=date(2021, 1, 15 + i), especie=Especie.SAIDA,
                quantidade=Decimal("1"),
                enquadramento=EnquadramentoLegal.CONSUMIDOR_FINAL,
                icms_efetivo=Decimal("2.50"), cfop="5405", ordem_na_fonte=2 + i))

        linhas = razao.apurar()
        assert len(linhas) == 5

        # a baixa consome o estoque inteiro e o ressarcimento é a diferença
        # positiva entre o suportado que saiu e o ICMS efetivo da entrada
        assert linhas[0].saldo_quantidade == Decimal("0")
        assert linhas[0].ressarcimento == Decimal("100.00")   # 180,00 - 80,00

        # a entrada repõe o estoque e o custo médio passa a ser o dela
        assert linhas[1].saldo_quantidade == Decimal("60")
        assert linhas[1].saldo_unitario == Decimal("2.5")

        # cada venda baixa uma unidade pelo unitário do saldo anterior
        for i, linha in enumerate(linhas[2:], 1):
            assert linha.saldo_quantidade == Decimal(60 - i)
            # 2,50 de suportado contra 2,50 de ICMS efetivo: nada a ressarcir
            assert linha.ressarcimento == Decimal("0")

    def test_estoque_zerado_nao_deixa_valor_residual(self):
        """Depois da baixa total, o saldo em valor tem de ser zero também.

        Sobrar centavo de arredondamento ali contamina o custo médio de toda a
        ficha seguinte."""
        razao = RazaoDoItem("1", SaldoInicial(Decimal("3"), Decimal("10.00")))
        razao.lancar(Movimento(
            data=date(2021, 1, 5), especie=Especie.SAIDA, quantidade=Decimal("3"),
            enquadramento=EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO,
            icms_efetivo=Decimal("0"), cfop="5927"))
        linha = razao.apurar()[0]
        assert linha.saldo_quantidade == Decimal("0")
        assert linha.saldo_valor == Decimal("0")


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


class TestValorDaAbertura:
    """Item 3.3.8: as entradas mais recentes, suficientes para a quantidade, com média ponderada."""

    def test_o_exemplo_do_manual(self):
        from cat.dominio.icms.cat42.razao import EntradaAnterior, valor_da_abertura  # noqa: PLC0415
        # último: 10 un a R$ 15; penúltimo: 20 un a R$ 10; quantidade 12
        v = valor_da_abertura(D(12), [EntradaAnterior(date(2020, 11, 5), D(20), D(200)),
                                      EntradaAnterior(date(2020, 12, 20), D(10), D(150))])
        assert v.valor == D(170)
        assert (v.valor / 12).quantize(D("0.01")) == D("14.17")
        assert not v.parcial and not v.sem_valor

    def test_entradas_que_nao_alcancam_valoram_o_resto_pela_media(self):
        from cat.dominio.icms.cat42.razao import EntradaAnterior, valor_da_abertura  # noqa: PLC0415
        v = valor_da_abertura(D(10), [EntradaAnterior(date(2020, 12, 1), D(4), D(8))])
        assert (v.valor, v.coberta, v.parcial) == (D(20), D(4), True)

    def test_sem_entrada_fica_sem_valor(self):
        from cat.dominio.icms.cat42.razao import valor_da_abertura  # noqa: PLC0415
        v = valor_da_abertura(D(10), [])
        assert (v.valor, v.sem_valor, v.parcial) == (D(0), True, False)
        assert not valor_da_abertura(D(0), []).sem_valor

    def test_no_mesmo_dia_vale_a_ordem(self):
        from cat.dominio.icms.cat42.razao import EntradaAnterior, valor_da_abertura  # noqa: PLC0415
        dia = date(2020, 12, 20)
        # a de ordem maior é a mais recente: 5 un a R$ 4 cobrem tudo
        v = valor_da_abertura(D(5), [EntradaAnterior(dia, D(5), D(10), ordem=0),
                                     EntradaAnterior(dia, D(5), D(20), ordem=1)])
        assert v.valor == D(20)


class TestEntradasDoRemetente:
    """§ 5º da CAT 42/2018: a entrada sem retido vale o das entradas mais recentes do remetente."""

    def test_e_a_mesma_conta_das_entradas_mais_recentes(self):
        from cat.dominio.icms.cat42.razao import (  # noqa: PLC0415
            EntradaAnterior,
            valor_pelas_entradas_do_remetente,
        )
        # o CD comprou 10 a R$ 20 e depois 10 a R$ 40; transfere 12: as 10 últimas e 2 das primeiras
        v = valor_pelas_entradas_do_remetente(D(12), [EntradaAnterior(date(2021, 1, 5), D(10), D(20)),
                                                      EntradaAnterior(date(2021, 1, 8), D(10), D(40))])
        assert (v.valor, v.coberta, v.parcial) == (D(44), D(12), False)

    def test_cfop_recebido_espelha_o_enviado(self):
        from cat.dominio.icms.cat42.enquadramento import (  # noqa: PLC0415
            CFOP_TRANSFERENCIA,
            CFOP_TRANSFERENCIA_RECEBIDA,
        )
        assert {"1152", "1409", "2152", "2409"} <= CFOP_TRANSFERENCIA_RECEBIDA
        assert len(CFOP_TRANSFERENCIA_RECEBIDA) == len(CFOP_TRANSFERENCIA)
        assert not any(c[0] in "56" for c in CFOP_TRANSFERENCIA_RECEBIDA)



class TestEscolherDestaque:
    """Transferência recebida sem retido (decisão de 25/11/2026): 1º o destaque
    do mesmo produto na mesma filial, 6 meses para trás com prioridade, senão 6
    para frente; 2º o do remetente e o de outra filial da mesma UF, na mesma
    janela; 3º sem nenhum, marcar para estimar."""

    LOJA, CD, OUTRA, PR = "L", "CD", "O", "PR"
    DIA = date(2026, 1, 22)

    @staticmethod
    def destaques(**por_filial):
        from cat.dominio.icms.cat42.razao import DestaquesDaFilial, EntradaAnterior  # noqa: PLC0415
        return {f: DestaquesDaFilial([EntradaAnterior(dia, Decimal(q), Decimal(v), ordem=i)
                                      for i, (dia, q, v) in enumerate(sorted(e))])
                for f, e in por_filial.items()}

    def escolher(self, destaques, quantidade=10, remetente="CD", mesma_uf=None):
        from cat.dominio.icms.cat42.razao import escolher_destaque  # noqa: PLC0415
        return escolher_destaque(Decimal(quantidade), self.DIA, self.LOJA, remetente, destaques, mesma_uf)

    def test_a_propria_filial_vence_o_remetente_mais_perto_no_tempo(self):
        e = self.escolher(self.destaques(
            L=[(date(2025, 11, 10), 10, 25)],          # 2,50/un, dois meses antes
            CD=[(date(2026, 1, 15), 130, 383.04)]))    # uma semana antes
        assert (e.criterio.value, e.filial, e.valor.valor) == ("mesma_filial_anterior", "L", Decimal(25))

    def test_antes_e_depois_na_filial_vale_o_de_antes(self):
        e = self.escolher(self.destaques(L=[(date(2026, 1, 25), 10, 30), (date(2025, 9, 1), 10, 20)]))
        assert (e.criterio.value, e.valor.valor) == ("mesma_filial_anterior", Decimal(20))

    def test_so_depois_na_filial_ainda_vence_o_remetente(self):
        e = self.escolher(self.destaques(L=[(date(2026, 3, 1), 10, 30)], CD=[(date(2026, 1, 15), 10, 99)]))
        assert (e.criterio.value, e.filial, e.valor.valor) == ("mesma_filial_posterior", "L", Decimal(30))

    def test_fora_dos_6_meses_nao_conta(self):
        e = self.escolher(self.destaques(L=[(date(2025, 7, 21), 10, 20), (date(2026, 7, 23), 10, 20)],
                                         CD=[(date(2026, 1, 15), 10, 40)]))
        assert (e.criterio.value, e.filial) == ("remetente_anterior", "CD")

    def test_o_limite_de_6_meses_entra(self):
        e = self.escolher(self.destaques(L=[(date(2025, 7, 22), 10, 20)]))
        assert e.criterio.value == "mesma_filial_anterior"

    def test_remetente_de_outra_uf_nao_serve(self):
        e = self.escolher(self.destaques(PR=[(date(2026, 1, 20), 10, 99)], O=[(date(2025, 12, 1), 10, 40)]),
                          remetente="PR", mesma_uf={"L", "O"})
        assert (e.criterio.value, e.filial, e.valor.valor) == ("outra_filial_anterior", "O", Decimal(40))

    def test_outra_filial_mais_proxima_antes(self):
        e = self.escolher(self.destaques(A=[(date(2025, 10, 1), 10, 10)], B=[(date(2026, 1, 2), 10, 20)],
                                         C=[(date(2026, 1, 25), 10, 30)]), remetente=None)
        assert (e.criterio.value, e.filial) == ("outra_filial_anterior", "B")

    def test_outra_filial_so_depois(self):
        e = self.escolher(self.destaques(A=[(date(2026, 4, 1), 10, 10)], B=[(date(2026, 2, 1), 10, 20)]),
                          remetente=None)
        assert (e.criterio.value, e.filial) == ("outra_filial_posterior", "B")

    def test_sem_destaque_nenhum_marca_para_estimar_e_nao_inventa_valor(self):
        e = self.escolher(self.destaques(PR=[(date(2026, 1, 20), 10, 99)]), remetente="PR", mesma_uf={"L"})
        assert e.precisa_estimar and e.filial is None and e.valor.valor == 0 and e.entradas_usadas == 0

    def test_uma_nota_nao_basta_soma_a_seguinte_com_media_ponderada(self):
        e = self.escolher(self.destaques(L=[(date(2026, 1, 10), 6, 18), (date(2025, 12, 1), 10, 20)]))
        # 6 un a 3,00 + 4 un a 2,00 = 26
        assert (e.entradas_usadas, e.valor.valor) == (2, Decimal(26))

    def test_depois_compoe_a_partir_da_mais_proxima(self):
        e = self.escolher(self.destaques(L=[(date(2026, 2, 1), 10, 30), (date(2026, 5, 1), 10, 50)]))
        assert (e.criterio.value, e.entradas_usadas, e.valor.valor) == ("mesma_filial_posterior", 1, Decimal(30))

    def test_somar_meses_no_fim_do_mes(self):
        from cat.dominio.icms.cat42.razao import somar_meses  # noqa: PLC0415
        assert somar_meses(date(2026, 8, 31), -6) == date(2026, 2, 28)
        assert somar_meses(date(2026, 1, 22), -6) == date(2025, 7, 22)
        assert somar_meses(date(2025, 12, 31), 2) == date(2026, 2, 28)

"""O que cinco anos já levaram.

O prazo para repetir o indébito é de cinco anos contados do pagamento (LC
118/2005), e PIS/COFINS vence no dia 25 do mês seguinte ao fato gerador. A
conta decide milhões num trabalho de cinco anos — e decide por dia, não por
mês: a competência de 08/2021 venceu em 25/09/2021, e um pedido de 24/09/2026
ainda a alcança por um dia.
"""

from __future__ import annotations

from datetime import date

from cat.dominio.piscofins.prescricao import limite, prescrita, vencimento


class TestOVencimento:
    def test_e_o_dia_25_do_mes_seguinte(self):
        assert vencimento("2021-03") == date(2021, 4, 25)
        assert vencimento("2024-01") == date(2024, 2, 25)

    def test_dezembro_vence_no_ano_seguinte(self):
        assert vencimento("2021-12") == date(2022, 1, 25)


class TestOCorte:
    def test_um_dia_antes_ainda_alcanca(self):
        """25/09/2021 é o vencimento de 08/2021; um pedido em 24/09/2026 pega."""
        assert not prescrita("2021-08", date(2026, 9, 24))

    def test_um_dia_depois_ja_perdeu(self):
        assert prescrita("2021-08", date(2026, 9, 26))

    def test_no_proprio_dia_ainda_alcanca(self):
        assert not prescrita("2021-08", date(2026, 9, 25))

    def test_competencia_recente_nunca_prescreve(self):
        assert not prescrita("2026-04", date(2026, 9, 24))

    def test_a_data_do_pedido_muda_o_alcance(self):
        """Protocolar em janeiro alcança um mês que julho já perdeu."""
        assert not prescrita("2021-03", date(2026, 4, 20))
        assert prescrita("2021-03", date(2026, 7, 20))


class TestOLimite:
    def test_volta_cinco_anos(self):
        assert limite(date(2026, 9, 24)) == date(2021, 9, 24)

    def test_29_de_fevereiro_nao_estoura(self):
        """Cinco anos antes de 29/02/2024 não existe; cai em 28/02/2019."""
        assert limite(date(2024, 2, 29)) == date(2019, 2, 28)

"""A Selic que corrige o indébito do Tema 69.

Esta tabela ficou meses sem ser exercitada: a conferência do 903 rodava com
`--selic-do-gabarito`, que pula a tabela inteira, e por isso dois erros de
dinheiro moraram aqui sem sinal nenhum — a série deslocada um mês e a falta do
mês de defasagem entre a competência e o pagamento. Os dois estão medidos
abaixo contra os números do próprio relatório do MA.

Os valores conferidos são taxas públicas e acumulados de Selic; não há dado de
cliente neste arquivo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cat.infraestrutura.sped.tabelas.tab_selic import (
    MENSAL,
    SelicDesconhecida,
    acumulada,
    ultimo_mes,
)

# o mês da restituição do gabarito do 903 conferido em 30/09/2026
ATE = "2026-09"

# competência -> "SELIC Acumulada" como o MA escreveu. Três pontas da série:
# a mais velha, uma do meio e a mais nova
DO_GABARITO = {
    "2021-02": Decimal("61.72"),
    "2023-06": Decimal("38.73"),
    "2025-10": Decimal("11.18"),
}


class TestAAcumulada:
    @pytest.mark.parametrize(("competencia", "esperado"), sorted(DO_GABARITO.items()))
    def test_bate_com_o_relatorio_do_ma(self, competencia: str, esperado: Decimal) -> None:
        assert acumulada(competencia, ATE) == esperado

    def test_comeca_dois_meses_depois_da_competencia(self) -> None:
        """A defasagem do pagamento: o tributo de um mês se paga no seguinte.

        Começar no mês seguinte à competência — o que parecia certo e estava
        errado — daria uma parcela a mais de Selic em toda competência.
        """
        esperado = Decimal(1) + sum(
            (MENSAL[m] for m in ("2025-12", "2026-01", "2026-02", "2026-03",
                                 "2026-04", "2026-05", "2026-06", "2026-07",
                                 "2026-08")),
            Decimal(0))
        assert acumulada("2025-10", ATE) == esperado
        assert acumulada("2025-10", ATE) == acumulada("2025-09", ATE) - MENSAL["2025-11"]

    def test_o_mes_do_pagamento_nao_rende(self) -> None:
        """Pago em setembro e restituído em setembro: só o 1% do mês final."""
        assert acumulada("2026-08", ATE) == Decimal(1)
        assert acumulada("2026-09", ATE) == Decimal(1)

    def test_recusa_o_que_a_serie_nao_cobre(self) -> None:
        with pytest.raises(SelicDesconhecida) as erro:
            acumulada("2026-01", "2030-01")
        assert "tab_selic.MENSAL" in str(erro.value)


class TestASerie:
    def test_nao_tem_buraco(self) -> None:
        """Mês faltando no meio devolveria correção a menos, calado."""
        meses = sorted(MENSAL)
        a, m = (int(x) for x in meses[0].split("-"))
        for esperado in meses:
            assert esperado == f"{a:04d}-{m:02d}", f"buraco antes de {esperado}"
            m += 1
            if m == 13:
                a, m = a + 1, 1

    def test_cobre_o_mes_da_restituicao_conferida(self) -> None:
        assert ultimo_mes() >= "2026-08"

    def test_e_a_serie_4390_do_banco_central(self) -> None:
        """A fonte, medida — não suposta.

        Pula quando não há rede: a tabela está no repositório justamente para
        que o cálculo não dependa de estar on-line. O teste é a conferência de
        quem a mantém, não uma dependência de quem a usa.
        """
        import json
        import urllib.error
        import urllib.request

        url = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados"
               "?formato=json&dataInicial=01/01/2021&dataFinal=31/12/2021")
        try:
            with urllib.request.urlopen(url, timeout=15) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as erro:
            pytest.skip(f"sem rede para o SGS do Banco Central: {erro}")

        for linha in dados:
            _, mes, ano = linha["data"].split("/")
            assert MENSAL[f"{ano}-{mes}"] == Decimal(linha["valor"])

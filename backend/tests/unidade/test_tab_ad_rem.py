"""A ad rem do monofásico: a tabela que multiplica o número inteiro.

O crédito de quem consome combustível é `litros × ad rem × FCV`. Não há soma
que dilua um erro aqui: ele vai proporcionalmente para o total, num pedido que
alguém assina.

Por isso os dois lados são testados. Que ela **acerta** onde foi conferida no
texto do convênio — e que ela **recusa** onde não foi, em vez de devolver o
palpite mais próximo. Recusar é a parte que protege.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cat.infraestrutura.sped.tabelas import tab_ad_rem
from cat.infraestrutura.sped.tabelas.tab_ad_rem import (
    DIESEL,
    GASOLINA,
    GLP,
    AdRemDesconhecida,
    da_competencia,
    unidade_de,
)

# o fator de correção do volume de São Paulo para o diesel (Ato COTEPE 64/2019)
FCV_SP_DIESEL = Decimal("0.9976")


class TestOQueEstaConferido:
    @pytest.mark.parametrize("produto, competencia, esperado", [
        (DIESEL, "2024-02", "1.0635"),
        (DIESEL, "2024-12", "1.0635"),
        (DIESEL, "2025-02", "1.12"),
        (DIESEL, "2025-12", "1.12"),
        (DIESEL, "2026-01", "1.17"),
        (GASOLINA, "2025-02", "1.47"),
        (GASOLINA, "2026-01", "1.57"),
        (GLP, "2024-02", "1.4139"),
        (GLP, "2025-02", "1.39"),
        (GLP, "2026-01", "1.47"),
    ])
    def test_a_vigencia_vale_do_mes_dela_em_diante(self, produto, competencia, esperado):
        assert da_competencia(produto, competencia) == Decimal(esperado)

    def test_o_mes_da_virada_mudou_em_2026(self):
        """2024 e 2025 viraram em 1º de fevereiro; 2026 virou em 1º de janeiro.

        Quem assumir "sempre fevereiro" erra janeiro de 2026 em 4,3% no diesel —
        e erra calado, porque 1,12 é um número plausível para aquele mês.
        """
        assert da_competencia(DIESEL, "2025-01") == Decimal("1.0635")
        assert da_competencia(DIESEL, "2025-02") == Decimal("1.12")

        assert da_competencia(DIESEL, "2026-01") == Decimal("1.17")
        assert da_competencia(DIESEL, "2025-12") == Decimal("1.12")

    def test_o_glp_e_por_quilo_e_o_resto_por_litro(self):
        """É o que pega quem não olha: o SPED declara o botijão em unidades."""
        assert unidade_de(GLP) == "quilo"
        assert unidade_de(DIESEL) == unidade_de(GASOLINA) == "litro"


class TestOQueElaRecusa:
    def test_competencia_anterior_a_mais_antiga_conferida(self):
        with pytest.raises(AdRemDesconhecida) as erro:
            da_competencia(DIESEL, "2023-09")

        assert "2023-09" in str(erro.value)
        assert "2024-02" in str(erro.value), "diz qual é a vigência mais antiga"

    def test_recusa_mesmo_havendo_palpite_e_diz_qual_e(self):
        """**O palpite entra na mensagem, nunca na conta.**

        O diesel de 0,9456 é o caso mais forte que existe: aparece no exemplo da
        própria SEFAZ-SP e bate exato com a escrituração da empresa G em 2024-01.
        Mesmo assim recusa, porque ninguém leu a redação original da cláusula
        sétima — e exemplo em resposta de consulta não é o ato legal.
        """
        with pytest.raises(AdRemDesconhecida) as erro:
            da_competencia(DIESEL, "2024-01")

        assert "0.9456" in str(erro.value)
        assert "convênio" in str(erro.value).lower()

    def test_produto_fora_do_monofasico(self):
        """Lubrificante nunca entrou no monofásico, e pedir a ad rem dele é erro."""
        with pytest.raises(AdRemDesconhecida) as erro:
            da_competencia("lubrificante", "2025-06")

        assert "monofásico" in str(erro.value)


class TestOLivroDoClienteNaoCorroboraAAdRem:
    """A corroboração que eu afirmei em 03/10/2026 e que a medição derrubou.

    O módulo dizia que a escrituração da empresa G era uma segunda prova da ad
    rem — "o crédito dela dividido pelos litros dá exatamente 1,0635". E havia
    um teste aqui que parecia confirmar isso.

    **O teste era vazio.** Ele comparava `creditado × FCV` com
    `litros × ad_rem × FCV`, usando um par (litros, creditado) escrito à mão na
    própria parametrização. Qualquer par cuja razão fosse a ad rem passaria,
    inclusive um inventado — e era o caso: o par dizia R$ 207.403,35 em 2024-02,
    e o `E111` real daquele mês traz **R$ 69.134,45**.

    Com o leitor de pé (`sped/combustivel.py`) a razão foi medida em nove
    competências e varia de **0,58 a 59,79**. O livro do cliente é o objeto da
    auditoria, não prova da alíquota.

    O que sobra aqui é o que sempre foi aritmética e não medição: o tamanho do
    desvio de quem pula o FCV.
    """

    def test_pular_o_fcv_credita_024_por_cento_a_mais(self):
        """O tamanho do desvio, para ninguém o confundir com arredondamento."""
        litros = Decimal("195020")
        ad_rem = da_competencia(DIESEL, "2024-02")

        sem_fcv = litros * ad_rem
        com_fcv = sem_fcv * FCV_SP_DIESEL

        a_mais = (sem_fcv - com_fcv) / com_fcv * 100
        assert Decimal("0.23") < a_mais < Decimal("0.25")

    def test_o_desvio_do_fcv_nao_depende_do_volume(self):
        """É proporcional, e por isso o número de litros do exemplo é
        arbitrário — ao contrário do que a versão anterior sugeria ao usar um
        volume que dizia ser do cliente."""
        ad_rem = da_competencia(DIESEL, "2024-02")

        def a_mais(litros: str) -> Decimal:
            com = Decimal(litros) * ad_rem * FCV_SP_DIESEL
            return (Decimal(litros) * ad_rem - com) / com

        assert a_mais("1") == a_mais("195020") == a_mais("7231083")


class TestAFormaDaTabela:
    def test_as_vigencias_vem_da_mais_nova_para_a_mais_antiga(self):
        """É a ordem em que `da_competencia` procura: a primeira que couber vence."""
        for produto, vigencias in tab_ad_rem.AD_REM.items():
            datas = [v.desde for v in vigencias]
            assert datas == sorted(datas, reverse=True), produto

    def test_toda_vigencia_diz_de_onde_saiu(self):
        """Número sem fundamento não se confere depois, e vira folclore."""
        for produto, vigencias in tab_ad_rem.AD_REM.items():
            for v in vigencias:
                assert "onvênio" in v.fundamento, f"{produto} {v.desde}"

    def test_o_que_esta_a_conferir_nao_esta_conferido(self):
        """As duas listas não podem se sobrepor: seria conferido e suspeito ao
        mesmo tempo, e alguém usaria a errada."""
        for (produto, desde) in tab_ad_rem.A_CONFERIR:
            conferidas = {v.desde for v in tab_ad_rem.AD_REM.get(produto, ())}
            assert desde not in conferidas, f"{produto} {desde} está nas duas"

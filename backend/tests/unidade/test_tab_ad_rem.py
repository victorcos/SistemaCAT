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
        própria SEFAZ-SP e bate exato com a escrituração da ETTORI em 2024-01.
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


class TestContraOLivroDoCliente:
    """A prova que vale mais que a leitura do convênio: o número do cliente.

    A ETTORI credita o monofásico por ajuste `SP020799` na apuração. O crédito
    dela dividido pelos litros do mês dá a ad rem que ela usou — e ela usou a da
    lei. Lei e livro concordando é o padrão desta casa (ver `tab_aliquota_icms`).

    **E a diferença que sobra tem nome:** ela não aplica o FCV. Credita
    `litros × ad rem`, quando o devido é `litros × ad rem × 0,9976`. São 0,24% a
    mais, sistemáticos — e é por isso que o módulo audita o crédito tomado em
    vez de só procurar crédito novo.
    """

    @pytest.mark.parametrize("competencia, litros, creditado", [
        ("2024-02", "195020", "207403.35"),
        ("2024-06", "211963", "225422.70"),
    ])
    def test_a_conta_reproduz_o_credito_do_cliente_menos_o_fcv(
            self, competencia, litros, creditado):
        ad_rem = da_competencia(DIESEL, competencia)

        devido = Decimal(litros) * ad_rem * FCV_SP_DIESEL
        tomado = Decimal(creditado)

        # o que o cliente creditou é o devido dividido pelo FCV — isto é, ele
        # pulou o fator. A conta fecha em menos de um real em R$ 200 mil
        assert abs(tomado * FCV_SP_DIESEL - devido) < 1

    def test_pular_o_fcv_credita_024_por_cento_a_mais(self):
        """O tamanho do desvio, para ninguém o confundir com arredondamento."""
        litros = Decimal("195020")
        ad_rem = da_competencia(DIESEL, "2024-02")

        sem_fcv = litros * ad_rem
        com_fcv = sem_fcv * FCV_SP_DIESEL

        a_mais = (sem_fcv - com_fcv) / com_fcv * 100
        assert Decimal("0.23") < a_mais < Decimal("0.25")


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

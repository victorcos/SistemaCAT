"""A alíquota de ICMS que o ICMS-ST presumido usa.

Três regras aqui valem dinheiro, e as três estão medidas abaixo:

- **a alíquota tem data.** Um pedido de restituição cobre cinco anos e atravessa
  mudança de lei estadual; uma tabela com um número por estado aplicaria a de
  hoje a uma operação de 2021, calada;
- **estado não conferido recusa.** Errar a interna em um ponto e meio sobre os
  R$ 117 milhões de base de um cliente médio são R$ 160 mil de crédito pedido
  indevidamente, e esse erro não aparece em lugar nenhum do relatório;
- **a exceção do produto vem antes da regra.** Quem cadastrou a exceção daquele
  item sabe mais sobre ele do que a alíquota geral do estado.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cat.infraestrutura.sped.tabelas import tab_aliquota_icms as tab

CNPJ = "11222333000181"


class TestAInterestadual:
    """Resolução 22/1989 do Senado. Não muda desde então, e por isso não tem data."""

    def test_do_sul_sudeste_para_o_norte_nordeste_e_sete(self):
        assert tab.da_regra("MG", "CE", "2022-10") == Decimal(7)
        assert tab.da_regra("SP", "AM", "2022-10") == Decimal(7)
        # o Espírito Santo entra na regra dos 7% apesar de ser Sudeste
        assert tab.da_regra("MG", "ES", "2022-10") == Decimal(7)

    def test_entre_sul_e_sudeste_e_doze(self):
        assert tab.da_regra("MG", "SP", "2022-10") == Decimal(12)
        assert tab.da_regra("RS", "PR", "2022-10") == Decimal(12)

    def test_do_norte_para_o_sul_tambem_e_doze(self):
        """A regra dos 7% é só na saída do Sul/Sudeste; a volta é 12%."""
        assert tab.da_regra("CE", "MG", "2022-10") == Decimal(12)

    def test_vale_mesmo_para_estado_sem_interna_conferida(self):
        """A interestadual é lei federal: não depende de conferir o estado."""
        assert tab.da_regra("SP", "RJ", "2022-10") == Decimal(12)


class TestAInterna:
    def test_minas_esta_conferida(self):
        assert tab.interna("MG", "2022-10") == Decimal(18)
        assert tab.da_regra("MG", "MG", "2022-10") == Decimal(18)

    def test_estado_nao_conferido_recusa(self):
        """E a recusa diz o que fazer, inclusive o que **não** serve de prova."""
        with pytest.raises(tab.AliquotaDesconhecida) as erro:
            tab.interna("SP", "2022-10")

        recado = str(erro.value)
        assert "não está conferida" in recado
        assert "aferir_aliquota_interna" in recado
        assert "escritório anterior" in recado

    def test_a_suspeita_aparece_no_recado_e_nao_no_calculo(self):
        """Saber por onde começar não é o mesmo que poder usar."""
        assert tab.A_CONFERIR["SP"] == Decimal(18)
        with pytest.raises(tab.AliquotaDesconhecida):
            tab.interna("SP", "2022-10")

    def test_competencia_anterior_a_vigencia_mais_antiga_recusa(self):
        """Antes do que se sabe, não se chuta: recusa dizendo desde quando sabe."""
        with pytest.raises(tab.AliquotaDesconhecida) as erro:
            tab.interna("MG", "2010-05")

        assert "só é conhecida a partir de" in str(erro.value)

    def test_uf_vazia_recusa(self):
        with pytest.raises(tab.AliquotaDesconhecida):
            tab.interna("", "2022-10")


class TestAVigencia:
    """O degrau: a mesma UF com duas alíquotas, cada uma no seu tempo."""

    @pytest.fixture
    def estado_que_subiu(self, monkeypatch):
        monkeypatch.setitem(tab.INTERNA, "XX", (
            tab.Vigencia(Decimal(17), "2018-01", "lei antiga"),
            tab.Vigencia(Decimal(20), "2024-04", "lei nova"),
        ))

    def test_antes_do_degrau_vale_a_antiga(self, estado_que_subiu):
        assert tab.interna("XX", "2024-03") == Decimal(17)

    def test_no_mes_do_degrau_ja_vale_a_nova(self, estado_que_subiu):
        assert tab.interna("XX", "2024-04") == Decimal(20)

    def test_depois_do_degrau_vale_a_nova(self, estado_que_subiu):
        assert tab.interna("XX", "2025-12") == Decimal(20)

    def test_a_ordem_de_cadastro_nao_importa(self, monkeypatch):
        """Quem acrescenta uma vigência não precisa saber onde encaixá-la."""
        monkeypatch.setitem(tab.INTERNA, "YY", (
            tab.Vigencia(Decimal(20), "2024-04", "lei nova"),
            tab.Vigencia(Decimal(17), "2018-01", "lei antiga"),
        ))

        assert tab.interna("YY", "2024-03") == Decimal(17)
        assert tab.interna("YY", "2024-04") == Decimal(20)


class TestAExcecaoDoProduto:
    def test_a_excecao_vence_a_regra(self):
        excecoes = {(CNPJ, "MG", "MG", "SKU1"): Decimal(12)}

        assert tab.aplicavel("MG", "MG", "2022-10", CNPJ, "SKU1", excecoes) == Decimal(12)

    def test_sem_excecao_vale_a_regra(self):
        assert tab.aplicavel("MG", "MG", "2022-10", CNPJ, "SKU1", {}) == Decimal(18)

    def test_a_excecao_de_outro_item_nao_vale(self):
        excecoes = {(CNPJ, "MG", "MG", "SKU1"): Decimal(12)}

        assert tab.aplicavel("MG", "MG", "2022-10", CNPJ, "SKU2", excecoes) == Decimal(18)

    def test_a_excecao_de_outro_estabelecimento_nao_vale(self):
        """Código de item é do ERP de quem o cadastrou, e não atravessa CNPJ."""
        excecoes = {("99999999000199", "MG", "MG", "SKU1"): Decimal(12)}

        assert tab.aplicavel("MG", "MG", "2022-10", CNPJ, "SKU1", excecoes) == Decimal(18)

    def test_a_excecao_dispensa_o_estado_estar_conferido(self):
        """Quem cadastrou aquele item sabe dele mais que a alíquota geral."""
        excecoes = {(CNPJ, "SP", "SP", "SKU1"): Decimal(12)}

        assert tab.aplicavel("SP", "SP", "2022-10", CNPJ, "SKU1", excecoes) == Decimal(12)

    def test_sem_excecao_o_estado_nao_conferido_recusa(self):
        with pytest.raises(tab.AliquotaDesconhecida):
            tab.aplicavel("SP", "SP", "2022-10", CNPJ, "SKU9", {})


class TestATabela:
    def test_o_que_esta_conferido_traz_fundamento(self):
        """Linha sem ato legal é opinião com cara de lei."""
        for uf, vigencias in tab.INTERNA.items():
            for vigencia in vigencias:
                assert vigencia.fundamento.strip(), f"{uf} sem fundamento"
                assert len(vigencia.desde) == 7, f"{uf}: vigência não é aaaa-mm"

    def test_nenhuma_uf_esta_nos_dois_lugares(self):
        """Conferida e a conferir ao mesmo tempo seria dúvida sobre o que vale."""
        assert not set(tab.INTERNA) & set(tab.A_CONFERIR)

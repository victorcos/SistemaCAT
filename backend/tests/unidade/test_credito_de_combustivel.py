"""Quanto a linha vale — e o que acontece quando a tabela não sabe.

A conta em si é curta: `quantidade × ad rem × FCV` no monofásico, `base ×
alíquota` na era do ST. O que este arquivo guarda é mais o segundo caso: **o que
a tabela não cobre não vira zero, vira recusa com o motivo**, e a linha aparece
no relatório fora do total.

A diferença não é de estilo. Zero soma; recusa aparece. Uma competência sem
vigência cadastrada, tratada como zero, sai do relatório como "não havia crédito
naquele mês" — e ninguém procura o que não viu.

**Nenhum valor de cliente entra como fixture.** As linhas são sintéticas; a
conferência contra a escrituração real está medida em `DECISOES.md`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cat.infraestrutura.sped.classificador_de_combustivel import classificar
from cat.infraestrutura.sped.combustivel import LinhaDeCompra, codigo_de_tributacao
from cat.infraestrutura.sped.credito_de_combustivel import (
    MEDIA,
    MONOFASICO,
    RECUSADO,
    ST,
    Credito,
    apurar,
)
from cat.infraestrutura.sped.tabelas.tab_combustivel import DIESEL, GLP

NCM_DIESEL = "27101921"
NCM_GASOLINA = "27101259"
NCM_GLP = "27111910"
NCM_LUBRIFICANTE = "27101932"


def _linha(*, competencia: str = "2024-06", uf: str = "SP",
           quantidade: str | None = "1000", unidade: str = "L",
           valor: str | None = "6000,00", cst: str = "061") -> LinhaDeCompra:
    """Uma compra sintética, com só o que a apuração lê."""
    return LinhaDeCompra(
        cnpj_do_estabelecimento="44000003000109", uf=uf, competencia=competencia,
        situacao="00", modelo="55", serie="1", numero="1", chave="3" * 44,
        data_de_emissao=f"{competencia}-15", cnpj_do_fornecedor="11222333000181",
        nome_do_fornecedor="POSTO DO TESTE",
        numero_do_item="1", codigo_do_item="I-1",
        descricao_no_documento="DIESEL S10",
        quantidade=None if quantidade is None else Decimal(quantidade),
        unidade=unidade,
        valor_do_item=None if valor is None else Decimal(valor.replace(",", ".")),
        cfop="1653", tributacao=codigo_de_tributacao(cst),
        base_do_icms=None, aliquota_do_icms=None, valor_do_icms=None,
        base_do_st=None, aliquota_do_st=None, valor_do_st=None,
    )


def _apurar(linha: LinhaDeCompra, descricao: str = "OLEO DIESEL B S10",
            ncm: str = NCM_DIESEL) -> Credito:
    return apurar(linha, classificar(descricao, ncm, linha.unidade))


class TestNoMonofasico:
    def test_a_conta_e_quantidade_vezes_ad_rem_vezes_fcv(self):
        """1.000 litros × 1,0635 × 0,9976 (diesel em SP) = R$ 1.060,95."""
        c = _apurar(_linha(quantidade="1000", competencia="2024-06"))

        assert c.regime == MONOFASICO
        assert (c.ad_rem, c.fcv) == (Decimal("1.0635"), Decimal("0.9976"))
        assert c.valor == Decimal("1060.95")
        assert c.entra_no_total

    def test_os_fatores_ficam_a_vista(self):
        """O relatório mostra a conta, não só o resultado: o cliente pergunta
        "por que esse número?" e a resposta tem de caber na linha."""
        c = _apurar(_linha())

        assert c.quantidade is not None and c.fator is not None
        assert c.ad_rem is not None and c.fcv is not None
        assert "ad rem" in c.porque and "FCV" in c.porque

    def test_o_fcv_e_da_uf_da_linha(self):
        """Usar o FCV de outro estado erra 0,33% sistemáticos — aconteceu num
        papel de trabalho de terceiro, ver `tab_fcv`."""
        em_sp = _apurar(_linha(uf="SP"))
        em_es = _apurar(_linha(uf="ES"))

        assert em_sp.fcv == Decimal("0.9976")
        assert em_es.fcv == Decimal("0.9943")
        assert em_sp.valor != em_es.valor

    def test_o_glp_multiplica_o_fator_da_embalagem(self):
        """10 botijões de 20 kg são 200 kg, não 10. A ad rem do GLP é por quilo."""
        linha = _linha(quantidade="10", unidade="UN", competencia="2025-06")
        c = _apurar(linha, "P20 - GLP 20 KGS", NCM_GLP)

        assert c.produto == GLP
        assert c.fator == Decimal(20)
        assert c.quantidade == Decimal(200)
        # 200 kg × 1,39 (GLP em 2025) × 1 (massa não dilata)
        assert c.valor == Decimal("278.00")

    def test_o_fcv_do_glp_e_um_porque_massa_nao_dilata(self):
        linha = _linha(quantidade="10", unidade="UN", competencia="2025-06")
        c = _apurar(linha, "P20 - GLP 20 KGS", NCM_GLP)

        assert c.fcv == Decimal(1)


class TestNaEraDoSt:
    def test_a_conta_e_base_vezes_aliquota(self):
        """R$ 6.000 × 12% (diesel em SP até 2021) = R$ 720."""
        c = _apurar(_linha(competencia="2020-11", cst="060"))

        assert c.regime == ST
        assert c.aliquota == Decimal(12)
        assert c.valor == Decimal("720.00")

    def test_o_complemento_de_sp_entra_quando_e_a_vigencia_dele(self):
        """13,3% de 15/01/2021 a 14/01/2023 — ignorá-lo perde 10% do crédito."""
        antes = _apurar(_linha(competencia="2020-11", cst="060"))
        durante = _apurar(_linha(competencia="2022-06", cst="060"))

        assert (antes.aliquota, durante.aliquota) == (Decimal(12), Decimal("13.3"))
        assert durante.valor > antes.valor

    def test_sai_marcada_como_estimativa(self):
        """**Medido: zero base de ST em 5.234 linhas de CST 60/61.** A base usada
        é o valor do item, e quem somar um total com estimativa dentro tem de
        saber disso pela própria linha."""
        c = _apurar(_linha(competencia="2022-06", cst="060"))

        assert c.estimativa
        assert "ESTIMATIVA" in c.porque
        assert "PMPF" in c.porque, "diz qual era a base verdadeira"

    def test_o_monofasico_nao_e_estimativa(self):
        """Lá os três fatores são tabela; aqui a base é proxy."""
        assert not _apurar(_linha(competencia="2024-06")).estimativa


class TestAViradaDeEra:
    def test_a_mesma_linha_muda_de_conta_conforme_a_competencia(self):
        """O diesel virou em 05/2023. Antes, percentual; depois, ad rem."""
        antes = _apurar(_linha(competencia="2023-04", cst="060"))
        depois = _apurar(_linha(competencia="2024-06", cst="061"))

        assert (antes.regime, depois.regime) == (ST, MONOFASICO)
        assert antes.aliquota is not None and antes.ad_rem is None
        assert depois.ad_rem is not None and depois.aliquota is None

    @pytest.mark.parametrize("competencia", [
        "2023-05", "2023-08", "2023-10", "2023-12", "2024-01"])
    def test_os_nove_primeiros_meses_do_monofasico_recusam(self, competencia):
        """**O maior buraco de cobertura do motor hoje, e ele aparece.**

        O monofásico do diesel começou em 05/2023, e a vigência mais antiga
        **conferida** no `tab_ad_rem` é de 02/2024. As nove competências do meio
        não se calculam: a ad rem delas está em `A_CONFERIR`, com a suspeita de
        0,9456 que ninguém leu no texto do convênio.

        Não é defeito desta função — é a recusa funcionando. A empresa G tomou
        crédito nesses meses, e auditá-los exige abrir a redação original da
        cláusula sétima do Conv. 199/2022. O relatório mostra a linha, com este
        motivo, fora do total.
        """
        c = _apurar(_linha(competencia=competencia))

        assert c.regime == MONOFASICO
        assert c.valor is None
        assert "0.9456" in c.porque, "a mensagem diz qual é a suspeita"

    def test_a_gasolina_vira_um_mes_depois_do_diesel(self):
        """05/2023 ainda é era do ST para a gasolina, e já é monofásico para o
        diesel. Uma data só para os dois erra maio de 2023 inteiro."""
        diesel = _apurar(_linha(competencia="2023-05"))
        gasolina = _apurar(_linha(competencia="2023-05", cst="060"),
                           "GASOLINA COMUM", NCM_GASOLINA)

        assert diesel.regime == MONOFASICO
        assert gasolina.regime == ST


class TestORecusadoApareceENaoSoma:
    def test_recusa_devolve_None_e_nao_zero(self):
        """Zero soma; `None` aparece. É a diferença entre "não havia crédito" e
        "ninguém calculou"."""
        c = _apurar(_linha(competencia="2023-09"))

        assert c.valor is None
        assert c.cobertura == RECUSADO
        assert not c.entra_no_total

    def test_ad_rem_nao_conferida_recusa_dizendo_o_que_falta(self):
        """2023-09 é anterior à vigência mais antiga conferida do diesel."""
        c = _apurar(_linha(competencia="2023-09"))

        assert "não está conferida" in c.porque
        assert "CONFAZ" in c.porque, "diz onde conferir"

    def test_mes_partido_recusa_e_manda_separar_pela_data(self):
        """SP tem dois: 01/2021 e 01/2023, quando o complemento entrou e saiu."""
        c = _apurar(_linha(competencia="2021-01", cst="060"))

        assert c.valor is None
        assert "data do documento" in c.porque

    def test_aliquota_nao_conferida_recusa(self):
        """Minas não teve a alíquota de combustível levantada."""
        c = _apurar(_linha(competencia="2022-06", uf="MG", cst="060"))

        assert c.valor is None
        assert "INTERNA" in c.porque, "diz onde acrescentar"

    def test_fcv_de_uf_que_nao_existe_recusa(self):
        c = _apurar(_linha(competencia="2024-06", uf="ZZ"))

        assert c.valor is None
        assert "ZZ" in c.porque

    def test_sem_quantidade_recusa(self):
        c = _apurar(_linha(quantidade=None))

        assert c.valor is None
        assert "quantidade" in c.porque

    def test_sem_fator_recusa(self):
        """GLP declarado em `UN` sem o fardo no texto nem no 0220."""
        linha = _linha(quantidade="10", unidade="UN", competencia="2025-06")
        c = _apurar(linha, "GLP BOTIJAO", NCM_GLP)

        assert c.valor is None
        assert "fator" in c.porque

    def test_sem_valor_do_item_recusa_na_era_do_st(self):
        c = _apurar(_linha(competencia="2022-06", valor=None, cst="060"))

        assert c.valor is None
        assert "valor do item" in c.porque

    def test_sem_competencia_recusa(self):
        c = _apurar(_linha(competencia=""))

        assert c.valor is None
        assert "0000" in c.porque

    def test_toda_recusa_traz_porque(self):
        """Recusa sem motivo é linha que ninguém sabe como resolver."""
        casos = [
            _linha(competencia="2023-09"),
            _linha(competencia="2021-01", cst="060"),
            _linha(quantidade=None),
            _linha(competencia=""),
            _linha(competencia="2024-06", uf="ZZ"),
        ]
        for linha in casos:
            c = _apurar(linha)
            assert c.cobertura == RECUSADO
            assert len(c.porque) > 20, c


class TestOQueNaoEDaTese:
    def test_lubrificante_recusa_dizendo_que_e_outra_tese(self):
        c = _apurar(_linha(), "OLEO MOTOR DIESEL SAE15", NCM_LUBRIFICANTE)

        assert c.valor is None
        assert "não entra nesta tese" in c.porque

    def test_linha_nao_classificada_recusa_com_o_motivo_do_classificador(self):
        c = _apurar(_linha(), "LANTERNA", "")

        assert c.valor is None
        assert "não foi classificada" in c.porque


class TestACoberturaDaRegra:
    def test_o_teto_e_media_porque_falta_a_tabela_de_internalizacao(self):
        """O Conv. 26/2023 dá o direito; quem concede é o estado, por norma
        própria — e não se levantou quais UF a editaram. Chamar de alta sem a
        norma seria inventar certeza."""
        c = _apurar(_linha())

        assert c.cobertura == MEDIA
        assert "média" in c.porque

    def test_nenhuma_apuracao_chega_a_alta_hoje(self):
        """Quando a tabela de internalização existir, este teste muda — e é por
        isso que ele existe: para que a mudança seja deliberada."""
        for competencia in ("2024-06", "2025-06", "2022-06"):
            for cst in ("061", "060"):
                c = _apurar(_linha(competencia=competencia, cst=cst))
                assert c.cobertura != "alta"


class TestNuncaLevanta:
    @pytest.mark.parametrize("competencia, uf, quantidade, unidade, valor", [
        ("", "", None, "", None),
        ("1999-01", "ZZ", "0", "???", "0"),
        ("2024-06", "sp", "-5", "L", "-10,00"),
        ("9999-99", "SP", "1", "L", "1,00"),
    ])
    def test_entrada_torta_devolve_credito_em_vez_de_erro(
            self, competencia, uf, quantidade, unidade, valor):
        """As exceções das tabelas são capturadas e **viram texto na linha**: é a
        única forma de o motivo chegar ao relatório. Deixá-las subir derrubaria
        a rodada por causa de uma competência sem vigência."""
        c = _apurar(_linha(competencia=competencia, uf=uf, quantidade=quantidade,
                           unidade=unidade, valor=valor))

        assert isinstance(c, Credito)

    def test_quantidade_negativa_nao_e_tratada_como_erro(self):
        """Devolução aparece como quantidade negativa, e o crédito dela é
        negativo mesmo — quem decide se entra é a rodada, não esta função."""
        c = _apurar(_linha(quantidade="-100"))

        assert c.valor is not None and c.valor < 0

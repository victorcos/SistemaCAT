"""A correção à mão, antes de virar linha no banco.

A regra é a mesma para quem sobe planilha e para quem edita na tela, e é aqui
que ela é conferida: sem motivo não grava, alíquota fora da faixa não passa, e
correção de linha precisa dizer qual linha é.
"""

from decimal import Decimal

import pytest

from cat.dominio.cat42.correcao import (
    Alvo,
    Campo,
    CorrecaoInvalida,
    validar,
)


def d(v) -> Decimal:
    return Decimal(str(v))


class TestOAlvo:
    def test_aliquota_e_reducao_sao_da_mercadoria(self):
        assert Campo.ALIQUOTA.alvo is Alvo.MERCADORIA
        assert Campo.REDUCAO_BASE.alvo is Alvo.MERCADORIA

    @pytest.mark.parametrize("campo", [Campo.ENQUADRAMENTO, Campo.QUANTIDADE, Campo.VALOR_ITEM,
                                       Campo.ICMS_SUPORTADO, Campo.EXCLUIDA])
    def test_o_resto_e_da_linha(self, campo):
        assert campo.alvo is Alvo.LINHA

    def test_todo_campo_diz_o_que_faz(self):
        for campo in Campo:
            assert campo.rotulo and campo.o_que_faz.endswith(".")


class TestOMotivo:
    def test_sem_motivo_nao_grava(self):
        with pytest.raises(CorrecaoInvalida, match="motivo escrito"):
            validar(Campo.ALIQUOTA, 25, "", codigo="4002")

    def test_motivo_de_uma_letra_nao_e_motivo(self):
        with pytest.raises(CorrecaoInvalida, match="motivo escrito"):
            validar(Campo.ALIQUOTA, 25, "x", codigo="4002")

    def test_motivo_gigante_e_recusado(self):
        with pytest.raises(CorrecaoInvalida, match="500"):
            validar(Campo.ALIQUOTA, 25, "a" * 501, codigo="4002")


class TestCorrecaoDeMercadoria:
    def test_aliquota(self):
        c = validar("aliquota", "25", "Sem 0200; NCM 3305.90.00, art. 55, IV", codigo=" 4002 ")
        assert (c.campo, c.valor, c.codigo) == (Campo.ALIQUOTA, d("25.0000"), "4002")
        assert c.alvo is Alvo.MERCADORIA and c.valor_gravado == "25.0000"

    def test_aliquota_aceita_virgula_decimal(self):
        assert validar("aliquota", "13,3", "redutor do Decreto 65.255", codigo="X").valor == d("13.3000")

    @pytest.mark.parametrize("valor", [0, -1, "101", "abc"])
    def test_aliquota_fora_da_faixa(self, valor):
        with pytest.raises(CorrecaoInvalida):
            validar("aliquota", valor, "motivo bom", codigo="X")

    def test_reducao_zero_tira_a_reducao(self):
        assert validar("reducao_base", 0, "produto sem benefício", codigo="X").valor == d("0.0000")

    def test_reducao_de_cem_nao_existe(self):
        with pytest.raises(CorrecaoInvalida, match="exclusive"):
            validar("reducao_base", 100, "motivo bom", codigo="X")

    def test_mercadoria_sem_codigo_e_recusada(self):
        with pytest.raises(CorrecaoInvalida, match="código"):
            validar("aliquota", 25, "motivo bom")

    def test_documento_informado_na_mercadoria_e_ignorado(self):
        c = validar("aliquota", 25, "motivo bom", codigo="X", documento="1" * 44, numero_item=2)
        assert (c.documento, c.numero_item) == ("", None)


class TestCorrecaoDeLinha:
    def test_enquadramento(self):
        c = validar("enquadramento", "1", "Venda a consumidor confirmada pelo cliente",
                    cnpj="43112531000421", documento="3" * 44, numero_item="2", codigo="1012")
        assert (c.campo, c.valor, c.numero_item) == (Campo.ENQUADRAMENTO, 1, 2)
        assert c.alvo is Alvo.LINHA and c.valor_gravado == "1"

    @pytest.mark.parametrize("valor", [5, -1, "1.5"])
    def test_enquadramento_fora_de_0_a_4(self, valor):
        with pytest.raises(CorrecaoInvalida, match="0 a 4"):
            validar("enquadramento", valor, "motivo bom", documento="3" * 44, numero_item=1)

    def test_enquadramento_que_nao_e_numero(self):
        with pytest.raises(CorrecaoInvalida, match="não é um número"):
            validar("enquadramento", "x", "motivo bom", documento="3" * 44, numero_item=1)

    def test_linha_sem_documento_e_recusada(self):
        with pytest.raises(CorrecaoInvalida, match="chave ou o número"):
            validar("quantidade", 3, "motivo bom", numero_item=1)

    def test_linha_sem_item_e_recusada_e_o_erro_explica(self):
        with pytest.raises(CorrecaoInvalida, match="relatório de PDV"):
            validar("quantidade", 3, "motivo bom", documento="3" * 44)

    def test_quantidade_negativa_nao_passa(self):
        with pytest.raises(CorrecaoInvalida, match="espécie"):
            validar("quantidade", -3, "motivo bom", documento="3" * 44, numero_item=1)

    def test_valor_do_item_aceita_zero(self):
        c = validar("valor_item", "0", "bonificação sem valor", documento="3" * 44, numero_item=1)
        assert c.valor == d("0.000000")

    @pytest.mark.parametrize("texto, esperado", [("sim", True), ("SIM", True), ("x", True),
                                                 ("nao", False), ("não", False), ("", False)])
    def test_excluida_entende_o_que_a_planilha_escreve(self, texto, esperado):
        c = validar("excluida", texto, "cancelada na SEFAZ, fora da lista", documento="3" * 44, numero_item=1)
        assert c.valor is esperado and c.valor_gravado == ("sim" if esperado else "nao")

    def test_excluida_com_resposta_estranha(self):
        with pytest.raises(CorrecaoInvalida, match="sim ou não"):
            validar("excluida", "talvez", "motivo bom", documento="3" * 44, numero_item=1)


class TestOQueNaoExiste:
    def test_campo_desconhecido(self):
        with pytest.raises(CorrecaoInvalida, match="Campo desconhecido"):
            validar("aliquota_st", 25, "motivo bom", codigo="X")

    def test_cnpj_torto(self):
        with pytest.raises(CorrecaoInvalida, match="14 dígitos"):
            validar("aliquota", 25, "motivo bom", cnpj="123", codigo="X")

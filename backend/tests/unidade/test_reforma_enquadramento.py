"""O enquadramento do item: NCM, capítulo e a categoria do Imposto Seletivo."""

import pytest

from cat.dominio.reforma.enquadramento import (
    capitulo, categoria_do_seletivo, familia, normalizar_ncm, subcapitulo)
from cat.dominio.reforma.parametros import CENARIO_BASE


@pytest.mark.parametrize("bruto,esperado", [
    ("03032300", "03032300"), (3032300, "03032300"), ("3032300.0", "03032300"),
    ("2202.10.00", "22021000"), (None, ""), ("", ""),
    ("012119010", "012119010"),   # nove dígitos não é NCM: volta para a pendência
])
def test_ncm_normalizada(bruto, esperado):
    assert normalizar_ncm(bruto) == esperado


def test_capitulo_e_subcapitulo():
    assert capitulo("22021000") == "22" and subcapitulo("22021000") == "2202"
    assert capitulo("") == "--"


def test_familia_e_a_primeira_palavra():
    assert familia("cerv lt heineken 350ml") == "CERV"
    assert familia(None) == "(sem descrição)"


class TestSeletivo:
    @pytest.mark.parametrize("ncm,categoria", [
        ("24022000", "fumo"), ("22030000", "alcool"), ("22084000", "alcool"),
        ("22021000", "acucaradas"), ("22029900", "acucaradas"),
        ("22029100", ""),            # outra bebida não alcoólica: fora
        ("87032310", "veiculos"), ("27101259", "extracao"), ("04032000", ""),
    ])
    def test_pela_ncm(self, ncm, categoria):
        c = categoria_do_seletivo(ncm, None, CENARIO_BASE)
        assert (c.chave, c.origem) == (categoria, "ncm")

    def test_o_cadastro_tira_o_zero_acucar(self):
        """O refrigerante zero divide a NCM com o açucarado. Só o cadastro, por
        SKU, separa — e ele vence a regra."""
        c = categoria_do_seletivo("22021000", "nenhuma", CENARIO_BASE)
        assert (c.chave, c.origem) == ("", "cadastro")

    def test_o_cadastro_pode_incluir(self):
        assert categoria_do_seletivo("21069010", "Acucaradas", CENARIO_BASE).chave == "acucaradas"

    def test_o_cadastro_pode_escrever_o_nome(self):
        """A planilha de resultado da primeira simulação escrevia o nome, com acento."""
        assert categoria_do_seletivo("22030000", "Bebidas Alcoólicas", CENARIO_BASE).chave == "alcool"

    def test_categoria_desconhecida_no_cadastro_e_recusada(self):
        """Erro de digitação não pode virar "não paga IS" calado."""
        with pytest.raises(ValueError, match="desconhecida"):
            categoria_do_seletivo("22021000", "refri", CENARIO_BASE)

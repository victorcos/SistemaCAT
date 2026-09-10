"""CNPJ, nos dois formatos.

O alfanumérico não é hipótese: a Receita começou a emitir em 31/07/2026. Um
validador que só aceite dígito recusaria empresa nova legítima.
"""

import pytest

from cat.dominio.comum.cnpj import (
    Cnpj,
    CnpjInvalido,
    digitos_verificadores,
    limpar,
    tentar,
)

# CNPJs reais de arquivos desta casa
BOA = "50948371000178"
AVENIDA = "44358067000178"
CENTERBOX = "11497712000184"


class TestNumerico:
    @pytest.mark.parametrize("valor", [BOA, AVENIDA, CENTERBOX])
    def test_aceita_cnpj_real(self, valor):
        assert Cnpj(valor).valor == valor

    def test_aceita_com_pontuacao(self):
        assert Cnpj("50.948.371/0001-78").valor == BOA

    def test_recusa_digito_errado(self):
        with pytest.raises(CnpjInvalido, match="dígito verificador"):
            Cnpj("50948371000179")

    def test_recusa_tamanho_errado(self):
        with pytest.raises(CnpjInvalido, match="14 caracteres"):
            Cnpj("5094837100017")

    def test_recusa_sequencia_repetida(self):
        """Passa no módulo 11 mas não existe."""
        with pytest.raises(CnpjInvalido, match="repetida"):
            Cnpj("00000000000000")

    def test_recusa_vazio(self):
        with pytest.raises(CnpjInvalido):
            Cnpj("")


class TestAlfanumerico:
    def test_aceita_letras_nas_doze_primeiras(self):
        base = "12ABC34501DE"
        c = Cnpj(base + digitos_verificadores(base))
        assert c.e_alfanumerico

    def test_a_regra_nova_da_o_mesmo_digito_para_cnpj_antigo(self):
        """É o que permite uma implementação só para os dois formatos."""
        assert digitos_verificadores(BOA[:12]) == BOA[12:]

    def test_recusa_letra_no_digito_verificador(self):
        with pytest.raises(CnpjInvalido, match="só dígito"):
            Cnpj("12ABC34501DEA1")

    def test_cnpj_so_de_numeros_nao_e_alfanumerico(self):
        assert not Cnpj(BOA).e_alfanumerico


class TestPartes:
    def test_raiz_ordem_e_dv(self):
        c = Cnpj(BOA)
        assert c.raiz == "50948371"
        assert c.ordem == "0001"
        assert c.dv == "78"

    def test_matriz(self):
        assert Cnpj(BOA).e_matriz

    def test_filial_nao_e_matriz(self):
        # 50948371000259 é filial do mesmo grupo
        assert not Cnpj("50948371000259").e_matriz

    def test_mesma_raiz(self):
        assert Cnpj(BOA).mesma_raiz(Cnpj("50948371000259"))
        assert not Cnpj(BOA).mesma_raiz(Cnpj(AVENIDA))

    def test_derivar_a_matriz_de_uma_filial(self):
        """Trocar a ordem muda o dígito, então tem de recalcular."""
        filial = Cnpj("50948371000259")
        assert filial.matriz().valor == BOA

    def test_matriz_de_matriz_e_ela_mesma(self):
        m = Cnpj(BOA)
        assert m.matriz() is m


class TestApresentacao:
    def test_formatado(self):
        assert Cnpj(BOA).formatado == "50.948.371/0001-78"

    def test_str_usa_o_formatado(self):
        assert str(Cnpj(BOA)) == "50.948.371/0001-78"

    def test_limpar_nao_valida(self):
        assert limpar(" 50.948.371/0001-78 ") == BOA


class TestTentar:
    def test_devolve_none_em_vez_de_explodir(self):
        """Ao ler arquivo de terceiro, recusar a linha por um campo torto é
        pior do que seguir sem ele."""
        assert tentar("nao e cnpj") is None
        assert tentar("") is None

    def test_devolve_o_cnpj_quando_valido(self):
        assert tentar(BOA).valor == BOA

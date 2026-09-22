"""A apuração do período: separar o que se pede do que se recolhe, e dizer o
que ainda trava a competência."""

from decimal import Decimal

import pytest

from cat.dominio.icms.cat42.apuracao import CompetenciaApurada, MotivoDeBloqueio


def competencia(**kw) -> CompetenciaApurada:
    base = {"cnpj": "11517841000278", "uf": "SP", "competencia": "2021-05",
            "inventarios_conferidos": 10}
    return CompetenciaApurada(**{**base, **kw})


class TestRessarcimentoEComplemento:
    def test_nao_se_compensam(self):
        """São coisas opostas: um se pede, o outro se recolhe. O líquido é
        leitura, e os dois valores continuam inteiros."""
        c = competencia(ressarcimento=Decimal("1000"), complemento=Decimal("250"))
        assert c.ressarcimento == Decimal("1000")
        assert c.complemento == Decimal("250")
        assert c.liquido == Decimal("750")

    def test_credito_do_artigo_271_vem_zerado_e_preparado(self):
        """Coluna 27: só no enquadramento 4, e vem da coluna 21, que ainda não
        se apura. Zerada de propósito, não esquecida."""
        assert competencia().credito_operacao_propria == Decimal(0)


class TestAptidao:
    def test_competencia_limpa_e_apta(self):
        c = competencia(ressarcimento=Decimal("10"), itens=5, linhas=50)
        assert c.apta and c.motivos == []

    @pytest.mark.parametrize("campo,valor,motivo", [
        ("uf", "PR", MotivoDeBloqueio.FORA_DE_SP),
        ("fichas_retiradas", 1, MotivoDeBloqueio.FICHA_RETIRADA),
        ("confronto_pendente", 3, MotivoDeBloqueio.CONFRONTO_PENDENTE),
        ("sem_aliquota", 2, MotivoDeBloqueio.SEM_ALIQUOTA),
        ("indefinidas", 1, MotivoDeBloqueio.ENQUADRAMENTO_INDEFINIDO),
        ("inventarios_divergentes", 1, MotivoDeBloqueio.DIVERGE_DO_INVENTARIO),
        ("inventarios_conferidos", 0, MotivoDeBloqueio.SEM_INVENTARIO),
    ])
    def test_cada_pendencia_trava_e_se_explica(self, campo, valor, motivo):
        c = competencia(**{campo: valor})
        assert not c.apta
        assert motivo in c.motivos
        assert motivo.rotulo and motivo.o_que_fazer

    def test_o_valor_aparece_mesmo_travado(self):
        """Apurar e poder entregar são coisas diferentes: o número se mostra,
        e a lista do que falta vai junto."""
        c = competencia(uf="PR", ressarcimento=Decimal("90"), fichas_retiradas=4)
        assert c.ressarcimento == Decimal("90")
        assert [m.value for m in c.motivos] == ["fora_de_sp", "ficha_retirada"]

    def test_uf_desconhecida_nao_acusa_de_fora_de_sp(self):
        """Sem a UF na EFD não se afirma que o estabelecimento é de outro
        estado — seria acusar pelo que não se sabe."""
        assert MotivoDeBloqueio.FORA_DE_SP not in competencia(uf="").motivos

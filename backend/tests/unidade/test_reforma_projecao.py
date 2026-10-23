"""A projeção da reforma: as fórmulas, as identidades e a regressão contra a
primeira simulação feita à mão (empresa 23, saídas de dez/2025)."""

from decimal import Decimal

import pytest

from cat.dominio.reforma.dre import conferir
from cat.dominio.reforma.parametros import (
    CENARIO_BASE, Cenario, CenarioInvalido, GrupoDeAliquota, ParametrosDoAno, normalizar_cclasstrib)
from cat.dominio.reforma.projecao import BaseDaLinha, projetar, receita_bruta_requerida

D = Decimal


def base(**kw) -> BaseDaLinha:
    padrao = dict(receita_bruta=D(100), debito_icms=D(18), debito_pis_cofins=D("9.25"),
                  credito_icms=D(9), credito_pis_cofins=D("4.5"), custo_liquido=D(50),
                  pis_cofins_sem_credito=D(2), ipi_entrada=D(1))
    return BaseDaLinha(**{**padrao, **{k: D(str(v)) for k, v in kw.items()}})


class TestAnoBase:
    def test_2025_reproduz_o_modelo_de_hoje(self):
        """Propriedade obrigatória: sem reforma, a receita líquida é a de hoje e
        o lucro bruto é o da apuração atual — ao centavo."""
        b = base()
        r = projetar(b, D(0), CENARIO_BASE.do_ano(2025))
        assert r.receita_liquida == b.receita_liquida
        assert r.lucro_bruto == b.lucro_bruto_atual
        assert r.debito_cbs == r.debito_ibs == 0

    def test_2026_nao_tem_efeito_liquido(self):
        """O teste de 2026 é destacado e compensado: a margem não mexe, mas o
        valor destacado aparece como informação."""
        b = base()
        hoje = projetar(b, D(0), CENARIO_BASE.do_ano(2025))
        teste = projetar(b, D(0), CENARIO_BASE.do_ano(2026))
        assert teste.lucro_bruto == hoje.lucro_bruto
        assert teste.teste_destacado == D("0.010") * teste.receita_liquida


class TestFormulas:
    def test_ibs_cbs_por_fora(self):
        """2033, alíquota padrão: a receita sem tributos é o que sobra da bruta
        dividido por 1,265, e o débito é 26,5% dela."""
        r = projetar(base(debito_pis_cofins=0), D(0), CENARIO_BASE.do_ano(2033))
        assert r.debito_icms == 0
        assert r.receita_liquida == D(100) / D("1.265")
        assert r.debito_cbs + r.debito_ibs == pytest.approx(D(100) - r.receita_liquida)

    def test_aliquota_zero_nao_debita_nem_credita(self):
        r = projetar(base(), D(1), CENARIO_BASE.do_ano(2033))
        assert r.debito_cbs == r.debito_ibs == r.credito_cbs == r.credito_ibs == 0

    def test_reducao_de_60(self):
        r = projetar(base(), D("0.6"), CENARIO_BASE.do_ano(2033))
        assert r.debito_cbs == r.receita_liquida * D("0.088") * D("0.4")

    def test_pis_cofins_sem_credito_fica_no_custo_em_todo_ano(self):
        """Ele já está no preço de compra; a reforma não o tira de lá. Só o IPI
        sai do custo em 2027."""
        b = base()
        for ano in (2025, 2027, 2033):
            r = projetar(b, D(0), CENARIO_BASE.do_ano(ano))
            assert r.custo_de_compra == D(52)
        assert projetar(b, D(0), CENARIO_BASE.do_ano(2025)).ipi_custo == 1
        assert projetar(b, D(0), CENARIO_BASE.do_ano(2027)).ipi_custo == 0

    def test_seletivo_e_custo_e_aumenta_o_credito(self):
        """O IS é cobrado do fabricante e chega no preço, sem crédito. Mas ele
        está na base do IBS/CBS do fornecedor, e por isso o crédito sobe."""
        sem = projetar(base(), D(0), CENARIO_BASE.do_ano(2033))
        com = projetar(base(seletivo_pleno=10), D(0), CENARIO_BASE.do_ano(2033))
        assert com.cmv - sem.cmv == 10
        assert com.credito_cbs + com.credito_ibs - sem.credito_cbs - sem.credito_ibs == \
            D(10) * D("0.265")

    def test_seletivo_so_a_partir_de_2027(self):
        b = base(seletivo_pleno=10)
        assert projetar(b, D(0), CENARIO_BASE.do_ano(2026)).seletivo == 0
        assert projetar(b, D(0), CENARIO_BASE.do_ano(2027)).seletivo == 10


class TestSomavel:
    def test_projetar_a_soma_e_somar_as_projecoes(self):
        """A propriedade que permite agregar antes de projetar."""
        a, b = base(), base(receita_bruta=37, debito_icms=5, seletivo_pleno=3)
        for ano in CENARIO_BASE.anos:
            junto = projetar(a + b, D("0.6"), ano)
            separado = projetar(a, D("0.6"), ano) + projetar(b, D("0.6"), ano)
            assert junto.lucro_bruto == pytest.approx(separado.lucro_bruto, abs=D("1e-20"))
            assert junto.total_a_recolher == pytest.approx(separado.total_a_recolher, abs=D("1e-20"))


class TestConferencias:
    @pytest.mark.parametrize("ano", [a.ano for a in CENARIO_BASE.anos])
    def test_as_tres_fecham_em_todo_ano(self, ano):
        r = projetar(base(seletivo_pleno=4, debito_ipi=2), D("0.6"), CENARIO_BASE.do_ano(ano))
        assert all(c.fecha for c in conferir(r)), conferir(r)


class TestVariacaoTeorica:
    def test_no_ano_base_e_zero(self):
        b = base()
        rb = receita_bruta_requerida(b, D(0), CENARIO_BASE.do_ano(2025), b.lucro_bruto_atual)
        assert rb == pytest.approx(b.receita_bruta)


class TestCenario:
    def test_cclasstrib_em_dois_grupos_e_recusado(self):
        with pytest.raises(CenarioInvalido, match="dois grupos"):
            Cenario("x", CENARIO_BASE.anos, (
                GrupoDeAliquota("a", "A", D(0), frozenset({"000001"})),
                GrupoDeAliquota("b", "B", D(1), frozenset({"000001"})),
            ), ())

    def test_ano_repetido_e_recusado(self):
        ano = CENARIO_BASE.anos[0]
        with pytest.raises(CenarioInvalido, match="repetidos"):
            Cenario("x", (ano, ano), CENARIO_BASE.grupos, ())

    def test_aliquota_fora_de_0_a_1(self):
        ruim = ParametrosDoAno(2025, D(2), D(0), D(1), True, True, False, False)
        with pytest.raises(CenarioInvalido, match="CBS"):
            Cenario("x", (ruim,), CENARIO_BASE.grupos, ())

    @pytest.mark.parametrize("bruto,esperado", [
        (1, "000001"), ("1", "000001"), (200003, "200003"), ("200003.0", "200003"), (None, "")])
    def test_cclasstrib_volta_com_zeros(self, bruto, esperado):
        assert normalizar_cclasstrib(bruto) == esperado

    def test_cclasstrib_desconhecido_nao_vira_padrao(self):
        """Item sem grupo é pendência de cadastro: chutar a padrão esconderia
        quem ninguém revisou."""
        assert CENARIO_BASE.grupo("999999") is None
        assert CENARIO_BASE.grupo(1).chave == "padrao"

    def test_fator_de_sensibilidade_do_seletivo(self):
        from dataclasses import replace
        metade = replace(CENARIO_BASE, fator_seletivo=D("0.5"))
        assert metade.aliquota_do_seletivo("alcool") == D("0.25")
        assert CENARIO_BASE.aliquota_do_seletivo(None) == 0


# ---------------------------------------------------------------------------
# Regressão: os totais por grupo da primeira simulação (empresa 23, dez/2025,
# 474.289 linhas), aba "Base Dez-2025" da planilha principal. Como o modelo é
# linear, projetar os três totais dá o mesmo que projetar as linhas. Os
# esperados são os da tabela de referência do README, em R$ milhões com uma
# casa — daí a tolerância de 60 mil.
# ---------------------------------------------------------------------------

GRUPOS_DEZ_2025 = {
    D(0): BaseDaLinha(
        receita_bruta=D("315189475.1247"), debito_icms=D("65273124.2644"),
        debito_pis_cofins=D("14261886.8999"), credito_icms=D("35835949.1574"),
        credito_pis_cofins=D("12884608.2013"), custo_liquido=D("194573061.7991"),
        pis_cofins_sem_credito=D("7756450.228"), ipi_entrada=D("3227049.4957"),
        seletivo_pleno=D("23419588.0512")),
    D("0.6"): BaseDaLinha(
        receita_bruta=D("69469344.1456"), debito_icms=D("12820160.1792"),
        debito_pis_cofins=D("1189261.7913"), credito_icms=D("7145576.3576"),
        credito_pis_cofins=D("1272502.2145"), custo_liquido=D("45484364.8875"),
        pis_cofins_sem_credito=D("3407744.3419"), ipi_entrada=D("2407.5888"),
        seletivo_pleno=D("448090.3577")),
    D(1): BaseDaLinha(
        receita_bruta=D("231206368.0276"), debito_icms=D("36124741.8902"),
        debito_pis_cofins=D("423126.3695"), credito_icms=D("24045504.2092"),
        credito_pis_cofins=D("365563.8202"), custo_liquido=D("158119480.3898"),
        pis_cofins_sem_credito=D("16434877.8146"), ipi_entrada=D("2.6079"),
        seletivo_pleno=D("810.8723")),
}

#        ano: (lucro bruto, tributo a recolher, créditos, valor bruto das compras)
REFERENCIA = {
    2025: (56.8, 48.5, 81.5, 510.6),
    2026: (56.8, 48.5, 81.5, 510.6),
    2027: (29.9, 47.7, 88.6, 538.3),
    2028: (29.9, 47.7, 88.6, 538.3),
    2029: (36.6, 43.4, 86.3, 535.9),
    2030: (43.2, 39.1, 83.9, 533.6),
    2031: (49.7, 35.0, 81.6, 531.2),
    2032: (56.2, 30.8, 79.2, 528.8),
    2033: (93.5, 7.6, 65.1, 514.7),
}


def _total(ano: int):
    params = CENARIO_BASE.do_ano(ano)
    resultados = [projetar(b, red, params) for red, b in GRUPOS_DEZ_2025.items()]
    total = resultados[0]
    for r in resultados[1:]:
        total = total + r
    return total


class TestRegressaoEmpresa23:
    def test_lucro_bruto_de_2025_ao_centavo(self):
        assert _total(2025).lucro_bruto.quantize(D("0.01")) == D("56767446.75")

    @pytest.mark.parametrize("ano", sorted(REFERENCIA))
    def test_ano_a_ano(self, ano):
        lb, recolher, creditos, bruto = REFERENCIA[ano]
        t = _total(ano)
        mi = D(1_000_000)
        assert float(t.lucro_bruto / mi) == pytest.approx(lb, abs=0.06)
        assert float(t.total_a_recolher / mi) == pytest.approx(recolher, abs=0.06)
        assert float(t.creditos_recuperaveis / mi) == pytest.approx(creditos, abs=0.06)
        assert float(t.valor_bruto_das_compras / mi) == pytest.approx(bruto, abs=0.06)

    def test_margem_de_2033(self):
        assert float(_total(2033).margem) == pytest.approx(0.152, abs=0.0005)

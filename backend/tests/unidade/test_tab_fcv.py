"""O FCV: a tabela que a física confere.

Diferente da ad rem, que é número de convênio e só se confirma lendo o convênio,
o FCV tem uma propriedade interna que o denuncia quando está errado: **ele cai
conforme a temperatura do estado sobe**. Combustível faturado a 20 °C ocupa mais
espaço quando está mais quente, e o fator desfaz isso.

Essa monotonia é testada aqui porque é a única conferência que não depende de
ninguém reler o Ato COTEPE.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cat.infraestrutura.sped.tabelas import tab_fcv
from cat.infraestrutura.sped.tabelas.tab_ad_rem import DIESEL, GASOLINA, GLP
from cat.infraestrutura.sped.tabelas.tab_fcv import FcvDesconhecido, fator


class TestOQueOAtoPublica:
    @pytest.mark.parametrize("uf, produto, esperado", [
        ("SP", DIESEL, "0.9976"),
        ("SP", GASOLINA, "0.9967"),
        ("ES", DIESEL, "0.9943"),
        ("ES", GASOLINA, "0.9923"),
        ("MG", DIESEL, "0.9967"),
        ("PR", DIESEL, "0.9980"),
        ("RJ", DIESEL, "0.9951"),
    ])
    def test_os_valores_do_ato(self, uf, produto, esperado):
        assert fator(uf, produto, "2024-06") == Decimal(esperado)

    def test_as_27_unidades_estao_la(self):
        assert len(tab_fcv.POR_UF) == 27

    def test_a_uf_vem_normalizada(self):
        """O SPED escreve a UF em maiúscula, mas quem chama pode não escrever."""
        assert fator("sp", DIESEL, "2024-06") == fator(" SP ", DIESEL, "2024-06")


class TestAFisicaConfere:
    def test_o_fator_cai_conforme_a_temperatura_sobe(self):
        """A conferência que não depende de reler o Ato.

        Mais quente, mais dilatado, mais correção para baixo. Um valor digitado
        errado quebra esta ordem — foi por isso que a temperatura ficou na
        tabela em vez de só no comentário.
        """
        por_temperatura = sorted(tab_fcv.POR_UF.items(),
                                 key=lambda kv: kv[1].temperatura)

        for produto in ("diesel", "gasolina"):
            valores = [getattr(f, produto) for _, f in por_temperatura]
            assert valores == sorted(valores, reverse=True), produto

    def test_a_gasolina_corrige_mais_que_o_diesel(self):
        """Ela é mais leve e dilata mais. Vale em todas as 27."""
        for uf, f in tab_fcv.POR_UF.items():
            assert f.gasolina < f.diesel, uf

    def test_estados_de_mesma_temperatura_tem_o_mesmo_fator(self):
        """DF e MG estão ambos a 24,0 °C — se divergissem, um estaria errado."""
        assert tab_fcv.POR_UF["DF"] == tab_fcv.POR_UF["MG"]

    def test_todo_fator_corrige_para_baixo_e_pouco(self):
        """Entre 0,98 e 1: acima de 1 seria dilatar, e abaixo de 0,98 seria erro
        de digitação de uma casa."""
        for uf, f in tab_fcv.POR_UF.items():
            for v in (f.gasolina, f.diesel):
                assert Decimal("0.98") < v < Decimal(1), uf


class TestOGlpNaoTemFcv:
    def test_devolve_um_porque_massa_nao_dilata(self):
        """Não é valor desconhecido disfarçado de neutro: é a ausência de
        correção, e o GLP é tributado por quilo."""
        assert fator("SP", GLP, "2024-06") == Decimal(1)

    def test_e_devolve_um_ate_para_uf_que_nao_existe(self):
        """Porque a resposta não depende da UF — é do produto."""
        assert fator("ZZ", GLP, "2024-06") == Decimal(1)


class TestOQueEleRecusa:
    def test_uf_que_nao_existe(self):
        with pytest.raises(FcvDesconhecido) as erro:
            fator("ZZ", DIESEL, "2024-06")

        assert "ZZ" in str(erro.value)

    def test_competencia_anterior_ao_ato(self):
        """O Ato vale de 2020-01; antes dele havia outro, que não se levantou."""
        with pytest.raises(FcvDesconhecido) as erro:
            fator("SP", DIESEL, "2019-12")

        assert "2019-12" in str(erro.value)
        assert "2020-01" in str(erro.value)

    def test_produto_sem_fcv_publicado(self):
        """O Ato traz gasolina A e óleo diesel, e mais nada."""
        with pytest.raises(FcvDesconhecido) as erro:
            fator("SP", "querosene", "2024-06")

        assert "quilo" in str(erro.value), "explica por que o GLP é diferente"


class TestOErroQueEstaTabelaDenuncia:
    def test_usar_o_fator_de_sp_num_cliente_do_es_erra_033_por_cento(self):
        """**Aconteceu**, num papel de trabalho de projeto encerrado.

        Ele declarava usar "o FCV para o estado de São Paulo" e o cliente era do
        Espírito Santo. O erro é pequeno por linha e sistemático em tudo —
        exatamente o tipo que ninguém encontra conferindo um total.
        """
        sp = fator("SP", DIESEL, "2024-06")
        es = fator("ES", DIESEL, "2024-06")

        desvio = (sp - es) / es * 100
        assert Decimal("0.32") < desvio < Decimal("0.34")

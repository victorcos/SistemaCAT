"""A redução de base que a entrada declara e que alcança o efetivo da saída.

Os números são os do fornecedor da empresa D, nota a nota: ele reduz a base
e informa em `pRedBC` o percentual que **sobra**, não o que reduziu. Por isso a
conta sai do `vBC`, e não da tag — ver `cat.dominio.icms.cat42.reducao`.
"""

from decimal import Decimal

import pytest

from cat.dominio.icms.cat42.reducao import (
    CST_COM_REDUCAO,
    base_reduzida,
    icms_efetivo,
    reducao_da_entrada,
)


def d(v) -> Decimal:
    return Decimal(str(v))


class TestOQueAEntradaDeclara:
    def test_grecin_cst70_reduz_52_por_cento_e_da_carga_de_12(self):
        # nota do fornecedor: vProd 22.589,28, vBC 10.842,85 (48%), pICMS 25%,
        # vICMS 2.710,71 — que é 12% do valor da mercadoria
        reducao = reducao_da_entrada("570", d("10842.85"), d("22589.28"), None)
        assert reducao == d("52.0000")
        assert icms_efetivo(d("22589.28"), d(25), reducao).quantize(d("0.01")) == d("2710.71")
        # a carga da saída fica em 12% do valor, não nos 25% cheios
        assert icms_efetivo(d(100), d(25), reducao).quantize(d("0.01")) == d("12.00")

    def test_vagisil_cst70_reduz_um_terco_e_tambem_da_12(self):
        # vProd 10.646,88, vBC 7.222,08 (66,67%), pICMS 18% -> vICMS 1.299,97
        reducao = reducao_da_entrada("870", d("7222.08"), d("10646.88"), None)
        assert reducao == d("32.1672")
        assert icms_efetivo(d("10646.88"), d(18), reducao).quantize(d("0.01")) == d("1299.97")
        assert icms_efetivo(d(100), d(18), d("33.3300")).quantize(d("0.01")) == d("12.00")

    def test_pRedBC_lido_ao_pe_da_letra_daria_outro_numero(self):
        """O que a RVZ fez: 25% x (1 - 0,48) = 13%, contra os 12% do vBC."""
        assert icms_efetivo(d(100), d(25), d(48)) == d(13)
        assert icms_efetivo(d(100), d(18), d("66.67")).quantize(d("0.01")) == d("6.00")

    @pytest.mark.parametrize("cst", ["020", "070", "20", "70"])
    def test_le_os_dois_cst_com_e_sem_origem(self, cst):
        assert reducao_da_entrada(cst, d(50), d(100), None) == d("50.0000")

    @pytest.mark.parametrize("cst", ["060", "000", "010", "090", "", None])
    def test_cst_sem_reducao_nao_devolve_nada(self, cst):
        assert reducao_da_entrada(cst, d(50), d(100), None) is None

    @pytest.mark.parametrize("base, valor, desconto", [
        (None, d(100), None),      # sem base
        (d(50), None, None),       # sem valor
        (d(0), d(100), None),      # base zerada: é isenção, não redução
        (d(120), d(100), None),    # base maior que o valor: não se sustenta
        (d(100), d(100), None),    # sem redução nenhuma
        (d(50), d(100), d(100)),   # desconto come o valor todo
    ])
    def test_o_que_nao_se_sustenta_fica_sem_reducao(self, base, valor, desconto):
        assert reducao_da_entrada("070", base, valor, desconto) is None

    def test_o_conjunto_de_cst_e_o_que_o_manual_admite(self):
        assert CST_COM_REDUCAO == {"20", "70"}


class TestOQuePrevalece:
    """Vale o `pRedBC` do documento (decisão do Victor, 18/09/2026).

    O arquivo do fornecedor da empresa D é incoerente — declara 48% e usa
    base de 48,84% —, e a decisão foi seguir a tag, que é o campo que a
    legislação define como percentual de redução.
    """

    def test_o_pRedBC_declarado_vence_a_base_usada(self):
        # nota 51462, item 1012-N: pRedBC 48,00 com vBC de 48,84% do valor
        assert reducao_da_entrada("570", d("60.48"), d("123.84"), None, d(48)) == d("48.0000")
        assert icms_efetivo(d("39.99"), d(25), d(48)).quantize(d("0.0001")) == d("5.1987")

    def test_sem_pRedBC_vale_a_base_que_a_nota_usou(self):
        """A EFD não tem esse campo: ali a redução continua saindo do vBC."""
        assert reducao_da_entrada("570", d("60.48"), d("123.84")) == d("51.1628")

    @pytest.mark.parametrize("declarada", [d(0), d(100), d(-1), d("100.01")])
    def test_pRedBC_fora_de_0_a_100_e_ignorado(self, declarada):
        assert reducao_da_entrada("570", d(48), d(100), None, declarada) == d("52.0000")


class TestOQueAplicaNaSaida:
    def test_sem_reducao_a_base_e_o_valor_cheio(self):
        assert base_reduzida(d(100), None) == d(100)
        assert base_reduzida(d(100), d(0)) == d(100)
        assert icms_efetivo(d(100), d(18), None) == d(18)

    def test_com_reducao_a_aliquota_incide_sobre_o_que_sobrou(self):
        assert base_reduzida(d(100), d(52)) == d(48)
        assert icms_efetivo(d("216.60"), d(18), d("33.3300")).quantize(d("0.01")) == d("25.99")

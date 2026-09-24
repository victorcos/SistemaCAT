"""A exclusão do PIS e da COFINS da própria base.

O gabarito é o exemplo aprovado em 24/09/2026, na definição da regra: venda de
R$ 1.000,00, PIS de 1,65% e COFINS de 7,6%. A base perde **as duas**
contribuições — R$ 907,50 —, e o que volta é R$ 8,56. Qualquer mudança que
altere esse número está mudando a tese, não o código.
"""

from __future__ import annotations

from cat.infraestrutura.exclusoes.piscofins_na_propria_base import (
    Grupo,
    Total,
    calcular,
)
from cat.infraestrutura.gestao.modelos import ApuracaoEFD

CNPJ = "03083231002148"
PERIODO = "2025-09"

# posições do vetor de somas: [vl_item, vl_bc, vl_trib, quant, linhas]
def _somas(base: int, valor: int, quant: int = 0, linhas: int = 1) -> list[int]:
    return [base, base, valor, quant, linhas]


def _apuracao(documentos: dict, contagens: dict | None = None) -> ApuracaoEFD:
    return ApuracaoEFD(
        arquivo="contrib.txt", file_hash="x", tamanho=1,
        cnpj=CNPJ, periodo=PERIODO,
        documentos=documentos, contagens=contagens or {},
    )


def _venda(cst: str = "01", cfop: str = "5102", registro: str = "C170",
           base: int = 100_000, pis: int = 1_650, cofins: int = 7_600,
           operacao: str = "S") -> dict:
    """Uma venda de R$ 1.000,00 com PIS de R$ 16,50 e COFINS de R$ 76,00."""
    return {
        ("PIS", registro, operacao, cst, cfop, "", "1,65"): _somas(base, pis),
        ("COFINS", registro, operacao, cst, cfop, "", "7,60"): _somas(base, cofins),
    }


class TestARegraDaTese:
    def test_a_base_perde_as_duas_contribuicoes(self):
        r = calcular([_apuracao(_venda())])

        (grupo, a), = r.grupos.items()
        assert grupo == Grupo(CNPJ, PERIODO, "C170", "01", "5102")
        assert a.excluido == 9_250                 # 16,50 + 76,00
        assert a.base_nova_pis == 90_750           # 1.000,00 - 92,50
        assert a.base_nova_cofins == 90_750

    def test_o_que_volta_e_o_do_gabarito(self):
        r = calcular([_apuracao(_venda())])

        (_, a), = r.grupos.items()
        assert a.pis_novo == 1_497                 # 907,50 x 1,65%
        assert a.cofins_novo == 6_897              # 907,50 x 7,60%
        assert a.diferenca_pis == 153              # R$ 1,53
        assert a.diferenca_cofins == 703           # R$ 7,03
        assert a.diferenca == 856                  # R$ 8,56
        assert r.resumo.diferenca == 856

    def test_a_aliquota_e_a_do_proprio_arquivo(self):
        """Alíquota fora do padrão não quebra a conta: vale valor ÷ base."""
        r = calcular([_apuracao(_venda(pis=650, cofins=3_000))])  # cumulativo

        (_, a), = r.grupos.items()
        assert a.excluido == 3_650
        # 96.350 x 0,65% = 626,275 -> 626; e x 3% = 2.890,50 -> 2.891 (meio p/ cima)
        assert a.pis_novo == 626
        assert a.cofins_novo == 2_891
        assert a.diferenca == (650 - 626) + (3_000 - 2_891)


class TestOArredondamento:
    def test_arredonda_uma_vez_por_grupo_e_nao_por_linha(self):
        """Três vendas somam antes de arredondar, e o total muda por causa disso.

        Sozinha, a venda de R$ 10,00 com PIS de R$ 0,10 e COFINS de R$ 0,30
        não devolve nada: 9,60 x 1% = 0,096, que arredonda de volta para 0,10.
        Somadas as três, a conta é 28,80 x 1% = 0,288 -> 0,29, e volta um
        centavo. Arredondar linha a linha esconde a diferença; é o mesmo
        efeito, com o sinal trocado, que inflou o Gross UP do Superpão.
        """
        linha = _venda(base=1_000, pis=10, cofins=30)

        uma = calcular([_apuracao(linha)])
        (_, a_uma), = uma.grupos.items()
        assert a_uma.pis_novo == 10 and a_uma.diferenca_pis == 0

        tres = calcular([_apuracao(linha)] * 3)
        (_, a_tres), = tres.grupos.items()

        assert a_tres.base_pis == 3_000 and a_tres.pis == 30
        assert a_tres.pis_novo == 29          # 2.880 x (30/3.000) = 28,8 -> 29
        assert a_tres.diferenca_pis == 1      # e não 3 x 0
        assert a_tres.diferenca_pis != 3 * a_uma.diferenca_pis

    def test_o_mesmo_grupo_em_dois_arquivos_soma_antes_de_recalcular(self):
        """Duas competências do mesmo CNPJ são grupos diferentes; o mesmo par
        registro/CST/CFOP dentro da mesma competência é um grupo só."""
        outro = ApuracaoEFD(arquivo="b.txt", file_hash="y", tamanho=1,
                            cnpj=CNPJ, periodo=PERIODO, documentos=_venda())
        r = calcular([_apuracao(_venda()), outro])

        assert len(r.grupos) == 1
        (_, a), = r.grupos.items()
        assert a.base_pis == 200_000
        assert a.pis == 3_300


class TestOQueFicaDeFora:
    def test_aquisicao_nao_entra_porque_a_tese_e_do_debito(self):
        r = calcular([_apuracao(_venda(operacao="E", cfop="1102"))])

        assert r.grupos == {}
        assert "aquisição: a tese é do débito" in r.resumo.fora

    def test_aliquota_em_reais_nao_entra(self):
        """CST 03: a contribuição vem da quantidade, não da receita."""
        r = calcular([_apuracao(_venda(cst="03"))])

        assert r.grupos == {}
        assert any("alíquota em reais" in motivo for motivo in r.resumo.fora)

    def test_receita_sem_contribuicao_nao_entra(self):
        r = calcular([_apuracao(_venda(cst="06", pis=0, cofins=0))])

        assert r.grupos == {}
        assert any("sem contribuição" in motivo for motivo in r.resumo.fora)

    def test_base_menor_que_a_contribuicao_nao_vira_credito(self):
        """Arquivo inconsistente não pode "recuperar" 100% do grupo."""
        r = calcular([_apuracao(_venda(base=5_000, pis=1_650, cofins=7_600))])

        assert r.resumo.grupos == 0
        assert r.resumo.diferenca == 0
        assert r.resumo.fora["base menor que a contribuição do próprio grupo"] == 1
        assert r.por_periodo() == {}

    def test_todo_descarte_e_contado(self):
        """Nada sai em silêncio: cada motivo com a sua quantidade."""
        r = calcular([_apuracao({
            **_venda(),
            **_venda(cst="03", cfop="5405"),
            **_venda(operacao="E", cfop="1102"),
        })])

        assert sum(r.resumo.fora.values()) == 4   # duas chaves por venda descartada
        assert r.resumo.grupos == 1


class TestOQueOArquivoTemEAContaNaoLe:
    def test_registro_fora_da_leitura_vira_aviso_com_a_quantidade(self):
        r = calcular([_apuracao(_venda(), contagens={"C601": 12, "D350": 3, "C170": 900})])

        assert len(r.resumo.avisos) == 2
        assert any("12 linha(s) de C601" in a for a in r.resumo.avisos)
        assert any("3 linha(s) de D350" in a for a in r.resumo.avisos)

    def test_sem_esses_registros_nao_ha_aviso(self):
        r = calcular([_apuracao(_venda(), contagens={"C170": 900})])

        assert r.resumo.avisos == []


class TestBasesQueDivergem:
    def test_cada_tributo_recalcula_sobre_a_propria_base(self):
        documentos = {
            ("PIS", "C170", "S", "01", "5102", "", "1,65"): _somas(100_000, 1_650),
            ("COFINS", "C170", "S", "01", "5102", "", "7,60"): _somas(90_000, 6_840),
        }
        r = calcular([_apuracao(documentos)])

        (_, a), = r.grupos.items()
        assert a.bases_divergem
        assert a.base == 100_000                       # o relatório mostra a maior
        assert a.base_nova_pis == 100_000 - 8_490
        assert a.base_nova_cofins == 90_000 - 8_490
        assert any("base de PIS diferente" in aviso for aviso in r.resumo.avisos)


class TestOTotalPorCompetencia:
    def test_soma_as_competencias_separadas(self):
        outubro = ApuracaoEFD(arquivo="out.txt", file_hash="z", tamanho=1,
                              cnpj=CNPJ, periodo="2025-10", documentos=_venda())
        r = calcular([_apuracao(_venda()), outubro])

        total = r.por_periodo()
        assert list(total) == ["2025-09", "2025-10"]
        assert all(isinstance(a, Total) for a in total.values())
        assert total["2025-09"].diferenca == 856
        assert total["2025-09"].grupos == 1
        assert r.resumo.periodos == ["2025-09", "2025-10"]

    def test_o_total_e_a_soma_dos_grupos_ja_arredondados(self):
        """Recalcular sobre a soma daria outro número — e a planilha somada à
        mão não bateria com o total da tela."""
        documentos = {}
        for n, cfop in enumerate(("5102", "5405", "5949"), start=1):
            documentos.update({
                ("PIS", "C170", "S", "01", cfop, "", "1,65"): [1_000, 1_000, 10, 0, 1],
                ("COFINS", "C170", "S", "01", cfop, "", "7,60"): [1_000, 1_000, 30, 0, 1],
            })
        r = calcular([_apuracao(documentos)])

        soma_das_linhas = sum(a.diferenca for a in r.grupos.values())
        assert r.por_periodo()[PERIODO].diferenca == soma_das_linhas
        assert r.resumo.diferenca == soma_das_linhas


class TestOParDeRegistrosDaMesmaReceita:
    """C181 traz o PIS e C185 a COFINS da mesma consolidação.

    Separados, a base entrava duas vezes e cada grupo excluía só a própria
    contribuição — a tese conservadora, não a escolhida. Na CEMA isso custou
    29% nos meses em que o cliente escritura por C180.
    """

    def test_pis_e_cofins_do_mesmo_c180_caem_no_mesmo_grupo(self):
        documentos = {
            ("PIS", "C181", "S", "01", "5102", "", "1,65"): _somas(100_000, 1_650),
            ("COFINS", "C185", "S", "01", "5102", "", "7,60"): _somas(100_000, 7_600),
        }
        r = calcular([_apuracao(documentos)])

        (grupo, a), = r.grupos.items()
        assert grupo.registro == "C180/C181/C185"
        assert a.base == 100_000              # a receita, uma vez só
        assert a.excluido == 9_250            # as duas contribuições
        assert a.diferenca == 856             # o mesmo gabarito da venda única

    def test_registro_que_ja_traz_os_dois_nao_muda_de_nome(self):
        r = calcular([_apuracao(_venda(registro="C170"))])

        (grupo, _), = r.grupos.items()
        assert grupo.registro == "C170"

    def test_o_par_nao_junta_cfop_nem_cst_diferentes(self):
        """Juntar a família não pode misturar o que era distinto."""
        documentos = {
            ("PIS", "C181", "S", "01", "5102", "", "1,65"): _somas(100_000, 1_650),
            ("COFINS", "C185", "S", "01", "5405", "", "7,60"): _somas(200_000, 15_200),
        }
        r = calcular([_apuracao(documentos)])

        assert len(r.grupos) == 2

"""O ICMS suportado na entrada: a cascata de fontes e a marca de procedência.

O caso que dá o tom é o CST 60. Ele é 42% das entradas da base real e vem com
zero em ICMS e em ST, porque o imposto foi retido antes e o remetente não
destaca nada. Um cálculo que somasse os campos do arquivo devolveria zero e
pareceria certo.
"""

from decimal import Decimal

import pytest

from cat.dominio.cat42.suportado import (
    EntradaParaApurar,
    Fonte,
    ResumoDaApuracao,
    apurar,
)


def d(v: str) -> Decimal:
    return Decimal(v)


class TestExemploDoManual:
    def test_os_vinte_e_sete_reais_do_manual(self):
        """Mercadoria a R$ 100,00, IVA-ST 50%, alíquota interna 18%.

        Base de retenção R$ 150,00 e ICMS suportado R$ 27,00: R$ 18,00 de
        operação própria mais R$ 9,00 de retido. É o exemplo do manual, e
        serve de âncora para qualquer mudança futura na fórmula.
        """
        r = apurar(EntradaParaApurar(
            cst_icms="010",
            valor_icms=d("18.00"),     # 100,00 x 18%
            valor_st=d("9.00"),        # 150,00 x 18% menos os 18,00
            bc_st=d("150.00"),
        ))
        assert r.valor == d("27.00")
        assert r.fonte is Fonte.DOCUMENTO
        assert r.apurado


class TestDestacadoNoDocumento:
    def test_soma_operacao_propria_e_retido(self):
        r = apurar(EntradaParaApurar(cst_icms="10", valor_icms=d("12.34"),
                                     valor_st=d("5.66")))
        assert r.valor == d("18.00")
        assert r.fonte is Fonte.DOCUMENTO

    def test_o_fecoep_entra_no_suportado(self):
        """O manual inclui o FECOEP da Lei 16.006/2015. Deixá-lo de fora
        subestima o ressarcimento em todo item que o tenha."""
        r = apurar(EntradaParaApurar(cst_icms="10", valor_icms=d("18.00"),
                                     valor_st=d("9.00"), fcp_st=d("2.00")))
        assert r.valor == d("29.00")

    def test_documento_vence_o_que_o_fornecedor_informou(self):
        """Ordem de prova: o destacado na própria nota vale mais."""
        r = apurar(EntradaParaApurar(cst_icms="10", valor_icms=d("18.00"),
                                     valor_st=d("9.00"),
                                     retido_informado=d("999.00")))
        assert r.valor == d("27.00")
        assert r.fonte is Fonte.DOCUMENTO


class TestCst60:
    """O caso que obriga a etapa a existir."""

    def test_sem_nada_nao_e_apuravel_e_diz_por_que(self):
        r = apurar(EntradaParaApurar(cst_icms="060"))
        assert r.fonte is Fonte.NAO_APURAVEL
        assert r.valor == Decimal(0)
        assert not r.apurado
        assert "CST 60" in r.motivo
        assert "retido antes" in r.motivo

    def test_com_o_retido_informado_pelo_fornecedor_apura(self):
        """É o `infAdFisco` da NF-e, ou a coluna 'ST integral' do relatório."""
        r = apurar(EntradaParaApurar(cst_icms="060", retido_informado=d("4.75")))
        assert r.valor == d("4.75")
        assert r.fonte is Fonte.INFORMADO_PELO_FORNECEDOR
        assert r.fonte.e_documental

    def test_com_base_e_aliquota_reconstroi_e_marca_como_reconstruido(self):
        r = apurar(EntradaParaApurar(cst_icms="060", bc_st=d("150.00"),
                                     aliquota_interna=d("18")))
        assert r.valor == d("27.00")
        assert r.fonte is Fonte.BASE_E_ALIQUOTA
        assert not r.fonte.e_documental, "reconstrução não é documento"

    def test_informado_vence_reconstrucao(self):
        r = apurar(EntradaParaApurar(cst_icms="060", retido_informado=d("4.75"),
                                     bc_st=d("150.00"), aliquota_interna=d("18")))
        assert r.fonte is Fonte.INFORMADO_PELO_FORNECEDOR

    def test_base_sem_aliquota_nao_reconstroi(self):
        """Meia informação não vira número: sem alíquota não há o que aplicar."""
        r = apurar(EntradaParaApurar(cst_icms="060", bc_st=d("150.00")))
        assert r.fonte is Fonte.NAO_APURAVEL


class TestMotivoDeNaoApurar:
    def test_cst_de_retencao_sem_destaque_acusa_a_nota(self):
        r = apurar(EntradaParaApurar(cst_icms="070"))
        assert r.fonte is Fonte.NAO_APURAVEL
        assert "deveria trazer" in r.motivo

    def test_cst_normal_nao_e_falta_de_dado(self):
        """CST 00 não tem imposto suportado a apurar, e isso não é defeito."""
        r = apurar(EntradaParaApurar(cst_icms="000", valor_icms=d("18.00")))
        assert r.fonte is Fonte.NAO_APURAVEL
        assert "não é de substituição" in r.motivo

    def test_item_sem_cst_diz_que_nem_da_para_classificar(self):
        r = apurar(EntradaParaApurar())
        assert "sem CST" in r.motivo


class TestCstComOrigem:
    @pytest.mark.parametrize("cst", ["060", "160", "260", "360", "460", "560",
                                     "760", "60"])
    def test_a_origem_nao_muda_a_tributacao(self, cst):
        """O primeiro dígito do CST é a origem da mercadoria, não a
        tributação. Ignorá-lo é o que faz 060 e 560 caírem na mesma regra."""
        r = apurar(EntradaParaApurar(cst_icms=cst))
        assert "CST 60" in r.motivo, cst


class TestResumo:
    def test_separa_o_que_tem_documento_do_que_foi_reconstruido(self):
        """O número que decide se a apuração pode ser entregue."""
        resumo = ResumoDaApuracao()
        resumo.somar(apurar(EntradaParaApurar(cst_icms="10", valor_icms=d("18"),
                                              valor_st=d("9"))))
        resumo.somar(apurar(EntradaParaApurar(cst_icms="60",
                                              retido_informado=d("10"))))
        resumo.somar(apurar(EntradaParaApurar(cst_icms="60", bc_st=d("100"),
                                              aliquota_interna=d("18"))))
        resumo.somar(apurar(EntradaParaApurar(cst_icms="60")))

        assert resumo.itens == 4
        assert resumo.itens_apurados == 3
        assert resumo.cobertura == 0.75
        assert resumo.valor_total == d("55.00")      # 27 + 10 + 18 + 0
        assert resumo.valor_documental == d("37.00")  # 27 + 10
        assert round(resumo.fracao_documental, 4) == round(37 / 55, 4)

    def test_resumo_vazio_nao_divide_por_zero(self):
        resumo = ResumoDaApuracao()
        assert resumo.cobertura == 0.0
        assert resumo.fracao_documental == 0.0

    def test_cada_fonte_e_contada_em_separado(self):
        resumo = ResumoDaApuracao()
        for _ in range(3):
            resumo.somar(apurar(EntradaParaApurar(cst_icms="60")))
        assert resumo.por_fonte[Fonte.NAO_APURAVEL] == 3
        assert resumo.por_fonte[Fonte.DOCUMENTO] == 0


class TestOrdemDasFontes:
    def test_a_ordem_e_de_prova_e_esta_no_valor_do_enum(self):
        """Fonte menor é fonte melhor, e é assim que se compara sem tabela."""
        assert Fonte.DOCUMENTO.value < Fonte.INFORMADO_PELO_FORNECEDOR.value
        assert Fonte.INFORMADO_PELO_FORNECEDOR.value < Fonte.BASE_E_ALIQUOTA.value
        assert Fonte.BASE_E_ALIQUOTA.value < Fonte.NAO_APURAVEL.value

    def test_so_as_duas_primeiras_sao_documentais(self):
        assert Fonte.DOCUMENTO.e_documental
        assert Fonte.INFORMADO_PELO_FORNECEDOR.e_documental
        assert not Fonte.BASE_E_ALIQUOTA.e_documental
        assert not Fonte.NAO_APURAVEL.e_documental

    def test_toda_fonte_tem_rotulo_para_a_tela(self):
        for f in Fonte:
            assert f.rotulo and not f.rotulo.startswith("Fonte.")

"""O enquadramento legal da saída, a partir do CFOP e do CST.

O que se protege aqui é a fronteira entre regra e suposição. O manual fixa
três casos; o CFOP resolve mais um; e o resto depende de quem comprou. Este
último grupo tem de sair como indefinido, porque ele é 98% do movimento de uma
base real e chutá-lo decidiria a apuração inteira sem base.
"""

import pytest

from cat.dominio.icms.cat42.enquadramento import (
    CFOP_DEVOLUCAO,
    CFOP_TRANSFERENCIA,
    VendaAConsumidor,
    classificar,
    consumidor_final_pelo_modelo,
    e_devolucao,
    e_interestadual,
    motivo_do_indefinido,
)
from cat.dominio.icms.cat42.razao import EnquadramentoLegal as E


class TestOQueOManualFixa:
    def test_baixa_de_estoque_e_fato_gerador_nao_realizado(self):
        """CFOP 5.927: perecimento, deterioração, roubo, furto, extravio."""
        assert classificar("5927") is E.FATO_GERADOR_NAO_REALIZADO
        assert classificar("5.927") is E.FATO_GERADOR_NAO_REALIZADO

    def test_saida_para_outro_estado_e_enquadramento_4(self):
        assert classificar("6102") is E.OUTRO_ESTADO
        assert classificar("6405") is E.OUTRO_ESTADO

    def test_exterior_tambem_sai_do_estado(self):
        assert classificar("7102") is E.OUTRO_ESTADO

    def test_isento_e_nao_tributado_caem_no_3(self):
        for cst in ("40", "041", "50"):
            assert classificar("5102", cst_icms=cst) is E.ISENCAO_OU_NAO_INCIDENCIA, cst

    def test_o_manual_vence_o_resto(self):
        """5.927 continua sendo enquadramento 2 mesmo com comprador conhecido."""
        assert classificar("5927", consumidor_final=True) is E.FATO_GERADOR_NAO_REALIZADO


class TestCst60NaoEIsento:
    def test_st_ja_retida_nao_vira_isencao(self):
        """É o caso do ressarcimento. Tratá-lo como isento jogaria a apuração
        inteira na coluna errada, e em silêncio."""
        assert classificar("5405", cst_icms="060",
                           consumidor_final=True) is E.CONSUMIDOR_FINAL
        assert classificar("5405", cst_icms="060") is None


class TestTransferencia:
    def test_transferencia_e_demais_saidas(self):
        """A mercadoria segue para revenda: não é saída a consumidor."""
        assert classificar("5152") is E.DEMAIS_SAIDAS
        assert classificar("5409") is E.DEMAIS_SAIDAS

    def test_transferencia_para_fora_do_estado_ainda_e_enquadramento_4(self):
        """O destino vence a natureza da operação."""
        assert classificar("6152") is E.OUTRO_ESTADO


class TestDependeDeQuemComprou:
    @pytest.mark.parametrize("cfop", ["5102", "5405", "5101", "5403"])
    def test_sem_saber_o_comprador_fica_indefinido(self, cfop):
        """São 98% do movimento de uma base real. Chutar aqui é decidir a
        apuração inteira sem base."""
        assert classificar(cfop) is None

    @pytest.mark.parametrize("cfop", ["5102", "5405"])
    def test_consumidor_final_cai_no_1(self, cfop):
        assert classificar(cfop, consumidor_final=True) is E.CONSUMIDOR_FINAL

    @pytest.mark.parametrize("cfop", ["5102", "5405"])
    def test_contribuinte_que_revende_cai_no_0(self, cfop):
        assert classificar(cfop, consumidor_final=False) is E.DEMAIS_SAIDAS

    def test_o_motivo_explica_o_que_falta(self):
        motivo = motivo_do_indefinido("5405")
        assert "5405" in motivo
        assert "consumidor final" in motivo
        assert "revende" in motivo


class TestModeloDoDocumento:
    """A informação que o CFOP não tem, e que não é suposição.

    NFC-e e CF-e SAT existem para documentar venda a consumidor final. Numa
    base real são 98,4% das linhas de saída, então é isto que tira a apuração
    do indefinido — sem chutar quem comprou.
    """

    @pytest.mark.parametrize("modelo", ["65", "59", "02", "2", "2D"])
    def test_modelo_de_consumidor_resolve_o_enquadramento(self, modelo):
        assert consumidor_final_pelo_modelo(modelo) is True
        assert classificar("5405", modelo=modelo) is E.CONSUMIDOR_FINAL

    def test_nfe_continua_indefinida(self):
        """O modelo 55 serve aos dois casos: dizer que é consumidor seria o
        chute que este módulo existe para evitar."""
        assert consumidor_final_pelo_modelo("55") is None
        assert classificar("5102", modelo="55") is None

    def test_o_zero_a_esquerda_nao_muda_o_modelo(self):
        assert consumidor_final_pelo_modelo("02") is consumidor_final_pelo_modelo("2")

    def test_quem_chama_pode_contrariar_o_modelo(self):
        """Se a fonte souber o comprador, ela manda: o modelo é o padrão,
        não a última palavra."""
        assert classificar("5102", modelo="65",
                           consumidor_final=False) is E.DEMAIS_SAIDAS

    def test_o_manual_ainda_vence_o_modelo(self):
        assert classificar("5927", modelo="65") is E.FATO_GERADOR_NAO_REALIZADO
        assert classificar("6102", modelo="65") is E.OUTRO_ESTADO


class TestVendaAConsumidorEEscolhaDoTrabalho:
    """O trabalho diz se pede o enquadramento 1. A empresa 17 transmitiu o cupom no 0:
    só a perda e a interestadual geram ressarcimento, e não há complemento."""

    O_ZERO = VendaAConsumidor.DEMAIS_SAIDAS

    def test_o_padrao_e_o_do_manual(self):
        assert classificar("5405", modelo="59") is E.CONSUMIDOR_FINAL
        assert VendaAConsumidor.de(None) is VendaAConsumidor.ENQUADRAMENTO_1
        assert VendaAConsumidor.de("") is VendaAConsumidor.ENQUADRAMENTO_1

    @pytest.mark.parametrize("modelo", ["59", "65", "02", "2D"])
    def test_cupom_vai_para_o_zero(self, modelo):
        assert classificar("5405", modelo=modelo, venda_a_consumidor=self.O_ZERO) is E.DEMAIS_SAIDAS

    def test_nfe_deixa_de_ser_indefinida(self):
        """Consumidor ou revendedor, os dois caem no 0: não há o que perguntar."""
        assert classificar("5102", modelo="55", venda_a_consumidor=self.O_ZERO) is E.DEMAIS_SAIDAS
        assert classificar("5102", modelo="55", consumidor_final=True,
                           venda_a_consumidor=self.O_ZERO) is E.DEMAIS_SAIDAS

    def test_o_que_o_manual_fixa_nao_muda(self):
        assert classificar("5927", modelo="55", venda_a_consumidor=self.O_ZERO) is E.FATO_GERADOR_NAO_REALIZADO
        assert classificar("6102", modelo="65", venda_a_consumidor=self.O_ZERO) is E.OUTRO_ESTADO
        assert classificar("5102", "040", venda_a_consumidor=self.O_ZERO) is E.ISENCAO_OU_NAO_INCIDENCIA

    def test_valor_desconhecido_e_recusado(self):
        with pytest.raises(ValueError):
            VendaAConsumidor.de("enquadramento_9")


class TestEntradaMalFormada:
    def test_sem_cfop_nao_enquadra(self):
        assert classificar("") is None
        assert classificar(None) is None
        assert "sem CFOP" in motivo_do_indefinido("")

    def test_o_ponto_do_cfop_nao_muda_nada(self):
        assert classificar("5.152") is classificar("5152")
        assert e_interestadual("6.102")


class TestDevolucao:
    def test_devolucao_e_do_razao_nao_do_enquadramento(self):
        """Devolução inverte o sinal da operação de origem. Virar enquadramento
        próprio duplicaria toda a regra de cálculo."""
        assert e_devolucao("1411")
        assert e_devolucao("5.411")
        assert not e_devolucao("5102")

    def test_nenhum_cfop_e_devolucao_e_transferencia_ao_mesmo_tempo(self):
        """Estar nos dois conjuntos faria a ordem das regras decidir o
        resultado, que é como se esconde um erro de classificação."""
        assert not (CFOP_DEVOLUCAO & CFOP_TRANSFERENCIA)


class TestQuemGeraRessarcimento:
    def test_so_o_zero_nunca_gera(self):
        assert not E.DEMAIS_SAIDAS.gera_ressarcimento
        for e in (E.CONSUMIDOR_FINAL, E.FATO_GERADOR_NAO_REALIZADO,
                  E.ISENCAO_OU_NAO_INCIDENCIA, E.OUTRO_ESTADO):
            assert e.gera_ressarcimento, e

    def test_o_confronto_muda_com_o_enquadramento(self):
        """1 e 3 confrontam com o ICMS da saída; 2 e 4 com o da entrada."""
        assert E.CONSUMIDOR_FINAL.confronta_com_saida
        assert E.ISENCAO_OU_NAO_INCIDENCIA.confronta_com_saida
        assert not E.FATO_GERADOR_NAO_REALIZADO.confronta_com_saida
        assert not E.OUTRO_ESTADO.confronta_com_saida

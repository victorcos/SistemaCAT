"""O domínio do histórico, na parte que o motor usa: o status barra etapa.

Comentário, frases e a exigência de motivo foram com a tela para a API em C#
(api/tests/Cat.Dominio.Testes/HistoricoTestes.cs).
"""

from cat.dominio.projeto.historico import StatusDoProjeto


class TestStatus:
    def test_os_quatro_que_existem(self):
        assert [s.value for s in StatusDoProjeto] == [
            "em_andamento", "pausado", "cancelado", "concluido",
        ]

    def test_trabalho_parado_nao_roda_etapa(self):
        # pausar precisa significar alguma coisa: sem isto seria só uma cor
        assert not StatusDoProjeto.PAUSADO.aceita_processamento
        assert not StatusDoProjeto.CANCELADO.aceita_processamento

    def test_trabalho_que_anda_e_o_entregue_rodam(self):
        # concluído roda porque refazer uma conferência depois da entrega é
        # exatamente o que se faz quando o cliente questiona um número
        assert StatusDoProjeto.EM_ANDAMENTO.aceita_processamento
        assert StatusDoProjeto.CONCLUIDO.aceita_processamento

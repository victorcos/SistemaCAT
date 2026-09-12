"""O domínio do histórico: status, comentário e as frases.

Sem banco e sem API — é regra, e regra tem de caber num teste que roda em
milissegundos.
"""

import pytest

from cat.dominio.projeto.historico import (
    TAMANHO_MAXIMO_DO_COMENTARIO,
    ComentarioLongoDemais,
    ComentarioVazio,
    StatusDoProjeto,
    TipoDeEvento,
    frase_de_status,
    frase_de_sucessao,
    validar_comentario,
)


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

    def test_parar_e_cancelar_exigem_motivo(self):
        assert StatusDoProjeto.PAUSADO.exige_motivo
        assert StatusDoProjeto.CANCELADO.exige_motivo
        assert not StatusDoProjeto.EM_ANDAMENTO.exige_motivo
        assert not StatusDoProjeto.CONCLUIDO.exige_motivo

    def test_todo_status_tem_rotulo_e_explicacao(self):
        for s in StatusDoProjeto:
            assert s.rotulo and s.rotulo[0].isupper()
            assert s.explicacao.endswith(".")


class TestComentario:
    def test_apara_espaco(self):
        assert validar_comentario("  falei com o cliente  ") == "falei com o cliente"

    def test_vazio_nao_entra(self):
        with pytest.raises(ComentarioVazio):
            validar_comentario("   \n  ")

    def test_longo_demais_nao_entra(self):
        with pytest.raises(ComentarioLongoDemais):
            validar_comentario("a" * (TAMANHO_MAXIMO_DO_COMENTARIO + 1))

    def test_no_limite_entra(self):
        texto = "a" * TAMANHO_MAXIMO_DO_COMENTARIO
        assert validar_comentario(texto) == texto


class TestTipos:
    def test_so_o_comentario_e_da_pessoa(self):
        do_sistema = [t for t in TipoDeEvento if t.e_do_sistema]
        assert TipoDeEvento.COMENTARIO not in do_sistema
        assert len(do_sistema) == len(list(TipoDeEvento)) - 1


class TestFrases:
    def test_status(self):
        assert frase_de_status(
            StatusDoProjeto.EM_ANDAMENTO, StatusDoProjeto.PAUSADO
        ) == "Em andamento → Pausado"

    def test_sucessao_com_e_sem_anterior(self):
        assert frase_de_sucessao("Ana", "Bruno") == "Ana → Bruno"
        assert frase_de_sucessao(None, "Bruno") == "Responsável definido: Bruno"

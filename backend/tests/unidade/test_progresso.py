"""O andamento do que roda dentro de uma requisição.

Medido em 14/10/2026: montar a Consulta de Entradas em xlsx levou 35 minutos,
materializar o resumo do razão contábil 149 segundos, os filtros da 047 113
segundos. Em todos, a tela mostrava um girador e nada mais — e já houve quem
concluísse que tinha travado e clicasse de novo, dobrando o trabalho do
servidor.

O que estes testes guardam é o que faz esse contador ser barato e honesto:
sem chave ele não existe, o laço não paga trava por linha, e o que a tela lê
nunca passa de 100%.
"""

from __future__ import annotations

import time

import pytest

from cat.aplicacao import progresso


@pytest.fixture(autouse=True)
def registro_limpo():
    progresso._registro.clear()
    yield
    progresso._registro.clear()


class TestSemChaveNaoCusta:
    """Nenhuma operação precisa saber se alguém está olhando."""

    def test_relator_mudo_aceita_tudo_e_nao_registra_nada(self):
        with progresso.relatando(None) as r:
            r.passo("Montando", 1000)
            for _ in range(10_000):
                r.avancar()
        assert progresso._registro == {}
        assert not r.ligado

    def test_fora_de_um_bloco_o_atual_e_mudo(self):
        assert not progresso.atual().ligado
        progresso.atual().avancar(5)          # não pode estourar


class TestOQueATelaLe:
    def test_a_fracao_sai_do_feito_sobre_o_total(self):
        with progresso.relatando("k1") as r:
            r.passo("Montando a planilha", 200)
            r.avancar(50)
            r._publicar(agora=True)
            lido = progresso.ler("k1")
            assert (lido.passo, lido.feito, lido.total) == ("Montando a planilha", 50, 200)
            assert lido.fracao == 0.25

    def test_passo_sem_total_nao_inventa_porcentagem(self):
        """Compactar o zip não tem contagem — e fingir uma seria pior que não ter."""
        with progresso.relatando("k2") as r:
            r.passo("Compactando o arquivo")
            assert progresso.ler("k2").fracao == 0.0
            assert progresso.ler("k2").passo == "Compactando o arquivo"

    def test_passar_do_total_nao_passa_de_cem_por_cento(self):
        """Com filtro, o total é um teto: a barra chega ao fim antes, nunca além."""
        with progresso.relatando("k3") as r:
            r.passo("Montando", 10)
            r.avancar(50)
            r._publicar(agora=True)
            assert progresso.ler("k3").fracao == 1.0

    def test_ao_sair_do_bloco_fica_terminado(self):
        """A tela que perguntar depois do fim vê 100%, e não um número parado."""
        with progresso.relatando("k4") as r:
            r.passo("Montando", 1000)
            r.avancar(3)
        lido = progresso.ler("k4")
        assert lido.terminado and lido.fracao == 1.0

    def test_termina_mesmo_quando_a_operacao_estoura(self):
        with pytest.raises(RuntimeError):
            with progresso.relatando("k5") as r:
                r.passo("Montando", 10)
                raise RuntimeError("acabou o disco")
        assert progresso.ler("k5").terminado


class TestOLacoNaoPagaPorIsso:
    def test_avancar_nao_publica_a_cada_linha(self, monkeypatch):
        """Um laço de 4,7 milhões de linhas não aguenta uma trava por linha."""
        publicadas = []
        monkeypatch.setattr(progresso, "INTERVALO_DE_PUBLICACAO", 10.0)
        with progresso.relatando("k6") as r:
            r.passo("Montando", 1_000)
            antes = progresso.ler("k6").feito
            for _ in range(1_000):
                r.avancar()
            publicadas.append(progresso.ler("k6").feito)
        # o passo publicou na hora; as mil chamadas seguintes, nenhuma
        assert antes == 0 and publicadas == [0]

    def test_mas_publica_quando_o_intervalo_passa(self, monkeypatch):
        monkeypatch.setattr(progresso, "INTERVALO_DE_PUBLICACAO", 0.0)
        with progresso.relatando("k7") as r:
            r.passo("Montando", 10)
            r.avancar()
            assert progresso.ler("k7").feito == 1


class TestChaveQueNaoExiste:
    def test_perguntar_por_chave_desconhecida_devolve_nada(self):
        assert progresso.ler("nunca-existiu") is None

    def test_andamento_vencido_some(self, monkeypatch):
        with progresso.relatando("k8") as r:
            r.passo("Montando", 10)
        monkeypatch.setattr(progresso, "VALIDADE", -1.0)
        assert progresso.ler("k8") is None

    def test_a_limpeza_tira_os_vencidos_do_registro(self, monkeypatch):
        with progresso.relatando("velho") as r:
            r.passo("Montando", 10)
        progresso._registro["velho"].atualizado_em = time.monotonic() - 10_000
        with progresso.relatando("novo"):
            pass
        assert "velho" not in progresso._registro

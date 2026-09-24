"""O trabalhador da fila fora do motor.

Nasceu de uma rodada perdida: a Gestão de 65 arquivos morreu no quarto porque
alguém salvou um `.py` e o `--reload` derrubou o motor — e com ele a fila, que
era uma thread lá dentro. O laço precisa rodar em processo próprio e parar
quando mandarem, sem depender de quem atende as telas.
"""

from __future__ import annotations

import pytest

from workers import fila


@pytest.fixture(autouse=True)
def fila_limpa():
    fila.parar()
    yield
    fila.parar()


def test_recupera_o_que_ficou_rodando_antes_de_pegar_a_fila(monkeypatch):
    """Linha 'rodando' quando o trabalhador sobe é rodada que alguém matou."""
    ordem: list[str] = []
    monkeypatch.setattr(fila, "recuperar_interrompidas", lambda: ordem.append("recuperou"))
    monkeypatch.setattr(fila, "processar_uma", lambda: (ordem.append("olhou"), fila.parar())[0])

    fila.rodar_ate_parar()

    assert ordem[:2] == ["recuperou", "olhou"]


def test_para_quando_pedem_e_nao_fica_girando(monkeypatch):
    voltas = {"n": 0}

    def uma():
        voltas["n"] += 1
        if voltas["n"] >= 3:
            fila.parar()
        return None

    monkeypatch.setattr(fila, "recuperar_interrompidas", lambda: None)
    monkeypatch.setattr(fila, "processar_uma", uma)
    monkeypatch.setattr(fila, "SEGUNDOS_ENTRE_OLHADAS", 0.01)

    fila.rodar_ate_parar()

    assert voltas["n"] == 3


def test_erro_ao_olhar_a_fila_nao_mata_o_trabalhador(monkeypatch):
    """Banco fora do ar por um instante não pode derrubar quem roda a fila."""
    tentativas = {"n": 0}

    def uma():
        tentativas["n"] += 1
        if tentativas["n"] == 1:
            raise RuntimeError("banco fora do ar")
        fila.parar()
        return None

    monkeypatch.setattr(fila, "recuperar_interrompidas", lambda: None)
    monkeypatch.setattr(fila, "processar_uma", uma)
    monkeypatch.setattr(fila, "SEGUNDOS_ENTRE_OLHADAS", 0.01)

    fila.rodar_ate_parar()

    assert tentativas["n"] == 2

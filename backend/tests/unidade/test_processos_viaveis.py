"""Quando um processo novo consegue nascer do atual.

O caso que importa é o do motor: o servidor do uvicorn nasce de um `spawn`, com
um `__main__` sem arquivo, e é de dentro dele que a fila abre a rodada e a
etapa 7 abre os processos dos arquivos. Os alvos moram aqui, no nível de cima,
porque o processo novo os reimporta pelo nome.
"""

from __future__ import annotations

import multiprocessing
import sys
import types
from concurrent.futures import ProcessPoolExecutor

from cat.infraestrutura.analitico.arquivo_digital import _processos_viaveis


def dobrar(n: int) -> int:
    return 2 * n


def no_filho(fila) -> None:
    """Como o servidor do motor: um processo nascido de spawn, que abre outros."""
    viavel = _processos_viaveis()
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
        fila.put((viavel, pool.submit(dobrar, 21).result()))


class TestComoOMainNasce:
    def _com_main(self, monkeypatch, **atributos):
        principal = types.ModuleType("__main__")
        for nome, valor in atributos.items():
            setattr(principal, nome, valor)
        monkeypatch.setitem(sys.modules, "__main__", principal)

    def test_sem_arquivo_nem_nome_e_viavel(self, monkeypatch):
        self._com_main(monkeypatch, __spec__=None)
        assert _processos_viaveis()

    def test_script_da_entrada_padrao_nao_e(self, monkeypatch):
        self._com_main(monkeypatch, __spec__=None, __file__="<stdin>")
        assert not _processos_viaveis()

    def test_script_de_arquivo_e(self, monkeypatch):
        self._com_main(monkeypatch, __spec__=None, __file__=__file__)
        assert _processos_viaveis()


class TestComoNoMotor:
    def test_processo_nascido_de_spawn_abre_outros(self):
        contexto = multiprocessing.get_context("spawn")
        fila = contexto.Queue()
        filho = contexto.Process(target=no_filho, args=(fila,))
        filho.start()
        resultado = fila.get(timeout=120)
        filho.join(60)
        assert resultado == (True, 42)
        assert filho.exitcode == 0

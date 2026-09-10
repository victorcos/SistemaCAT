"""Fila de trabalho pesado, dentro do próprio processo da API.

A arquitetura prevê Celery para isto, e é para lá que vai quando o sistema
deixar de rodar na máquina de quem trabalha. Enquanto roda local, Celery
exigiria subir Redis ou RabbitMQ só para enfileirar uma tarefa por vez — mais
peça para instalar, para manter e para quebrar do que o problema pede.

O que **não** muda com a troca: a tarefa já não vive na requisição, cada rodada
já é linha na tabela `execucao`, e o front já acompanha por identificador. O
dia da migração troca este arquivo e mais nada.

Uma linha de execução por vez, de propósito. Duas extrações simultâneas
disputariam a mesma rede e o mesmo disco e terminariam as duas mais devagar do
que uma depois da outra.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from cat.log import obter_log

log = obter_log(__name__)

_fila = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cat-tarefa")


def disparar(funcao: Callable[..., None], *args, **kwargs) -> Future:
    """Põe a tarefa na fila e volta na hora."""
    futuro = _fila.submit(funcao, *args, **kwargs)
    futuro.add_done_callback(_registrar_falha)
    log.info("tarefa enfileirada",
             extra={"tarefa": funcao.__name__, "argumentos": [str(a) for a in args]})
    return futuro


def _registrar_falha(futuro: Future) -> None:
    """A tarefa já grava o próprio erro; isto é a rede de segurança.

    Sem este retorno de chamada, uma exceção que escapasse da tarefa ficaria
    guardada dentro do Future e ninguém veria — o pior tipo de falha, a que não
    aparece em lugar nenhum.
    """
    erro = futuro.exception()
    if erro is not None:
        log.exception("tarefa terminou em exceção não tratada",
                      exc_info=erro)


def encerrar(esperar: bool = False) -> None:
    _fila.shutdown(wait=esperar, cancel_futures=not esperar)

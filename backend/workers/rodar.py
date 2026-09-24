"""O trabalhador da fila, em processo próprio.

Existe por uma rodada perdida. Em 23/09/2026 a Gestão Fiscal de 65 arquivos
morreu no quarto, com "Interrompida: o motor reiniciou durante a rodada" — e a
mensagem dizia a verdade: o motor de desenvolvimento roda com `--reload`, a
fila era uma thread dentro dele, e salvar um `.py` derruba o processo. Com duas
pessoas mexendo no código, isso acontece dezenas de vezes por dia; uma apuração
de uma hora nunca chegava ao fim.

Aqui a fila não recarrega. O motor atende as telas e reinicia à vontade; quem
roda a apuração é este processo, que só para quando alguém o para.

Para valer, **o motor precisa subir com `CAT_FILA_AUTOMATICA=false`**. Senão
são dois trabalhadores no mesmo banco: o `SKIP LOCKED` impede que peguem a
mesma execução, mas o que reiniciar marcará como interrompida a rodada que o
outro está tocando. `scripts/subir.ps1` já sobe assim.

    python -m workers.rodar
"""

from __future__ import annotations

import os
import signal
import sys

from cat.config import obter_config
from cat.log import configurar, obter_log
from workers import fila

log = obter_log(__name__)


def principal() -> int:
    configurar(obter_config().log_nivel)

    def sair(*_: object) -> None:
        log.info("trabalhador da fila recebeu pedido de parada")
        fila.parar()

    # Ctrl+C na janela, e o encerramento que o sistema pede ao desligar
    for numero in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(numero, sair)
        except (ValueError, OSError):  # sinal que este sistema não entrega
            log.debug("sinal não registrado neste sistema", extra={"sinal": numero})

    cfg = obter_config()
    log.info("trabalhador da fila em processo próprio", extra={
        "pid": os.getpid(), "rodadas_em_processo": cfg.rodadas_em_processo,
        "fila_automatica_no_motor": cfg.fila_automatica,
    })
    if cfg.fila_automatica:
        # não dá para impedir daqui, mas dá para deixar escrito no log de quem
        # for investigar por que uma rodada virou "interrompida" sozinha
        log.warning("o motor também está configurado para rodar a fila; "
                    "suba o motor com CAT_FILA_AUTOMATICA=false")

    fila.rodar_ate_parar()
    log.info("trabalhador da fila encerrado")
    return 0


if __name__ == "__main__":
    sys.exit(principal())

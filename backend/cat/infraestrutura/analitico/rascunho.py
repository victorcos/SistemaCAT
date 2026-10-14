"""O arquivo provisório: escrever ao lado e só então ocupar o nome final.

Materializar um resumo custa minutos, e quem lê o arquivo pronto não pode
encontrar um pela metade. A saída é escrever num nome provisório e renomear no
fim — `os.replace` é atômico dentro do mesmo volume, então ou o nome final tem
o arquivo inteiro ou não tem nada.

## O nome provisório não pode ser o PID

Era assim até 14/10/2026. O motor atende vários pedidos **no mesmo processo**:
duas pessoas abrindo a mesma tela ao mesmo tempo escolhiam o mesmo nome, o
DuckDB recusava gravar num arquivo que já estava aberto, e o segundo pedido
morria com 500 — sem mensagem que ajudasse ninguém:

    IOException: Cannot open file "...razao_por_conta.parquet.33192.parcial":
    O arquivo já está sendo usado por outro processo.
    PermissionError: [WinError 5] Acesso negado

Aconteceu três vezes em um minuto na empresa 24, em 14/10/2026. Um
identificador por **chamada** não colide, que é a única coisa que o PID tentava
ser.

## Apagar é sempre tolerante

Rascunho que não dá para remover é lixo, não defeito. Deixar a remoção
estourar troca um problema pequeno — um arquivo a mais em disco — por um
grande: a falha de limpeza escondendo a falha de verdade, como aconteceu acima,
onde o `PermissionError` da limpeza apagou do log o erro que o causou.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from cat.log import obter_log

log = obter_log(__name__)


def apagar(caminho: str) -> None:
    """Remove o arquivo se der, e nunca estraga o motivo real da falha."""
    with contextlib.suppress(OSError):
        os.remove(caminho)


def nome_provisorio(caminho: str) -> str:
    """Um nome ao lado do final, exclusivo desta chamada.

    Para quem não cabe no `materializando` — corpo longo, mais de um arquivo
    aberto, limpeza que também precisa fechar um escritor.
    """
    return f"{caminho}.{uuid4().hex}.parcial"


@contextmanager
def materializando(caminho: str) -> Iterator[str]:
    """Empresta um nome provisório e só o promove a `caminho` se tudo correr bem.

    Quem usa escreve no nome que recebe e fecha o que abriu **dentro** do bloco:
    no Windows não se renomeia arquivo com handle aberto, e o `os.replace` daqui
    acontece depois do `finally` de quem chamou.
    """
    provisorio = f"{caminho}.{uuid4().hex}.parcial"
    try:
        yield provisorio
    except BaseException:
        apagar(provisorio)
        raise
    os.replace(provisorio, caminho)

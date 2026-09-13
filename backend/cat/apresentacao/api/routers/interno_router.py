"""Canal interno com a API em C#. Não é rota de gente.

A API em C# decide se a pessoa pode; o motor faz o que é de disco. Este canal
existe para isso (docs/MIGRACAO_CSHARP.md §4) e tem três portas fechadas:

1. o motor só escuta em 127.0.0.1 (scripts/subir.ps1);
2. o repasse público do C# leva só /api, /docs e /openapi.json — /interno nunca
   chega aqui vindo da tela;
3. toda chamada traz o segredo compartilhado CAT_MOTOR_SEGREDO. Sem ele
   configurado, o canal fica fechado para todo mundo, em vez de aberto.

**Apagar pasta só dentro da pasta de trabalho.** O Python apagava o caminho que
estivesse gravado na execução, sem conferir. Um valor torto no banco — ou uma
pasta de trabalho trocada no .env — mandava apagar outra coisa. Agora o que está
fora da raiz é recusado e volta dito, e a própria raiz também.
"""

from __future__ import annotations

import hmac
import os
import shutil
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from cat.config import obter_config
from cat.log import obter_log

log = obter_log(__name__)
router = APIRouter(prefix="/interno", tags=["interno"], include_in_schema=False)


def exigir_segredo(
    x_cat_motor_segredo: Annotated[str | None, Header()] = None,
) -> None:
    esperado = obter_config().motor_segredo
    if not esperado:
        log.error("canal interno chamado sem CAT_MOTOR_SEGREDO configurado no motor",
                  extra={"acao": "definir CAT_MOTOR_SEGREDO"})
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "CAT_MOTOR_SEGREDO não está definido no motor.")
    if not x_cat_motor_segredo or not hmac.compare_digest(
        x_cat_motor_segredo.encode(), esperado.encode()
    ):
        log.warning("canal interno recusou chamada sem o segredo certo")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Segredo do canal interno não confere.")


class PedidoApagarPastas(BaseModel):
    pastas: list[str]


class PastasApagadas(BaseModel):
    apagadas: list[str]
    recusadas: list[str]


def _dentro_da_raiz(pasta: str, raiz: str) -> bool:
    alvo = os.path.realpath(pasta)
    try:
        # commonpath recusa caminhos em unidades diferentes no Windows
        return alvo != raiz and os.path.commonpath([raiz, alvo]) == raiz
    except ValueError:
        return False


@router.post("/pastas/apagar", response_model=PastasApagadas,
             dependencies=[Depends(exigir_segredo)])
def apagar_pastas(pedido: PedidoApagarPastas) -> PastasApagadas:
    raiz = os.path.realpath(obter_config().raiz_de_trabalho)
    apagadas: list[str] = []
    recusadas: list[str] = []
    for pasta in pedido.pastas:
        if not pasta or not _dentro_da_raiz(pasta, raiz):
            recusadas.append(pasta)
            continue
        shutil.rmtree(os.path.realpath(pasta), ignore_errors=True)
        apagadas.append(pasta)

    (log.warning if recusadas else log.info)(
        "pastas de trabalho apagadas a pedido da API",
        extra={"apagadas": len(apagadas), "recusadas": recusadas, "raiz": raiz},
    )
    return PastasApagadas(apagadas=apagadas, recusadas=recusadas)

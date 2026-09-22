"""O motor: FastAPI só com o canal interno.

A tela fala com a API em C# (api/), e a API fala com o motor por
127.0.0.1 com o segredo CAT_MOTOR_SEGREDO (routers/interno_router.py). Desde a
fatia 7 (docs/MIGRACAO_CSHARP.md) não há rota pública aqui, nem documentação
interativa: quem descreve a API é o C#.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cat.config import obter_config
from cat.versao import versao
from cat.infraestrutura.repositorios.banco import conferir_migracoes
from cat.log import configurar, contexto, obter_log

log = obter_log(__name__)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    cfg = obter_config()
    configurar(cfg.log_nivel)
    conferir_migracoes()
    if not cfg.motor_segredo:
        log.error(
            "CAT_MOTOR_SEGREDO não definido. O canal interno fica fechado e a "
            "API em C# não consegue pedir nada ao motor.",
            extra={"acao": "definir CAT_MOTOR_SEGREDO"},
        )
    # A pasta de trabalho vai no log de subida de propósito. Um servidor
    # antigo sobreviveu a um reinício e continuou servindo com a configuração
    # velha, e a única pista era uma execução gravando no disco errado. Se o
    # processo diz onde vai escrever no momento em que sobe, isso se pega
    # na hora — e não depois de encher um disco.
    log.info("motor no ar", extra={"banco": cfg.banco_url.split("://")[0],
                                   "versao": versao(),
                                   "pasta_de_trabalho": cfg.raiz_de_trabalho,
                                 "memoria_analitica": cfg.memoria_analitica,
                                 "threads_analiticas": cfg.threads_analiticas})
    if cfg.fila_automatica:
        from workers import fila  # noqa: PLC0415
        fila.iniciar_em_segundo_plano()
    yield
    if cfg.fila_automatica:
        fila.parar()
    log.info("motor encerrado")


app = FastAPI(
    title="CRM Fiscal — motor",
    # de uma fonte só: o arquivo VERSAO na raiz. Escrita à mão aqui, parou em
    # 0.3.0 enquanto as etiquetas do git iam a v0.15.2 — e a saúde mentia.
    version=versao(),
    lifespan=ciclo_de_vida,
    # sem /docs, /redoc e /openapi.json: nada aqui é para ser descoberto
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def registrar_requisicao(request: Request, chamar):
    """Toda requisição carrega um identificador. Sem isso não dá para juntar as
    linhas de log de um mesmo pedido quando há concorrência."""
    req_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
    inicio = time.perf_counter()

    with contexto(requisicao_id=req_id, rota=request.url.path,
                  metodo=request.method):
        try:
            resposta = await chamar(request)
        except Exception:
            log.exception(
                "falha não tratada",
                extra={"ms": round((time.perf_counter() - inicio) * 1000, 1)},
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Erro interno.", "requisicao_id": req_id},
                headers={"X-Request-Id": req_id},
            )

        ms = round((time.perf_counter() - inicio) * 1000, 1)
        # 4xx e 5xx merecem atenção; 2xx é rotina
        (log.warning if resposta.status_code >= 400 else log.info)(
            "requisição atendida",
            extra={"status": resposta.status_code, "ms": ms},
        )
        resposta.headers["X-Request-Id"] = req_id
        return resposta


from cat.apresentacao.api.routers import interno_router  # noqa: E402

# Toda rota pública mora na API em C# desde 13/09/2026, e os comandos semear e
# emergencia em api/src/Cat.Ferramentas. O que lê ou escreve disco chega aqui
# pelo canal interno; a fila de execuções roda em workers/fila.py.
app.include_router(interno_router.router)

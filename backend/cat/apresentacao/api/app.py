"""Aplicação FastAPI."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cat.config import obter_config
from cat.infraestrutura.repositorios.banco import conferir_migracoes
from cat.log import configurar, contexto, obter_log

log = obter_log(__name__)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    cfg = obter_config()
    configurar(cfg.log_nivel)
    conferir_migracoes()
    if cfg.segredo_e_padrao:
        log.error(
            "CAT_JWT_SEGREDO está com o valor padrão. Qualquer um pode forjar "
            "um token. Definir a variável antes de expor o serviço.",
            extra={"acao": "definir CAT_JWT_SEGREDO"},
        )
    if cfg.sem_pimenta:
        log.warning(
            "CAT_SENHA_PIMENTA não definida. As senhas seguem protegidas por "
            "Argon2id com sal, mas um vazamento do banco não teria a barreira "
            "extra do segredo de servidor.",
            extra={"acao": "definir CAT_SENHA_PIMENTA"},
        )
    log.info("API no ar", extra={"banco": cfg.banco_url.split("://")[0],
                                 "origens": cfg.lista_origens})
    yield
    log.info("API encerrada")


app = FastAPI(
    title="Sistema CAT",
    description="Apuração das obrigações da CAT. BMS Consultoria Tributária.",
    version="0.3.0",
    lifespan=ciclo_de_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=obter_config().lista_origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/api/saude", tags=["infra"])
def saude() -> dict[str, str]:
    return {"status": "ok", "versao": app.version}


from cat.apresentacao.api.routers import (  # noqa: E402
    auth_router, importacao_router, lote_router, usuarios_router,
)

app.include_router(auth_router.router)
app.include_router(usuarios_router.router)
app.include_router(importacao_router.router)
app.include_router(lote_router.router)

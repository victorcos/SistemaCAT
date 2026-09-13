"""Aplicação FastAPI."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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
    # A pasta de trabalho vai no log de subida de propósito. Um servidor
    # antigo sobreviveu a um reinício e continuou servindo com a configuração
    # velha, e a única pista era uma execução gravando no disco errado. Se o
    # processo diz onde vai escrever no momento em que sobe, isso se pega
    # na hora — e não depois de encher um disco.
    log.info("API no ar", extra={"banco": cfg.banco_url.split("://")[0],
                                 "origens": cfg.lista_origens,
                                 "pasta_de_trabalho": cfg.raiz_de_trabalho,
                                 "memoria_analitica": cfg.memoria_analitica,
                                 "threads_analiticas": cfg.threads_analiticas})
    yield
    log.info("API encerrada")


app = FastAPI(
    title="Sistema CAT",
    description="Apuração das obrigações da CAT. BMS Consultoria Tributária.",
    # de uma fonte só: o pyproject.toml. Escrita à mão aqui, parou em 0.3.0
    # enquanto as etiquetas do git iam a v0.15.2 — e /api/saude mentia.
    version=versao(),
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
def saude() -> dict[str, object]:
    """Vivo, e com QUAL configuração — só o que não é segredo.

    Serve para conferir de fora o que o processo que responde realmente
    enxerga. Sem isso, um servidor antigo que sobreviveu a um reinício é
    indistinguível do novo: os dois respondem "ok".
    """
    cfg = obter_config()
    return {
        "status": "ok",
        "versao": app.version,
        "pasta_de_trabalho": cfg.raiz_de_trabalho,
        "memoria_analitica": cfg.memoria_analitica,
        "threads_analiticas": cfg.threads_analiticas,
    }


from cat.apresentacao.api.routers import (  # noqa: E402
    conferencia_router, importacao_router, interno_router, lote_router,
    movimentos_router,
)

# O login (/api/auth), a gestão de usuários (/api/usuarios), empresas, frentes,
# projetos, a exclusão de trabalho e o histórico (linha do tempo, comentário,
# status e sucessão) moram na API em C# desde 13/09/2026; os
# comandos semear e emergencia em api/src/Cat.Ferramentas. O motor atende o
# que lê disco e o canal interno com a API.
app.include_router(interno_router.router)
# O motor só valida o token nas rotas que ainda atende (seguranca.py).
app.include_router(importacao_router.router)
app.include_router(lote_router.router)
app.include_router(conferencia_router.router)
app.include_router(movimentos_router.router)

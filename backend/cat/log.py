"""Log estruturado — obrigatório em todo o sistema.

Ver docs/ARQUITETURA.md seção 12. A regra é do dono do produto: código sem log
não entra. Este módulo existe para que ninguém tenha desculpa de "dava trabalho".

Cada linha sai como um JSON, com o contexto que localiza o problema sem precisar
reproduzir: execução, projeto, empresa, usuário e etapa.

Uso:

    from cat.log import obter_log, contexto

    log = obter_log(__name__)

    with contexto(execucao_id="e-42", empresa="50948371000178", etapa="leitura"):
        log.info("arquivo aberto", extra={"arquivo": nome, "bytes": tamanho})
"""

from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator

# contexto que acompanha a linha de log sem precisar ser passado de função em função
_CONTEXTO: ContextVar[dict[str, Any]] = ContextVar("contexto_log", default={})

# campos que o LogRecord já traz e não devem ser repetidos no JSON
_RESERVADOS = frozenset(
    """args asctime created exc_info exc_text filename funcName levelname levelno
    lineno module msecs message msg name pathname process processName
    relativeCreated stack_info thread threadName taskName""".split()
)

# nunca escrever isto em log, mesmo que venha no extra
_SEGREDOS = frozenset(
    {"senha", "password", "token", "access_token", "secret", "authorization",
     "hashed_password", "chave", "api_key"}
)


def _limpar(valor: Any) -> Any:
    """Remove segredo de dicionário aninhado, preservando o resto."""
    if isinstance(valor, dict):
        return {
            k: ("***" if k.lower() in _SEGREDOS else _limpar(v))
            for k, v in valor.items()
        }
    if isinstance(valor, (list, tuple)):
        return [_limpar(v) for v in valor]
    return valor


class FormatadorJson(logging.Formatter):
    """Uma linha, um JSON. Log que só humano lê não se consulta depois."""

    def format(self, record: logging.LogRecord) -> str:
        linha: dict[str, Any] = {
            "instante": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "nivel": record.levelname,
            "origem": record.name,
            "mensagem": record.getMessage(),
        }

        ctx = _CONTEXTO.get()
        if ctx:
            linha.update(_limpar(ctx))

        for chave, valor in record.__dict__.items():
            if chave in _RESERVADOS or chave.startswith("_"):
                continue
            linha[chave] = "***" if chave.lower() in _SEGREDOS else _limpar(valor)

        if record.exc_info:
            linha["excecao"] = self.formatException(record.exc_info)

        # local exato, para não caçar a origem depois
        linha["local"] = f"{record.pathname}:{record.lineno}"

        return json.dumps(linha, ensure_ascii=False, default=str)


def configurar(nivel: str = "INFO") -> None:
    """Liga o log estruturado. Chamar uma vez, na subida da aplicação."""
    raiz = logging.getLogger()
    raiz.handlers.clear()

    saida = logging.StreamHandler(sys.stdout)
    saida.setFormatter(FormatadorJson())
    raiz.addHandler(saida)
    raiz.setLevel(nivel.upper())

    # o uvicorn duplica linha se mantiver os handlers dele
    for nome in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        aux = logging.getLogger(nome)
        aux.handlers.clear()
        aux.propagate = True


def obter_log(nome: str) -> logging.Logger:
    return logging.getLogger(nome)


@contextmanager
def contexto(**campos: Any) -> Iterator[None]:
    """Acrescenta campos a todo log emitido dentro do bloco.

    Aninhável: o contexto de dentro soma ao de fora, não substitui.
    """
    anterior = _CONTEXTO.get()
    token = _CONTEXTO.set({**anterior, **campos})
    try:
        yield
    finally:
        _CONTEXTO.reset(token)


def contexto_atual() -> dict[str, Any]:
    return dict(_CONTEXTO.get())

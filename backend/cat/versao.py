"""A versão do sistema, de uma fonte só.

Estava escrita à mão em dois lugares — `app.py` e `pyproject.toml` — e os dois
pararam em 0.3.0 enquanto as etiquetas do git chegavam a v0.15.2. A saúde dizia
uma coisa e o repositório outra, e o endpoint que existe para dizer *o que está
rodando* passou a mentir.

Fonte única, desde a fatia 7: o arquivo `VERSAO` na raiz do repositório, lido
também pela API em C#. São dois programas e um número. A etiqueta do git repete
esse número (regra em `docs/VERSIONAMENTO.md`), e um teste falha quando a
etiqueta está à frente do arquivo — que é exatamente como o drift aconteceu.

O `version` do `pyproject.toml` não é lido: o setuptools não aceita buscar o
número num arquivo fora de `backend/`, e duas cópias do número é o defeito que
este módulo existe para evitar.

Sem o arquivo, ou com algo que não é um número de versão nele, a resposta é
`0.0.0+desconhecida`, com aviso no log. Versão nunca derruba o motor.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from cat.log import obter_log

log = obter_log(__name__)

DESCONHECIDA = "0.0.0+desconhecida"

# cat/versao.py -> cat/ -> backend/ -> raiz do repositório
ARQUIVO = Path(__file__).resolve().parents[2] / "VERSAO"

_NUMERO = re.compile(r"\A\s*(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\s*\Z")


@lru_cache
def versao() -> str:
    return ler(ARQUIVO)


def ler(arquivo: Path) -> str:
    try:
        # utf-8-sig: o Bloco de Notas grava o arquivo com BOM
        achado = _NUMERO.match(arquivo.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as erro:
        log.warning("não deu para ler o arquivo VERSAO",
                    extra={"arquivo": str(arquivo), "motivo": str(erro)})
        return DESCONHECIDA
    if achado is None:
        log.warning("o arquivo VERSAO não traz um número de versão",
                    extra={"arquivo": str(arquivo)})
        return DESCONHECIDA
    return achado.group(1)


def como_tupla(texto: str) -> tuple[int, ...]:
    """`0.15.2` -> (0, 15, 2). Ignora o que vier depois de `+` ou `-`."""
    base = texto.lstrip("v").split("+")[0].split("-")[0]
    return tuple(int(p) for p in base.split(".") if p.isdigit())

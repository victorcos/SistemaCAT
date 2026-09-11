"""A versão do sistema, de uma fonte só.

Estava escrita à mão em dois lugares — `app.py` e `pyproject.toml` — e os dois
pararam em 0.3.0 enquanto as etiquetas do git chegavam a v0.15.2. O
`/api/saude` dizia uma coisa e o repositório outra, e o endpoint que existe
para dizer *o que está rodando* passou a mentir.

Fonte única: o `version` do `pyproject.toml`. A etiqueta do git repete esse
número (regra em `docs/VERSIONAMENTO.md`), e um teste falha quando a etiqueta
está à frente do arquivo — que é exatamente como o drift aconteceu.

Ordem de leitura:

1. metadados do pacote instalado (`importlib.metadata`), se alguém um dia o
   instalar com pip;
2. o `pyproject.toml` ao lado do pacote, que é como o sistema roda hoje;
3. `0.0.0+desconhecida`, com aviso no log. Versão nunca derruba a API.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from importlib import metadata
from pathlib import Path

from cat.log import obter_log

log = obter_log(__name__)

NOME_DO_PACOTE = "sistema-cat"
DESCONHECIDA = "0.0.0+desconhecida"

# cat/versao.py -> cat/ -> backend/pyproject.toml
_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@lru_cache
def versao() -> str:
    try:
        return metadata.version(NOME_DO_PACOTE)
    except metadata.PackageNotFoundError:
        pass

    try:
        with _PYPROJECT.open("rb") as f:
            lida = tomllib.load(f)["project"]["version"]
        if isinstance(lida, str) and lida.strip():
            return lida.strip()
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as erro:
        log.warning("não deu para ler a versão do pyproject.toml",
                    extra={"arquivo": str(_PYPROJECT), "motivo": str(erro)})
    return DESCONHECIDA


def como_tupla(texto: str) -> tuple[int, ...]:
    """`0.15.2` -> (0, 15, 2). Ignora o que vier depois de `+` ou `-`."""
    base = texto.lstrip("v").split("+")[0].split("-")[0]
    return tuple(int(p) for p in base.split(".") if p.isdigit())

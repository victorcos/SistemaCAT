"""A versão do sistema, de uma fonte só.

Estava escrita à mão em dois lugares — `app.py` e `pyproject.toml` — e os dois
pararam em 0.3.0 enquanto as etiquetas do git chegavam a v0.15.2. O
`/api/saude` dizia uma coisa e o repositório outra, e o endpoint que existe
para dizer *o que está rodando* passou a mentir.

Fonte única: o `version` do `pyproject.toml`. A etiqueta do git repete esse
número (regra em `docs/VERSIONAMENTO.md`), e um teste falha quando a etiqueta
está à frente do arquivo — que é exatamente como o drift aconteceu.

Ordem de leitura:

1. o `pyproject.toml` ao lado do pacote. Vem PRIMEIRO porque é a fonte: numa
   instalação editável (`pip install -e`), os metadados do pacote congelam a
   versão do dia da instalação e não acompanham o `git pull` — o `/api/saude`
   voltaria a mentir, agora para o outro lado;
2. metadados do pacote instalado (`importlib.metadata`), quando não há
   `pyproject.toml` ao lado (pacote empacotado de verdade);
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
    if _PYPROJECT.is_file():
        try:
            with _PYPROJECT.open("rb") as f:
                lida = tomllib.load(f)["project"]["version"]
            if isinstance(lida, str) and lida.strip():
                return lida.strip()
        except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as erro:
            log.warning("não deu para ler a versão do pyproject.toml",
                        extra={"arquivo": str(_PYPROJECT), "motivo": str(erro)})

    try:
        return metadata.version(NOME_DO_PACOTE)
    except metadata.PackageNotFoundError:
        pass
    return DESCONHECIDA


def como_tupla(texto: str) -> tuple[int, ...]:
    """`0.15.2` -> (0, 15, 2). Ignora o que vier depois de `+` ou `-`."""
    base = texto.lstrip("v").split("+")[0].split("-")[0]
    return tuple(int(p) for p in base.split(".") if p.isdigit())

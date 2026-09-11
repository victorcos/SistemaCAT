"""A versão vem de uma fonte só, e a etiqueta do git não pode correr na frente.

O drift real: `app.py` e `pyproject.toml` pararam em 0.3.0 enquanto as
etiquetas chegavam a v0.15.2. O teste de git guarda exatamente isso — etiqueta
à frente do arquivo. O contrário (arquivo à frente da etiqueta) é normal: é o
commit de bump, antes de etiquetar.
"""

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from cat.versao import DESCONHECIDA, _PYPROJECT, como_tupla, versao


def test_le_do_pyproject():
    with _PYPROJECT.open("rb") as f:
        esperada = tomllib.load(f)["project"]["version"]
    assert versao() == esperada
    assert versao() != DESCONHECIDA


def test_a_api_expoe_a_mesma_versao():
    from cat.apresentacao.api.app import app  # noqa: PLC0415

    assert app.version == versao()


class TestTupla:
    def test_numeros(self):
        assert como_tupla("0.15.2") == (0, 15, 2)

    def test_ignora_prefixo_e_sufixo(self):
        assert como_tupla("v1.2.3") == (1, 2, 3)
        assert como_tupla("1.2.3+local") == (1, 2, 3)

    def test_compara_como_numero_e_nao_como_texto(self):
        # "0.9" < "0.15" como número; como texto seria o contrário
        assert como_tupla("0.9.0") < como_tupla("0.15.0")


def _etiqueta_mais_recente() -> str | None:
    if shutil.which("git") is None:
        return None
    raiz = Path(__file__).resolve().parents[2]
    try:
        saida = subprocess.run(
            ["git", "-C", str(raiz), "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return saida.stdout.strip() or None


def test_a_etiqueta_do_git_nao_corre_na_frente_do_pyproject():
    etiqueta = _etiqueta_mais_recente()
    if etiqueta is None:
        pytest.skip("fora de um repositório git, ou sem git")
    assert como_tupla(etiqueta) <= como_tupla(versao()), (
        f"a etiqueta {etiqueta} está à frente do pyproject ({versao()}). "
        "Bump no pyproject vem ANTES de etiquetar."
    )

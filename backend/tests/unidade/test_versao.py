"""A versão vem de uma fonte só, e a etiqueta do git não pode correr na frente.

O drift real: `app.py` e `pyproject.toml` pararam em 0.3.0 enquanto as
etiquetas chegavam a v0.15.2. O teste de git guarda exatamente isso — etiqueta
à frente do arquivo. O contrário (arquivo à frente da etiqueta) é normal: é o
commit de bump, antes de etiquetar.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from cat.versao import ARQUIVO, DESCONHECIDA, como_tupla, ler, versao


def test_le_do_arquivo_VERSAO_na_raiz():
    assert ARQUIVO.parent == Path(__file__).resolve().parents[3]
    assert versao() == ARQUIVO.read_text(encoding="utf-8-sig").strip()
    assert versao() != DESCONHECIDA


def test_o_motor_expoe_a_mesma_versao():
    from cat.apresentacao.api.app import app  # noqa: PLC0415

    assert app.version == versao()


@pytest.mark.parametrize("conteudo, esperada", [
    ("1.2.3\n", "1.2.3"),
    ("\ufeff1.2.3\r\n", "1.2.3"),
    ("0.35.0-rc.1", "0.35.0-rc.1"),
    ('version = "1.2.3"', DESCONHECIDA),
    ("1.2.3\n4.5.6\n", DESCONHECIDA),
])
def test_so_aceita_o_numero_sozinho(tmp_path, conteudo, esperada):
    arquivo = tmp_path / "VERSAO"
    arquivo.write_text(conteudo, encoding="utf-8")
    assert ler(arquivo) == esperada


def test_sem_arquivo_diz_que_nao_sabe(tmp_path):
    assert ler(tmp_path / "VERSAO") == DESCONHECIDA


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


def test_a_etiqueta_do_git_nao_corre_na_frente_do_arquivo_VERSAO():
    etiqueta = _etiqueta_mais_recente()
    if etiqueta is None:
        pytest.skip("fora de um repositório git, ou sem git")
    assert como_tupla(etiqueta) <= como_tupla(versao()), (
        f"a etiqueta {etiqueta} está à frente do VERSAO ({versao()}). "
        "Bump no VERSAO vem ANTES de etiquetar."
    )

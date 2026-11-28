"""O formatador do log não pode quebrar por causa do que o chamador passa.

Quando quebra, o Python engole o erro dentro do handler: a aplicação segue,
a linha de log desaparece e ninguém fica sabendo. Foi o que aconteceu em
28/11/2026 com a linha "ICMS suportado apurado" — `suportado.py` loga
`{f.value: n}` e a enum `Fonte` tem valores inteiros, então `k.lower()`
estourava `AttributeError` dentro de `_limpar`.
"""
from __future__ import annotations

import json
import logging

from cat.log import FormatadorJson, contexto


def _formatar(mensagem: str, **extra) -> dict:
    """Uma linha de log, já como o dicionário que sai no JSON."""
    registro = logging.LogRecord(
        name="teste", level=logging.INFO, pathname=__file__, lineno=1,
        msg=mensagem, args=(), exc_info=None,
    )
    for chave, valor in extra.items():
        setattr(registro, chave, valor)
    return json.loads(FormatadorJson().format(registro))


def test_dicionario_com_chave_inteira_nao_quebra():
    """O caso real: a enum `Fonte` tem valores 1, 2, 3 e 9."""
    linha = _formatar("ICMS suportado apurado", por_fonte={1: 294, 2: 854304, 9: 3242188})
    # o JSON converte chave numérica para texto, e é isso que se consulta depois
    assert linha["por_fonte"] == {"1": 294, "2": 854304, "9": 3242188}
    assert linha["mensagem"] == "ICMS suportado apurado"


def test_chave_que_nao_e_texto_nem_numero_tambem_passa():
    linha = _formatar("tupla como chave", mapa={(1, 2): "par"})
    assert "mapa" in linha


def test_segredo_continua_mascarado():
    linha = _formatar("login", usuario="automacao", senha="nao-deve-sair",
                      dados={"token": "nao-deve-sair", "porta": 8010})
    assert linha["senha"] == "***"
    assert linha["dados"]["token"] == "***"
    assert linha["dados"]["porta"] == 8010
    assert "nao-deve-sair" not in json.dumps(linha, ensure_ascii=False)


def test_segredo_mascarado_em_dicionario_de_chave_mista():
    """Chave inteira ao lado de chave de segredo: a numérica passa, a outra não."""
    linha = _formatar("misto", mapa={1: "um", "password": "nao-deve-sair"})
    assert linha["mapa"]["1"] == "um"
    assert linha["mapa"]["password"] == "***"


def test_contexto_entra_na_linha():
    with contexto(execucao_id=242, projeto_id=32, etapa="razao"):
        linha = _formatar("etapa em curso")
    assert linha["execucao_id"] == 242
    assert linha["projeto_id"] == 32
    assert linha["etapa"] == "razao"

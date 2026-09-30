"""A série 4390 do SGS do Banco Central: "Selic acumulada no mês".

É a mesma série que a Receita publica para corrigir indébito, e isso não foi
suposto: as diferenças entre competências consecutivas do relatório 903 do MA
batem com ela nos 56 meses conferidos (ver `sped/tabelas/tab_selic.py`).

**Sem biblioteca nova.** `urllib` da própria Python resolve um GET que devolve
JSON, e uma dependência a mais num motor que roda na máquina de quem trabalha
custa mais do que as vinte linhas que ela pouparia.

**Rede nunca derruba a rodada.** Tudo o que pode dar errado aqui — DNS, TLS,
tempo esgotado, JSON estranho, valor que não é número — vira
`ConsultaAoBcbFalhou`, e quem chama decide. Como o que já está no banco não
muda, quase sempre a decisão é seguir com ele.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

from cat.log import obter_log

log = obter_log(__name__)

SERIE = 4390
URL = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{SERIE}/dados"
FONTE = f"bcb-sgs-{SERIE}"

# 20s é generoso para um JSON de poucos kB, e é o teto: a rodada não fica
# pendurada esperando o Banco Central
TEMPO_LIMITE = 20.0


class ConsultaAoBcbFalhou(RuntimeError):
    """Não deu para falar com o SGS, ou o que voltou não era a série."""


def baixar(de: str, ate: str, tempo_limite: float = TEMPO_LIMITE) -> dict[str, Decimal]:
    """As taxas mensais de `de` a `ate`, em "aaaa-mm". Nunca devolve vazio.

    Vazio seria indistinguível de "o Banco Central não tem esses meses ainda",
    e quem chama trataria a ausência como resposta. Sem linha nenhuma, é erro.
    """
    endereco = f"{URL}?formato=json&dataInicial={_dia_um(de)}&dataFinal={_fim(ate)}"
    try:
        with urllib.request.urlopen(endereco, timeout=tempo_limite) as resposta:
            bruto = resposta.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as erro:
        raise ConsultaAoBcbFalhou(
            f"não deu para falar com o SGS do Banco Central: {erro}") from erro

    try:
        linhas = json.loads(bruto)
    except ValueError as erro:
        raise ConsultaAoBcbFalhou(
            f"o SGS devolveu algo que não é JSON: {erro}") from erro

    taxas = _converter(linhas)
    if not taxas:
        raise ConsultaAoBcbFalhou(
            f"o SGS não devolveu nenhuma taxa entre {de} e {ate}.")

    log.info("selic baixada do Banco Central", extra={
        "serie": SERIE, "de": de, "ate": ate, "meses": len(taxas),
        "primeiro": min(taxas), "ultimo": max(taxas)})
    return taxas


def _converter(linhas: object) -> dict[str, Decimal]:
    """`[{"data": "01/03/2021", "valor": "0.20"}]` -> `{"2021-03": 0.20}`.

    Linha torta é descartada com aviso, e não derruba as boas: uma série de
    cem meses não pode ser perdida por causa de uma.
    """
    if not isinstance(linhas, list):
        raise ConsultaAoBcbFalhou("o SGS devolveu um objeto onde deveria haver lista.")

    taxas: dict[str, Decimal] = {}
    for linha in linhas:
        try:
            dia, mes, ano = str(linha["data"]).split("/")
            taxas[f"{ano}-{mes}"] = Decimal(str(linha["valor"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            log.warning("linha da série da Selic ignorada por não fazer sentido",
                        extra={"linha": str(linha)[:120]})
    return taxas


def _dia_um(mes: str) -> str:
    """"2021-03" -> "01/03/2021", que é o formato que o SGS aceita."""
    ano, m = mes.split("-")
    return f"01/{m}/{ano}"


def _fim(mes: str) -> str:
    """O último dia possível do mês. 31 serve: o SGS corta no que existe."""
    ano, m = mes.split("-")
    return f"31/{m}/{ano}" if m in {"01", "03", "05", "07", "08", "10", "12"} else (
        f"28/{m}/{ano}" if m == "02" else f"30/{m}/{ano}")

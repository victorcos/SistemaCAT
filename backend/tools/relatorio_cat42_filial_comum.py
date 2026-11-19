"""Constantes e funções de texto do relatório CAT 42 por filial (leiaute v5), para a empresa 17."""
from __future__ import annotations

import re
import unicodedata

LIMITE_EXCEL = 1_048_576 - 20
SITUACOES_REGULARES = ("00", "01", "06", "07", "08")

UNIFICADO = "unificado"
MESMO = "não precisa: compra e venda no mesmo código"
ESTOQUE = "não precisa: saída coberta pelo estoque inicial"
SEM_PAR = "sem par: saída sem entrada"
SO_ENTRADA = "só entrada na base (sem saída no período)"
PARADO = "sem movimento no período"

# "parece que a compra ainda está em caixa": custo médio acima de 1,3x o preço de
# venda. E o fator só é aceito se puser a razão de volta na faixa de um varejo.
RAZAO_SUSPEITA = 1.3
FAIXA_BOA = (0.3, 1.3)


def sem_acento(t: str | None) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c)).upper()


_MEDIDA = re.compile(r"(\d+[\.,]?\d*)\s*(ML|LT|KGS|KG|GR|UN|CM|MG|L|G|M)\b")
_PALAVRA = re.compile(r"[A-Z]{3,}")


def medidas(t: str) -> set[str]:
    """As medidas do texto, normalizadas: '350 ML' e '350ML' são a mesma."""
    saida = set()
    for numero, unidade in _MEDIDA.findall(sem_acento(t)):
        valor = numero.replace(",", ".")
        if valor.endswith(".0"):
            valor = valor[:-2]
        saida.add(f"{valor}{unidade}")
    return saida


def palavras(t: str) -> list[str]:
    return _PALAVRA.findall(sem_acento(t))


def _combinam(a: str, b: str) -> bool:
    """Uma palavra combina com a outra quando uma é começo da outra (CERV = CERVEJA)."""
    return a == b or (len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)))


def descricao_bate(entrada: str, saida: str) -> str:
    """'confere', 'conferir — medida diferente' ou 'conferir — descrição diferente'."""
    if not (entrada or "").strip() or not (saida or "").strip():
        return ""
    pa, pb = palavras(entrada), palavras(saida)
    if not pa or not pb:
        return ""
    ma, mb = medidas(entrada), medidas(saida)
    if ma and mb and not (ma & mb):
        return "conferir — medida diferente"
    comuns = sum(1 for a in pa if any(_combinam(a, b) for b in pb))
    return "confere" if comuns / min(len(pa), len(pb)) >= 0.6 else "conferir — descrição diferente"


_UNIDADE_COM_FATOR = re.compile(r"^(?:CX|FD|PCT|PC|PK|DP|C|P)/?(\d{1,4})$")
_NA_DESCRICAO = (
    re.compile(r"\bCX\s*C/\s*(\d{1,4})\b"),
    re.compile(r"\bC/\s*(\d{1,4})\b"),
    re.compile(r"\b(\d{1,4})\s*X\s*\d+[\.,]?\d*\s*(?:G|ML|KG|L|UN)\b"),
    re.compile(r"\bCAIXA\s*(\d{1,4})\s*UN\b"),
)


def fator_da_unidade(unidade: str | None) -> int | None:
    """CX12 -> 12, FD6 -> 6, C/10 -> 10. Só o que a própria sigla diz."""
    m = _UNIDADE_COM_FATOR.match(sem_acento(unidade).replace(" ", ""))
    if not m:
        return None
    valor = int(m.group(1))
    return valor if 2 <= valor <= 1000 else None


def fator_da_descricao(descricao: str | None) -> int | None:
    t = sem_acento(descricao)
    for padrao in _NA_DESCRICAO:
        m = padrao.search(t)
        if m:
            valor = int(m.group(1))
            if 2 <= valor <= 1000:
                return valor
    return None


def ean(valor: str | None) -> str | None:
    """O EAN do cadastro: 8 a 14 dígitos, sem os zeros à esquerda."""
    g = (valor or "").strip().lstrip("0")
    return g if g.isdigit() and 8 <= len(g) <= 14 else None


def n(x):
    """Decimal e afins viram float; o resto passa. O xlsxwriter não escreve Decimal."""
    return None if x is None else float(x)


def media(total, qtd):
    t, q = n(total), n(qtd)
    return None if not t or not q else t / q


def lista(v, limite: int = 8) -> str:
    itens = sorted({str(x) for x in (v or []) if str(x or "").strip()})
    if not itens:
        return ""
    if len(itens) <= limite:
        return ", ".join(itens)
    return ", ".join(itens[:limite]) + f" (+{len(itens) - limite})"


def descricao_com_outras(texto: str | None, quantas: int | None, cadastro: str | None, lado: str) -> str:
    if not (texto or "").strip():
        return f"— sem {lado} nesta filial — cadastro: {cadastro or ''}"
    return f"{texto} (+{quantas - 1} outras)" if quantas and quantas > 1 else texto

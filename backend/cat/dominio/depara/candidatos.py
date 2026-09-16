"""De-para de códigos: achar o mesmo produto escriturado com códigos diferentes.

A CAT 42 controla o estoque por mercadoria. Quando a entrada é escriturada com
um código e a saída com outro, o razão monta duas fichas — uma só com
entradas, que não pede nada, e outra só com saídas, que fica negativa e sai do
total. O ressarcimento daquele produto some sem aviso de que era o mesmo.

Na Advertising Operations (RVZ, 2022 a 2024) o mesmo produto tinha até quatro
códigos: `1111` na venda, `1111K3` no kit de três, `1111K3         08` na compra
(o código de venda mais espaços e "08") e `X00450IETL` na venda por
marketplace. Nada disso é exceção: é o ERP de um distribuidor.

## Como se acha

Os códigos que são o mesmo produto formam um **grupo**, ligados por:

* **GTIN** — o mesmo código de barras (0200 ou XML). Prova forte;
* **sufixo que se repete** — o código de compra é o de venda mais um sufixo, e o
  mesmo sufixo aparece em vários pares (no mínimo `MINIMO_DE_PARES_DO_SUFIXO`).
  Um par só com sufixo pode ser coincidência; dez pares com "08", não;
* **kit** — o código ou a descrição diz "KIT 3X"/`K3`, e existe o código da
  unidade com a mesma base. Liga com **fator**: 1 kit = 3 unidades;
* **descrição e NCM** — a mesma descrição, limpa de lote e validade, e o mesmo
  NCM. Prova média: vai à revisão marcada assim.

Só se propõe grupo que **conserta alguma ficha**: com pelo menos um código sem
entrada ou sem saída. Dois códigos com entrada e saída cada um são, até prova
em contrário, produtos diferentes que se parecem.

Em cada grupo, o código que fica é o de **mais saídas** (é nele que o cliente
vende); os outros viram pares `origem → destino` com o fator acumulado.

## O que impede juntar demais

* `K3` no fim do código é kit, não sufixo: quem liga o kit à unidade é a regra
  do kit, com fator. Tratado como sufixo, o kit virava unidade com fator 1;
* GTIN não liga kit a unidade — são embalagens diferentes do mesmo produto, e
  o fator não sai do GTIN;
* GTIN só liga descrições compatíveis (metade das palavras em comum): o 0200
  da Advertising trazia no `1114` ("GRECIN 5 PRETO") o GTIN do `1050` ("GRECIN
  TONS DE GRISALHO"), e o GTIN sozinho juntava seis produtos num;
* quando dois caminhos do grupo dão fatores diferentes para o mesmo código, o
  grupo inteiro cai para confiança média, com o conflito escrito.

Nada aqui é aplicado sozinho: é proposta, com o motivo escrito, para o analista
aprovar (decisão do Victor, 16/09/2026). O que não casar vai para o cliente
preencher.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

ZERO = Decimal(0)
UM = Decimal(1)

MINIMO_DE_PARES_DO_SUFIXO = 3
TAMANHO_MAXIMO_DO_SUFIXO = 3


class Motivo(str, Enum):
    GTIN = "gtin"
    SUFIXO = "sufixo"
    KIT = "kit"
    DESCRICAO = "descricao"
    CLIENTE = "cliente"
    ANALISTA = "analista"

    @property
    def rotulo(self) -> str:
        return {
            Motivo.GTIN: "Mesmo código de barras",
            Motivo.SUFIXO: "Código de compra = código de venda + sufixo",
            Motivo.KIT: "Kit de unidades do mesmo produto",
            Motivo.DESCRICAO: "Mesma descrição e NCM",
            Motivo.CLIENTE: "Informado pelo cliente",
            Motivo.ANALISTA: "Informado pelo analista",
        }[self]


class Confianca(str, Enum):
    ALTA = "alta"
    MEDIA = "media"


@dataclass(frozen=True)
class ItemParaCasar:
    """O que se sabe de um código num estabelecimento."""

    codigo: str
    descricao: str = ""
    ncm: str = ""
    gtins: frozenset[str] = frozenset()
    entradas: Decimal = ZERO        # quantidade entrada no período
    saidas: Decimal = ZERO          # quantidade saída no período
    estoque_inicial: Decimal = ZERO  # abertura do inventário

    @property
    def tem_origem(self) -> bool:
        return self.entradas > ZERO or self.estoque_inicial > ZERO

    @property
    def tem_saida(self) -> bool:
        return self.saidas > ZERO


@dataclass(frozen=True)
class Par:
    """`quantidade na origem × fator = quantidade no destino`."""

    origem: str
    destino: str
    fator: Decimal
    motivos: tuple[Motivo, ...]
    confianca: Confianca
    explicacao: str


@dataclass
class _Ligacao:
    a: str
    b: str
    # quantidade em `a` × fator = quantidade em `b`
    fator: Decimal
    motivo: Motivo
    detalhe: str


# ---------------------------------------------------------------------------
# normalização
# ---------------------------------------------------------------------------
_ESPACOS = re.compile(r"\s+")
_LOTE_VALIDADE = re.compile(r"\b(LOTE|LT|VAL|VALIDADE|FAB)\b\s*[:.]?\s*\S+", re.IGNORECASE)
_KIT_NA_DESCRICAO = re.compile(r"\bKIT\s*(?:C/|COM|DE)?\s*(\d{1,3})\s*(?:X|UN|UNID|UNIDADES)?\b"
                               r"|\b(\d{1,3})\s*X\s*KIT\b|\bKIT\b.*?\b(\d{1,3})\s*X\b", re.IGNORECASE)
_KIT_NO_CODIGO = re.compile(r"^(.+?)K(\d{1,2})$", re.IGNORECASE)
_NAO_ALFANUMERICO = re.compile(r"[^A-Z0-9 ]+")


def normalizar_codigo(codigo: str) -> str:
    """Sem espaços: o ERP da Advertising grava `1012           08` e `101208`."""
    return _ESPACOS.sub("", codigo or "").upper()


def normalizar_descricao(descricao: str) -> str:
    """Maiúsculas, sem acento, sem lote e validade, sem pontuação, espaço único."""
    texto = unicodedata.normalize("NFKD", descricao or "").encode("ascii", "ignore").decode()
    texto = _LOTE_VALIDADE.sub(" ", texto.upper())
    texto = _NAO_ALFANUMERICO.sub(" ", texto)
    return _ESPACOS.sub(" ", texto).strip()


def gtin_valido(gtin: str) -> bool:
    """8, 12, 13 ou 14 dígitos, não todos iguais, com o dígito verificador certo."""
    g = (gtin or "").strip()
    if len(g) not in (8, 12, 13, 14) or not g.isdigit() or len(set(g)) == 1:
        return False
    corpo, dv = g[:-1], int(g[-1])
    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(corpo)))
    return (10 - soma % 10) % 10 == dv


def fator_do_kit(item: ItemParaCasar) -> tuple[int, str] | None:
    """(unidades no kit, base do código) quando o item é kit; senão None."""
    codigo = normalizar_codigo(item.codigo)
    no_codigo = _KIT_NO_CODIGO.match(codigo)
    achado = _KIT_NA_DESCRICAO.search(normalizar_descricao(item.descricao))
    n_descricao = next((int(g) for g in achado.groups() if g), None) if achado else None
    if no_codigo and int(no_codigo.group(2)) > 1:
        return int(no_codigo.group(2)), no_codigo.group(1)
    if n_descricao and n_descricao > 1:
        return n_descricao, codigo
    return None


def descricoes_compativeis(a: str, b: str, minimo: float = 0.5) -> bool:
    """Se as duas descrições falam do mesmo produto: metade das palavras em comum.

    Sem descrição de um lado não há o que contrariar, e vale o GTIN.
    """
    pa = {p for p in _descricao_sem_kit(a).split() if len(p) >= 2}
    pb = {p for p in _descricao_sem_kit(b).split() if len(p) >= 2}
    if not pa or not pb:
        return True
    return len(pa & pb) / len(pa | pb) >= minimo


def _descricao_sem_kit(descricao: str) -> str:
    texto = normalizar_descricao(descricao)
    texto = re.sub(r"\bKIT\s*(C|COM|DE)?\s*\d{1,3}\s*(X|UN|UNID|UNIDADES)?\b", " ", texto)
    texto = re.sub(r"\b\d{1,3}\s*X\b", " ", texto)
    texto = re.sub(r"\bKIT\b", " ", texto)
    return _ESPACOS.sub(" ", texto).strip()


# ---------------------------------------------------------------------------
# as ligações
# ---------------------------------------------------------------------------
def _por_gtin(itens: dict[str, ItemParaCasar]) -> list[_Ligacao]:
    por_gtin: dict[str, list[str]] = {}
    for codigo, item in itens.items():
        for g in item.gtins:
            if gtin_valido(g):
                por_gtin.setdefault(g.lstrip("0"), []).append(codigo)
    ligacoes = []
    for gtin, codigos in por_gtin.items():
        codigos = sorted(set(codigos))
        for outro in codigos[1:]:
            # kit e unidade com o mesmo GTIN: o fator não sai daqui
            if (fator_do_kit(itens[outro]) is None) != (fator_do_kit(itens[codigos[0]]) is None):
                continue
            if not descricoes_compativeis(itens[outro].descricao, itens[codigos[0]].descricao):
                continue
            ligacoes.append(_Ligacao(outro, codigos[0], UM, Motivo.GTIN, f"GTIN {gtin}"))
    return ligacoes


def _por_sufixo(itens: dict[str, ItemParaCasar]) -> list[_Ligacao]:
    """Pares `base + sufixo`, só com sufixo que se repete."""
    normal = {normalizar_codigo(c): c for c in itens}
    pares: dict[str, list[tuple[str, str]]] = {}
    for longo_n, longo in normal.items():
        if _KIT_NO_CODIGO.match(longo_n):
            continue                     # `1111K3` é kit do 1111, não sufixo
        for tamanho in range(1, TAMANHO_MAXIMO_DO_SUFIXO + 1):
            base_n, sufixo = longo_n[:-tamanho], longo_n[-tamanho:]
            if len(base_n) >= 2 and base_n in normal:
                pares.setdefault(sufixo, []).append((longo, normal[base_n]))
    ligacoes = []
    for sufixo, lista in pares.items():
        if len(lista) < MINIMO_DE_PARES_DO_SUFIXO:
            continue
        for longo, base in lista:
            ligacoes.append(_Ligacao(longo, base, UM, Motivo.SUFIXO,
                                     f"sufixo \"{sufixo}\", repetido em {len(lista)} pares"))
    # o mesmo código sem espaços (`1012           08` e `101208`) é o mesmo código
    por_normal: dict[str, list[str]] = {}
    for c in itens:
        por_normal.setdefault(normalizar_codigo(c), []).append(c)
    for n, lista in por_normal.items():
        lista = sorted(lista)
        for outro in lista[1:]:
            ligacoes.append(_Ligacao(outro, lista[0], UM, Motivo.SUFIXO, "mesmo código sem os espaços"))
    return ligacoes


def _por_kit(itens: dict[str, ItemParaCasar]) -> list[_Ligacao]:
    normal = {normalizar_codigo(c): c for c in itens}
    por_descricao: dict[str, list[str]] = {}
    for c, item in itens.items():
        if fator_do_kit(item) is None:
            por_descricao.setdefault(_descricao_sem_kit(item.descricao), []).append(c)
    ligacoes = []
    for codigo, item in itens.items():
        kit = fator_do_kit(item)
        if kit is None:
            continue
        unidades, base = kit
        unidade = normal.get(base) if base != normalizar_codigo(codigo) else None
        if unidade is None:
            candidatos = [c for c in por_descricao.get(_descricao_sem_kit(item.descricao), [])
                          if (itens[c].ncm or item.ncm) == (item.ncm or itens[c].ncm)]
            unidade = candidatos[0] if len(candidatos) == 1 else None
        if unidade is not None and unidade != codigo:
            ligacoes.append(_Ligacao(codigo, unidade, Decimal(unidades), Motivo.KIT,
                                     f"kit de {unidades} unidades"))
    return ligacoes


def _por_descricao(itens: dict[str, ItemParaCasar]) -> list[_Ligacao]:
    grupos: dict[tuple[str, str], list[str]] = {}
    for c, item in itens.items():
        d = normalizar_descricao(item.descricao)
        if len(d) >= 6 and item.ncm and fator_do_kit(item) is None:
            grupos.setdefault((d, item.ncm), []).append(c)
    ligacoes = []
    for (d, ncm), codigos in grupos.items():
        codigos = sorted(codigos)
        for outro in codigos[1:]:
            ligacoes.append(_Ligacao(outro, codigos[0], UM, Motivo.DESCRICAO, f"\"{d}\", NCM {ncm}"))
    return ligacoes


# ---------------------------------------------------------------------------
# os grupos e os pares
# ---------------------------------------------------------------------------
@dataclass
class _Grupo:
    codigos: set[str] = field(default_factory=set)
    # fator de cada código para a raiz provisória do grupo: q(código) × f = q(raiz)
    fatores: dict[str, Decimal] = field(default_factory=dict)
    motivos: dict[str, set[Motivo]] = field(default_factory=dict)
    detalhes: dict[str, list[str]] = field(default_factory=dict)
    conflitos: list[str] = field(default_factory=list)


def propor(itens: list[ItemParaCasar]) -> list[Par]:
    """Os pares `origem → destino` que juntam o mesmo produto, para revisão."""
    por_codigo = {i.codigo: i for i in itens}
    ligacoes = (_por_gtin(por_codigo) + _por_sufixo(por_codigo)
                + _por_kit(por_codigo) + _por_descricao(por_codigo))

    # o fator de cada código até uma raiz comum, andando pelas ligações
    vizinhos: dict[str, list[tuple[str, Decimal, _Ligacao]]] = {}
    for l in ligacoes:
        vizinhos.setdefault(l.a, []).append((l.b, l.fator, l))
        vizinhos.setdefault(l.b, []).append((l.a, UM / l.fator, l))

    vistos: set[str] = set()
    pares: list[Par] = []
    for inicio in sorted(vizinhos):
        if inicio in vistos:
            continue
        grupo = _Grupo()
        grupo.fatores[inicio] = UM
        fila = [inicio]
        while fila:
            atual = fila.pop()
            if atual in grupo.codigos:
                continue
            grupo.codigos.add(atual)
            for vizinho, fator, ligacao in vizinhos.get(atual, []):
                # q(vizinho) × f(vizinho) = q(raiz), e q(atual) × fator = q(vizinho)
                esperado = grupo.fatores[atual] / fator
                if vizinho in grupo.fatores and grupo.fatores[vizinho] != esperado:
                    grupo.conflitos.append(f"{vizinho}: fator {grupo.fatores[vizinho].normalize()} "
                                           f"ou {esperado.normalize()} ({ligacao.detalhe})")
                grupo.fatores.setdefault(vizinho, esperado)
                for c in (ligacao.a, ligacao.b):
                    grupo.motivos.setdefault(c, set()).add(ligacao.motivo)
                    grupo.detalhes.setdefault(c, [])
                    if ligacao.detalhe not in grupo.detalhes[c]:
                        grupo.detalhes[c].append(ligacao.detalhe)
                if vizinho not in grupo.codigos:
                    fila.append(vizinho)
        vistos |= grupo.codigos
        pares += _pares_do_grupo(grupo, por_codigo)
    return sorted(pares, key=lambda p: (p.destino, p.origem))


def _pares_do_grupo(grupo: _Grupo, itens: dict[str, ItemParaCasar]) -> list[Par]:
    membros = [itens[c] for c in grupo.codigos if c in itens]
    if len(membros) < 2:
        return []
    # só vale propor se juntar conserta alguma ficha
    if all(m.tem_origem and m.tem_saida for m in membros):
        return []
    if not any(m.tem_origem for m in membros) or not any(m.tem_saida for m in membros):
        return []
    # o destino é onde se vende: mais saídas na unidade da raiz; empate, o código mais curto
    destino = max(membros, key=lambda m: (m.saidas * grupo.fatores[m.codigo],
                                          -len(normalizar_codigo(m.codigo)), m.codigo))
    f_destino = grupo.fatores[destino.codigo]
    pares = []
    for m in membros:
        if m.codigo == destino.codigo:
            continue
        # q(m) × f(m) = q(raiz) = q(destino) × f(destino)  →  q(destino) = q(m) × f(m) / f(destino)
        fator = (grupo.fatores[m.codigo] / f_destino).normalize()
        motivos = tuple(sorted(grupo.motivos.get(m.codigo, set()) | grupo.motivos.get(destino.codigo, set()),
                               key=lambda x: list(Motivo).index(x)))
        confianca = (Confianca.ALTA if any(x in (Motivo.GTIN, Motivo.SUFIXO, Motivo.KIT) for x in motivos)
                     and not grupo.conflitos else Confianca.MEDIA)
        detalhes = "; ".join(dict.fromkeys(grupo.detalhes.get(m.codigo, []) + grupo.detalhes.get(destino.codigo, [])))
        if grupo.conflitos:
            detalhes = f"fatores em conflito no grupo ({'; '.join(grupo.conflitos[:2])}); {detalhes}"
        pares.append(Par(m.codigo, destino.codigo, fator, motivos, confianca, detalhes))
    return pares

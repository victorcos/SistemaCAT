"""Quanto falta, para o que roda **dentro de uma requisição**.

A execução de etapa já tem andamento: `fracao` e `passo` no banco, que a tela
lê enquanto a rodada acontece (`components/ui/Andamento.tsx`). O que nunca teve
foi tudo o que o motor faz dentro de um pedido HTTP — montar planilha,
materializar resumo, recortar lista. Medido em 14/10/2026, no mesmo dia:

* montar a Consulta de Entradas em xlsx: **35 minutos**;
* materializar o resumo do razão contábil: **149 segundos**;
* os filtros da 047: **113 segundos**; as linhas: **125 segundos**.

Em todas elas a tela mostra um girador e nada mais. Quem espera não sabe se
falta um minuto ou meia hora, nem se ainda está vivo — e já houve quem
concluísse que tinha travado e clicasse de novo, dobrando o trabalho do
servidor.

## Como se liga

Quem pede manda uma **chave** (um identificador que a própria tela inventa) e
consulta o andamento por ela. Sem chave, nada é registrado e o custo é zero —
nenhuma operação precisa saber se alguém está olhando.

Dentro do motor o relator anda por `ContextVar`, e não por parâmetro. É
deliberado: `gerar` chega ao laço do xlsx atravessando cinco funções e nove
geradores diferentes, e acrescentar um argumento a todos eles só para carregar
um contador espalharia o assunto por arquivos que não têm nada com ele. O
`ContextVar` também atravessa sozinho o `run_in_threadpool` do FastAPI, que é
onde as rotas síncronas do motor realmente rodam.

## O laço não pode pagar por isso

Um laço de 4,7 milhões de linhas não aguenta pegar uma trava por linha. O
relator conta em memória local e só publica de `INTERVALO_DE_PUBLICACAO` em
`INTERVALO_DE_PUBLICACAO` — a conta que a tela lê fica no máximo esse tanto
atrasada, e um quarto de segundo de atraso não muda decisão nenhuma de quem
está esperando meia hora.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator
from dataclasses import dataclass, field

from cat.log import obter_log

log = obter_log(__name__)

# de quanto em quanto tempo o relator publica o que contou
INTERVALO_DE_PUBLICACAO = 0.25

# quanto tempo um andamento parado continua legível. Serve para a tela que
# perguntou tarde ainda ver o fim, e para o registro não crescer para sempre
VALIDADE = 600.0


@dataclass
class Andamento:
    """O que a tela lê. `total` em zero significa passo sem contagem."""

    passo: str = ""
    feito: int = 0
    total: int = 0
    terminado: bool = False
    atualizado_em: float = field(default_factory=time.monotonic)

    @property
    def fracao(self) -> float:
        if self.terminado:
            return 1.0
        if self.total <= 0:
            return 0.0
        return min(self.feito / self.total, 1.0)

    def como_dicionario(self) -> dict:
        return {"passo": self.passo, "feito": self.feito, "total": self.total,
                "fracao": round(self.fracao, 4), "terminado": self.terminado}


_registro: dict[str, Andamento] = {}
_porteiro = threading.Lock()


class Relator:
    """O que a operação usa para contar. Sem chave, não faz nada."""

    def __init__(self, chave: str | None) -> None:
        self._chave = chave
        self._feito = 0
        self._total = 0
        self._passo = ""
        self._publicado_em = 0.0

    @property
    def ligado(self) -> bool:
        return self._chave is not None

    def passo(self, texto: str, total: int = 0) -> None:
        """Começa uma etapa nomeada. `total` conhecido vira porcentagem."""
        self._passo = texto
        self._total = total
        self._feito = 0
        self._publicar(agora=True)

    def avancar(self, quantos: int = 1) -> None:
        self._feito += quantos
        self._publicar()

    def terminar(self) -> None:
        if not self.ligado:
            return
        with _porteiro:
            _registro[self._chave] = Andamento(
                passo=self._passo, feito=self._feito, total=self._total, terminado=True)

    def _publicar(self, agora: bool = False) -> None:
        if not self.ligado:
            return
        instante = time.monotonic()
        if not agora and instante - self._publicado_em < INTERVALO_DE_PUBLICACAO:
            return
        self._publicado_em = instante
        with _porteiro:
            _registro[self._chave] = Andamento(
                passo=self._passo, feito=self._feito, total=self._total)


_MUDO = Relator(None)
_atual: ContextVar[Relator] = ContextVar("relator", default=_MUDO)


def atual() -> Relator:
    """O relator deste pedido, ou um mudo quando ninguém está olhando."""
    return _atual.get()


@contextmanager
def relatando(chave: str | None) -> Iterator[Relator]:
    """Liga o relator para o bloco inteiro, e o desliga ao sair."""
    relator = Relator(chave)
    marca = _atual.set(relator)
    try:
        yield relator
    finally:
        relator.terminar()
        _atual.reset(marca)
        _limpar_vencidos()


def ler(chave: str) -> Andamento | None:
    """O andamento de uma chave, ou nada se ela não existe mais."""
    with _porteiro:
        andamento = _registro.get(chave)
    if andamento is None:
        return None
    if time.monotonic() - andamento.atualizado_em > VALIDADE:
        return None
    return andamento


def _limpar_vencidos() -> None:
    limite = time.monotonic() - VALIDADE
    with _porteiro:
        vencidas = [c for c, a in _registro.items() if a.atualizado_em < limite]
        for chave in vencidas:
            del _registro[chave]
    if vencidas:
        log.debug("andamentos vencidos removidos", extra={"quantos": len(vencidas)})

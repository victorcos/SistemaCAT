"""O que toda rodada longa com tela precisa: diário, freio e cancelamento.

Nasceu na etapa 4 e saiu dela quando a etapa 5 precisou do mesmo. Copiar
seria ter duas regras de cancelar — e a primeira correção feita numa só
deixaria uma etapa dizendo que parou uma rodada que vai até o fim.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, UsuarioDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

SEGUNDOS_ENTRE_AVISOS = 2.0

# só as etapas cuja rodada confere o freio. Nas outras, gravar "cancelando"
# deixaria a tela dizendo que vai parar uma rodada que vai até o fim
ETAPAS_CANCELAVEIS = frozenset({"st_suportado", "razao", "apuracao", "arquivo_digital", "pre_validacao"})


class Diario:
    """O resumo que a tela lê enquanto a rodada anda: andamento e log.

    Vai ao banco de tempos em tempos, não a cada lote — gravar JSON a cada
    duzentos mil itens seria o banco fazendo mais trabalho que a rodada.
    """

    def __init__(self, execucao: ExecucaoDB, sessao: Session, versao: int) -> None:
        self.execucao = execucao
        self.sessao = sessao
        self.base: dict = {"versao": versao, "log": []}
        self.ultimo = 0.0

    def anotar(self, nivel: str, texto: str) -> None:
        self.base["log"].append({
            "em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "nivel": nivel, "texto": texto,
        })
        self.salvar()

    def salvar(self) -> None:
        # dicionário novo: o SQLAlchemy só percebe a mudança de um JSON quando
        # o objeto inteiro é trocado
        self.execucao.resumo = {**self.base, "log": list(self.base["log"])}
        try:
            self.sessao.commit()
        except Exception:                        # noqa: BLE001
            # progresso é enfeite; perder um aviso não pode derrubar a rodada
            self.sessao.rollback()
            log.warning("não deu para gravar o andamento da rodada", exc_info=True)
        self.ultimo = time.monotonic()

    def salvar_de_vez_em_quando(self) -> None:
        if time.monotonic() - self.ultimo >= SEGUNDOS_ENTRE_AVISOS:
            self.salvar()


class Freio:
    """Pergunta ao banco, de tempos em tempos, se alguém mandou parar.

    Sessão própria e curta: a da rodada tem o objeto da execução em memória, e
    um `refresh` nela desfaria o progresso ainda não gravado.
    """

    def __init__(self, execucao_id: int) -> None:
        self.execucao_id = execucao_id
        self.ultimo = 0.0
        self.parar = False

    def __call__(self) -> bool:
        if self.parar:
            return True
        agora = time.monotonic()
        if agora - self.ultimo < 1.0:
            return False
        self.ultimo = agora
        try:
            with Sessao() as s:
                situacao = s.scalar(select(ExecucaoDB.situacao)
                                    .where(ExecucaoDB.id == self.execucao_id))
        except Exception:                        # noqa: BLE001
            log.warning("não deu para conferir se a rodada foi cancelada", exc_info=True)
            return False
        self.parar = situacao == "cancelando"
        return self.parar


class CancelamentoRecusado(ValueError):
    def __init__(self, status: int, mensagem: str) -> None:
        self.status = status
        super().__init__(mensagem)


def cancelar(execucao_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    """Na fila, cancela na hora; rodando, pede para parar no próximo ponto seguro."""
    execucao = sessao.get(ExecucaoDB, execucao_id)
    if execucao is None:
        raise CancelamentoRecusado(404, "Execução não encontrada.")
    if execucao.etapa not in ETAPAS_CANCELAVEIS:
        raise CancelamentoRecusado(422, "Esta etapa ainda não aceita cancelamento.")
    if execucao.situacao not in ("na_fila", "rodando", "cancelando"):
        raise CancelamentoRecusado(409, "Esta rodada já terminou.")

    with contexto(etapa=execucao.etapa, execucao_id=execucao_id, usuario_id=usuario_id):
        if execucao.situacao == "na_fila":
            execucao.situacao = "cancelada"
            execucao.passo = "Cancelada"
            execucao.terminada_em = datetime.now(timezone.utc)
        elif execucao.situacao == "rodando":
            execucao.situacao = "cancelando"
            execucao.passo = "Cancelando"
        sessao.commit()
        log.info("cancelamento pedido", extra={"situacao": execucao.situacao})
    return execucao


# ---------------------------------------------------------------------------
# formatação do log da tela
# ---------------------------------------------------------------------------
def nome_de(usuario_id: int | None, sessao: Session) -> str:
    if usuario_id is None:
        return ""
    return sessao.scalar(select(UsuarioDB.nome_exibicao)
                         .where(UsuarioDB.id == usuario_id)) or ""


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def pct(f: float) -> str:
    return f"{f * 100:.1f}%".replace(".", ",")


def duracao(segundos: float) -> str:
    minutos, seg = divmod(int(segundos), 60)
    return f"{minutos} min {seg:02d} s" if minutos else f"{seg} s"


def reais(valor) -> str:
    return "R$ " + f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

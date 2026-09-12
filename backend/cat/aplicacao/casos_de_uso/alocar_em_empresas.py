"""Quem trabalha em qual empresa.

O escopo de visibilidade do sistema nasce daqui: `Usuario.empresas` é o
conjunto das alocações **vigentes**, e toda consulta a dado fiscal passa por
`exigir_empresa`. Até agora a alocação só nascia de um jeito — quem cadastra
a empresa pelo SPED fica alocado nela —, o que deixava os outros sem acesso a
nada e sem caminho para ganhá-lo.

**Desalocar não apaga a linha.** Preenche-se `fim`, como o modelo pede desde o
começo: é o que permite responder, meses depois, quem tinha acesso a um dado
em determinado mês. Alocar de novo cria uma linha nova — o histórico fica com
as duas passagens, que é a verdade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.dominio.acesso.usuario import Usuario
from cat.infraestrutura.repositorios.modelos import (
    AlocacaoDB,
    EmpresaDB,
    UsuarioDB,
)
from cat.log import obter_log

log = obter_log(__name__)

PAPEL_PADRAO = "executor"


class UsuarioNaoEncontrado(ValueError):
    def __init__(self) -> None:
        super().__init__("Usuário não encontrado.")


class NaoPodeAlocar(PermissionError):
    def __init__(self) -> None:
        super().__init__(
            "Só gestor define a quais empresas alguém tem acesso. Quem executa "
            "pede ao gestor — o escopo é decisão de quem coordena."
        )


class NaoPodeTirarDeSi(ValueError):
    def __init__(self) -> None:
        super().__init__(
            "Você não pode tirar o seu próprio acesso a uma empresa. Peça a "
            "outro gestor — evita alguém se trancar para fora por engano."
        )


class EmpresaInexistente(ValueError):
    def __init__(self, ids: set[int]) -> None:
        super().__init__(
            "Empresa não encontrada: " + ", ".join(str(i) for i in sorted(ids))
        )


@dataclass(frozen=True)
class AcessoAEmpresa:
    """Uma empresa e se esta pessoa a alcança hoje."""

    empresa_id: int
    razao_social: str
    uf: str | None
    tem_acesso: bool
    desde: datetime | None = None


def vigentes(usuario_id: int, sessao: Session) -> set[int]:
    """Os ids das empresas que a pessoa alcança agora."""
    return set(
        sessao.scalars(
            select(AlocacaoDB.empresa_id).where(
                AlocacaoDB.usuario_id == usuario_id, AlocacaoDB.fim.is_(None)
            )
        )
    )


def listar(usuario_id: int, sessao: Session) -> list[AcessoAEmpresa]:
    """Todas as empresas, marcando quais esta pessoa alcança.

    Devolve todas de propósito: a tela é de *conceder e tirar*, e mostrar só
    o que já tem deixaria o gesto de conceder sem alvo.
    """
    alvo = sessao.get(UsuarioDB, usuario_id)
    if alvo is None:
        raise UsuarioNaoEncontrado

    desde = {
        a.empresa_id: a.inicio
        for a in sessao.scalars(
            select(AlocacaoDB).where(
                AlocacaoDB.usuario_id == usuario_id, AlocacaoDB.fim.is_(None)
            )
        )
    }
    empresas = sessao.scalars(select(EmpresaDB).order_by(EmpresaDB.razao_social))
    return [
        AcessoAEmpresa(
            empresa_id=e.id,
            razao_social=e.razao_social,
            uf=e.uf,
            tem_acesso=e.id in desde,
            desde=desde.get(e.id),
        )
        for e in empresas
    ]


@dataclass(frozen=True)
class OQueMudou:
    concedidas: list[str]
    encerradas: list[str]

    @property
    def mudou(self) -> bool:
        return bool(self.concedidas or self.encerradas)


def definir(
    usuario_id: int, empresas: set[int], por: Usuario, sessao: Session
) -> OQueMudou:
    """Faz o acesso da pessoa ser exatamente este conjunto de empresas."""
    if not por.papel.administra_usuarios:
        raise NaoPodeAlocar

    alvo = sessao.get(UsuarioDB, usuario_id)
    if alvo is None:
        raise UsuarioNaoEncontrado

    existentes = set(sessao.scalars(select(EmpresaDB.id)))
    if not empresas <= existentes:
        raise EmpresaInexistente(empresas - existentes)

    atuais = vigentes(usuario_id, sessao)
    conceder = empresas - atuais
    encerrar = atuais - empresas

    if encerrar and alvo.id == por.id:
        raise NaoPodeTirarDeSi

    nomes = {
        e.id: e.razao_social
        for e in sessao.scalars(select(EmpresaDB).where(EmpresaDB.id.in_(conceder | encerrar)))
    } if (conceder or encerrar) else {}

    agora = datetime.now(timezone.utc)
    for empresa_id in sorted(conceder):
        sessao.add(
            AlocacaoDB(
                usuario_id=alvo.id, empresa_id=empresa_id,
                papel_projeto=PAPEL_PADRAO, alocado_por=por.id, inicio=agora,
            )
        )
    for alocacao in sessao.scalars(
        select(AlocacaoDB).where(
            AlocacaoDB.usuario_id == alvo.id,
            AlocacaoDB.empresa_id.in_(encerrar),
            AlocacaoDB.fim.is_(None),
        )
    ):
        # a linha fica: quem tinha acesso em março continua respondível
        alocacao.fim = agora
        alocacao.motivo_saida = f"acesso encerrado por {por.usuario}"

    mudou = OQueMudou(
        concedidas=[nomes.get(i, str(i)) for i in sorted(conceder)],
        encerradas=[nomes.get(i, str(i)) for i in sorted(encerrar)],
    )
    if mudou.mudou:
        sessao.commit()
        log.warning(
            "acesso a empresas alterado",
            extra={"usuario_id": alvo.id, "usuario": alvo.usuario,
                   "concedidas": mudou.concedidas, "encerradas": mudou.encerradas,
                   "por_usuario_id": por.id},
        )
    return mudou

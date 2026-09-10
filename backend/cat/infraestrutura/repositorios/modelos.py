"""Tabelas. Reflete o modelo desenhado em docs/ARQUITETURA.md.

Nesta fatia entram só as tabelas que a tela de login exige. Projeto, atividade e
execução vêm na etapa de ingestão, mas empresa e alocação já entram porque o
escopo de visibilidade nasce delas.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EmpresaDB(Base):
    __tablename__ = "empresa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cnpj_raiz: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    razao_social: Mapped[str] = mapped_column(Text, nullable=False)
    grupo_economico: Mapped[str | None] = mapped_column(Text)
    uf: Mapped[str | None] = mapped_column(String(2))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class UsuarioDB(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    nome_exibicao: Mapped[str] = mapped_column(Text, nullable=False)
    senha_hash: Mapped[str] = mapped_column(Text, nullable=False)
    papel: Mapped[str] = mapped_column(String(20), nullable=False, default="leitura")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )

    # a tabela de alocação aponta duas vezes para usuário (quem foi alocado e
    # quem alocou), então o lado da chave precisa ser dito explicitamente
    alocacoes: Mapped[list["AlocacaoDB"]] = relationship(
        back_populates="usuario_obj",
        lazy="selectin",
        foreign_keys="AlocacaoDB.usuario_id",
    )


class AlocacaoDB(Base):
    """Quem trabalha em qual empresa, com histórico.

    Nunca apagar linha. Quando a pessoa sai, preenche-se `fim`. É o que permite
    responder quem tinha acesso a um dado em determinado mês, meses depois.
    """

    __tablename__ = "alocacao"
    __table_args__ = (UniqueConstraint("usuario_id", "empresa_id", "inicio"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), nullable=False)
    papel_projeto: Mapped[str] = mapped_column(String(20), nullable=False)
    inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )
    fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alocado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    motivo_saida: Mapped[str | None] = mapped_column(Text)

    usuario_obj: Mapped[UsuarioDB] = relationship(
        back_populates="alocacoes", foreign_keys=[usuario_id]
    )

    @property
    def vigente(self) -> bool:
        return self.fim is None

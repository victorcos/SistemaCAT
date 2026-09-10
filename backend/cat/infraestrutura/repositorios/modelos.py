"""Tabelas. Reflete o modelo desenhado em docs/ARQUITETURA.md.

Nesta fatia entram só as tabelas que a tela de login exige. Projeto, atividade e
execução vêm na etapa de ingestão, mas empresa e alocação já entram porque o
escopo de visibilidade nasce delas.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EmpresaDB(Base):
    """Uma empresa cliente, identificada pela raiz do CNPJ.

    A raiz é a chave porque é o que todas as filiais compartilham. O CNPJ da
    matriz fica ao lado por ser o que as pessoas reconhecem.
    """

    __tablename__ = "empresa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cnpj_raiz: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    cnpj_matriz: Mapped[str | None] = mapped_column(String(14))
    razao_social: Mapped[str] = mapped_column(Text, nullable=False)
    grupo_economico: Mapped[str | None] = mapped_column(Text)
    uf: Mapped[str | None] = mapped_column(String(2))
    inscricao_estadual: Mapped[str | None] = mapped_column(String(20))
    # verdadeiro enquanto veio só do arquivo e ninguém conferiu
    pre_cadastro: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, server_default=func.now(),
        nullable=False,
    )
    criada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))


class UsuarioDB(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    nome_exibicao: Mapped[str] = mapped_column(Text, nullable=False)
    senha_hash: Mapped[str] = mapped_column(Text, nullable=False)
    papel: Mapped[str] = mapped_column(String(20), nullable=False, default="leitura")
    cargo: Mapped[str] = mapped_column(String(20), nullable=False, default="outro")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    senha_provisoria: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
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


class EstabelecimentoDB(Base):
    """Uma filial ou a matriz. Um por CNPJ completo.

    O escopo de confidencialidade é por EMPRESA, não por estabelecimento: quem
    enxerga a empresa enxerga todas as filiais dela.
    """

    __tablename__ = "estabelecimento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), nullable=False)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, nullable=False)
    nome: Mapped[str | None] = mapped_column(Text)
    ie: Mapped[str | None] = mapped_column(String(20))
    uf: Mapped[str | None] = mapped_column(String(2))
    e_matriz: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    ativo: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    empresa: Mapped[EmpresaDB] = relationship(lazy="joined")


class ProjetoDB(Base):
    """Um trabalho contratado para uma empresa, numa frente e num período.

    Frente e competências são o que delimita o escopo: "CAT 42 da Sulamericana,
    01/2021 a 12/2025". Toda execução e toda entrega pendura aqui.
    """

    __tablename__ = "projeto"
    __table_args__ = (UniqueConstraint("empresa_id", "frente", "nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), nullable=False)
    frente: Mapped[str] = mapped_column(String(20), nullable=False)
    nome: Mapped[str] = mapped_column(Text, nullable=False)
    competencia_ini: Mapped[date] = mapped_column(Date, nullable=False)
    competencia_fim: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="em_andamento", nullable=False
    )
    observacao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )
    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))

    empresa: Mapped[EmpresaDB] = relationship(lazy="joined")

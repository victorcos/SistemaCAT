"""Conexão e sessão."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from cat.config import obter_config
from cat.infraestrutura.repositorios.modelos import Base

_cfg = obter_config()
_conectar_args = (
    {"check_same_thread": False} if _cfg.banco_url.startswith("sqlite") else {}
)

motor = create_engine(_cfg.banco_url, connect_args=_conectar_args, pool_pre_ping=True)
Sessao = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


def criar_tabelas() -> None:
    Base.metadata.create_all(motor)


def obter_sessao() -> Iterator[Session]:
    sessao = Sessao()
    try:
        yield sessao
    finally:
        sessao.close()

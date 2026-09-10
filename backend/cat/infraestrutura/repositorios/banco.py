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
    """Cria o esquema direto pelos modelos.

    Só para teste e para os comandos de linha. Em Postgres quem manda é a
    migração: `alembic upgrade head`. Criar tabela pela aplicação faria o
    esquema divergir do histórico de migrações sem ninguém perceber.
    """
    Base.metadata.create_all(motor)


def conferir_migracoes() -> None:
    """Avisa se o banco está atrás das migrações, em vez de criar tabela.

    Subir com esquema desatualizado dá erro obscuro na primeira consulta. Aqui
    o problema aparece na subida, com o comando que resolve.
    """
    from sqlalchemy import inspect

    from cat.log import obter_log

    log = obter_log(__name__)
    inspetor = inspect(motor)
    faltando = sorted(set(Base.metadata.tables) - set(inspetor.get_table_names()))
    if faltando:
        log.error(
            "banco sem as tabelas do sistema. Rode as migrações.",
            extra={"tabelas_faltando": faltando,
                   "acao": "cd backend && alembic upgrade head"},
        )


def obter_sessao() -> Iterator[Session]:
    sessao = Sessao()
    try:
        yield sessao
    finally:
        sessao.close()

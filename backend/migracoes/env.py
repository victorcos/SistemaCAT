"""Alembic — a URL do banco e os metadados vêm do próprio sistema.

Sem isto, o alembic.ini teria a senha do banco em texto claro e versionada.
Aqui ele lê a mesma configuração da aplicação, que vem de variável de ambiente.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from cat.config import obter_config
from cat.infraestrutura.repositorios.modelos import Base

config = context.config
config.set_main_option("sqlalchemy.url", obter_config().banco_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conectavel = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with conectavel.connect() as conexao:
        context.configure(
            connection=conexao,
            target_metadata=target_metadata,
            # sem isto, mudança de tipo de coluna passa despercebida
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

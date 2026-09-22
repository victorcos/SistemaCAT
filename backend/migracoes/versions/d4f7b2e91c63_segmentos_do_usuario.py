"""Segmentos tributários do usuário, e o módulo do trabalho.

Terceira dimensão de acesso, ao lado do papel e da alocação por empresa: em que
assunto a pessoa trabalha. Papel diz o QUE ela pode fazer, a alocação diz SOBRE
QUAIS EMPRESAS, e o segmento diz EM QUE ASSUNTO.

Gestor e dev não precisam de linha aqui: enxergam todo segmento por papel, pela
mesma razão que já ignoram o escopo de empresa.

O trabalho ganha `modulo` para a tela do segmento saber o que listar. Todo
trabalho que já existe é de ICMS — o sistema nasceu na CAT 42 —, então o padrão
é 'icms' e nenhuma linha antiga fica órfã.

Revision ID: d4f7b2e91c63
Revises: b2d8f41ac6e7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4f7b2e91c63"
down_revision = "b2d8f41ac6e7"
branch_labels = None
depends_on = None

MODULO_PADRAO = "icms"


def upgrade() -> None:
    op.create_table(
        "usuario_segmento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("segmento", sa.String(length=30), nullable=False),
        sa.Column("liberado_por", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("liberado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        # o mesmo segmento duas vezes para a mesma pessoa não quer dizer nada
        sa.UniqueConstraint("usuario_id", "segmento", name="uq_usuario_segmento"),
    )
    op.create_index("ix_usuario_segmento_usuario", "usuario_segmento", ["usuario_id"])

    op.add_column("projeto", sa.Column("modulo", sa.String(length=30), nullable=False,
                                       server_default=MODULO_PADRAO))
    op.create_index("ix_projeto_modulo", "projeto", ["modulo"])

    # Quem já trabalha aqui continua trabalhando. Sem este preenchimento, a
    # coluna nova nasceria negando tudo a todo mundo: ninguém tem segmento no
    # instante em que a tabela é criada, e analista, revisor e leitura ficariam
    # trancados fora do que usam todo dia. Todo trabalho que existe é de ICMS —
    # o sistema nasceu na CAT 42 —, então é esse o acesso que se preserva.
    #
    # Gestor e dev ficam de fora: enxergam todo segmento por papel, e gravar
    # linha para eles guardaria um dado que mente sobre o acesso real.
    op.execute(f"""
        INSERT INTO usuario_segmento (usuario_id, segmento)
        SELECT id, '{MODULO_PADRAO}' FROM usuario WHERE papel NOT IN ('gestor', 'dev')
    """)


def downgrade() -> None:
    op.drop_index("ix_projeto_modulo", table_name="projeto")
    op.drop_column("projeto", "modulo")
    op.drop_index("ix_usuario_segmento_usuario", table_name="usuario_segmento")
    op.drop_table("usuario_segmento")

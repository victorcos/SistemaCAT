"""execucao de processamento pesado

A extração completa de uma empresa lê mais de 100 GB e leva minutos, então não
cabe dentro da requisição. Cada rodada vira linha aqui, com o que leu e o que
produziu — é o que responde de onde veio um número meses depois.

Revision ID: d7f4b28c1a55
Revises: c3a91d5e7b40
Create Date: 2026-09-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7f4b28c1a55'
down_revision: Union[str, Sequence[str], None] = 'c3a91d5e7b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'execucao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('projeto_id', sa.Integer(), nullable=False),
        sa.Column('etapa', sa.String(length=30), nullable=False),
        sa.Column('situacao', sa.String(length=20),
                  server_default='na_fila', nullable=False),
        sa.Column('passo', sa.Text(), nullable=True),
        sa.Column('fracao', sa.Float(), server_default='0', nullable=False),
        sa.Column('arquivos_totais', sa.Integer(), server_default='0', nullable=False),
        sa.Column('arquivos_lidos', sa.Integer(), server_default='0', nullable=False),
        sa.Column('bytes_lidos', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('documentos', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('pasta_de_trabalho', sa.Text(), nullable=True),
        sa.Column('resumo', sa.JSON(), nullable=True),
        sa.Column('erro', sa.Text(), nullable=True),
        sa.Column('iniciada_em', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('terminada_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('criada_por', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['projeto_id'], ['projeto.id'], ),
        sa.ForeignKeyConstraint(['criada_por'], ['usuario.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_execucao_projeto', 'execucao', ['projeto_id', 'etapa'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_execucao_projeto', table_name='execucao')
    op.drop_table('execucao')

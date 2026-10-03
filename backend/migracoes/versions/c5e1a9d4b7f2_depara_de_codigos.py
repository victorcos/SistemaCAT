"""depara de codigos

O mesmo produto escriturado com codigos diferentes (compra com o codigo do
fornecedor ou com sufixo, kit, marketplace) vira um par aprovado pelo analista,
que o razao aplica. O par e da empresa, nao do trabalho. Decisao do Victor,
16/09/2026, a partir da CAT 42 da empresa D.

Revision ID: c5e1a9d4b7f2
Revises: b8d3e61f2a47
Create Date: 2026-09-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c5e1a9d4b7f2'
down_revision: Union[str, Sequence[str], None] = 'b8d3e61f2a47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'depara_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('cnpj', sa.String(length=14), server_default='', nullable=False),
        sa.Column('codigo_origem', sa.Text(), nullable=False),
        sa.Column('codigo_destino', sa.Text(), nullable=False),
        sa.Column('fator', sa.Numeric(precision=24, scale=9), server_default='1', nullable=False),
        sa.Column('motivo', sa.String(length=20), nullable=False),
        sa.Column('situacao', sa.String(length=12), nullable=False),
        sa.Column('confianca', sa.String(length=10), nullable=True),
        sa.Column('explicacao', sa.Text(), nullable=True),
        sa.Column('projeto_id', sa.Integer(), nullable=True),
        sa.Column('decidido_por', sa.Integer(), nullable=True),
        sa.Column('decidido_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresa.id'], ),
        sa.ForeignKeyConstraint(['projeto_id'], ['projeto.id'], ),
        sa.ForeignKeyConstraint(['decidido_por'], ['usuario.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('empresa_id', 'cnpj', 'codigo_origem', name='uq_depara_origem'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('depara_item')

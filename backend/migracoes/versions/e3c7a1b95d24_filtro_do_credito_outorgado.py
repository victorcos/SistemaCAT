"""filtro do credito outorgado

Quais produtos tem o beneficio, por trabalho: as NCM e os termos de descricao
que a triagem usa. E do trabalho, e nao da empresa, porque o credito outorgado
e concedido por lei estadual a uma lista de mercadorias que muda com o estado e
com o periodo. Cai em cascata com o projeto, como o evento do projeto.

Revision ID: e3c7a1b95d24
Revises: d4f7b2e91c63
Create Date: 2026-09-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e3c7a1b95d24'
down_revision: Union[str, Sequence[str], None] = 'd4f7b2e91c63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'credito_outorgado_filtro',
        sa.Column('projeto_id', sa.Integer(), nullable=False),
        sa.Column('ncms', sa.JSON(), nullable=False),
        sa.Column('termos', sa.JSON(), nullable=False),
        sa.Column('sem_filtro', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('guardar_descartados', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('atualizado_em', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('atualizado_por', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['projeto_id'], ['projeto.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['atualizado_por'], ['usuario.id']),
        sa.PrimaryKeyConstraint('projeto_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('credito_outorgado_filtro')

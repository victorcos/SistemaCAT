"""aprovacao da entrega

A etapa 8 (relatorios e entrega) nao conclui ao gerar o pacote: um revisor ou
gestor confere e aprova. Quem aprovou e quando ficam na propria execucao, em
coluna e nao no resumo, porque o resumo e do motor e a aprovacao e da API.
Decisao do Victor, 16/09/2026.

Revision ID: b8d3e61f2a47
Revises: a6c2e9f13d80
Create Date: 2026-09-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8d3e61f2a47'
down_revision: Union[str, Sequence[str], None] = 'a6c2e9f13d80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('execucao', sa.Column('aprovada_por', sa.Integer(), nullable=True))
    op.add_column('execucao', sa.Column('aprovada_em', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key('fk_execucao_aprovada_por_usuario', 'execucao', 'usuario', ['aprovada_por'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_execucao_aprovada_por_usuario', 'execucao', type_='foreignkey')
    op.drop_column('execucao', 'aprovada_em')
    op.drop_column('execucao', 'aprovada_por')

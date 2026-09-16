"""venda a consumidor no projeto

Como o trabalho enquadra a venda a consumidor final: no enquadramento 1, como
diz o manual (ressarcimento e complemento), ou nas demais saidas, como a IRMAOS
BOA transmitiu o cupom (so a perda e a interestadual geram ressarcimento).
Decisao do Victor, 16/09/2026: e escolha de cada trabalho. Todo trabalho que
ja existe fica no enquadramento 1, que e como o razao ja vinha montando.

Revision ID: a6c2e9f13d80
Revises: c24f9ed57d0f
Create Date: 2026-09-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a6c2e9f13d80'
down_revision: Union[str, Sequence[str], None] = 'c24f9ed57d0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('projeto',
                  sa.Column('venda_a_consumidor', sa.String(length=20), nullable=False,
                            server_default='enquadramento_1'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projeto', 'venda_a_consumidor')

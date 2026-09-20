"""valor anterior na correcao

O historico do trabalho mostra o antes e o depois de cada alteracao, e para isso
a correcao guarda o valor que estava la quando alguem a fez. Pedido do Victor,
20/09/2026.

Revision ID: b2d8f41ac6e7
Revises: a1c7e39d5b82
Create Date: 2026-09-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d8f41ac6e7"
down_revision: Union[str, Sequence[str], None] = "a1c7e39d5b82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("correcao", sa.Column("valor_anterior", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("correcao", "valor_anterior")

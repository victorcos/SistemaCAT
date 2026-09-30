"""selic mensal

A taxa Selic de cada mes, guardada para nunca mais ser buscada. Mes fechado nao
muda: a de marco de 2021 hoje e a mesma de daqui a dez anos. Guardando, a
correcao do indebito nao depende de a API do Banco Central estar no ar — a
rodada so sai a rede pelos meses que ainda faltam.

Nao tem empresa nem projeto: a Selic e a mesma para todo mundo.

Revision ID: f5b81e3c2a97
Revises: e3c7a1b95d24
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f5b81e3c2a97'
down_revision: Union[str, Sequence[str], None] = 'e3c7a1b95d24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'selic_mensal',
        # "aaaa-mm". Texto, e nao data: o que existe e o mes, e a ordenacao de
        # texto neste formato ja e cronologica
        sa.Column('competencia', sa.String(length=7), nullable=False),
        # em por cento no mes, como o Banco Central publica
        sa.Column('taxa', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('fonte', sa.String(length=20), nullable=False),
        sa.Column('obtida_em', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('competencia'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('selic_mensal')

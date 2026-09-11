"""retificadora no arquivo do lote

O registro 0000 diz se a EFD e original ou retificadora, e a retificadora
substitui a original do mesmo estabelecimento e periodo por inteiro. Sem guardar
isso, a conferencia lia as duas: dobrava os documentos do periodo e misturava
valores de antes e depois da retificacao.

Revision ID: e8b2c7d41f09
Revises: d7f4b28c1a55
Create Date: 2026-09-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e8b2c7d41f09'
down_revision: Union[str, Sequence[str], None] = 'd7f4b28c1a55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default porque a tabela ja tem linhas: sem ele, NOT NULL falha
    op.add_column(
        'arquivo_do_lote',
        sa.Column('retificadora', sa.Boolean(), server_default='false',
                  nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('arquivo_do_lote', 'retificadora')

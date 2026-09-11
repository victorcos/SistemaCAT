"""hash de conteudo no arquivo do lote

A importacao deduplicava por caminho: o mesmo SPED copiado em duas pastas
entrava duas vezes e dobrava os documentos do periodo. O hash (SHA-256) so e
calculado para candidatos a copia -- mesmo tamanho, tipo, CNPJ, competencia e
finalidade -- e fica gravado para a proxima importacao comparar. Vazio para
tudo que foi importado antes desta regra.

Revision ID: f1a4c9e27b63
Revises: e8b2c7d41f09
Create Date: 2026-09-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a4c9e27b63'
down_revision: Union[str, Sequence[str], None] = 'e8b2c7d41f09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('arquivo_do_lote',
                  sa.Column('hash_conteudo', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('arquivo_do_lote', 'hash_conteudo')

"""aliquota de item

A aliquota de ICMS de um produto, quando ela foge da regra do estado. Serve ao
ICMS-ST presumido do relatorio 839: o ST que se exclui da base do PIS/COFINS e
base vezes aliquota, e a aliquota tem duas metades. A regra -- interna do estado,
ou a Resolucao 22/1989 do Senado na interestadual -- e lei, e mora no codigo. A
excecao e classificacao fiscal de mercadoria, e e esta tabela.

Esta no banco porque e dado de cliente: codigo de item e do ERP de quem o
cadastrou, e versionar isso no repositorio seria publicar a carteira de produtos
de quem nos contratou.

Revision ID: a7d3f18b264e
Revises: f5b81e3c2a97
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7d3f18b264e'
down_revision: Union[str, Sequence[str], None] = 'f5b81e3c2a97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'aliquota_de_item',
        # o estabelecimento, e nao a empresa: a mesma mercadoria pode ter
        # tratamento diferente em filiais de estados diferentes
        sa.Column('cnpj', sa.String(length=14), nullable=False),
        sa.Column('uf_origem', sa.String(length=2), nullable=False),
        sa.Column('uf_destino', sa.String(length=2), nullable=False),
        sa.Column('codigo_do_item', sa.String(length=60), nullable=False),
        # em por cento: 12 e 12%
        sa.Column('aliquota', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('fonte', sa.String(length=20), nullable=False),
        sa.Column('atualizada_em', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('cnpj', 'uf_origem', 'uf_destino', 'codigo_do_item'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('aliquota_de_item')

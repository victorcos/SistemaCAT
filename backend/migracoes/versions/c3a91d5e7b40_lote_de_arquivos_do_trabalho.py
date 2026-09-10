"""lote de arquivos do trabalho

Separa a entrada de dados do cadastro. O cadastro cria empresa e projeto a
partir de uma amostra do SPED; o lote registra a base de trabalho inteira, que
mora em pasta de rede e volta mais de uma vez.

Revision ID: c3a91d5e7b40
Revises: 62fe3d195ce5
Create Date: 2026-09-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3a91d5e7b40'
down_revision: Union[str, Sequence[str], None] = '62fe3d195ce5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'lote',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('projeto_id', sa.Integer(), nullable=False),
        sa.Column('pasta', sa.Text(), nullable=False),
        sa.Column('total_arquivos', sa.Integer(), server_default='0', nullable=False),
        sa.Column('arquivos_uteis', sa.Integer(), server_default='0', nullable=False),
        sa.Column('bytes_totais', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('competencia_ini', sa.Date(), nullable=True),
        sa.Column('competencia_fim', sa.Date(), nullable=True),
        sa.Column('observacao', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('criado_por', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['projeto_id'], ['projeto.id'], ),
        sa.ForeignKeyConstraint(['criado_por'], ['usuario.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lote_projeto', 'lote', ['projeto_id'])

    op.create_table(
        'arquivo_do_lote',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lote_id', sa.Integer(), nullable=False),
        sa.Column('caminho', sa.Text(), nullable=False),
        sa.Column('nome', sa.Text(), nullable=False),
        sa.Column('tamanho', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('cnpj', sa.String(length=14), nullable=True),
        sa.Column('competencia', sa.Date(), nullable=True),
        sa.Column('uf', sa.String(length=2), nullable=True),
        sa.Column('detalhe', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['lote_id'], ['lote.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lote_id', 'caminho'),
    )
    op.create_index('ix_arquivo_do_lote_tipo', 'arquivo_do_lote',
                    ['lote_id', 'tipo'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_arquivo_do_lote_tipo', table_name='arquivo_do_lote')
    op.drop_table('arquivo_do_lote')
    op.drop_index('ix_lote_projeto', table_name='lote')
    op.drop_table('lote')

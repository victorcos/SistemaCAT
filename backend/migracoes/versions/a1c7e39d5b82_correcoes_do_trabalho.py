"""correcoes do trabalho

O que uma pessoa corrige a mao no que o sistema calculou: aliquota e reducao da
mercadoria, enquadramento, quantidade, valor e ICMS de uma linha, e tirar ou
trazer de volta a linha da ficha. E do trabalho, nao da empresa, e nao apaga o
dado de origem: fica ao lado, com autor, data e motivo. Decisao do Victor,
20/09/2026.

Revision ID: a1c7e39d5b82
Revises: c5e1a9d4b7f2
Create Date: 2026-09-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c7e39d5b82"
down_revision: Union[str, Sequence[str], None] = "c5e1a9d4b7f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "correcao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("projeto_id", sa.Integer(), nullable=False),
        sa.Column("campo", sa.String(length=20), nullable=False),
        # o alvo: mercadoria (cnpj + codigo) ou linha (cnpj + documento + item)
        sa.Column("cnpj", sa.String(length=14), server_default="", nullable=False),
        sa.Column("codigo", sa.Text(), server_default="", nullable=False),
        sa.Column("documento", sa.Text(), server_default="", nullable=False),
        sa.Column("numero_item", sa.Integer(), nullable=True),
        # o valor vai como texto: cada campo tem o seu tipo, e o dominio converte
        sa.Column("valor", sa.Text(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("situacao", sa.String(length=10), server_default="ativa", nullable=False),
        sa.Column("criada_por", sa.Integer(), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("desfeita_por", sa.Integer(), nullable=True),
        sa.Column("desfeita_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["projeto_id"], ["projeto.id"], ),
        sa.ForeignKeyConstraint(["criada_por"], ["usuario.id"], ),
        sa.ForeignKeyConstraint(["desfeita_por"], ["usuario.id"], ),
        sa.PrimaryKeyConstraint("id"),
        # uma correcao ativa por alvo e campo: corrigir de novo substitui
        sa.UniqueConstraint("projeto_id", "campo", "cnpj", "codigo", "documento", "numero_item",
                            name="uq_correcao_alvo"),
    )
    op.create_index("ix_correcao_projeto", "correcao", ["projeto_id", "situacao"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_correcao_projeto", table_name="correcao")
    op.drop_table("correcao")

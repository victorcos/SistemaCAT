"""tiquete de download em cascata

A chave estrangeira do tiquete para `execucao` nascera sem cascata, e com isso
qualquer tiquete deixado para tras travava a exclusao do trabalho inteiro --
erro 23503 na tela, ao apagar um projeto. Um tiquete vive dois minutos e nao
pode ser o que impede apagar nada.

Mesma coisa para `usuario`: apagar quem baixou um arquivo nao pode esbarrar num
tiquete vencido.

Revision ID: d1a5c38e7b94
Revises: c4e07a91d5b2
Create Date: 2026-10-02

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1a5c38e7b94'
down_revision: Union[str, Sequence[str], None] = 'c4e07a91d5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FKS = (
    ("tiquete_de_download_execucao_id_fkey", "execucao_id", "execucao"),
    ("tiquete_de_download_usuario_id_fkey", "usuario_id", "usuario"),
)


def upgrade() -> None:
    """Upgrade schema."""
    for nome, coluna, alvo in _FKS:
        op.drop_constraint(nome, "tiquete_de_download", type_="foreignkey")
        op.create_foreign_key(nome, "tiquete_de_download", alvo,
                              [coluna], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    """Downgrade schema."""
    for nome, coluna, alvo in _FKS:
        op.drop_constraint(nome, "tiquete_de_download", type_="foreignkey")
        op.create_foreign_key(nome, "tiquete_de_download", alvo, [coluna], ["id"])

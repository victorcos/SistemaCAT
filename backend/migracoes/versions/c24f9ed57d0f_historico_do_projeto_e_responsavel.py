"""Histórico do projeto e responsável.

Duas coisas que faltavam para o trabalho ter memória:

* `evento_do_projeto` — a linha do tempo: o que o sistema fez e o que a
  pessoa comentou, na ordem em que aconteceu;
* `projeto.responsavel_id` — quem responde pelo trabalho hoje, que nem
  sempre é quem o criou.

Os projetos que já existem herdam o criador como responsável: é a verdade
mais próxima disponível, e melhor que deixar todos sem dono.

Nota sobre o autogenerate: ele propôs derrubar `ix_lote_projeto`, que é um
índice real e em uso. Falso positivo — o índice está declarado no modelo com
nome explícito e ele não reconheceu. Removido daqui à mão.

Revision ID: c24f9ed57d0f
Revises: f1a4c9e27b63
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c24f9ed57d0f"
down_revision: Union[str, Sequence[str], None] = "f1a4c9e27b63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evento_do_projeto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("projeto_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("dados", sa.JSON(), nullable=True),
        sa.Column("autor_id", sa.Integer(), nullable=True),
        sa.Column("autor_nome", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["autor_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["projeto_id"], ["projeto.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evento_projeto", "evento_do_projeto", ["projeto_id", "criado_em"]
    )

    # batch_alter_table e nao add_column + create_foreign_key: SQLite nao tem
    # ALTER de constraint, e o batch copia-e-move resolve. No Postgres vira o
    # ALTER normal, com o mesmo resultado.
    #
    # Nota: a cadeia de migracoes ainda NAO roda inteira em SQLite — a de
    # 62fe3d195ce5 usa create_foreign_key direto e quebra la. E anterior a
    # esta e nao se conserta aqui; fica registrado para quando o caminho sem
    # Docker do instalar.ps1 for exercitado de verdade.
    with op.batch_alter_table("projeto") as lote:
        lote.add_column(sa.Column("responsavel_id", sa.Integer(), nullable=True))
        lote.create_foreign_key(
            "fk_projeto_responsavel", "usuario", ["responsavel_id"], ["id"]
        )
    op.execute(
        "UPDATE projeto SET responsavel_id = criado_por WHERE responsavel_id IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("projeto") as lote:
        lote.drop_constraint("fk_projeto_responsavel", type_="foreignkey")
        lote.drop_column("responsavel_id")
    op.drop_index("ix_evento_projeto", table_name="evento_do_projeto")
    op.drop_table("evento_do_projeto")

"""tiquete de download

Autorizacao de um download, de vida curta, para baixar por navegacao.

O front baixava com fetch e blob -- o arquivo inteiro na memoria da aba antes de
gravar. Numa lista de 2,93 milhoes de linhas isso nao passa, e o servidor ja
servia do disco em fluxo: todo o desperdicio estava no navegador. A saida e
deixar o navegador baixar, por navegacao, com o gerenciador dele gravando direto
no disco. Mas navegacao nao manda cabecalho Authorization, e e para isso que o
tiquete serve.

No banco e nao em memoria porque havera mais de uma instancia da API: tiquete
emitido numa e resgatado noutra tem de ser encontrado.

Revision ID: c4e07a91d5b2
Revises: a7d3f18b264e
Create Date: 2026-10-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e07a91d5b2'
down_revision: Union[str, Sequence[str], None] = 'a7d3f18b264e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tiquete_de_download',
        # o proprio segredo e a chave: 32 bytes aleatorios em base64url
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('execucao_id', sa.Integer(), nullable=False),
        # a etapa pela qual a tela pediu, de quem e o catalogo de planilhas
        sa.Column('etapa', sa.String(length=30), nullable=False),
        sa.Column('qual', sa.String(length=40), nullable=False),
        sa.Column('formato', sa.String(length=10), nullable=False),
        # o recorte: lista diferente e arquivo diferente, e o tiquete autoriza um
        sa.Column('modelos', sa.Text(), nullable=True),
        sa.Column('classificacoes', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        # primeiro resgate. Auditoria, nao trava: o gerenciador de download do
        # navegador repete a requisicao, e recusar a repeticao transformaria um
        # soluco de rede em "o link morreu". O que protege e o prazo
        sa.Column('usado_em', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['execucao_id'], ['execucao.id']),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # a limpeza dos vencidos varre por este indice ao emitir um novo tiquete:
    # sem tarefa agendada, e sem a tabela crescer para sempre
    op.create_index('ix_tiquete_expira', 'tiquete_de_download', ['expira_em'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_tiquete_expira', table_name='tiquete_de_download')
    op.drop_table('tiquete_de_download')

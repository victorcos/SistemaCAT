"""Remover um lote de dentro de um trabalho.

Desfaz a importação, não o dado do cliente: o lote é o registro de onde os
arquivos estão, e eles continuam no servidor de arquivos. Fica com o motor
porque é da rota de lotes (docs/MIGRACAO_CSHARP.md, fatia 5).

Apagar o trabalho inteiro — a outra operação destrutiva, a que pede a senha de
novo — mora na API em C# desde 13/09/2026. As pastas de trabalho que ele leva
junto são apagadas aqui, pelo canal interno (routers/interno_router.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cat.dominio.acesso.usuario import Usuario
from cat.infraestrutura.repositorios.modelos import (
    ArquivoDoLoteDB,
    ExecucaoDB,
    LoteDB,
)
from cat.log import obter_log

log = obter_log(__name__)


class TrabalhoNaoEncontrado(LookupError):
    pass


@dataclass(frozen=True)
class LoteApagado:
    pasta: str
    arquivos: int
    conferencias_invalidadas: int


def excluir_lote(lote_id: int, usuario: Usuario, sessao: Session) -> LoteApagado:
    """Tira um lote do trabalho. Os arquivos em disco não são tocados.

    O lote é só o registro de onde os arquivos estão — apagá-lo desfaz a
    importação, não o dado do cliente, que continua no servidor de arquivos.
    """
    lote = sessao.get(LoteDB, lote_id)
    if lote is None:
        raise TrabalhoNaoEncontrado(lote_id)

    arquivos = sessao.scalar(
        select(func.count()).select_from(ArquivoDoLoteDB)
        .where(ArquivoDoLoteDB.lote_id == lote_id)) or 0
    # toda conferência já feita olhou este lote; tirá-lo muda o resultado
    conferencias = sessao.scalar(
        select(func.count()).select_from(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == lote.projeto_id,
               ExecucaoDB.situacao == "concluida")) or 0

    pasta, projeto_id = lote.pasta, lote.projeto_id
    sessao.execute(delete(ArquivoDoLoteDB).where(ArquivoDoLoteDB.lote_id == lote_id))
    sessao.execute(delete(LoteDB).where(LoteDB.id == lote_id))
    sessao.commit()

    log.warning(
        "lote removido do trabalho",
        extra={"lote_id": lote_id, "projeto_id": projeto_id, "pasta": pasta,
               "arquivos": arquivos, "conferencias_afetadas": conferencias,
               "por_usuario_id": usuario.id, "por_usuario": usuario.usuario},
    )
    return LoteApagado(pasta=pasta, arquivos=arquivos,
                       conferencias_invalidadas=conferencias)

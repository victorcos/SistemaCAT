"""Apagar um trabalho, e apagar um lote de dentro dele.

São as duas únicas operações destrutivas do sistema, e por isso ficam num
módulo só: quem for mexer aqui vê as duas de uma vez e enxerga o que cada uma
leva junto.

**Apagar o trabalho pede a senha de novo.** Não é desconfiança de quem está
logado — é o mesmo motivo pelo qual banco pede senha para transferir depois de
você já ter entrado: a sessão fica aberta o dia inteiro, e uma tela deixada em
máquina destravada não pode ser suficiente para desfazer meses de apuração. É a
única operação do sistema que exige isso.

**Nada disso é reversível.** Não há lixeira, e é decisão consciente: manter
projeto apagado meio-vivo no banco cria dois estados para tudo o que consulta
projeto, e mais cedo ou mais tarde alguém conta um trabalho excluído num
relatório. O que fica é o registro no log — quem apagou, quando, e quanto
havia dentro.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cat.dominio.acesso.usuario import Usuario
from cat.infraestrutura.repositorios.modelos import (
    ArquivoDoLoteDB,
    ExecucaoDB,
    LoteDB,
    ProjetoDB,
)
from cat.log import obter_log

log = obter_log(__name__)


class SenhaNaoConfere(PermissionError):
    """A senha informada na confirmação não é a do usuário."""


class TrabalhoNaoEncontrado(LookupError):
    pass


@dataclass(frozen=True)
class OQueSeraApagado:
    """O que a tela mostra antes de o usuário confirmar.

    Existe para a confirmação ser informada: "apagar o trabalho?" é uma
    pergunta muito diferente de "apagar o trabalho, 3 lotes, 7.036 arquivos e
    2 conferências?".
    """

    projeto: str
    empresa: str
    lotes: int
    arquivos: int
    execucoes: int


def resumir(projeto_id: int, sessao: Session) -> OQueSeraApagado:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is None:
        raise TrabalhoNaoEncontrado(projeto_id)

    lotes = sessao.scalar(
        select(func.count()).select_from(LoteDB)
        .where(LoteDB.projeto_id == projeto_id)) or 0
    arquivos = sessao.scalar(
        select(func.count()).select_from(ArquivoDoLoteDB)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .where(LoteDB.projeto_id == projeto_id)) or 0
    execucoes = sessao.scalar(
        select(func.count()).select_from(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == projeto_id)) or 0

    return OQueSeraApagado(
        projeto=projeto.nome,
        empresa=projeto.empresa.razao_social if projeto.empresa else "",
        lotes=lotes, arquivos=arquivos, execucoes=execucoes,
    )


def excluir_trabalho(projeto_id: int, usuario: Usuario, senha: str,
                     sessao: Session, senhas, repositorio) -> OQueSeraApagado:
    """Apaga o projeto e tudo que pendura nele. Exige a senha do usuário."""
    resumo = resumir(projeto_id, sessao)

    if not senha or not senhas.conferir(senha, repositorio.obter_hash_senha(usuario.id)):
        # não incrementa a trava de login de propósito: errar a senha ao
        # confirmar uma exclusão não pode bloquear o acesso da pessoa ao
        # sistema inteiro. Mas fica no log como evento de segurança.
        log.warning(
            "senha incorreta na confirmação de exclusão de trabalho",
            extra={"usuario_id": usuario.id, "usuario": usuario.usuario,
                   "projeto_id": projeto_id},
        )
        raise SenhaNaoConfere

    execucoes = list(sessao.scalars(
        select(ExecucaoDB).where(ExecucaoDB.projeto_id == projeto_id)))
    for execucao in execucoes:
        _apagar_pasta(execucao.pasta_de_trabalho)

    lotes = list(sessao.scalars(
        select(LoteDB.id).where(LoteDB.projeto_id == projeto_id)))
    if lotes:
        sessao.execute(
            delete(ArquivoDoLoteDB).where(ArquivoDoLoteDB.lote_id.in_(lotes)))
    sessao.execute(delete(ExecucaoDB).where(ExecucaoDB.projeto_id == projeto_id))
    sessao.execute(delete(LoteDB).where(LoteDB.projeto_id == projeto_id))
    sessao.execute(delete(ProjetoDB).where(ProjetoDB.id == projeto_id))
    sessao.commit()

    # o log é o que resta: não há lixeira, então o registro de quem apagou o
    # quê precisa ser completo o bastante para responder meses depois
    log.warning(
        "trabalho excluído",
        extra={"projeto_id": projeto_id, "projeto": resumo.projeto,
               "empresa": resumo.empresa, "lotes": resumo.lotes,
               "arquivos": resumo.arquivos, "execucoes": resumo.execucoes,
               "por_usuario_id": usuario.id, "por_usuario": usuario.usuario,
               "papel": usuario.papel.value},
    )
    return resumo


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


def _apagar_pasta(caminho: str | None) -> None:
    if caminho:
        shutil.rmtree(caminho, ignore_errors=True)

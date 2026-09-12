"""Histórico de movimentação: os itens da EFD, marcados pela conferência.

Terceira etapa. Mesmo desenho da conferência: a rodada não cabe numa
requisição, então se cria a execução, se devolve o identificador e o front
acompanha. As planilhas saem depois, por download, a partir dos parquets da
própria execução.

* **movimentos** — cada C170/C810 com cadastro e marca da conferência;
* **itens** — o cadastro 0200 que vale;
* **inventario** — o bloco H, item a item;
* **analitico** — C190/C850 por documento, com `tem_item`.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.extrair_movimentos import (
    ETAPA,
    NadaParaExtrair,
    executar,
    preparar,
)
from cat.apresentacao.api.routers.conferencia_router import (
    SITUACOES_EM_CURSO,
    TIPOS,
    ExecucaoDto,
    PodeEscrever,
    _conjunto,
    _dto,
    _execucao,
    _precisa_gerar,
    _projeto,
)
from cat.aplicacao.casos_de_uso.historico_do_projeto import TrabalhoParado
from cat.apresentacao.api.seguranca import UsuarioAtual
from cat.infraestrutura.analitico.movimentacao import (
    ARQUIVO_ANALITICO,
    ARQUIVO_ITENS,
    ARQUIVO_MOVIMENTOS,
)
from cat.infraestrutura.analitico.movimentos import ARQUIVO_INVENTARIO
from cat.infraestrutura.planilhas.conferencia import FORMATOS
from cat.infraestrutura.planilhas.movimentacao import (
    gerar_analitico,
    gerar_inventario,
    gerar_itens,
    gerar_movimentos,
)
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB
from cat.infraestrutura.tarefas import disparar
from cat.log import contexto, obter_log

log = obter_log(__name__)
router = APIRouter(prefix="/api", tags=["movimentos"])

PLANILHAS = {
    "movimentos": ("movimentos.xlsx", ARQUIVO_MOVIMENTOS, gerar_movimentos),
    "itens": ("itens.xlsx", ARQUIVO_ITENS, gerar_itens),
    "inventario": ("inventario.xlsx", ARQUIVO_INVENTARIO, gerar_inventario),
    "analitico": ("analitico.xlsx", ARQUIVO_ANALITICO, gerar_analitico),
}


def _desta_etapa(execucao_id: int, usuario, sessao: Session) -> ExecucaoDB:
    execucao = _execucao(execucao_id, usuario, sessao)
    if execucao.etapa != ETAPA:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Execução não encontrada.")
    return execucao


@router.post("/projetos/{projeto_id}/movimentos", response_model=ExecucaoDto,
             status_code=status.HTTP_202_ACCEPTED)
def iniciar(
    projeto_id: int,
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> ExecucaoDto:
    _projeto(projeto_id, usuario, sessao)
    em_curso = sessao.scalar(
        select(ExecucaoDB).where(
            ExecucaoDB.projeto_id == projeto_id,
            ExecucaoDB.etapa == ETAPA,
            ExecucaoDB.situacao.in_(SITUACOES_EM_CURSO),
        )
    )
    if em_curso is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Já existe uma extração de movimentos em andamento neste trabalho.",
        )

    with contexto(etapa=ETAPA, usuario_id=usuario.id, projeto_id=projeto_id):
        try:
            execucao = preparar(projeto_id, usuario.id, sessao)
        except (TrabalhoParado, NadaParaExtrair) as erro:
            log.warning("extração de movimentos recusada", extra={"motivo": str(erro)})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)
            ) from erro

        disparar(executar, execucao.id)
        log.info("extração de movimentos iniciada",
                 extra={"execucao_id": execucao.id,
                        "arquivos": execucao.arquivos_totais})
        return _dto(execucao)


@router.get("/projetos/{projeto_id}/movimentos", response_model=list[ExecucaoDto])
def listar(
    projeto_id: int,
    usuario: UsuarioAtual,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> list[ExecucaoDto]:
    _projeto(projeto_id, usuario, sessao)
    linhas = sessao.scalars(
        select(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == projeto_id, ExecucaoDB.etapa == ETAPA)
        .order_by(ExecucaoDB.id.desc())
        .limit(20)
    ).all()
    return [_dto(e) for e in linhas]


@router.get("/movimentos/{execucao_id}", response_model=ExecucaoDto)
def detalhar(
    execucao_id: int,
    usuario: UsuarioAtual,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> ExecucaoDto:
    return _dto(_desta_etapa(execucao_id, usuario, sessao))


@router.get("/movimentos/{execucao_id}/planilhas/{qual}")
def baixar_planilha(
    execucao_id: int,
    qual: str,
    usuario: UsuarioAtual,
    sessao: Annotated[Session, Depends(obter_sessao)],
    modelos: str | None = None,
    classificacoes: str | None = None,
    formato: str = "xlsx",
) -> FileResponse:
    if qual not in PLANILHAS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Planilha desconhecida.")
    if formato not in FORMATOS:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Formato desconhecido: {formato}. Vale xlsx ou csv.",
        )

    execucao = _desta_etapa(execucao_id, usuario, sessao)
    if execucao.situacao != "concluida":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "A extração ainda não terminou.")

    nome, parquet, gerador = PLANILHAS[qual]
    escolhidos = _conjunto(modelos)
    classes = _conjunto(classificacoes)
    pasta = execucao.pasta_de_trabalho or ""
    origem = os.path.join(pasta, parquet)
    if not os.path.isfile(origem):
        raise HTTPException(
            status.HTTP_410_GONE,
            "Os arquivos desta extração não estão mais em disco. Rode de novo.",
        )

    partes = sorted(escolhidos or ()) + sorted(classes or ())
    sufixo = "-" + "_".join(partes) if partes else ""
    raiz, _ = os.path.splitext(nome)
    # o formato entra no nome do cache: sem isso o xlsx já gerado responderia
    # ao pedido de csv, porque os dois só se diferenciavam pelo filtro
    destino = os.path.join(pasta, f"{raiz}{sufixo}.{formato}")
    if _precisa_gerar(destino, origem):
        with contexto(etapa=ETAPA, execucao_id=execucao_id, planilha=qual):
            linhas = gerador(origem, destino, escolhidos, classes,
                             formato=formato)
            log.info("planilha de movimentos gerada",
                     extra={"planilha": qual, "linhas": linhas,
                            "formato": formato})

    return FileResponse(
        destino,
        media_type=TIPOS[formato],
        filename=os.path.basename(destino),
    )

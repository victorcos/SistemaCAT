"""Canal interno com a API em C#. Não é rota de gente.

A API em C# decide se a pessoa pode; o motor faz o que é de disco. Este canal
existe para isso (docs/MIGRACAO_CSHARP.md §4) e tem três portas fechadas:

1. o motor só escuta em 127.0.0.1 (scripts/subir.ps1);
2. o repasse público do C# leva só /api, /docs e /openapi.json — /interno nunca
   chega aqui vindo da tela (e, desde a fatia 5, nada de /api chega mais);
3. toda chamada traz o segredo compartilhado CAT_MOTOR_SEGREDO. Sem ele
   configurado, o canal fica fechado para todo mundo, em vez de aberto.

O que passa por aqui é o que lê ou apaga disco: apagar pasta de trabalho,
inspecionar a pasta de um lote e analisar a remessa enviada. A regra de quem
pode, o registro no banco e a resposta à tela ficam no C#.

**Apagar pasta só dentro da pasta de trabalho.** O Python apagava o caminho que
estivesse gravado na execução, sem conferir. Um valor torto no banco — ou uma
pasta de trabalho trocada no .env — mandava apagar outra coisa. Agora o que está
fora da raiz é recusado e volta dito, e a própria raiz também.
"""

from __future__ import annotations

import hmac
import os
import shutil
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.analisar_remessa import RemessaAnalisada, analisar
from cat.aplicacao.casos_de_uso.inspecionar_lote import (
    PastaInvalida,
    ProjetoInexistente,
    inspecionar_do_projeto,
)
from cat.config import obter_config
from cat.dominio.comum.cnpj import Cnpj
from cat.infraestrutura.arquivos.remessa import RemessaInvalida, percorrer
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.log import contexto, obter_log

log = obter_log(__name__)
router = APIRouter(prefix="/interno", tags=["interno"], include_in_schema=False)


def exigir_segredo(
    x_cat_motor_segredo: Annotated[str | None, Header()] = None,
) -> None:
    esperado = obter_config().motor_segredo
    if not esperado:
        log.error("canal interno chamado sem CAT_MOTOR_SEGREDO configurado no motor",
                  extra={"acao": "definir CAT_MOTOR_SEGREDO"})
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "CAT_MOTOR_SEGREDO não está definido no motor.")
    if not x_cat_motor_segredo or not hmac.compare_digest(
        x_cat_motor_segredo.encode(), esperado.encode()
    ):
        log.warning("canal interno recusou chamada sem o segredo certo")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Segredo do canal interno não confere.")


class PedidoApagarPastas(BaseModel):
    pastas: list[str]


class PastasApagadas(BaseModel):
    apagadas: list[str]
    recusadas: list[str]


def _dentro_da_raiz(pasta: str, raiz: str) -> bool:
    alvo = os.path.realpath(pasta)
    try:
        # commonpath recusa caminhos em unidades diferentes no Windows
        return alvo != raiz and os.path.commonpath([raiz, alvo]) == raiz
    except ValueError:
        return False


@router.post("/pastas/apagar", response_model=PastasApagadas,
             dependencies=[Depends(exigir_segredo)])
def apagar_pastas(pedido: PedidoApagarPastas) -> PastasApagadas:
    raiz = os.path.realpath(obter_config().raiz_de_trabalho)
    apagadas: list[str] = []
    recusadas: list[str] = []
    for pasta in pedido.pastas:
        if not pasta or not _dentro_da_raiz(pasta, raiz):
            recusadas.append(pasta)
            continue
        shutil.rmtree(os.path.realpath(pasta), ignore_errors=True)
        apagadas.append(pasta)

    (log.warning if recusadas else log.info)(
        "pastas de trabalho apagadas a pedido da API",
        extra={"apagadas": len(apagadas), "recusadas": recusadas, "raiz": raiz},
    )
    return PastasApagadas(apagadas=apagadas, recusadas=recusadas)


# ---------------------------------------------------------------------------
# Lote: o que a pasta tem para um trabalho
# ---------------------------------------------------------------------------
class PedidoInspecionarLote(BaseModel):
    projeto_id: int
    pasta: str = Field(min_length=1, max_length=1000)


class ArquivoInspecionado(BaseModel):
    nome: str
    caminho: str
    tamanho: int
    tipo: str
    cnpj: str | None = None
    competencia: date | None = None
    uf: str = ""
    detalhe: str = ""
    motivo: str = ""
    retificadora: bool = False
    hash_conteudo: str | None = None
    # já está neste trabalho: a API não o registra de novo
    ja_no_trabalho: bool = False


class LoteInspecionado(BaseModel):
    """Tudo que a API precisa para mostrar a conferência e para registrar.

    Os arquivos vão inteiros, e não só a amostra: é desta mesma lista que a API
    grava o lote quando a pessoa confirma. Os avisos saem prontos daqui porque
    dependem do que só a leitura sabe — cópia, retificadora, não baixado.
    """

    pasta: str
    arquivos: list[ArquivoInspecionado]
    de_outra_empresa: int
    copias: int
    serve: bool
    competencias: list[date]
    cnpjs: list[str]
    avisos: list[str]


@router.post("/lotes/inspecionar", response_model=LoteInspecionado,
             dependencies=[Depends(exigir_segredo)])
def inspecionar_lote(
    pedido: PedidoInspecionarLote,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> LoteInspecionado:
    with contexto(etapa="inspecionar_lote", projeto_id=pedido.projeto_id, pasta=pedido.pasta):
        try:
            resumo, ja = inspecionar_do_projeto(pedido.projeto_id, pedido.pasta, sessao)
        except ProjetoInexistente:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabalho não encontrado.") from None
        except PastaInvalida as erro:
            log.warning("pasta recusada", extra={"motivo": str(erro)})
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro

    return LoteInspecionado(
        pasta=resumo.pasta,
        arquivos=[
            ArquivoInspecionado(
                nome=a.nome, caminho=a.caminho, tamanho=a.tamanho, tipo=a.tipo.value,
                cnpj=a.cnpj, competencia=a.competencia, uf=a.uf, detalhe=a.detalhe,
                motivo=a.motivo, retificadora=a.retificadora,
                hash_conteudo=a.hash_conteudo, ja_no_trabalho=a.caminho in ja,
            )
            for a in resumo.arquivos
        ],
        de_outra_empresa=len(resumo.de_outra_empresa),
        copias=len(resumo.copias),
        serve=resumo.serve,
        competencias=resumo.competencias,
        cnpjs=resumo.cnpjs,
        avisos=resumo.avisos,
    )


# ---------------------------------------------------------------------------
# Remessa: de quem é o arquivo enviado
# ---------------------------------------------------------------------------
class EstabelecimentoDetectadoDto(BaseModel):
    cnpj: str
    cnpj_formatado: str
    nome: str
    uf: str
    inscricao_estadual: str
    e_matriz: bool
    arquivos: int
    competencias: int


class RemessaDto(BaseModel):
    """A análise, sem o que é do banco: se a empresa já está cadastrada, a API diz."""

    razao_social: str
    cnpj_raiz: str
    cnpj_matriz: str | None
    cnpj_matriz_formatado: str | None
    matriz_encontrada: bool
    uf: str
    inscricao_estadual: str
    filiais: int
    total_arquivos: int
    lidos: int
    recusados: int
    tipos: dict[str, int]
    arquivos_para_cat: int
    primeira_competencia: date | None
    ultima_competencia: date | None
    avisos: list[str]
    # só a matriz por padrão; as filiais entram sob demanda
    matriz: EstabelecimentoDetectadoDto | None = None


@router.post("/remessas/analisar", response_model=RemessaDto,
             dependencies=[Depends(exigir_segredo)])
async def analisar_remessa(arquivo: Annotated[UploadFile, File()]) -> RemessaDto:
    conteudo = await arquivo.read()
    nome = arquivo.filename or "remessa"
    with contexto(etapa="analisar_remessa", arquivo=nome, bytes=len(conteudo)):
        try:
            r = analisar(list(percorrer(conteudo, nome)))
        except RemessaInvalida as erro:
            log.warning("remessa recusada", extra={"motivo": str(erro)})
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
        if not r.estabelecimentos:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Nenhum arquivo da remessa foi reconhecido como SPED.")
        return _remessa_dto(r)


def _remessa_dto(r: RemessaAnalisada) -> RemessaDto:
    matriz = next((e for e in r.estabelecimentos if e.e_matriz), None)
    return RemessaDto(
        razao_social=r.razao_social,
        cnpj_raiz=r.raiz_cnpj,
        cnpj_matriz=r.cnpj_matriz,
        cnpj_matriz_formatado=Cnpj(r.cnpj_matriz).formatado if r.cnpj_matriz else None,
        matriz_encontrada=matriz is not None,
        uf=r.uf_matriz,
        inscricao_estadual=r.ie_matriz,
        filiais=r.filiais,
        total_arquivos=r.total_arquivos,
        lidos=r.lidos,
        recusados=len(r.recusados),
        tipos=r.tipos,
        arquivos_para_cat=r.serve_para_cat,
        primeira_competencia=r.primeira_competencia,
        ultima_competencia=r.ultima_competencia,
        avisos=r.avisos,
        matriz=(
            EstabelecimentoDetectadoDto(
                cnpj=matriz.cnpj.valor, cnpj_formatado=matriz.cnpj.formatado,
                nome=matriz.nome, uf=matriz.uf,
                inscricao_estadual=matriz.inscricao_estadual, e_matriz=True,
                arquivos=matriz.arquivos, competencias=len(matriz.competencias),
            )
            if matriz else None
        ),
    )

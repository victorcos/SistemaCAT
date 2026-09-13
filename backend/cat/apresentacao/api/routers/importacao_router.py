"""Análise da remessa: ler o cabeçalho dos arquivos e dizer de quem são.

É a primeira tela do cadastro. O resto do fluxo — confirmar o pré-cadastro da
empresa e criar o projeto — mora na API em C# desde 13/09/2026
(docs/MIGRACAO_CSHARP.md). Esta rota fica no motor porque lê o arquivo enviado:
ler arquivo fiscal é trabalho do motor.

Nenhum arquivo é gravado nesta etapa. Ler o cabeçalho basta para identificar a
empresa, e guardar gigabytes antes de o usuário confirmar seria desperdício.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.analisar_remessa import RemessaAnalisada, analisar
from cat.apresentacao.api.seguranca import exigir_capacidade
from cat.dominio.acesso.usuario import Usuario
from cat.dominio.comum.cnpj import Cnpj
from cat.infraestrutura.arquivos.remessa import RemessaInvalida, percorrer
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.infraestrutura.repositorios.modelos import EmpresaDB
from cat.log import contexto, obter_log

log = obter_log(__name__)
router = APIRouter(prefix="/api", tags=["importação"])

PodeEscrever = Annotated[
    Usuario, Depends(exigir_capacidade("pode_escrever", "importar arquivos"))
]


# ---------------------------------------------------------------------------
# Contratos
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
    ja_cadastrada: bool = False
    empresa_id: int | None = None
    # só a matriz por padrão; as filiais entram sob demanda
    matriz: EstabelecimentoDetectadoDto | None = None


# ---------------------------------------------------------------------------
# 1. Analisar a remessa
# ---------------------------------------------------------------------------
@router.post("/importacoes/analisar", response_model=RemessaDto)
async def analisar_remessa(
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
    arquivo: Annotated[UploadFile, File()],
) -> RemessaDto:
    conteudo = await arquivo.read()
    nome = arquivo.filename or "remessa"

    with contexto(etapa="analisar_remessa", usuario_id=usuario.id,
                  arquivo=nome, bytes=len(conteudo)):
        try:
            r = analisar(list(percorrer(conteudo, nome)))
        except RemessaInvalida as erro:
            log.warning("remessa recusada", extra={"motivo": str(erro)})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)
            ) from erro

        if not r.estabelecimentos:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Nenhum arquivo da remessa foi reconhecido como SPED.",
            )
        return _para_dto(r, sessao)


def _para_dto(r: RemessaAnalisada, sessao: Session) -> RemessaDto:
    ja = sessao.scalar(select(EmpresaDB).where(EmpresaDB.cnpj_raiz == r.raiz_cnpj))
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
        ja_cadastrada=ja is not None,
        empresa_id=ja.id if ja else None,
        matriz=(
            EstabelecimentoDetectadoDto(
                cnpj=matriz.cnpj.valor,
                cnpj_formatado=matriz.cnpj.formatado,
                nome=matriz.nome,
                uf=matriz.uf,
                inscricao_estadual=matriz.inscricao_estadual,
                e_matriz=True,
                arquivos=matriz.arquivos,
                competencias=len(matriz.competencias),
            )
            if matriz
            else None
        ),
    )

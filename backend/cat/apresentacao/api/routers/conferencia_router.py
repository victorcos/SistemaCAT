"""Conferência de documentos: EFD contra XML e relatório do cliente.

A primeira análise do trabalho. Extrai C100 e C800 da EFD, junta a chave de
cada XML e de cada linha do relatório do cliente, confronta, e produz as duas
listas que o trabalho precisa:

* **notas não escrituradas** — estão na pasta e não na EFD, saem da análise;
* **notas a cobrar** — estão na EFD e o documento não veio.

* **notas conferidas** — estão na EFD e o documento veio; é o resultado
  positivo, o que segue para a apuração.

A rodada não cabe numa requisição: são 7.036 arquivos e 100 GB numa base desta
casa. Aqui se cria a execução, se devolve o identificador e o front acompanha.
As planilhas saem depois, por download, geradas a partir dos parquets da
própria execução.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import (
    ETAPA,
    NadaParaConferir,
    executar,
    preparar,
)
from cat.aplicacao.casos_de_uso.historico_do_projeto import TrabalhoParado
from cat.apresentacao.api.seguranca import (
    UsuarioAtual,
    exigir_capacidade,
    exigir_empresa,
)
from cat.dominio.acesso.usuario import Usuario
from cat.infraestrutura.analitico.confronto import (
    ARQUIVO_CONFERIDOS,
    ARQUIVO_NAO_ESCRITURADAS,
    ARQUIVO_SEM_DOCUMENTO,
)
from cat.infraestrutura.planilhas.conferencia import (
    FORMATOS,
    gerar_conferidas,
    gerar_nao_escrituradas,
    gerar_sem_documento,
)
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.infraestrutura.tarefas import disparar
from cat.log import contexto, obter_log

log = obter_log(__name__)
router = APIRouter(prefix="/api", tags=["conferência"])

PodeEscrever = Annotated[
    Usuario, Depends(exigir_capacidade("pode_escrever", "conferir documentos"))
]

SITUACOES_EM_CURSO = ("na_fila", "rodando")


# o que o navegador recebe. CSV vai com charset declarado: sem isso o Excel
# ignora o BOM em algumas versões e o acento se perde no caminho
TIPOS = {
    "xlsx": ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet"),
    "csv": "text/csv; charset=utf-8",
}

# nome do arquivo que o usuário recebe, e do que fica em cache na execução
PLANILHAS = {
    "nao-escrituradas": ("notas_nao_escrituradas.xlsx", ARQUIVO_NAO_ESCRITURADAS,
                         gerar_nao_escrituradas),
    "a-cobrar": ("notas_a_cobrar.xlsx", ARQUIVO_SEM_DOCUMENTO,
                 gerar_sem_documento),
    "conferidas": ("notas_conferidas.xlsx", ARQUIVO_CONFERIDOS,
                   gerar_conferidas),
}


class ExecucaoDto(BaseModel):
    id: int
    projeto_id: int
    etapa: str
    situacao: str
    passo: str | None = None
    fracao: float = 0.0
    arquivos_totais: int = 0
    arquivos_lidos: int = 0
    bytes_lidos: int = 0
    documentos: int = 0
    erro: str | None = None
    iniciada_em: str
    terminada_em: str | None = None
    resumo: dict | None = None

    @property
    def em_curso(self) -> bool:
        return self.situacao in SITUACOES_EM_CURSO


def _projeto(projeto_id: int, usuario: Usuario, sessao: Session) -> ProjetoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabalho não encontrado.")
    exigir_empresa(usuario, projeto.empresa_id)
    return projeto


def _execucao(execucao_id: int, usuario: Usuario, sessao: Session) -> ExecucaoDB:
    execucao = sessao.get(ExecucaoDB, execucao_id)
    if execucao is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Execução não encontrada.")
    _projeto(execucao.projeto_id, usuario, sessao)
    return execucao


def _dto(e: ExecucaoDB) -> ExecucaoDto:
    return ExecucaoDto(
        id=e.id, projeto_id=e.projeto_id, etapa=e.etapa, situacao=e.situacao,
        passo=e.passo, fracao=e.fracao, arquivos_totais=e.arquivos_totais,
        arquivos_lidos=e.arquivos_lidos, bytes_lidos=e.bytes_lidos,
        documentos=e.documentos, erro=e.erro,
        iniciada_em=e.iniciada_em.isoformat(),
        terminada_em=e.terminada_em.isoformat() if e.terminada_em else None,
        resumo=e.resumo,
    )


# ---------------------------------------------------------------------------
# 1. Começar a conferência
# ---------------------------------------------------------------------------
@router.post("/projetos/{projeto_id}/conferencias", response_model=ExecucaoDto,
             status_code=status.HTTP_202_ACCEPTED)
def iniciar(
    projeto_id: int,
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> ExecucaoDto:
    _projeto(projeto_id, usuario, sessao)

    # duas rodadas ao mesmo tempo no mesmo trabalho disputariam a mesma rede e
    # terminariam as duas mais devagar; e a segunda sobrescreveria a primeira
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
            "Já existe uma conferência em andamento neste trabalho.",
        )

    with contexto(etapa=ETAPA, usuario_id=usuario.id, projeto_id=projeto_id):
        try:
            execucao = preparar(projeto_id, usuario.id, sessao)
        except (TrabalhoParado, NadaParaConferir) as erro:
            log.warning("conferência recusada", extra={"motivo": str(erro)})
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)
            ) from erro

        disparar(executar, execucao.id)
        log.info("conferência iniciada",
                 extra={"execucao_id": execucao.id,
                        "arquivos": execucao.arquivos_totais})
        return _dto(execucao)


# ---------------------------------------------------------------------------
# 2. Acompanhar
# ---------------------------------------------------------------------------
@router.get("/projetos/{projeto_id}/conferencias", response_model=list[ExecucaoDto])
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


@router.get("/conferencias/{execucao_id}", response_model=ExecucaoDto)
def detalhar(
    execucao_id: int,
    usuario: UsuarioAtual,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> ExecucaoDto:
    return _dto(_execucao(execucao_id, usuario, sessao))


# ---------------------------------------------------------------------------
# 3. As três planilhas
# ---------------------------------------------------------------------------
@router.get("/conferencias/{execucao_id}/planilhas/{qual}")
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

    execucao = _execucao(execucao_id, usuario, sessao)
    if execucao.situacao != "concluida":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A conferência ainda não terminou.",
        )

    nome, parquet, gerador = PLANILHAS[qual]
    escolhidos = _conjunto(modelos)
    classes = _conjunto(classificacoes)
    pasta = execucao.pasta_de_trabalho or ""
    origem = os.path.join(pasta, parquet)
    if not os.path.isfile(origem):
        # os parquets são de disco local e podem ter sido limpos; a linha da
        # execução fica para sempre, o material de trabalho não. Ou a
        # execução é de antes de esta lista existir: a pasta está lá, a lista
        # não. Nos dois casos a saída é a mesma — rodar de novo.
        motivo = (
            "Esta conferência é de uma versão anterior e não tem esta lista."
            if os.path.isdir(pasta)
            else "Os arquivos desta conferência não estão mais em disco."
        )
        raise HTTPException(status.HTTP_410_GONE,
                            f"{motivo} Rode a conferência de novo.")

    # cada recorte vira arquivo próprio: sem isso, o primeiro download
    # ficaria em cache e o filtro seguinte devolveria a planilha errada
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
            log.info("planilha da conferência gerada",
                     extra={"planilha": qual, "linhas": linhas, "formato": formato,
                            "modelos": sorted(escolhidos) if escolhidos else "todos",
                            "classificacoes": sorted(classes) if classes else "todas"})

    return FileResponse(
        destino,
        media_type=TIPOS[formato],
        filename=os.path.basename(destino),
    )


def _conjunto(bruto: str | None) -> frozenset[str] | None:
    """"55,65" vira o conjunto; vazio significa todos."""
    if not bruto:
        return None
    escolhidos = {m.strip() for m in bruto.split(",") if m.strip()}
    return frozenset(escolhidos) or None


def _precisa_gerar(planilha: str, parquet: str) -> bool:
    """A planilha em cache só vale se for mais nova que o dado que a originou.

    Guardar por nome e nunca conferir a idade servia planilha velha depois de a
    conferência rodar de novo. Aconteceu de valer: um download real veio com o
    conteúdo de uma execução anterior, e o número na tela não batia com o do
    arquivo.
    """
    if not os.path.isfile(planilha):
        return True
    try:
        return os.path.getmtime(planilha) < os.path.getmtime(parquet)
    except OSError:
        return True

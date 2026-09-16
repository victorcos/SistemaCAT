"""Canal interno com a API em C#. Não é rota de gente.

A API em C# decide se a pessoa pode; o motor faz o que é de disco. Este canal
existe para isso (docs/MIGRACAO_CSHARP.md §4) e tem três portas fechadas:

1. o motor só escuta em 127.0.0.1 (scripts/subir.ps1);
2. a API em C# não repassa nada ao motor desde a fatia 7 — /interno nunca
   chega aqui vindo da tela, e o motor não tem outra rota;
3. toda chamada traz o segredo compartilhado CAT_MOTOR_SEGREDO. Sem ele
   configurado, o canal fica fechado para todo mundo, em vez de aberto.

O que passa por aqui é o que lê ou escreve disco: apagar pasta de trabalho,
inspecionar a pasta de um lote, analisar a remessa enviada, pôr uma execução na
fila e gerar planilha. A regra de quem
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
from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso import (
    apurar_periodo,
    apurar_suportado,
    conferir_documentos,
    extrair_movimentos,
    gerar_arquivo_digital,
    montar_razao,
    planilhas,
    rodada,
)
from cat.aplicacao.casos_de_uso.analisar_remessa import RemessaAnalisada, analisar
from cat.aplicacao.casos_de_uso.historico_do_projeto import TrabalhoParado
from cat.aplicacao.casos_de_uso.inspecionar_lote import (
    PastaInvalida,
    ProjetoInexistente,
    inspecionar_do_projeto,
)
from cat.config import obter_config
from cat.dominio.comum.cnpj import Cnpj
from cat.infraestrutura.analitico import apuracao as analitico_apuracao
from cat.infraestrutura.analitico import arquivo_digital as analitico_arquivo_digital
from cat.infraestrutura.analitico import razao as analitico_razao
from cat.infraestrutura.analitico import suportado as analitico_suportado
from cat.infraestrutura.arquivos.remessa import RemessaInvalida, percorrer
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB
from cat.log import contexto, obter_log
from cat.versao import versao

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


@router.get("/saude", dependencies=[Depends(exigir_segredo)])
def saude() -> dict[str, object]:
    """Vivo, e com QUAL configuração — só o que não é segredo.

    A API em C# mostra isto dentro do próprio /api/saude. Sem isso, um motor
    antigo que sobreviveu a um reinício é indistinguível do novo: os dois
    respondem "ok", e só a versão e a pasta de trabalho os separam.
    """
    cfg = obter_config()
    return {
        "status": "ok",
        "versao": versao(),
        "pasta_de_trabalho": cfg.raiz_de_trabalho,
        "memoria_analitica": cfg.memoria_analitica,
        "threads_analiticas": cfg.threads_analiticas,
    }


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


# ---------------------------------------------------------------------------
# Execução: preparar e pôr na fila
# ---------------------------------------------------------------------------
PREPARADORES = {
    conferir_documentos.ETAPA: (conferir_documentos.preparar, conferir_documentos.NadaParaConferir,
                                "Já existe uma conferência em andamento neste trabalho."),
    extrair_movimentos.ETAPA: (extrair_movimentos.preparar, extrair_movimentos.NadaParaExtrair,
                               "Já existe uma extração de movimentos em andamento neste trabalho."),
    apurar_suportado.ETAPA: (apurar_suportado.preparar, apurar_suportado.NadaParaApurar,
                             "Já existe uma apuração do ICMS suportado em andamento neste trabalho."),
    montar_razao.ETAPA: (montar_razao.preparar, montar_razao.NadaParaMontar,
                         "Já existe uma montagem do razão em andamento neste trabalho."),
    apurar_periodo.ETAPA: (apurar_periodo.preparar, apurar_periodo.NadaParaApurar,
                           "Já existe uma apuração do período em andamento neste trabalho."),
    gerar_arquivo_digital.ETAPA: (gerar_arquivo_digital.preparar, gerar_arquivo_digital.NadaParaGerar,
                                  "Já existe uma geração do arquivo digital em andamento neste trabalho."),
}

# "cancelando" ainda está em curso: a rodada só para no próximo ponto seguro, e
# uma segunda começando antes disso disputaria a mesma pasta
SITUACOES_EM_CURSO = ("na_fila", "rodando", "cancelando")


class PedidoDeExecucao(BaseModel):
    etapa: str
    projeto_id: int
    usuario_id: int


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


def execucao_dto(e: ExecucaoDB) -> ExecucaoDto:
    return ExecucaoDto(
        id=e.id, projeto_id=e.projeto_id, etapa=e.etapa, situacao=e.situacao,
        passo=e.passo, fracao=e.fracao, arquivos_totais=e.arquivos_totais,
        arquivos_lidos=e.arquivos_lidos, bytes_lidos=e.bytes_lidos,
        documentos=e.documentos, erro=e.erro,
        iniciada_em=e.iniciada_em.isoformat(),
        terminada_em=e.terminada_em.isoformat() if e.terminada_em else None,
        resumo=e.resumo,
    )


@router.post("/execucoes", response_model=ExecucaoDto, status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(exigir_segredo)])
def pedir_execucao(
    pedido: PedidoDeExecucao,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> ExecucaoDto:
    """Confere se há o que fazer, cria a execução na fila e registra no histórico.

    As regras de preparar ficam no motor porque são as mesmas da leitura: quais
    EFD valem (a retificadora substitui a original), se há documento para
    confrontar, se a conferência já concluiu. Quem roda é o trabalhador da fila.
    """
    if pedido.etapa not in PREPARADORES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Etapa desconhecida: {pedido.etapa}.")
    preparar, nada_a_fazer, ja_em_curso = PREPARADORES[pedido.etapa]

    # duas rodadas ao mesmo tempo no mesmo trabalho disputariam a mesma rede e
    # terminariam as duas mais devagar; e a segunda sobrescreveria a primeira
    em_curso = sessao.scalar(select(ExecucaoDB).where(
        ExecucaoDB.projeto_id == pedido.projeto_id, ExecucaoDB.etapa == pedido.etapa,
        ExecucaoDB.situacao.in_(SITUACOES_EM_CURSO)))
    if em_curso is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, ja_em_curso)

    with contexto(etapa=pedido.etapa, usuario_id=pedido.usuario_id, projeto_id=pedido.projeto_id):
        try:
            execucao = preparar(pedido.projeto_id, pedido.usuario_id, sessao)
        except (TrabalhoParado, nada_a_fazer) as erro:
            log.warning("execução recusada", extra={"motivo": str(erro)})
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
        log.info("execução na fila", extra={"execucao_id": execucao.id, "arquivos": execucao.arquivos_totais})
        return execucao_dto(execucao)


class PedidoDeCancelamento(BaseModel):
    usuario_id: int


@router.post("/execucoes/{execucao_id}/cancelar", response_model=ExecucaoDto,
             dependencies=[Depends(exigir_segredo)])
def cancelar_execucao(
    execucao_id: int,
    pedido: PedidoDeCancelamento,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> ExecucaoDto:
    """Na fila, cancela na hora; rodando, pede para parar no próximo ponto seguro.

    Quem pode cancelar é decisão da API em C# — a mesma de quem pode iniciar.
    """
    try:
        execucao = rodada.cancelar(execucao_id, pedido.usuario_id, sessao)
    except rodada.CancelamentoRecusado as erro:
        log.warning("cancelamento recusado",
                    extra={"execucao_id": execucao_id, "motivo": str(erro)})
        raise HTTPException(erro.status, str(erro)) from erro
    return execucao_dto(execucao)


# ---------------------------------------------------------------------------
# Analítico da apuração: uma página por vez, montada aqui
# ---------------------------------------------------------------------------
class PedidoDeLinhas(BaseModel):
    execucao_id: int
    escopo: str = "documento"
    fonte: str | None = None
    busca: str | None = Field(default=None, max_length=100)
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=analitico_suportado.POR_PAGINA_PADRAO, ge=1)


@router.post("/suportado/linhas", dependencies=[Depends(exigir_segredo)])
def linhas_do_suportado(
    pedido: PedidoDeLinhas,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> dict:
    """O analítico sai daqui porque é leitura de parquet: 8,7 milhões de itens
    numa base real, e a tela só pode receber uma página."""
    execucao = sessao.get(ExecucaoDB, pedido.execucao_id)
    if execucao is None or execucao.etapa != apurar_suportado.ETAPA:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Apuração não encontrada.")
    if execucao.situacao != "concluida":
        raise HTTPException(status.HTTP_409_CONFLICT, "A apuração ainda não terminou.")
    with contexto(etapa=apurar_suportado.ETAPA, execucao_id=execucao.id):
        try:
            return analitico_suportado.linhas(
                execucao.pasta_de_trabalho or "", pedido.escopo, pedido.fonte,
                pedido.busca, pedido.pagina, pedido.por_pagina)
        except FileNotFoundError:
            raise HTTPException(status.HTTP_410_GONE,
                                "Os arquivos desta apuração não estão mais em disco. Rode de novo.") from None
        except ValueError as erro:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro


# ---------------------------------------------------------------------------
# Razão: a lista de fichas e as linhas de uma ficha
# ---------------------------------------------------------------------------
class PedidoDeFichas(BaseModel):
    execucao_id: int
    busca: str | None = Field(default=None, max_length=100)
    so: str | None = None
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=analitico_razao.POR_PAGINA_PADRAO, ge=1)


class PedidoDeFicha(BaseModel):
    execucao_id: int
    cnpj: str = Field(min_length=1, max_length=20)
    codigo: str = Field(min_length=1, max_length=60)
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=analitico_razao.POR_PAGINA_PADRAO, ge=1)


def _razao_concluido(execucao_id: int, sessao: Session) -> ExecucaoDB:
    execucao = sessao.get(ExecucaoDB, execucao_id)
    if execucao is None or execucao.etapa != montar_razao.ETAPA:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Razão não encontrado.")
    if execucao.situacao != "concluida":
        raise HTTPException(status.HTTP_409_CONFLICT, "A montagem do razão ainda não terminou.")
    return execucao


def _traduzir_leitura(funcao):
    try:
        return funcao()
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE,
                            "Os arquivos deste razão não estão mais em disco. Rode de novo.") from None
    except ValueError as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro


@router.post("/razao/fichas", dependencies=[Depends(exigir_segredo)])
def fichas_do_razao(pedido: PedidoDeFichas, sessao: Annotated[Session, Depends(obter_sessao)]) -> dict:
    execucao = _razao_concluido(pedido.execucao_id, sessao)
    with contexto(etapa=montar_razao.ETAPA, execucao_id=execucao.id):
        return _traduzir_leitura(lambda: analitico_razao.lista_de_fichas(
            execucao.pasta_de_trabalho or "", pedido.busca, pedido.so, pedido.pagina, pedido.por_pagina))


@router.post("/razao/ficha", dependencies=[Depends(exigir_segredo)])
def linhas_do_razao(pedido: PedidoDeFicha, sessao: Annotated[Session, Depends(obter_sessao)]) -> dict:
    execucao = _razao_concluido(pedido.execucao_id, sessao)
    with contexto(etapa=montar_razao.ETAPA, execucao_id=execucao.id):
        return _traduzir_leitura(lambda: analitico_razao.linhas_da_ficha(
            execucao.pasta_de_trabalho or "", pedido.cnpj, pedido.codigo, pedido.pagina,
            pedido.por_pagina))


# ---------------------------------------------------------------------------
# Apuração do período: as competências fechadas
# ---------------------------------------------------------------------------
class PedidoDeCompetencias(BaseModel):
    execucao_id: int
    so: str | None = None
    busca: str | None = Field(default=None, max_length=100)
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=analitico_apuracao.POR_PAGINA_PADRAO, ge=1)


@router.post("/apuracao/competencias", dependencies=[Depends(exigir_segredo)])
def competencias_apuradas(
    pedido: PedidoDeCompetencias,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> dict:
    execucao = sessao.get(ExecucaoDB, pedido.execucao_id)
    if execucao is None or execucao.etapa != apurar_periodo.ETAPA:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Apuração não encontrada.")
    if execucao.situacao != "concluida":
        raise HTTPException(status.HTTP_409_CONFLICT, "A apuração do período ainda não terminou.")
    with contexto(etapa=apurar_periodo.ETAPA, execucao_id=execucao.id):
        return _traduzir_leitura(lambda: analitico_apuracao.competencias(
            execucao.pasta_de_trabalho or "", pedido.so, pedido.busca, pedido.pagina,
            pedido.por_pagina))


# ---------------------------------------------------------------------------
# Arquivo digital: os arquivos gerados e a pré-validação de cada um
# ---------------------------------------------------------------------------
class PedidoDeArquivos(BaseModel):
    execucao_id: int
    so: str | None = None
    busca: str | None = Field(default=None, max_length=100)
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=analitico_arquivo_digital.POR_PAGINA_PADRAO, ge=1)


class PedidoDeOcorrencias(BaseModel):
    execucao_id: int
    nome: str = Field(min_length=1, max_length=120)
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=analitico_arquivo_digital.POR_PAGINA_PADRAO, ge=1)


def _arquivo_digital_concluido(execucao_id: int, sessao: Session) -> ExecucaoDB:
    execucao = sessao.get(ExecucaoDB, execucao_id)
    if execucao is None or execucao.etapa != gerar_arquivo_digital.ETAPA:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Geração do arquivo digital não encontrada.")
    if execucao.situacao != "concluida":
        raise HTTPException(status.HTTP_409_CONFLICT, "A geração do arquivo digital ainda não terminou.")
    return execucao


@router.post("/arquivo_digital/arquivos", dependencies=[Depends(exigir_segredo)])
def arquivos_gerados(pedido: PedidoDeArquivos, sessao: Annotated[Session, Depends(obter_sessao)]) -> dict:
    execucao = _arquivo_digital_concluido(pedido.execucao_id, sessao)
    with contexto(etapa=gerar_arquivo_digital.ETAPA, execucao_id=execucao.id):
        return _traduzir_leitura(lambda: analitico_arquivo_digital.arquivos(
            execucao.pasta_de_trabalho or "", pedido.so, pedido.busca, pedido.pagina, pedido.por_pagina))


@router.post("/arquivo_digital/ocorrencias", dependencies=[Depends(exigir_segredo)])
def ocorrencias_do_arquivo(pedido: PedidoDeOcorrencias, sessao: Annotated[Session, Depends(obter_sessao)]) -> dict:
    execucao = _arquivo_digital_concluido(pedido.execucao_id, sessao)
    with contexto(etapa=gerar_arquivo_digital.ETAPA, execucao_id=execucao.id, arquivo=pedido.nome):
        return _traduzir_leitura(lambda: analitico_arquivo_digital.ocorrencias(
            execucao.pasta_de_trabalho or "", pedido.nome, pedido.pagina, pedido.por_pagina))


# ---------------------------------------------------------------------------
# Planilha: gerar a partir dos parquets e dizer onde está
# ---------------------------------------------------------------------------
class PedidoDePlanilha(BaseModel):
    execucao_id: int
    # a etapa pela qual a tela pediu: é dela a lista de planilhas e a mensagem
    etapa: str
    qual: str
    modelos: str | None = None
    classificacoes: str | None = None
    formato: str = "xlsx"


class PlanilhaDto(BaseModel):
    caminho: str
    nome: str
    tipo: str


@router.post("/planilhas", response_model=PlanilhaDto, dependencies=[Depends(exigir_segredo)])
def gerar_planilha(
    pedido: PedidoDePlanilha,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> PlanilhaDto:
    execucao = sessao.get(ExecucaoDB, pedido.execucao_id)
    if execucao is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Execução não encontrada.")
    try:
        pronta = planilhas.gerar(execucao, pedido.etapa, pedido.qual, pedido.modelos,
                                 pedido.classificacoes, pedido.formato)
    except planilhas.PlanilhaRecusada as erro:
        raise HTTPException(erro.status, str(erro)) from erro
    return PlanilhaDto(caminho=pronta.caminho, nome=pronta.nome, tipo=pronta.tipo)

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
fila, gerar planilha e conferir a Ficha 3 que volta editada à mão. A regra de
quem pode, o registro no banco e a resposta à tela ficam no C#.

**Apagar pasta só dentro da pasta de trabalho.** O Python apagava o caminho que
estivesse gravado na execução, sem conferir. Um valor torto no banco — ou uma
pasta de trabalho trocada no .env — mandava apagar outra coisa. Agora o que está
fora da raiz é recusado e volta dito, e a própria raiz também.
"""

from __future__ import annotations

import hmac
import os
import shutil
import tempfile
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso import (
    apurar_contribuicoes,
    apurar_periodo,
    apurar_suportado,
    conferir_documentos,
    extrair_movimentos,
    gerar_arquivo_digital,
    montar_entrega,
    montar_razao,
    planilhas,
    pre_validar_arquivos,
    quebrar_sped,
    rodada,
)
from cat.aplicacao.casos_de_uso.analisar_remessa import RemessaAnalisada, analisar
from cat.aplicacao.casos_de_uso import depara_do_trabalho
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
from cat.infraestrutura.analitico import entrega as analitico_entrega
from cat.infraestrutura.analitico import pre_validacao_do_cliente as analitico_pre_validacao
from cat.infraestrutura.analitico import razao as analitico_razao
from cat.infraestrutura.analitico import razao_contabil as analitico_razao_contabil
from cat.infraestrutura.analitico import suportado as analitico_suportado
from cat.infraestrutura.arquivos.remessa import RemessaInvalida, percorrer
from cat.infraestrutura.planilhas import correcoes_da_planilha
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
    # o tipo gravado no trabalho; diferente de `tipo`, a API reclassifica
    tipo_no_trabalho: str | None = None
    # se o trabalho DESTE módulo lê o arquivo — quem decide é o motor, que
    # conhece o tipo; a API só repassa
    alimenta: bool = False


class LoteInspecionado(BaseModel):
    """Tudo que a API precisa para mostrar a conferência e para registrar.

    Os arquivos vão inteiros, e não só a amostra: é desta mesma lista que a API
    grava o lote quando a pessoa confirma. Os avisos saem prontos daqui porque
    dependem do que só a leitura sabe — cópia, retificadora, não baixado.
    """

    pasta: str
    # o módulo do trabalho: é contra ele que "alimenta" e "serve" são medidos
    modulo: str
    arquivos: list[ArquivoInspecionado]
    de_outra_empresa: int
    copias: int
    # arquivos que OUTRO trabalho da mesma empresa já leu: entram, mas a
    # leitura não se repete. É o que permite o PIS/COFINS usar a EFD
    # ICMS/IPI que o trabalho de ICMS importou
    reaproveitados: int = 0
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
        modulo=resumo.modulo,
        arquivos=[
            ArquivoInspecionado(
                nome=a.nome, caminho=a.caminho, tamanho=a.tamanho, tipo=a.tipo.value,
                cnpj=a.cnpj, competencia=a.competencia, uf=a.uf, detalhe=a.detalhe,
                motivo=a.motivo, retificadora=a.retificadora,
                hash_conteudo=a.hash_conteudo, ja_no_trabalho=a.caminho in ja,
                tipo_no_trabalho=ja.get(a.caminho),
                alimenta=a.tipo.alimenta(resumo.modulo),
            )
            for a in resumo.arquivos
        ],
        de_outra_empresa=len(resumo.de_outra_empresa),
        copias=len(resumo.copias),
        reaproveitados=len(resumo.reaproveitados),
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
    # a que trabalho cada arquivo serve, e quais módulos a remessa atende
    observacoes: list[str]
    modulos_atendidos: list[str]
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
        observacoes=r.observacoes,
        modulos_atendidos=r.modulos_atendidos,
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
    pre_validar_arquivos.ETAPA: (pre_validar_arquivos.preparar, pre_validar_arquivos.NadaParaPreValidar,
                                 "Já existe uma pré-validação dos arquivos do cliente em andamento neste trabalho."),
    montar_entrega.ETAPA: (montar_entrega.preparar, montar_entrega.NadaParaEntregar,
                           "Já existe uma montagem da entrega em andamento neste trabalho."),
    apurar_contribuicoes.ETAPA: (
        apurar_contribuicoes.preparar, apurar_contribuicoes.NadaParaApurar,
        "Já existe uma apuração das contribuições em andamento neste trabalho."),
    quebrar_sped.ETAPA: (quebrar_sped.preparar, quebrar_sped.NadaParaQuebrar,
                         "Já existe uma quebra de SPED em andamento neste trabalho."),
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
# Razão contábil da ECD: o seletor de conta e os lançamentos de uma conta
#
# Mesma forma de tela que o razão da CAT 42 acima — escolher e depois olhar —,
# mas de outra etapa e de outro módulo: sai da quebra de SPED, do PIS/COFINS.
# ---------------------------------------------------------------------------
class PedidoDeContas(BaseModel):
    execucao_id: int
    busca: str | None = Field(default=None, max_length=100)
    cnpj: str | None = Field(default=None, max_length=20)
    so: str | None = None
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=analitico_razao_contabil.POR_PAGINA_PADRAO, ge=1)


class PedidoDeLancamentos(BaseModel):
    execucao_id: int
    cnpj: str = Field(min_length=1, max_length=20)
    conta: str = Field(min_length=1, max_length=60)
    busca: str | None = Field(default=None, max_length=100)
    de: str | None = Field(default=None, max_length=10)
    ate: str | None = Field(default=None, max_length=10)
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=analitico_razao_contabil.POR_PAGINA_PADRAO, ge=1)


class PedidoDoRazaoContabil(BaseModel):
    execucao_id: int


def _quebra_concluida(execucao_id: int, sessao: Session) -> ExecucaoDB:
    execucao = sessao.get(ExecucaoDB, execucao_id)
    if execucao is None or execucao.etapa != quebrar_sped.ETAPA:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quebra de SPED não encontrada.")
    if execucao.situacao != "concluida":
        raise HTTPException(status.HTTP_409_CONFLICT, "A quebra de SPED ainda não terminou.")
    return execucao


@router.post("/razao-contabil/contas", dependencies=[Depends(exigir_segredo)])
def contas_do_razao_contabil(
    pedido: PedidoDeContas, sessao: Annotated[Session, Depends(obter_sessao)]
) -> dict:
    execucao = _quebra_concluida(pedido.execucao_id, sessao)
    with contexto(etapa=quebrar_sped.ETAPA, execucao_id=execucao.id):
        return _traduzir_leitura(lambda: analitico_razao_contabil.contas(
            execucao.pasta_de_trabalho or "", pedido.busca, pedido.cnpj, pedido.so,
            pedido.pagina, pedido.por_pagina))


@router.post("/razao-contabil/lancamentos", dependencies=[Depends(exigir_segredo)])
def lancamentos_do_razao_contabil(
    pedido: PedidoDeLancamentos, sessao: Annotated[Session, Depends(obter_sessao)]
) -> dict:
    execucao = _quebra_concluida(pedido.execucao_id, sessao)
    with contexto(etapa=quebrar_sped.ETAPA, execucao_id=execucao.id):
        return _traduzir_leitura(lambda: analitico_razao_contabil.lancamentos(
            execucao.pasta_de_trabalho or "", pedido.cnpj, pedido.conta, pedido.busca,
            pedido.de, pedido.ate, pedido.pagina, pedido.por_pagina))


@router.post("/razao-contabil/estabelecimentos", dependencies=[Depends(exigir_segredo)])
def estabelecimentos_do_razao_contabil(
    pedido: PedidoDoRazaoContabil, sessao: Annotated[Session, Depends(obter_sessao)]
) -> dict:
    execucao = _quebra_concluida(pedido.execucao_id, sessao)
    with contexto(etapa=quebrar_sped.ETAPA, execucao_id=execucao.id):
        return _traduzir_leitura(lambda: {
            "linhas": analitico_razao_contabil.estabelecimentos(
                execucao.pasta_de_trabalho or "")})


# quanto se lê por vez da planilha que sobe. A Ficha 3 de uma base grande passa
# de 100 MB em xlsx, e carregá-la inteira em memória aqui seria o mesmo defeito
# que a remessa já ensinou
PEDACO_DA_PLANILHA = 1 << 20


@router.post("/correcoes/planilha", dependencies=[Depends(exigir_segredo)])
async def conferir_planilha_de_correcoes(
    execucao_id: int,
    arquivo: Annotated[UploadFile, File()],
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> dict:
    """A Ficha 3 editada sobe e volta o que mudou. **Nada é gravado aqui.**

    Quem grava é a API em C#, depois de a pessoa ver o diff e confirmar — e é
    ela também que decide quem pode. O motor faz o que é de disco: receber o
    arquivo, compará-lo com o parquet do razão e dizer a diferença.

    O razão vem na *query*, e não no formulário, de propósito: o corpo multipart
    atravessa o C# como chegou do navegador, e um `execucao_id` embutido nele
    seria escolhido por quem sobe o arquivo — daria para ler a ficha de outro
    trabalho. Na query, quem o escreve é a API, depois de conferir o acesso.
    """
    execucao = _razao_concluido(execucao_id, sessao)
    pasta = execucao.pasta_de_trabalho or ""
    ficha3 = os.path.join(pasta, analitico_razao.ARQUIVO_FICHA3)
    if not os.path.isfile(ficha3):
        raise HTTPException(status.HTTP_410_GONE,
                            "Os arquivos deste razão não estão mais em disco. Rode de novo.")
    nome = arquivo.filename or "ficha3.xlsx"
    _, extensao = os.path.splitext(nome)
    if extensao.lower() not in correcoes_da_planilha.EXTENSOES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Suba a Ficha 3 em xlsx ou csv, como o sistema a gera.")
    # o arquivo cai na pasta de trabalho do razão, que é disco local e foi
    # dimensionada para o volume desta etapa — nunca na pasta temporária do
    # Windows, que costuma ser o menor disco da máquina
    rascunho = tempfile.mkdtemp(prefix="correcoes-", dir=pasta)
    recebido = os.path.join(rascunho, "planilha" + extensao.lower())
    bytes_lidos = 0
    try:
        with open(recebido, "wb") as saida:
            while pedaco := await arquivo.read(PEDACO_DA_PLANILHA):
                saida.write(pedaco)
                bytes_lidos += len(pedaco)
        with contexto(etapa=montar_razao.ETAPA, execucao_id=execucao.id,
                      arquivo=nome, bytes=bytes_lidos):
            try:
                conferida = correcoes_da_planilha.conferir(recebido, ficha3, pasta=rascunho)
            except correcoes_da_planilha.PlanilhaIlegivel as erro:
                log.warning("planilha de correções recusada", extra={"motivo": str(erro)})
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
        return {"execucao_id": execucao.id, "projeto_id": execucao.projeto_id,
                "arquivo": nome, **conferida.como_json()}
    finally:
        shutil.rmtree(rascunho, ignore_errors=True)


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


def _arquivo_digital_concluido(execucao_id: int, sessao: Session,
                               etapas: tuple[str, ...] = (gerar_arquivo_digital.ETAPA,)) -> ExecucaoDB:
    execucao = sessao.get(ExecucaoDB, execucao_id)
    if execucao is None or execucao.etapa not in etapas:
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
    # a pré-validação do cliente grava as ocorrências no mesmo formato
    execucao = _arquivo_digital_concluido(pedido.execucao_id, sessao,
                                          (gerar_arquivo_digital.ETAPA, pre_validar_arquivos.ETAPA))
    with contexto(etapa=execucao.etapa, execucao_id=execucao.id, arquivo=pedido.nome):
        return _traduzir_leitura(lambda: analitico_arquivo_digital.ocorrencias(
            execucao.pasta_de_trabalho or "", pedido.nome, pedido.pagina, pedido.por_pagina))


@router.post("/pre_validacao/arquivos", dependencies=[Depends(exigir_segredo)])
def arquivos_do_cliente(pedido: PedidoDeArquivos, sessao: Annotated[Session, Depends(obter_sessao)]) -> dict:
    execucao = sessao.get(ExecucaoDB, pedido.execucao_id)
    if execucao is None or execucao.etapa != pre_validar_arquivos.ETAPA:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pré-validação não encontrada.")
    if execucao.situacao != "concluida":
        raise HTTPException(status.HTTP_409_CONFLICT, "A pré-validação ainda não terminou.")
    with contexto(etapa=pre_validar_arquivos.ETAPA, execucao_id=execucao.id):
        return _traduzir_leitura(lambda: analitico_pre_validacao.arquivos_do_cliente(
            execucao.pasta_de_trabalho or "", pedido.so, pedido.busca, pedido.pagina, pedido.por_pagina))


# ---------------------------------------------------------------------------
# Entrega: os estabelecimentos do pacote
# ---------------------------------------------------------------------------
class PedidoDeEstabelecimentos(BaseModel):
    execucao_id: int
    so: str | None = None
    busca: str | None = Field(default=None, max_length=100)
    pagina: int = Field(default=1, ge=1)
    por_pagina: int = Field(default=analitico_entrega.POR_PAGINA_PADRAO, ge=1)


@router.post("/entrega/estabelecimentos", dependencies=[Depends(exigir_segredo)])
def estabelecimentos_da_entrega(pedido: PedidoDeEstabelecimentos,
                                sessao: Annotated[Session, Depends(obter_sessao)]) -> dict:
    execucao = sessao.get(ExecucaoDB, pedido.execucao_id)
    if execucao is None or execucao.etapa != montar_entrega.ETAPA:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entrega não encontrada.")
    if execucao.situacao != "concluida":
        raise HTTPException(status.HTTP_409_CONFLICT, "A montagem da entrega ainda não terminou.")
    with contexto(etapa=montar_entrega.ETAPA, execucao_id=execucao.id):
        return _traduzir_leitura(lambda: analitico_entrega.estabelecimentos(
            execucao.pasta_de_trabalho or "", pedido.so, pedido.busca, pedido.pagina, pedido.por_pagina))


# ---------------------------------------------------------------------------
# De-para: o que o sistema propõe e o que já foi decidido
# ---------------------------------------------------------------------------
class PedidoDeDePara(BaseModel):
    projeto_id: int


@router.post("/depara/candidatos", dependencies=[Depends(exigir_segredo)])
def candidatos_de_depara(pedido: PedidoDeDePara, sessao: Annotated[Session, Depends(obter_sessao)]) -> dict:
    with contexto(etapa="depara", projeto_id=pedido.projeto_id):
        try:
            return depara_do_trabalho.candidatos_do_projeto(pedido.projeto_id, sessao)
        except LookupError as erro:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(erro)) from erro
        except depara_do_trabalho.SemMovimentacao as erro:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
        except FileNotFoundError:
            raise HTTPException(status.HTTP_410_GONE,
                                "Os arquivos da última movimentação não estão mais em disco. Rode de novo.") from None


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

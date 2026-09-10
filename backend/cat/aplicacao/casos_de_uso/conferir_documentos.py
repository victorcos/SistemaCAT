"""Conferir o que foi escriturado contra o documento que o cliente entregou.

Roda fora da requisição, como manda a arquitetura: a base de uma empresa desta
casa tem 7.036 arquivos e 100 GB, e um arquivo sozinho traz 39.265 registros
C100. A API cria a execução, devolve o identificador e o front acompanha.

A sequência é sempre a mesma:

    1. EFD  → parquet com todo C100 e C800
    2. pasta → parquet com a chave de cada XML e de cada linha do relatório
    3. confronto → duas listas em parquet e um resumo no banco

Os parquets ficam em disco local, numa pasta por execução. Disco de rede perde
gravação longa (ARQUITETURA §8), e uma execução dessas grava por minutos.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.config import obter_config
from cat.dominio.cat42.conferencia import ResumoDaConferencia
from cat.dominio.lote import TipoDeArquivo
from cat.infraestrutura.analitico.confronto import confrontar
from cat.infraestrutura.analitico.extracao import (
    Progresso,
    extrair_efd,
    extrair_pasta,
)
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import (
    ArquivoDoLoteDB,
    ExecucaoDB,
    LoteDB,
)
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "conferencia"

ARQUIVO_EFD = "efd.parquet"
ARQUIVO_PASTA = "pasta.parquet"

# de quanto em quanto tempo o progresso vai ao banco. Gravar a cada arquivo
# faria 7.036 UPDATEs para um trabalho que dura minutos.
SEGUNDOS_ENTRE_AVISOS = 2.0


class NadaParaConferir(ValueError):
    """O lote não tem o que confrontar."""


def caminhos_do_projeto(
    projeto_id: int, tipos: tuple[TipoDeArquivo, ...], sessao: Session
) -> list[str]:
    valores = [t.value for t in tipos]
    return list(sessao.scalars(
        select(ArquivoDoLoteDB.caminho)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .where(LoteDB.projeto_id == projeto_id,
               ArquivoDoLoteDB.tipo.in_(valores))
        .order_by(ArquivoDoLoteDB.caminho)
    ))


def pasta_da_execucao(execucao_id: int) -> str:
    raiz = obter_config().pasta_de_trabalho
    return os.path.join(raiz, f"execucao-{execucao_id}")


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    """Cria a execução já sabendo quantos arquivos vai ler.

    Confere aqui, ainda dentro da requisição, se há o que fazer: é barato, e
    dizer 'não há EFD neste trabalho' na hora vale mais do que uma execução que
    nasce e morre em silêncio.
    """
    efd = caminhos_do_projeto(projeto_id, (TipoDeArquivo.SPED_ICMS_IPI,), sessao)
    if not efd:
        raise NadaParaConferir(
            "Este trabalho não tem nenhuma EFD ICMS/IPI importada. "
            "Importe a base de dados antes de conferir."
        )
    documentos = caminhos_do_projeto(
        projeto_id,
        (TipoDeArquivo.XML_NFE, TipoDeArquivo.GERENCIAL_MOVIMENTO),
        sessao,
    )
    if not documentos:
        raise NadaParaConferir(
            "Este trabalho não tem XML nem relatório de movimento do cliente. "
            "Sem documento para confrontar, a conferência não diz nada."
        )

    execucao = ExecucaoDB(
        projeto_id=projeto_id,
        etapa=ETAPA,
        situacao="na_fila",
        passo="Na fila",
        arquivos_totais=len(efd) + len(documentos),
        criada_por=usuario_id,
    )
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    return execucao


def executar(execucao_id: int) -> None:
    """O trabalho pesado. Roda em linha de execução própria, com sessão própria."""
    with Sessao() as sessao:
        execucao = sessao.get(ExecucaoDB, execucao_id)
        if execucao is None:
            log.error("execução sumiu antes de rodar",
                      extra={"execucao_id": execucao_id})
            return

        destino = pasta_da_execucao(execucao_id)
        with contexto(etapa=ETAPA, execucao_id=execucao_id,
                      projeto_id=execucao.projeto_id):
            try:
                _rodar(execucao, destino, sessao)
            except Exception as erro:            # noqa: BLE001
                # qualquer falha precisa virar linha visível: execução que morre
                # calada deixa o usuário olhando uma barra que não anda
                log.exception("conferência falhou", extra={"erro": str(erro)})
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                sessao.commit()


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session) -> None:
    os.makedirs(destino, exist_ok=True)
    execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Lendo a EFD"
    sessao.commit()

    projeto_id = execucao.projeto_id
    efd = caminhos_do_projeto(projeto_id, (TipoDeArquivo.SPED_ICMS_IPI,), sessao)
    xmls = caminhos_do_projeto(projeto_id, (TipoDeArquivo.XML_NFE,), sessao)
    relatorios = caminhos_do_projeto(
        projeto_id, (TipoDeArquivo.GERENCIAL_MOVIMENTO,), sessao)

    execucao.arquivos_totais = len(efd) + len(xmls) + len(relatorios)
    sessao.commit()

    relogio = _Relogio(execucao, sessao, execucao.arquivos_totais)

    inicio = time.time()
    caminho_efd = os.path.join(destino, ARQUIVO_EFD)
    passo_efd = extrair_efd(efd, caminho_efd, avisar=relogio.marcar)

    relogio.deslocar(len(efd))
    execucao.passo = "Lendo os documentos do cliente"
    sessao.commit()

    caminho_pasta = os.path.join(destino, ARQUIVO_PASTA)
    passo_pasta = extrair_pasta(xmls, relatorios, caminho_pasta,
                                avisar=relogio.marcar)

    execucao.passo = "Confrontando"
    execucao.fracao = 0.97
    sessao.commit()

    resumo = confrontar(caminho_efd, caminho_pasta, destino)

    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.arquivos_lidos = execucao.arquivos_totais
    execucao.bytes_lidos = passo_efd.bytes_lidos + passo_pasta.bytes_lidos
    execucao.documentos = passo_efd.documentos
    execucao.resumo = _serializar(resumo, passo_efd, passo_pasta)
    execucao.terminada_em = datetime.now(timezone.utc)
    sessao.commit()

    log.info("conferência concluída",
             extra={"segundos": round(time.time() - inicio, 1),
                    "documentos": passo_efd.documentos,
                    "sem_documento": resumo.sem_documento,
                    "nao_escrituradas": resumo.nao_escrituradas})


def _serializar(resumo: ResumoDaConferencia, efd: Progresso,
                pasta: Progresso) -> dict:
    """O resumo vira JSON no banco. Decimal não é JSON: vai como texto."""
    dados = asdict(resumo)
    dados["origens"] = [o.value for o in resumo.origens]
    for chave in ("valor_conferido", "valor_nao_escriturado",
                  "valor_sem_documento"):
        dados[chave] = str(dados[chave])
    for lista in ("por_modelo", "por_operacao"):
        dados[lista] = [{**f, "valor": str(f["valor"])} for f in dados[lista]]
    dados["cobertura"] = round(resumo.cobertura, 4)
    dados["avisos"] = resumo.avisos
    dados["recusados"] = (efd.recusados + pasta.recusados)[:20]
    return dados


def descartar_pasta(execucao: ExecucaoDB) -> None:
    """Apaga os parquets de uma execução. A linha do banco fica."""
    if execucao.pasta_de_trabalho and os.path.isdir(execucao.pasta_de_trabalho):
        shutil.rmtree(execucao.pasta_de_trabalho, ignore_errors=True)


class _Relogio:
    """Leva o progresso ao banco de vez em quando, não a cada arquivo."""

    def __init__(self, execucao: ExecucaoDB, sessao: Session, total: int) -> None:
        self.execucao = execucao
        self.sessao = sessao
        self.total = max(total, 1)
        self.deslocamento = 0
        self.ultimo = 0.0

    def deslocar(self, quantos: int) -> None:
        self.deslocamento += quantos

    def marcar(self, progresso: Progresso) -> None:
        agora = time.monotonic()
        if agora - self.ultimo < SEGUNDOS_ENTRE_AVISOS:
            return
        self.ultimo = agora
        lidos = self.deslocamento + progresso.arquivos_lidos
        self.execucao.arquivos_lidos = lidos
        self.execucao.bytes_lidos = progresso.bytes_lidos
        self.execucao.documentos = progresso.documentos
        # 0,95 e não 1: o confronto ainda vem depois da leitura
        self.execucao.fracao = min(0.95, lidos / self.total)
        try:
            self.sessao.commit()
        except Exception:                        # noqa: BLE001
            # progresso é enfeite; perder um aviso não pode derrubar a extração
            self.sessao.rollback()

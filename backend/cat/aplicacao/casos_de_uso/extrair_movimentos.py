"""Extrair o histórico de movimentação do que a conferência encontrou.

Terceira etapa. Roda fora da requisição, como a conferência, e pela mesma
razão: lê todas as EFD vigentes do trabalho — numa base desta casa, 7.036
arquivos e 100 GB.

    1. EFD → cinco parquets: documentos, itens (C170/C810), analítico
       (C190/C850), cadastro (0200) e inventário (bloco H)
    2. consolidação → cadastro mais recente por item, movimentos com a marca
       da conferência (conferido / pendente / sem chave) e o analítico com
       `tem_item`
    3. resumo no banco: o que tem item, o que não tem e quanto vale

Depende da conferência concluída: é a lista de conferidos dela que marca cada
movimento. Sem ela a etapa não começa — a ordem das etapas é de dependência
real, não de tela.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import (
    ETAPA as ETAPA_CONFERENCIA,
    _Relogio,
    caminhos_de_efd_vigentes,
    pasta_da_execucao,
)
from cat.aplicacao.casos_de_uso.historico_do_projeto import (
    exigir_que_ande,
    registrar_de_etapa,
)
from cat.dominio.cat42.movimentacao import ResumoDaMovimentacao
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.confronto import ARQUIVO_CONFERIDOS
from cat.infraestrutura.analitico.movimentacao import consolidar
from cat.infraestrutura.analitico.movimentos import (
    ProgressoDeItens,
    extrair_movimentos,
)
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "movimentos"


class NadaParaExtrair(ValueError):
    """O trabalho não está pronto para esta etapa."""


def conferencia_concluida(projeto_id: int, sessao: Session) -> ExecucaoDB | None:
    """A última conferência concluída do trabalho, se houver."""
    return sessao.scalar(
        select(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == projeto_id,
               ExecucaoDB.etapa == ETAPA_CONFERENCIA,
               ExecucaoDB.situacao == "concluida")
        .order_by(ExecucaoDB.id.desc())
        .limit(1)
    )


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "extrair movimentos")

    efd, _ = caminhos_de_efd_vigentes(projeto_id, sessao)
    if not efd:
        raise NadaParaExtrair(
            "Este trabalho não tem nenhuma EFD ICMS/IPI importada. "
            "Importe a base de dados antes."
        )
    if conferencia_concluida(projeto_id, sessao) is None:
        raise NadaParaExtrair(
            "Conclua a conferência de documentos antes: é ela que diz quais "
            "movimentos têm documento e quais estão pendentes."
        )

    execucao = ExecucaoDB(
        projeto_id=projeto_id,
        etapa=ETAPA,
        situacao="na_fila",
        passo="Na fila",
        arquivos_totais=len(efd),
        criada_por=usuario_id,
    )
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Extração de movimentos · {len(efd)} EFD",
        dados={"execucao_id": execucao.id, "arquivos": len(efd)},
        autor_id=usuario_id,
    )
    return execucao


def executar(execucao_id: int) -> None:
    """O trabalho pesado. Linha de execução própria, sessão própria."""
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
                log.exception("extração de movimentos falhou",
                              extra={"erro": str(erro)})
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                sessao.commit()
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Extração de movimentos falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por,
                )


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session) -> None:
    os.makedirs(destino, exist_ok=True)
    execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Lendo os itens da EFD"
    sessao.commit()

    efd, substituidas = caminhos_de_efd_vigentes(execucao.projeto_id, sessao)
    execucao.arquivos_totais = len(efd)
    sessao.commit()

    inicio = time.time()
    relogio = _Relogio(execucao, sessao, len(efd))
    progresso = extrair_movimentos(efd, destino, avisar=relogio.marcar)

    execucao.passo = "Consolidando"
    execucao.arquivos_lidos = execucao.arquivos_totais
    execucao.documentos = progresso.documentos
    execucao.bytes_lidos = progresso.bytes_lidos
    execucao.fracao = 0.97
    sessao.commit()

    resumo = consolidar(destino, _conferidos(execucao.projeto_id, sessao))
    resumo.arquivos_fora_de_ordem = len(progresso.arquivos_com_orfaos)

    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.resumo = _serializar(resumo, progresso, len(substituidas))
    execucao.terminada_em = datetime.now(timezone.utc)
    sessao.commit()

    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Movimentos extraídos · {resumo.movimentos:,} linhas de item, "
        f"{resumo.saidas_sem_item:,} saídas sem item na EFD".replace(",", "."),
        dados={"execucao_id": execucao.id,
               "documentos": resumo.documentos,
               "movimentos": resumo.movimentos,
               "saidas_sem_item": resumo.saidas_sem_item,
               "segundos": round(time.time() - inicio, 1)},
        autor_id=execucao.criada_por,
    )
    log.info("movimentos extraídos e consolidados",
             extra={"segundos": round(time.time() - inicio, 1),
                    "documentos": progresso.documentos,
                    "movimentos": resumo.movimentos,
                    "saidas_sem_item": resumo.saidas_sem_item})


def _conferidos(projeto_id: int, sessao: Session) -> str | None:
    """O `conferidos.parquet` da última conferência concluída, se ainda existir."""
    anterior = conferencia_concluida(projeto_id, sessao)
    if anterior is None or not anterior.pasta_de_trabalho:
        return None
    caminho = os.path.join(anterior.pasta_de_trabalho, ARQUIVO_CONFERIDOS)
    if not os.path.isfile(caminho):
        log.warning("conferência concluída sem lista de conferidos em disco",
                    extra={"execucao_id": anterior.id, "caminho": caminho})
        return None
    return caminho


def _serializar(resumo: ResumoDaMovimentacao, progresso: ProgressoDeItens,
                substituidas: int) -> dict:
    """O resumo vira JSON no banco. Decimal não é JSON: vai como texto."""
    dados = asdict(resumo)
    for chave, valor in list(dados.items()):
        if isinstance(valor, list) and valor and isinstance(valor[0], dict):
            dados[chave] = [{**f, "valor": str(f["valor"])} for f in valor]
        elif hasattr(valor, "quantize"):
            dados[chave] = str(valor)
    dados["cobertura_de_item"] = round(resumo.cobertura_de_item, 4)
    dados["avisos"] = resumo.avisos
    dados["recusados"] = progresso.recusados[:20]
    dados["observacoes"] = progresso.observacoes[:20]
    dados["efd_originais_substituidas"] = substituidas
    dados["analiticos"] = progresso.analiticos
    return dados

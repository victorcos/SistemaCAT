"""Apurar ressarcimento e complemento — o fechamento do período.

Sexta etapa. Lê a Ficha 3 da etapa 5 e fecha por **estabelecimento e mês**, que
é a unidade do arquivo digital:

    1. ressarcimento e complemento, separados, com o crédito do artigo 271
       preparado (e zerado, até o confronto dos enquadramentos 2 e 4 existir);
    2. saldos de cada mercadoria no início e no fim do mês — o registro 1050 da
       etapa 7, campo a campo;
    3. o que trava cada competência, com o que fazer.

Apurar e poder entregar são coisas diferentes: o valor aparece sempre, e só a
competência sem pendência segue para o arquivo digital.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import pasta_da_execucao
from cat.aplicacao.casos_de_uso.historico_do_projeto import (
    exigir_que_ande,
    registrar_de_etapa,
)
from cat.aplicacao.casos_de_uso.montar_razao import ETAPA as ETAPA_RAZAO
from cat.aplicacao.casos_de_uso.montar_razao import _ufs
from cat.aplicacao.casos_de_uso.rodada import Diario, Freio, duracao, milhar, nome_de, reais
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.apuracao import (
    Andamento,
    apurar,
    serializar,
)
from cat.infraestrutura.analitico.razao import ARQUIVO_FICHA3
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "apuracao"
VERSAO_DO_RESUMO = 1


class NadaParaApurar(ValueError):
    """O trabalho não está pronto para esta etapa."""


def razao_concluido(projeto_id: int, sessao: Session) -> ExecucaoDB | None:
    return sessao.scalar(
        select(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == projeto_id,
               ExecucaoDB.etapa == ETAPA_RAZAO,
               ExecucaoDB.situacao == "concluida")
        .order_by(ExecucaoDB.id.desc())
        .limit(1)
    )


def _exigir_razao(projeto_id: int, sessao: Session) -> ExecucaoDB:
    razao = razao_concluido(projeto_id, sessao)
    if razao is None:
        raise NadaParaApurar("Monte o razão antes: é da Ficha 3 que sai o ressarcimento de "
                             "cada saída.")
    if not razao.pasta_de_trabalho or not os.path.isfile(
            os.path.join(razao.pasta_de_trabalho, ARQUIVO_FICHA3)):
        raise NadaParaApurar("Os arquivos do último razão não estão mais em disco. Monte o "
                             "razão de novo.")
    return razao


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "apurar ressarcimento e complemento")
    razao = _exigir_razao(projeto_id, sessao)

    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila",
                          passo="Na fila", criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Apuração do período sobre o razão #{razao.id}",
        dados={"execucao_id": execucao.id, "razao_execucao_id": razao.id},
        autor_id=usuario_id,
    )
    return execucao


def executar(execucao_id: int) -> None:
    with Sessao() as sessao:
        execucao = sessao.get(ExecucaoDB, execucao_id)
        if execucao is None:
            log.error("execução sumiu antes de rodar", extra={"execucao_id": execucao_id})
            return
        destino = pasta_da_execucao(execucao_id)
        diario = Diario(execucao, sessao, VERSAO_DO_RESUMO)
        with contexto(etapa=ETAPA, execucao_id=execucao_id, projeto_id=execucao.projeto_id):
            try:
                _rodar(execucao, destino, sessao, diario)
            except ApuracaoCancelada:
                log.warning("apuração do período cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. Nada foi gravado.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Apuração do período cancelada a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("apuração do período falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Apuração do período falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Fechando por estabelecimento e mês"
    execucao.fracao = 0.1
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    razao = _exigir_razao(execucao.projeto_id, sessao)
    diario.base["razao_execucao_id"] = razao.id
    diario.anotar("info", f"Fechando o período sobre o razão #{razao.id}.")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(a: Andamento) -> None:
        execucao.documentos = a.competencias
        diario.base["andamento"] = {"competencias": a.competencias}
        diario.salvar_de_vez_em_quando()

    resumo = apurar(razao.pasta_de_trabalho, destino, uf_por_cnpj=_ufs(execucao.projeto_id, sessao),
                    avisar=andou, deve_parar=parar)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.documentos = resumo.competencias
    diario.base.update(serializar(resumo))
    diario.base["segundos"] = segundos
    _anotar(diario, resumo)
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info", f"Concluída em {duracao(segundos)}: {milhar(resumo.competencias)} "
                          f"competências, {milhar(resumo.aptas)} aptas; "
                          f"{reais(resumo.ressarcimento_apto)} de ressarcimento pronto para pedir.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Período apurado · {milhar(resumo.aptas)} de {milhar(resumo.competencias)} competências "
        f"aptas, {reais(resumo.ressarcimento_apto)} a pedir",
        dados={"execucao_id": execucao.id, "competencias": resumo.competencias,
               "aptas": resumo.aptas, "ressarcimento": str(resumo.ressarcimento),
               "ressarcimento_apto": str(resumo.ressarcimento_apto), "segundos": segundos},
        autor_id=execucao.criada_por)


def _anotar(diario: Diario, resumo) -> None:
    diario.anotar("info", f"{milhar(resumo.competencias)} competências em "
                          f"{milhar(resumo.estabelecimentos)} estabelecimentos · "
                          f"{reais(resumo.ressarcimento)} de ressarcimento e "
                          f"{reais(resumo.complemento)} de complemento.")
    if resumo.saldos:
        diario.anotar("info", f"{milhar(resumo.saldos)} saldos de mercadoria por mês gravados — "
                              "é o registro 1050 do arquivo digital.")
    travadas = resumo.competencias - resumo.aptas
    if travadas:
        diario.anotar("aviso", f"{milhar(travadas)} competências travadas: "
                      + "; ".join(f"{n} por {codigo.replace('_', ' ')}"
                                  for codigo, n in sorted(resumo.por_motivo.items(),
                                                          key=lambda kv: -kv[1])) + ".")
    if resumo.credito_operacao_propria == 0:
        diario.anotar("aviso", "Crédito da operação própria (art. 271) zerado: depende do "
                               "confronto dos enquadramentos 2 e 4, ainda não apurado.")

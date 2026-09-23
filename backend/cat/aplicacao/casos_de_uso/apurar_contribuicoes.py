"""Etapa: apurar as contribuições — a Gestão Fiscal no padrão do MA.

Segunda etapa do módulo de PIS/COFINS. Lê a **EFD-Contribuições** e a **ECF** do
lote e monta os quadros que o MA exporta na Gestão:

* da EFD-Contribuições saem **PIS e COFINS**, nos 36 quadros — receita por CST,
  contribuição apurada, natureza dos créditos, ajustes e controle de saldos;
* da ECF saem **IRPJ e CSLL** do Lucro Real — Parte A do e-Lalur e do e-Lacs,
  cálculo do imposto e saldo da Parte B.

Qualquer uma das duas fontes pode faltar, e a etapa segue com o que houver: um
trabalho que só tem ECF ainda tem IRPJ/CSLL para mostrar. Faltarem as duas é que
é motivo para recusar.

**Não depende da quebra de SPED.** As duas leem os mesmos arquivos, mas para
coisas diferentes — a quebra produz o par que se confronta com a contabilidade,
esta produz a apuração. Amarrar uma à outra obrigaria a reler 1 GB para ver um
quadro.

A confiança nos números não é a mesma nos dois blocos, e a etapa diz isso: PIS e
COFINS foram conferidos contra o export real do MA em 59 competências; IRPJ e
CSLL nunca passaram por gabarito. Ver `tools/validar_gestao.py`.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import pasta_da_execucao
from cat.aplicacao.casos_de_uso.historico_do_projeto import exigir_que_ande, registrar_de_etapa
from cat.aplicacao.casos_de_uso.rodada import (
    Diario, Freio, caminhos_do_lote, duracao, milhar, nome_de,
)
from cat.dominio.lote import TipoDeArquivo
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.gestao import Andamento, apurar, serializar
from cat.infraestrutura.gestao.montagem import GestaoCancelada
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "apuracao_contribuicoes"
VERSAO_DO_RESUMO = 1


class NadaParaApurar(ValueError):
    """O lote não tem EFD-Contribuições nem ECF."""


def fontes_do_projeto(projeto_id: int, sessao: Session) -> tuple[list[str], list[str]]:
    """As EFD-Contribuições e as ECF do lote, em duas listas."""
    return (caminhos_do_lote(projeto_id, TipoDeArquivo.SPED_CONTRIBUICOES, sessao),
            caminhos_do_lote(projeto_id, TipoDeArquivo.SPED_ECF, sessao))


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "apurar as contribuições")
    contribuicoes, ecfs = fontes_do_projeto(projeto_id, sessao)
    if not contribuicoes and not ecfs:
        raise NadaParaApurar(
            "O lote não tem EFD-Contribuições nem ECF. Importe a pasta com os arquivos que o "
            "cliente transmitiu à Receita: da EFD-Contribuições saem PIS e COFINS, da ECF saem "
            "IRPJ e CSLL.")
    total = len(contribuicoes) + len(ecfs)
    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila", passo="Na fila",
                          arquivos_totais=total, criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Apuração das contribuições · {len(contribuicoes)} EFD-Contribuições e {len(ecfs)} ECF",
        dados={"execucao_id": execucao.id, "contribuicoes": len(contribuicoes),
               "ecf": len(ecfs)},
        autor_id=usuario_id)
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
            except GestaoCancelada:
                log.warning("apuração das contribuições cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. Os quadros pela metade não valem.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Apuração das contribuições cancelada a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("apuração das contribuições falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Apuração das contribuições falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Lendo os arquivos"
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    contribuicoes, ecfs = fontes_do_projeto(execucao.projeto_id, sessao)
    total = len(contribuicoes) + len(ecfs)
    execucao.arquivos_totais = total
    diario.anotar("info", f"{milhar(len(contribuicoes))} EFD-Contribuições e "
                          f"{milhar(len(ecfs))} ECF para apurar.")
    if not contribuicoes:
        diario.anotar("aviso", "Nenhuma EFD-Contribuições no lote: não haverá PIS nem COFINS.")
    if not ecfs:
        diario.anotar("aviso", "Nenhuma ECF no lote: não haverá IRPJ nem CSLL.")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(a: Andamento) -> None:
        execucao.arquivos_lidos = a.arquivos
        execucao.documentos = a.linhas
        execucao.fracao = min(0.99, a.arquivos / max(total, 1))
        execucao.passo = f"Apurando {a.arquivos} de {total}"
        diario.base["andamento"] = {"arquivos": a.arquivos, "linhas": a.linhas}
        diario.salvar_de_vez_em_quando()

    resumo = apurar(contribuicoes, ecfs, destino, avisar=andou, deve_parar=parar)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.arquivos_lidos = resumo.arquivos
    execucao.documentos = resumo.linhas
    diario.base.update(serializar(resumo))
    diario.base["segundos"] = segundos
    if resumo.ilegiveis:
        diario.anotar("aviso", f"{milhar(resumo.ilegiveis)} arquivos não deram para ler — "
                               "veja os avisos abaixo.")
    for aviso in resumo.avisos[:20]:
        diario.anotar("aviso", aviso)
    if "IRPJ" in resumo.tributos:
        diario.anotar("aviso", "IRPJ e CSLL ainda não foram conferidos contra o export do MA: "
                               "o gabarito de referência é de outra empresa. Confira antes de "
                               "entregar (tools/validar_gestao.py).")
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info", f"Concluída em {duracao(segundos)}: {milhar(resumo.quadros)} quadros e "
                          f"{milhar(resumo.linhas)} linhas em {len(resumo.competencias)} "
                          f"competências.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Contribuições apuradas · {milhar(resumo.quadros)} quadros em "
        f"{len(resumo.competencias)} competências ({', '.join(resumo.tributos) or 'nenhum tributo'})",
        dados={"execucao_id": execucao.id, "quadros": resumo.quadros,
               "linhas": resumo.linhas, "tributos": resumo.tributos,
               "competencias": len(resumo.competencias), "segundos": segundos},
        autor_id=execucao.criada_por)

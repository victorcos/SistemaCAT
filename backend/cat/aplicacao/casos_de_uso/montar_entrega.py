"""Montar a entrega — relatório executivo, dossiê e pacote.

Oitava e última etapa. Lê o que as etapas anteriores deixaram e junta num
pacote para baixar:

    1. a situação de cada competência: pronta para envio, prévia ou fora de SP;
    2. o dossiê de cada estabelecimento com competência pronta;
    3. o relatório executivo, o manifesto e o zip.

Gerar não conclui a etapa: um revisor ou gestor aprova o pacote na API, que
grava quem e quando na própria execução (decisão do Victor, 16/09/2026).

Recusa antes de pôr na fila a entrega que sairia de um arquivo digital velho:
se há apuração mais nova que a usada pelo arquivo digital, o pacote levaria
números que a tela da etapa 6 já não mostra.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import pasta_da_execucao
from cat.aplicacao.casos_de_uso.historico_do_projeto import exigir_que_ande, registrar_de_etapa
from cat.aplicacao.casos_de_uso.rodada import Diario, Freio, duracao, milhar, nome_de, reais
from cat.dominio.icms.cat42.entrega import Gravidade
from cat.dominio.icms.cat42.enquadramento import VendaAConsumidor
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.apuracao import ARQUIVO_APURACAO
from cat.infraestrutura.analitico.arquivo_digital import ARQUIVO_ARQUIVOS
from cat.infraestrutura.analitico.entrega import Andamento, Contexto, Fontes, montar, serializar
from cat.infraestrutura.analitico.razao import ARQUIVO_FICHA3
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.log import contexto, obter_log
from cat.versao import versao

log = obter_log(__name__)

ETAPA = "entrega"
VERSAO_DO_RESUMO = 1

ETAPA_ARQUIVO_DIGITAL = "arquivo_digital"
ETAPA_APURACAO = "apuracao"


class NadaParaEntregar(ValueError):
    """O trabalho não está pronto para esta etapa."""


def _ultima_concluida(projeto_id: int, etapa: str, sessao: Session) -> ExecucaoDB | None:
    return sessao.scalar(
        select(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == projeto_id, ExecucaoDB.etapa == etapa,
               ExecucaoDB.situacao == "concluida")
        .order_by(ExecucaoDB.id.desc()).limit(1))


def _exigir_fontes(projeto_id: int, sessao: Session) -> dict[str, ExecucaoDB]:
    """As execuções que a entrega usa, da etapa 7 para trás, pela cadeia que cada uma gravou."""
    arquivo = _ultima_concluida(projeto_id, ETAPA_ARQUIVO_DIGITAL, sessao)
    if arquivo is None or not arquivo.pasta_de_trabalho or not os.path.isfile(
            os.path.join(arquivo.pasta_de_trabalho, ARQUIVO_ARQUIVOS)):
        raise NadaParaEntregar("Gere o arquivo digital antes: a entrega junta os arquivos de envio, a apuração "
                               "e o razão que ele usou.")
    resumo = arquivo.resumo or {}
    apuracao = sessao.get(ExecucaoDB, resumo.get("apuracao_execucao_id") or 0)
    razao = sessao.get(ExecucaoDB, resumo.get("razao_execucao_id") or 0)
    if (apuracao is None or razao is None
            or not os.path.isfile(os.path.join(apuracao.pasta_de_trabalho or "", ARQUIVO_APURACAO))
            or not os.path.isfile(os.path.join(razao.pasta_de_trabalho or "", ARQUIVO_FICHA3))):
        raise NadaParaEntregar("A apuração ou o razão que o arquivo digital usou não estão mais em disco. "
                               "Refaça as etapas 5 a 7.")
    mais_nova = _ultima_concluida(projeto_id, ETAPA_APURACAO, sessao)
    if mais_nova is not None and mais_nova.id != apuracao.id:
        raise NadaParaEntregar(f"Há uma apuração mais nova (#{mais_nova.id}) que o arquivo digital #{arquivo.id} "
                               "não usou. Gere o arquivo digital de novo antes de montar a entrega.")

    fontes = {ETAPA_ARQUIVO_DIGITAL: arquivo, ETAPA_APURACAO: apuracao, "razao": razao}
    # o que vem antes do razão entra na trilha e nas pendências, mas não é obrigatório
    for etapa, identificador in (("st_suportado", (razao.resumo or {}).get("apuracao_execucao_id")),
                                 ("movimentos", (razao.resumo or {}).get("movimentos_execucao_id"))):
        anterior = sessao.get(ExecucaoDB, identificador) if identificador else None
        if anterior is not None:
            fontes[etapa] = anterior
    conferencia = _ultima_concluida(projeto_id, "conferencia", sessao)
    if conferencia is not None:
        fontes["conferencia"] = conferencia
    return fontes


def _contexto(projeto: ProjetoDB, fontes: dict[str, ExecucaoDB], gerado_por: str, sessao: Session) -> Contexto:
    ordem = ("conferencia", "movimentos", "st_suportado", "razao", ETAPA_APURACAO, ETAPA_ARQUIVO_DIGITAL)
    trilha = []
    for etapa in ordem:
        e = fontes.get(etapa)
        if e is None:
            continue
        resumo = e.resumo or {}
        segundos = resumo.get("segundos")
        if segundos is None and e.terminada_em and e.iniciada_em:
            segundos = round((e.terminada_em - e.iniciada_em).total_seconds(), 1)
        trilha.append({"etapa": etapa, "execucao_id": e.id, "terminada_em": e.terminada_em,
                       "iniciada_por": resumo.get("iniciada_por") or nome_de(e.criada_por, sessao),
                       "segundos": segundos})
    razao = fontes["razao"].resumo or {}
    venda = VendaAConsumidor.de(razao.get("venda_a_consumidor"))
    inicio, fim = razao.get("periodo_inicio") or "", razao.get("periodo_fim") or ""
    apurado = f"{inicio[5:7]}/{inicio[:4]} a {fim[5:7]}/{fim[:4]}" if inicio and fim else ""
    return Contexto(
        empresa=projeto.empresa.razao_social if projeto.empresa else "",
        cnpj_matriz=(projeto.empresa.cnpj_matriz or "") if projeto.empresa else "",
        trabalho=projeto.nome,
        periodo=f"{projeto.competencia_ini:%m/%Y} a {projeto.competencia_fim:%m/%Y}",
        periodo_apurado=apurado,
        venda_a_consumidor=venda.rotulo,
        gerado_por=gerado_por,
        gerado_em=datetime.now(timezone.utc),
        versao_do_sistema=versao(),
        resumos={etapa: (e.resumo or {}) for etapa, e in fontes.items()},
        trilha=trilha,
    )


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "montar a entrega")
    fontes = _exigir_fontes(projeto_id, sessao)

    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila",
                          passo="Na fila", criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Entrega sobre o arquivo digital #{fontes[ETAPA_ARQUIVO_DIGITAL].id}",
        dados={"execucao_id": execucao.id, "arquivo_digital_execucao_id": fontes[ETAPA_ARQUIVO_DIGITAL].id},
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
                log.warning("montagem da entrega cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. Nenhum pacote ficou gravado.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Montagem da entrega cancelada a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("montagem da entrega falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Montagem da entrega falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Reunindo as etapas"
    execucao.fracao = 0.05
    gerado_por = nome_de(execucao.criada_por, sessao)
    diario.base["iniciada_por"] = gerado_por
    sessao.commit()

    fontes = _exigir_fontes(execucao.projeto_id, sessao)
    projeto = sessao.get(ProjetoDB, execucao.projeto_id)
    ctx = _contexto(projeto, fontes, gerado_por, sessao)
    diario.base.update({f"{etapa}_execucao_id": e.id for etapa, e in fontes.items()})
    diario.anotar("info", f"Entrega sobre o arquivo digital #{fontes[ETAPA_ARQUIVO_DIGITAL].id}, a apuração "
                          f"#{fontes[ETAPA_APURACAO].id} e o razão #{fontes['razao'].id}.")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(a: Andamento) -> None:
        execucao.passo = a.passo
        execucao.documentos = a.estabelecimentos
        execucao.fracao = 0.1 + 0.85 * a.estabelecimentos / max(a.total, 1) if a.total else 0.1
        diario.base["andamento"] = {"estabelecimentos": a.estabelecimentos, "total": a.total}
        diario.salvar_de_vez_em_quando()

    resumo = montar(Fontes(arquivo_digital=fontes[ETAPA_ARQUIVO_DIGITAL].pasta_de_trabalho,
                           apuracao=fontes[ETAPA_APURACAO].pasta_de_trabalho,
                           razao=fontes["razao"].pasta_de_trabalho),
                    destino, ctx, avisar=andou, deve_parar=parar)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Aguardando aprovação"
    execucao.fracao = 1.0
    execucao.documentos = resumo.arquivos_no_pacote
    diario.base.update(serializar(resumo))
    diario.base["segundos"] = segundos
    _anotar(diario, resumo)
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info", f"Pacote montado em {duracao(segundos)}: {milhar(resumo.para_envio)} competências "
                          f"prontas para envio em {milhar(resumo.estabelecimentos_no_dossie)} estabelecimentos, "
                          f"{reais(resumo.ressarcimento_para_envio)} de ressarcimento. Aguarda a aprovação de um "
                          "revisor ou gestor.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Pacote de entrega montado · {milhar(resumo.para_envio)} competências para envio, "
        f"{reais(resumo.ressarcimento_para_envio)} · aguarda aprovação",
        dados={"execucao_id": execucao.id, "para_envio": resumo.para_envio, "previas": resumo.previas,
               "arquivos_no_pacote": resumo.arquivos_no_pacote, "segundos": segundos},
        autor_id=execucao.criada_por)


def _anotar(diario: Diario, r) -> None:
    if r.para_envio == 0:
        diario.anotar("aviso", "Nenhuma competência pronta para envio: o pacote leva só o relatório, com o que falta "
                               "em cada uma.")
    if r.sem_arquivo:
        diario.anotar("aviso", f"{milhar(r.sem_arquivo)} competências de SP sem arquivo gerado: o arquivo digital é "
                               "de antes desta apuração.")
    travas = [p for p in r.pendencias if p.gravidade is Gravidade.TRAVA]
    atencao = [p for p in r.pendencias if p.gravidade is Gravidade.ATENCAO]
    if travas:
        diario.anotar("aviso", f"{milhar(len(travas))} pendências travam o envio, entre elas «{travas[0].rotulo.lower()}» "
                               f"({milhar(travas[0].quantidade)} {travas[0].unidade}). A lista inteira está no relatório.")
    if atencao:
        diario.anotar("info", f"{milhar(len(atencao))} pendências pedem atenção antes de entregar.")

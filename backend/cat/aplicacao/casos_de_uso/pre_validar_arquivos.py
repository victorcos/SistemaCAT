"""Pré-validar os arquivos digitais que o cliente já transmitiu.

Fora do roteiro do trabalho, de propósito: não depende de nenhuma etapa, e o
trabalho de auditoria pode nem ter EFD — só os TXT que outra ferramenta gerou
(decisão do Victor, 16/09/2026). Lê o que o lote tem: o arquivo digital solto
e os zips, que costumam trazê-lo aos milhares.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import pasta_da_execucao
from cat.aplicacao.casos_de_uso.historico_do_projeto import exigir_que_ande, registrar_de_etapa
from cat.aplicacao.casos_de_uso.rodada import Diario, Freio, duracao, milhar, nome_de
from cat.dominio.lote import TipoDeArquivo
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.pre_validacao_do_cliente import Andamento, pre_validar, serializar
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ArquivoDoLoteDB, ExecucaoDB, LoteDB, ProjetoDB
from cat.config import obter_config
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "pre_validacao"
VERSAO_DO_RESUMO = 1


class NadaParaPreValidar(ValueError):
    """O lote não tem arquivo digital nem zip."""


def fontes_do_projeto(projeto_id: int, sessao: Session) -> list[str]:
    """O arquivo digital solto e os zips do lote — o que está dentro só se sabe abrindo.

    O zip que tem XML de nota virou `xml_compactado` na v0.53.2, e pode ter o
    arquivo digital junto: entra também.
    """
    return list(sessao.scalars(
        select(ArquivoDoLoteDB.caminho)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .where(LoteDB.projeto_id == projeto_id,
               (ArquivoDoLoteDB.tipo == TipoDeArquivo.CAT42_ARQUIVO_DIGITAL.value)
               | ((ArquivoDoLoteDB.tipo.in_((TipoDeArquivo.COMPACTADO.value,
                                             TipoDeArquivo.XML_COMPACTADO.value)))
                  & ArquivoDoLoteDB.nome.ilike("%.zip")))
        .order_by(ArquivoDoLoteDB.caminho).distinct()))


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "pré-validar os arquivos do cliente")
    fontes = fontes_do_projeto(projeto_id, sessao)
    if not fontes:
        raise NadaParaPreValidar("O lote não tem arquivo digital da CAT 42 nem zip. Importe a pasta com os "
                                 "arquivos que o cliente transmitiu.")
    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila", passo="Na fila",
                          arquivos_totais=len(fontes), criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Pré-validação dos arquivos do cliente · {len(fontes)} fontes do lote",
        dados={"execucao_id": execucao.id, "fontes": len(fontes)}, autor_id=usuario_id)
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
                log.warning("pré-validação cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. Nada foi gravado.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Pré-validação dos arquivos do cliente cancelada a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True}, autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("pré-validação falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Pré-validação dos arquivos do cliente falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]}, autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Lendo os arquivos do cliente"
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    projeto = sessao.get(ProjetoDB, execucao.projeto_id)
    raiz = projeto.empresa.cnpj_raiz
    fontes = fontes_do_projeto(execucao.projeto_id, sessao)
    execucao.arquivos_totais = len(fontes)
    diario.anotar("info", f"Pré-validação sobre {milhar(len(fontes))} fontes do lote (arquivo digital solto e zips).")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(a: Andamento) -> None:
        execucao.documentos = a.arquivos
        execucao.bytes_lidos = a.bytes
        diario.base["andamento"] = {"arquivos": a.arquivos, "bytes": a.bytes}
        diario.salvar_de_vez_em_quando()

    resumo = pre_validar(fontes, destino, raiz, avisar=andou, deve_parar=parar,
                         processos=obter_config().processos_para_arquivos)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.documentos = resumo.arquivos
    execucao.bytes_lidos = resumo.bytes
    diario.base.update(serializar(resumo))
    diario.base["segundos"] = segundos
    for n, texto in ((resumo.repetidos, "arquivos repetidos (mesmo estabelecimento e mês) não foram lidos de novo"),
                     (resumo.de_outra_empresa, "arquivos de outra empresa ficaram de fora"),
                     (resumo.nao_sao_da_cat42, "TXT que não são arquivo digital da CAT 42 foram ignorados"),
                     (resumo.ilegiveis, "arquivos ou zips ilegíveis")):
        if n:
            diario.anotar("aviso", f"{milhar(n)} {texto}.")
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info", f"Concluída em {duracao(segundos)}: {milhar(resumo.arquivos)} arquivos, "
                          f"{milhar(resumo.com_erro)} com erro; {milhar(resumo.itens_que_fecham)} de "
                          f"{milhar(resumo.itens_recompostos)} itens recompostos fecham com o 1050.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Arquivos do cliente pré-validados · {milhar(resumo.arquivos)} lidos, {milhar(resumo.com_erro)} com erro",
        dados={"execucao_id": execucao.id, "arquivos": resumo.arquivos, "com_erro": resumo.com_erro,
               "segundos": segundos}, autor_id=execucao.criada_por)

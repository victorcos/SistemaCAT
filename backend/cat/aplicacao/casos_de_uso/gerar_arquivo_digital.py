"""Gerar o arquivo digital — um por estabelecimento de SP e por mês.

Sétima etapa. Lê o que as etapas anteriores deixaram e escreve os registros
0000 a 1200 no leiaute da CAT 42:

    1. o cadastro do mês (0000 e 0150) do bloco 0 das EFD vigentes;
    2. para cada competência de SP apurada na etapa 6: 0200 do cadastro de
       itens, 1050 dos saldos, 1100 e 1200 das linhas da Ficha 3;
    3. a pré-validação de cada arquivo, lido de volta do disco.

Só vai para o envio a competência apta, sem trava e sem erro na pré-validação;
as outras de SP saem como prévia (decisão do Victor, 16/09/2026).

Recusa antes de pôr na fila o que daria arquivo de uma coisa e apuração de
outra: razão montado com outra escolha de venda a consumidor, apuração feita
sobre um razão que já não é o último, razão de antes de a Ficha 3 guardar o
documento de cada linha.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.apurar_periodo import ETAPA as ETAPA_APURACAO
from cat.aplicacao.casos_de_uso.apurar_periodo import razao_concluido
from cat.aplicacao.casos_de_uso.apurar_suportado import movimentacao_concluida
from cat.aplicacao.casos_de_uso.conferir_documentos import caminhos_de_efd_vigentes, pasta_da_execucao
from cat.aplicacao.casos_de_uso.historico_do_projeto import exigir_que_ande, registrar_de_etapa
from cat.aplicacao.casos_de_uso.montar_razao import venda_a_consumidor_do_projeto
from cat.aplicacao.casos_de_uso.rodada import Diario, Freio, duracao, milhar, nome_de, reais
from cat.dominio.cat42.enquadramento import VendaAConsumidor
from cat.dominio.lote import TipoDeArquivo
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.apuracao import ARQUIVO_APURACAO
from cat.infraestrutura.analitico.arquivo_digital import (
    Andamento,
    Fontes,
    gerar,
    serializar,
)
from cat.infraestrutura.analitico.razao import ARQUIVO_FICHA3
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ArquivoDoLoteDB, ExecucaoDB, LoteDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "arquivo_digital"
VERSAO_DO_RESUMO = 1


class NadaParaGerar(ValueError):
    """O trabalho não está pronto para esta etapa."""


def _ultima_concluida(projeto_id: int, etapa: str, sessao: Session) -> ExecucaoDB | None:
    return sessao.scalar(
        select(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == projeto_id, ExecucaoDB.etapa == etapa,
               ExecucaoDB.situacao == "concluida")
        .order_by(ExecucaoDB.id.desc()).limit(1))


def _exigir_fontes(projeto_id: int, sessao: Session) -> tuple[ExecucaoDB, ExecucaoDB, ExecucaoDB, VendaAConsumidor]:
    apuracao = _ultima_concluida(projeto_id, ETAPA_APURACAO, sessao)
    if apuracao is None or not apuracao.pasta_de_trabalho or not os.path.isfile(
            os.path.join(apuracao.pasta_de_trabalho, ARQUIVO_APURACAO)):
        raise NadaParaGerar("Apure o período antes: o arquivo digital sai das competências e dos "
                            "saldos da etapa 6.")
    razao_id = (apuracao.resumo or {}).get("razao_execucao_id")
    razao = sessao.get(ExecucaoDB, razao_id) if razao_id else None
    if razao is None or not razao.pasta_de_trabalho or not os.path.isfile(
            os.path.join(razao.pasta_de_trabalho, ARQUIVO_FICHA3)):
        raise NadaParaGerar("Os arquivos do razão desta apuração não estão mais em disco. Monte o razão "
                            "e apure o período de novo.")
    mais_recente = razao_concluido(projeto_id, sessao)
    if mais_recente is not None and mais_recente.id != razao.id:
        raise NadaParaGerar(f"Há um razão mais novo (#{mais_recente.id}) que a apuração #{apuracao.id} não "
                            "usou. Apure o período de novo antes de gerar o arquivo.")
    if "numero_item" not in pq.read_schema(os.path.join(razao.pasta_de_trabalho, ARQUIVO_FICHA3)).names:
        raise NadaParaGerar("O razão é de uma versão que não guardava a chave e o nº do item de cada "
                            "linha, que o registro 1100 exige. Monte o razão e apure o período de novo.")
    usada = VendaAConsumidor.de((razao.resumo or {}).get("venda_a_consumidor"))
    escolhida = venda_a_consumidor_do_projeto(projeto_id, sessao)
    if usada is not escolhida:
        raise NadaParaGerar(f"O razão foi montado com a venda a consumidor em «{usada.rotulo}», e o trabalho "
                            f"hoje está em «{escolhida.rotulo}». Monte o razão e apure o período de novo.")
    movimentos = movimentacao_concluida(projeto_id, sessao)
    if movimentos is None or not movimentos.pasta_de_trabalho or not os.path.isdir(movimentos.pasta_de_trabalho):
        raise NadaParaGerar("Os arquivos da extração de movimentos não estão mais em disco: é dela o "
                            "cadastro de itens do 0200. Extraia os movimentos de novo.")
    return apuracao, razao, movimentos, usada


def _efds(projeto_id: int, sessao: Session) -> list:
    """As EFD que valem, com estabelecimento e mês — a retificadora já venceu."""
    vigentes, _ = caminhos_de_efd_vigentes(projeto_id, sessao)
    vale = set(vigentes)
    return [(caminho, cnpj, competencia) for caminho, cnpj, competencia in sessao.execute(
        select(ArquivoDoLoteDB.caminho, ArquivoDoLoteDB.cnpj, ArquivoDoLoteDB.competencia)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .where(LoteDB.projeto_id == projeto_id,
               ArquivoDoLoteDB.tipo == TipoDeArquivo.SPED_ICMS_IPI.value,
               ArquivoDoLoteDB.cnpj.is_not(None), ArquivoDoLoteDB.competencia.is_not(None))
        .order_by(ArquivoDoLoteDB.caminho)).all() if caminho in vale]


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "gerar o arquivo digital")
    apuracao, razao, _, _ = _exigir_fontes(projeto_id, sessao)

    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila",
                          passo="Na fila", criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Arquivo digital sobre a apuração #{apuracao.id}",
        dados={"execucao_id": execucao.id, "apuracao_execucao_id": apuracao.id, "razao_execucao_id": razao.id},
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
                log.warning("geração do arquivo digital cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. Nenhum arquivo ficou gravado.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Geração do arquivo digital cancelada a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("geração do arquivo digital falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Geração do arquivo digital falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Lendo o cadastro das EFD"
    execucao.fracao = 0.05
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    apuracao, razao, movimentos, venda = _exigir_fontes(execucao.projeto_id, sessao)
    efds = _efds(execucao.projeto_id, sessao)
    diario.base.update({"apuracao_execucao_id": apuracao.id, "razao_execucao_id": razao.id,
                        "movimentos_execucao_id": movimentos.id})
    diario.anotar("info", f"Gerando sobre a apuração #{apuracao.id}, o razão #{razao.id} e "
                          f"{milhar(len(efds))} EFD vigentes. Venda a consumidor final: {venda.rotulo.lower()}.")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(a: Andamento) -> None:
        execucao.passo = "Escrevendo e pré-validando os arquivos"
        execucao.documentos = a.arquivos
        execucao.fracao = 0.1 + 0.88 * a.arquivos / max(a.total, 1)
        diario.base["andamento"] = {"arquivos": a.arquivos, "total": a.total}
        diario.salvar_de_vez_em_quando()

    fontes = Fontes(apuracao=apuracao.pasta_de_trabalho, razao=razao.pasta_de_trabalho,
                    movimentacao=movimentos.pasta_de_trabalho, efds=efds)
    resumo = gerar(fontes, destino, venda_a_consumidor=venda, avisar=andou, deve_parar=parar)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.documentos = resumo.arquivos
    diario.base.update(serializar(resumo))
    diario.base["segundos"] = segundos
    _anotar(diario, resumo)
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info", f"Concluída em {duracao(segundos)}: {milhar(resumo.arquivos)} arquivos, "
                          f"{milhar(resumo.para_envio)} para envio e {milhar(resumo.previas)} prévias; "
                          f"{reais(resumo.ressarcimento_para_envio)} de ressarcimento nos de envio.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Arquivo digital · {milhar(resumo.para_envio)} para envio e {milhar(resumo.previas)} prévias, "
        f"{reais(resumo.ressarcimento_para_envio)} a pedir",
        dados={"execucao_id": execucao.id, "arquivos": resumo.arquivos, "para_envio": resumo.para_envio,
               "previas": resumo.previas, "linhas": resumo.linhas, "segundos": segundos},
        autor_id=execucao.criada_por)


def _anotar(diario: Diario, r) -> None:
    if r.competencias_fora_de_sp:
        diario.anotar("info", f"{milhar(r.competencias_fora_de_sp)} competências fora de SP não geram "
                              "arquivo: a CAT 42 é paulista.")
    if r.competencias == 0:
        diario.anotar("aviso", "Nenhuma competência de São Paulo na apuração: não há arquivo a gerar.")
    if r.efds_ilegiveis:
        diario.anotar("aviso", f"{milhar(r.efds_ilegiveis)} EFD não puderam ser lidas para o cadastro (0000 e 0150).")
    if r.linhas_sem_documento:
        diario.anotar("aviso", f"{milhar(r.linhas_sem_documento)} linhas da Ficha 3 sem documento para o "
                               "arquivo — a venda de PDV do relatório não tem chave nem nº do item.")
    for t in serializar(r)["por_trava"]:
        diario.anotar("aviso", f"{milhar(t['arquivos'])} arquivos com «{t['rotulo'].lower()}».")
    if r.itens_recompostos:
        diario.anotar("info", f"Pré-validação: {milhar(r.itens_que_fecham)} de {milhar(r.itens_recompostos)} itens "
                              f"recompostos fecham com o 1050; {milhar(r.erros)} erros e {milhar(r.avisos)} avisos.")

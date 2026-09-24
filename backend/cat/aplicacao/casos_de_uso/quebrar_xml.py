"""Etapa: quebrar os XML do lote.

Abre as notas item a item e deixa em disco o parquet de onde sai a planilha —
uma linha por item, com as colunas que quem confere escolher.

**Não é uma leitura nova.** É a mesma de `itens_do_xml.py`, que a extração de
movimentos já usava desde a etapa 3 do ICMS: trata NF-e, NFC-e e CF-e SAT,
recusa CT-e e evento de cancelamento, escolhe entre cópias da mesma chave a
autorizada, e lê zip sem descompactar em disco. O que muda aqui é o propósito:
ali o XML alimenta a CAT 42; aqui ele é o produto.

**Serve aos dois módulos.** No ICMS, é o item que a EFD não traz — NF-e de
emissão própria e NFC-e vão à escrituração só com o analítico. No PIS/COFINS, é
onde estão o CST e a alíquota que o C170 consolidado esconde. Por isso a trilha
existe nos dois, e a planilha deixa escolher as colunas: quem confere ICMS não
quer ver ISSQN, e quem confere contribuição não quer ver ST.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import (
    caminhos_do_projeto,
    pasta_da_execucao,
)
from cat.aplicacao.casos_de_uso.historico_do_projeto import exigir_que_ande, registrar_de_etapa
from cat.aplicacao.casos_de_uso.rodada import (
    Diario, duracao, milhar, nome_de, raiz_do_trabalho,
)
from cat.dominio.lote import TipoDeArquivo
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.itens_do_xml import (
    ProgressoDoXml,
    extrair_itens_do_xml,
)
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "quebra_xml"
VERSAO_DO_RESUMO = 1

# o zip do portal entra inteiro: dentro dele vêm as notas e os eventos
FONTES = (TipoDeArquivo.XML_NFE, TipoDeArquivo.XML_COMPACTADO)


class NadaParaQuebrar(ValueError):
    """O lote não tem XML."""


def fontes_do_projeto(projeto_id: int, sessao: Session) -> list[str]:
    return caminhos_do_projeto(projeto_id, FONTES, sessao)


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "quebrar os XML")
    xmls = fontes_do_projeto(projeto_id, sessao)
    if not xmls:
        raise NadaParaQuebrar(
            "O lote não tem XML. Importe a pasta com as notas — soltas ou em zip, "
            "como o portal as entrega.")

    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila", passo="Na fila",
                          arquivos_totais=len(xmls), criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Quebra de XML · {milhar(len(xmls))} arquivos",
        dados={"execucao_id": execucao.id, "arquivos": len(xmls)},
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
            except Exception as erro:            # noqa: BLE001
                log.exception("quebra de xml falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Quebra de XML falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Lendo os XML"
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    xmls = fontes_do_projeto(execucao.projeto_id, sessao)
    total = len(xmls)
    execucao.arquivos_totais = total
    diario.anotar("info", f"{milhar(total)} arquivos de XML para abrir.")

    inicio = time.time()

    def andou(p: ProgressoDoXml) -> None:
        execucao.arquivos_lidos = p.arquivos_lidos
        execucao.documentos = p.documentos
        execucao.bytes_lidos = p.bytes_lidos
        execucao.fracao = min(0.99, p.arquivos_lidos / max(total, 1))
        execucao.passo = f"Lendo {milhar(p.arquivos_lidos)} de {milhar(total)}"
        diario.base["andamento"] = {"arquivos": p.arquivos_lidos, "notas": p.documentos,
                                    "itens": p.itens}
        diario.salvar_de_vez_em_quando()

    raiz = raiz_do_trabalho(execucao.projeto_id, sessao)
    progresso = extrair_itens_do_xml(xmls, destino, avisar=andou, cnpj_raiz=raiz)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.arquivos_lidos = progresso.arquivos_lidos
    execucao.documentos = progresso.documentos
    execucao.bytes_lidos = progresso.bytes_lidos
    diario.base.update({
        "versao": VERSAO_DO_RESUMO,
        "arquivos": progresso.arquivos_lidos,
        "notas": progresso.documentos,
        "itens": progresso.itens,
        "repetidos": progresso.repetidos,
        "nao_sao_documento": progresso.nao_sao_documento,
        "ilegiveis": progresso.ilegiveis,
        "sem_item": progresso.sem_item,
        "nao_autorizados": progresso.nao_autorizados,
        "copias_trocadas": progresso.copias_trocadas,
        "cancelamentos": len(progresso.cancelamentos),
        "de_outra_empresa": progresso.de_outra_empresa,
        "cnpjs_de_fora": dict(sorted(progresso.cnpjs_de_fora.items(),
                                     key=lambda par: -par[1])),
        "segundos": segundos,
    })

    # o descarte por empresa tem linha própria: é o único que fala de outro
    # cliente, e quem confere precisa ver de quem era o que saiu
    if progresso.de_outra_empresa:
        quem = sorted(progresso.cnpjs_de_fora, key=lambda c: -progresso.cnpjs_de_fora[c])[:3]
        reticencia = "…" if len(progresso.cnpjs_de_fora) > len(quem) else ""
        diario.anotar(
            "aviso",
            f"{milhar(progresso.de_outra_empresa)} nota(s) de outra empresa ficaram de fora "
            f"(CNPJ {', '.join(quem)}{reticencia}). O trabalho é da empresa do cadastro: "
            "nota de outro CNPJ não entra na planilha.")

    # nada some em silêncio: cada descarte tem contador e, aqui, uma linha
    for quantos, o_que in (
        (progresso.repetidos, "cópias repetidas da mesma nota"),
        (progresso.nao_sao_documento, "arquivos que não são documento de mercadoria "
                                      "(evento, CT-e, inutilização)"),
        (progresso.ilegiveis, "arquivos que não deram para ler"),
        (progresso.sem_item, "notas sem item"),
        (progresso.nao_autorizados, "notas com protocolo que não autoriza"),
    ):
        if quantos:
            diario.anotar("aviso", f"{milhar(quantos)} {o_que}.")
    if progresso.copias_trocadas:
        diario.anotar("info", f"{milhar(progresso.copias_trocadas)} notas tiveram a cópia "
                              "sem protocolo substituída pela autorizada.")

    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info", f"Concluída em {duracao(segundos)}: {milhar(progresso.documentos)} "
                          f"notas e {milhar(progresso.itens)} itens.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"XML quebrados · {milhar(progresso.documentos)} notas e "
        f"{milhar(progresso.itens)} itens",
        dados={"execucao_id": execucao.id, "notas": progresso.documentos,
               "itens": progresso.itens},
        autor_id=execucao.criada_por)
    diario.salvar()
    sessao.commit()

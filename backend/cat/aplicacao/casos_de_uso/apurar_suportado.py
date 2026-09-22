"""Apurar o ICMS suportado de cada item de entrada.

Quarta etapa. Roda fora da requisição, como as anteriores:

    1. relatórios do cliente → o imposto que o fornecedor informou, por
       (chave, código). É a fonte que fecha o buraco do CST 60;
    2. cascata sobre cada item de entrada da movimentação — destacado na
       nota, informado, reconstruído por base e alíquota, não apurável;
    3. resumo no banco: quanto apurou, de onde veio, o que falta e as quebras
       que a tela mostra sem reler o parquet.

Depende da movimentação concluída: é o `movimentos.parquet` dela que se
percorre. O resultado fica numa pasta própria — rodar a apuração de novo não
pode apagar o que a etapa 3 produziu.

## Cancelar

A tela pode mandar parar. Quem pede grava "cancelando" na execução; a rodada
confere isso entre um relatório e outro e entre um lote de itens e outro, e
para sem deixar meio resultado em disco. É cooperativo de propósito: matar a
linha de execução no meio de uma gravação de parquet deixaria um arquivo que
parece inteiro e não é.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import (
    caminhos_do_projeto,
    pasta_da_execucao,
)
from cat.aplicacao.casos_de_uso.extrair_movimentos import ETAPA as ETAPA_MOVIMENTOS
from cat.aplicacao.casos_de_uso.historico_do_projeto import (
    exigir_que_ande,
    registrar_de_etapa,
)
from cat.dominio.icms.cat42.suportado import Pendencia, ResumoDaApuracao
from cat.dominio.lote import TipoDeArquivo
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_MOVIMENTOS
from cat.infraestrutura.analitico.suportado import (
    ARQUIVO_RETIDO,
    Andamento,
    ApuracaoCancelada,
    RetidoExtraido,
    apurar,
    contar_entradas,
    extrair_retido,
    fatias_por_fonte,
    quebras,
)
from cat.aplicacao.casos_de_uso.rodada import (
    CancelamentoRecusado,  # noqa: F401 — quem já importava daqui
    Diario,
    Freio,
    cancelar,  # noqa: F401
    duracao as _duracao,
    milhar as _milhar,
    nome_de as _nome,
    pct as _pct,
)
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "st_suportado"

# a versão do resumo. A tela usa para reconhecer rodada de antes desta forma e
# pedir que se rode de novo, em vez de mostrar cartão vazio como se fosse zero
VERSAO_DO_RESUMO = 2

# a leitura dos relatórios é a metade lenta; a cascata, a outra
FRACAO_DOS_RELATORIOS = 0.40
FRACAO_DA_CASCATA = 0.85
# o índice por documento vem depois: noventa segundos numa base real
FRACAO_DO_INDICE = 0.96


class NadaParaApurar(ValueError):
    """O trabalho não está pronto para esta etapa."""


def movimentacao_concluida(projeto_id: int, sessao: Session) -> ExecucaoDB | None:
    """A última extração de movimentos concluída, se ainda tiver o parquet."""
    return sessao.scalar(
        select(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == projeto_id,
               ExecucaoDB.etapa == ETAPA_MOVIMENTOS,
               ExecucaoDB.situacao == "concluida")
        .order_by(ExecucaoDB.id.desc())
        .limit(1)
    )


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "apurar o ICMS suportado")

    movimentos = movimentacao_concluida(projeto_id, sessao)
    if movimentos is None:
        raise NadaParaApurar(
            "Conclua a extração de movimentos antes: a apuração percorre os "
            "itens de entrada que ela produziu."
        )
    if not movimentos.pasta_de_trabalho or not os.path.isfile(
            os.path.join(movimentos.pasta_de_trabalho, ARQUIVO_MOVIMENTOS)):
        raise NadaParaApurar(
            "Os arquivos da última extração de movimentos não estão mais em "
            "disco. Rode a extração de movimentos de novo."
        )

    relatorios = caminhos_do_projeto(
        projeto_id, (TipoDeArquivo.GERENCIAL_MOVIMENTO,), sessao)
    execucao = ExecucaoDB(
        projeto_id=projeto_id,
        etapa=ETAPA,
        situacao="na_fila",
        passo="Na fila",
        arquivos_totais=len(relatorios),
        criada_por=usuario_id,
    )
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Apuração do ICMS suportado · {len(relatorios)} relatórios do cliente",
        dados={"execucao_id": execucao.id, "relatorios": len(relatorios),
               "movimentos_execucao_id": movimentos.id},
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
        diario = Diario(execucao, sessao, VERSAO_DO_RESUMO)
        with contexto(etapa=ETAPA, execucao_id=execucao_id,
                      projeto_id=execucao.projeto_id):
            try:
                _rodar(execucao, destino, sessao, diario)
            except ApuracaoCancelada:
                log.warning("apuração do ICMS suportado cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. Nada foi gravado como resultado.")
                sessao.commit()
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Apuração do ICMS suportado cancelada a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por,
                )
            except Exception as erro:            # noqa: BLE001
                log.exception("apuração do ICMS suportado falhou",
                              extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                sessao.commit()
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Apuração do ICMS suportado falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por,
                )


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    # o pedido de cancelar pode chegar entre a fila reivindicar e a rodada
    # começar; regravar "rodando" por cima dele o apagaria
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Lendo os relatórios do cliente"
    diario.base["iniciada_por"] = _nome(execucao.criada_por, sessao)
    sessao.commit()

    movimentos = movimentacao_concluida(execucao.projeto_id, sessao)
    if movimentos is None or not movimentos.pasta_de_trabalho:
        raise NadaParaApurar("A extração de movimentos concluída não foi encontrada.")
    pasta_movimentos = movimentos.pasta_de_trabalho
    diario.base["movimentos_execucao_id"] = movimentos.id

    relatorios = caminhos_do_projeto(
        execucao.projeto_id, (TipoDeArquivo.GERENCIAL_MOVIMENTO,), sessao)
    execucao.arquivos_totais = len(relatorios)
    diario.anotar("info", f"Rodada iniciada sobre a movimentação #{movimentos.id} "
                          f"e {len(relatorios)} relatórios do cliente.")
    sessao.commit()

    inicio = time.time()
    parar = Freio(execucao.id)

    # 1. o imposto que o cliente informou
    def relatorio_lido(n: int, total: int) -> None:
        execucao.arquivos_lidos = n
        execucao.fracao = FRACAO_DOS_RELATORIOS * n / max(total, 1)
        diario.salvar_de_vez_em_quando()

    retido = extrair_retido(relatorios, os.path.join(destino, ARQUIVO_RETIDO),
                            avisar=relatorio_lido, deve_parar=parar)
    _anotar_retido(diario, retido)

    # 2. a cascata
    total = contar_entradas(pasta_movimentos)
    execucao.arquivos_lidos = execucao.arquivos_totais
    execucao.passo = "Percorrendo os itens de entrada"
    execucao.fracao = FRACAO_DOS_RELATORIOS
    diario.anotar("info", f"{_milhar(total)} itens de entrada a percorrer.")
    sessao.commit()

    def itens_percorridos(a: Andamento) -> None:
        execucao.documentos = a.itens
        execucao.fracao = FRACAO_DOS_RELATORIOS + (
            (FRACAO_DA_CASCATA - FRACAO_DOS_RELATORIOS) * a.itens / max(total, 1))
        diario.base["andamento"] = {"itens": a.itens, "apurados": a.apurados,
                                    "estabelecimentos": a.estabelecimentos,
                                    "total": total}
        diario.salvar_de_vez_em_quando()

    def indexando() -> None:
        execucao.passo = "Agrupando por documento para a tela"
        execucao.fracao = FRACAO_DA_CASCATA
        diario.salvar()

    resumo = apurar(pasta_movimentos, destino, avisar=itens_percorridos, deve_parar=parar,
                    ao_indexar=indexando)

    execucao.passo = "Montando as quebras"
    execucao.fracao = FRACAO_DO_INDICE
    sessao.commit()
    q = quebras(destino)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.documentos = resumo.itens
    diario.base.update(serializar(resumo, q, retido))
    diario.base["segundos"] = segundos
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info", f"Concluída em {_duracao(segundos)}: {_milhar(resumo.itens)} itens, "
                          f"{_pct(resumo.cobertura)} com valor apurado.")

    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"ICMS suportado apurado · {_milhar(resumo.itens)} itens, "
        f"{_pct(resumo.cobertura)} de cobertura",
        dados={"execucao_id": execucao.id, "itens": resumo.itens,
               "apurados": resumo.itens_apurados,
               "valor": str(resumo.valor_total), "segundos": segundos},
        autor_id=execucao.criada_por,
    )
    log.info("ICMS suportado apurado e resumido",
             extra={"segundos": segundos, "itens": resumo.itens,
                    "apurados": resumo.itens_apurados,
                    "valor": str(resumo.valor_total)})


def _anotar_retido(diario: Diario, r: RetidoExtraido) -> None:
    diario.base["relatorios"] = vars(r)
    if not r.arquivos:
        diario.anotar("aviso", "Nenhum relatório do cliente no trabalho: o CST 60 "
                               "fica sem a fonte que costuma preenchê-lo.")
        return
    diario.anotar("info", f"{r.arquivos} relatórios vistos · {_milhar(r.itens)} itens "
                          "com imposto informado"
                          + (f"; {r.so_de_saidas} só de saídas, deixados de lado." if r.so_de_saidas else "."))
    if r.recusados:
        diario.anotar("aviso", f"{r.recusados} relatórios ilegíveis ou de outra espécie "
                               "ficaram de fora.")
    if r.sem_chave:
        diario.anotar("aviso", f"{_milhar(r.sem_chave)} linhas de entrada sem chave de 44 "
                               "dígitos não casam com a EFD.")


def serializar(resumo: ResumoDaApuracao, q: dict, retido: RetidoExtraido | None = None) -> dict:
    """O resumo vira JSON no banco. Decimal não é JSON: vai como texto."""
    return {
        "versao": VERSAO_DO_RESUMO,
        "itens": resumo.itens,
        "apurados": resumo.itens_apurados,
        "cobertura": round(resumo.cobertura, 4),
        "valor_total": str(resumo.valor_total),
        "valor_documental": str(resumo.valor_documental),
        "fracao_documental": round(resumo.fracao_documental, 4),
        "itens_com_valor_do_xml": resumo.itens_com_valor_do_xml,
        "itens_com_retido_do_xml": resumo.itens_com_retido_do_xml,
        "por_fonte": [{**f, "valor": str(f["valor"])} for f in fatias_por_fonte(resumo)],
        "por_pendencia": {p.value: resumo.por_pendencia[p] for p in Pendencia},
        "por_cst": [{**c, "valor": str(c["valor"])} for c in q["por_cst"]],
        "por_competencia": [{**c, "valor": str(c["valor"])} for c in q["por_competencia"]],
        "estabelecimentos": q["estabelecimentos"],
        "cst_sem_o_que_apurar": q["cst_sem_o_que_apurar"],
    }

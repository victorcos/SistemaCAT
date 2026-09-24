"""Etapa: as exclusões da base do PIS/COFINS.

Hoje calcula uma tese — as próprias contribuições fora da base. O ICMS
destacado (Tema 69) entra depois, no mesmo parquet, com uma coluna de tese que
já existe.

**Não depende de a Gestão ter rodado, mas agradece quando rodou.** Se houver
agregado de uma Gestão concluída, a rodada sai em segundos; se não houver, lê
os SPED ela mesma — uma hora nesta casa — e deixa o agregado gravado, para que
a tese seguinte não pague de novo.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso import apurar_contribuicoes
from cat.aplicacao.casos_de_uso.conferir_documentos import pasta_da_execucao
from cat.aplicacao.casos_de_uso.historico_do_projeto import exigir_que_ande, registrar_de_etapa
from cat.aplicacao.casos_de_uso.rodada import (
    Diario, Freio, caminhos_do_lote, duracao, milhar, nome_de,
)
from cat.dominio.lote import TipoDeArquivo
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.exclusoes import (
    Andamento,
    ExclusaoCancelada,
    apurar,
    serializar,
)
from cat.infraestrutura.gestao.agregados import caminho as caminho_dos_agregados
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "exclusoes"
VERSAO_DO_RESUMO = 1


class NadaParaExcluir(ValueError):
    """O lote não tem EFD-Contribuições: não há receita de onde excluir."""


def fontes_do_projeto(projeto_id: int, sessao: Session) -> list[str]:
    return caminhos_do_lote(projeto_id, TipoDeArquivo.SPED_CONTRIBUICOES, sessao)


def agregados_do_projeto(projeto_id: int, sessao: Session) -> str | None:
    """A pasta da Gestão mais recente que deixou agregado em disco.

    A mais recente, e não a primeira que serve: se o trabalho rodou a Gestão de
    novo — porque chegou arquivo, porque a leitura foi corrigida —, é daquela
    que a exclusão tem de partir. Execução antiga tem agregado velho, e um
    número velho que bate com nada é pior que número nenhum.
    """
    execucoes = sessao.scalars(
        select(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == projeto_id,
               ExecucaoDB.etapa == apurar_contribuicoes.ETAPA,
               ExecucaoDB.situacao == "concluida")
        .order_by(ExecucaoDB.id.desc()))
    for execucao in execucoes:
        pasta = execucao.pasta_de_trabalho or ""
        if pasta and os.path.isfile(caminho_dos_agregados(pasta)):
            return pasta
    return None


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "apurar as exclusões")
    contribuicoes = fontes_do_projeto(projeto_id, sessao)
    agregados = agregados_do_projeto(projeto_id, sessao)
    if not contribuicoes and not agregados:
        raise NadaParaExcluir(
            "O lote não tem EFD-Contribuições. A exclusão sai da receita escriturada: "
            "importe a pasta com o que o cliente transmitiu à Receita.")

    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila", passo="Na fila",
                          arquivos_totais=len(contribuicoes), criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    de_onde = "do agregado da Gestão" if agregados else f"de {len(contribuicoes)} EFD-Contribuições"
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Exclusões da base · {de_onde}",
        dados={"execucao_id": execucao.id, "contribuicoes": len(contribuicoes),
               "agregados": bool(agregados)},
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
            except ExclusaoCancelada:
                log.warning("apuração das exclusões cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. O que ficou pela metade não vale.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Exclusões canceladas a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("apuração das exclusões falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Exclusões falharam · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Reunindo a receita"
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    contribuicoes = fontes_do_projeto(execucao.projeto_id, sessao)
    agregados = agregados_do_projeto(execucao.projeto_id, sessao)
    total = len(contribuicoes)
    execucao.arquivos_totais = total

    if agregados:
        diario.anotar("info", "Partindo do agregado que a Gestão deixou: sem reler os SPED.")
    else:
        diario.anotar("aviso", f"Nenhuma Gestão concluída neste trabalho — os "
                               f"{milhar(total)} SPED serão lidos agora, e o agregado fica "
                               "gravado para as próximas teses.")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(a: Andamento) -> None:
        execucao.arquivos_lidos = a.arquivos
        execucao.documentos = a.grupos
        execucao.fracao = min(0.99, a.arquivos / max(total, 1)) if total else 0.5
        execucao.passo = f"Lendo {a.arquivos} de {total}" if total else "Calculando"
        diario.base["andamento"] = {"arquivos": a.arquivos, "grupos": a.grupos}
        diario.salvar_de_vez_em_quando()

    resumo = apurar(contribuicoes, destino, agregados_de=agregados,
                    avisar=andou, deve_parar=parar)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.arquivos_lidos = resumo.arquivos
    execucao.documentos = resumo.grupos
    diario.base.update(serializar(resumo))
    diario.base["segundos"] = segundos

    for aviso in resumo.avisos[:20]:
        diario.anotar("aviso", aviso)
    if resumo.ilegiveis:
        diario.anotar("aviso", f"{milhar(resumo.ilegiveis)} arquivo(s) não deram para ler.")

    volta = resumo.diferenca / 100
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info",
                  f"Concluída em {duracao(segundos)}: {milhar(resumo.grupos)} grupos em "
                  f"{len(resumo.competencias)} competências. Excluindo as contribuições da "
                  f"própria base, voltam R$ {volta:,.2f}".replace(",", "X")
                  .replace(".", ",").replace("X", ".") + ".")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Exclusões apuradas · {milhar(resumo.grupos)} grupos em "
        f"{len(resumo.competencias)} competências",
        dados={"execucao_id": execucao.id, "grupos": resumo.grupos,
               "diferenca_centavos": resumo.diferenca, "fonte": resumo.fonte},
        autor_id=execucao.criada_por)
    diario.salvar()
    sessao.commit()

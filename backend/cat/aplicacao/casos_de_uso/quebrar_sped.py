"""Etapa: quebrar os SPED do trabalho.

Primeira etapa do módulo de PIS/COFINS depois da importação. Lê a
EFD-Contribuições e a ECD que o lote trouxe e deixa em disco o que se confronta:
a **Consulta de Entradas (037)**, do lado fiscal, e o **razão contábil**, do lado
da contabilidade.

Não depende de conferência nem de movimentos — aquelas são etapas do ICMS, do
rito da CAT 42. Aqui o caminho é outro: importar e quebrar.
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
from cat.infraestrutura.analitico.quebra_de_sped import (
    Andamento,
    QuebraCancelada,
    quebrar,
    serializar,
)
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ArquivoDoLoteDB, ExecucaoDB, LoteDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "quebra_de_sped"
VERSAO_DO_RESUMO = 1


class NadaParaQuebrar(ValueError):
    """O lote não tem EFD-Contribuições nem ECD."""


def fontes_do_projeto(projeto_id: int, sessao: Session) -> tuple[list[str], list[str]]:
    """As EFD-Contribuições e as ECD do lote, em duas listas.

    São tipos que o classificador já reconhece desde sempre — a importação nunca
    precisou de mudança para aceitá-los. O que faltava era etapa que os usasse.
    """
    def _do_tipo(tipo: TipoDeArquivo) -> list[str]:
        return list(sessao.scalars(
            select(ArquivoDoLoteDB.caminho)
            .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
            .where(LoteDB.projeto_id == projeto_id, ArquivoDoLoteDB.tipo == tipo.value)
            .order_by(ArquivoDoLoteDB.competencia, ArquivoDoLoteDB.caminho).distinct()))

    return _do_tipo(TipoDeArquivo.SPED_CONTRIBUICOES), _do_tipo(TipoDeArquivo.SPED_ECD)


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "quebrar os SPED")
    contribuicoes, ecds = fontes_do_projeto(projeto_id, sessao)
    if not contribuicoes and not ecds:
        raise NadaParaQuebrar(
            "O lote não tem EFD-Contribuições nem ECD. Importe a pasta com os arquivos "
            "que o cliente transmitiu à Receita.")
    total = len(contribuicoes) + len(ecds)
    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila", passo="Na fila",
                          arquivos_totais=total, criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Quebra de SPED · {len(contribuicoes)} EFD-Contribuições e {len(ecds)} ECD",
        dados={"execucao_id": execucao.id, "contribuicoes": len(contribuicoes), "ecd": len(ecds)},
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
            except QuebraCancelada:
                log.warning("quebra de sped cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. O que ficou pela metade não vale.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Quebra de SPED cancelada a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("quebra de sped falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Quebra de SPED falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Indexando os arquivos"
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    contribuicoes, ecds = fontes_do_projeto(execucao.projeto_id, sessao)
    total = len(contribuicoes) + len(ecds)
    execucao.arquivos_totais = total
    diario.anotar("info", f"{milhar(len(contribuicoes))} EFD-Contribuições e {milhar(len(ecds))} "
                          f"ECD para quebrar.")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(a: Andamento) -> None:
        execucao.arquivos_lidos = a.arquivos
        execucao.bytes_lidos = a.bytes
        execucao.documentos = a.entradas + a.razao
        execucao.fracao = a.arquivos / max(total, 1)
        execucao.passo = f"Quebrando {a.arquivos} de {total}"
        diario.base["andamento"] = {"arquivos": a.arquivos, "entradas": a.entradas,
                                    "razao": a.razao}
        diario.salvar_de_vez_em_quando()

    resumo = quebrar(contribuicoes, ecds, destino, avisar=andou, deve_parar=parar)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.arquivos_lidos = resumo.arquivos
    execucao.bytes_lidos = resumo.bytes
    execucao.documentos = resumo.entradas + resumo.linhas_do_razao
    diario.base.update(serializar(resumo))
    diario.base["segundos"] = segundos
    if resumo.ilegiveis:
        diario.anotar("aviso", f"{milhar(resumo.ilegiveis)} arquivos não deram para quebrar — "
                               "veja os avisos abaixo.")
    for aviso in resumo.avisos[:20]:
        diario.anotar("aviso", aviso)
    if resumo.contribuicoes and not resumo.entradas:
        diario.anotar("aviso", "Nenhuma entrada saiu das EFD-Contribuições. Confira se os "
                               "arquivos são do período certo e se têm bloco C.")
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info",
                  f"Concluída em {duracao(segundos)}: {milhar(resumo.linhas)} linhas lidas, "
                  f"{milhar(resumo.entradas)} entradas e {milhar(resumo.linhas_do_razao)} "
                  f"linhas de razão.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"SPED quebrados · {milhar(resumo.entradas)} entradas e "
        f"{milhar(resumo.linhas_do_razao)} linhas de razão",
        dados={"execucao_id": execucao.id, "arquivos": resumo.arquivos,
               "entradas": resumo.entradas, "razao": resumo.linhas_do_razao,
               "segundos": segundos}, autor_id=execucao.criada_por)

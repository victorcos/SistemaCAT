"""Etapa: apurar PIS/COFINS — o par que se confronta.

Lê a **EFD-Contribuições** e a **ECD** do lote e deixa em disco os dois lados:
a **Consulta de Entradas (037)**, do lado fiscal, e o **razão contábil**, do
lado da contabilidade. Onde os dois discordam é onde está o trabalho.

Até 23/09/2026 isto vinha dentro da quebra de SPED, porque portei as duas no
mesmo dia. Não são a mesma coisa: a quebra **abre** os arquivos — diz que
registros cada um tem e onde começam; esta **confronta**. Quem quer olhar um
C170 não quer esperar a 037 de um ano inteiro.

**Não depende da quebra**, nem de nenhuma outra etapa. As funcionalidades do
trabalho são independentes: a pessoa entra na de que precisa, e quando falta
base é esta etapa que diz o que falta — não uma aba apagada.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.conferir_documentos import pasta_da_execucao
from cat.aplicacao.casos_de_uso.historico_do_projeto import exigir_que_ande, registrar_de_etapa
from cat.aplicacao.casos_de_uso.quebrar_sped import fontes_do_projeto
from cat.aplicacao.casos_de_uso.rodada import Diario, Freio, duracao, milhar, nome_de
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.escrita import LeituraCancelada
from cat.infraestrutura.analitico.piscofins import Andamento, confrontar, serializar
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "apuracao_piscofins"
VERSAO_DO_RESUMO = 1


class NadaParaApurar(ValueError):
    """O lote não tem EFD-Contribuições nem ECD."""


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "apurar PIS/COFINS")
    contribuicoes, ecds = fontes_do_projeto(projeto_id, sessao)
    if not contribuicoes and not ecds:
        raise NadaParaApurar(
            "O lote não tem EFD-Contribuições nem ECD. Importe a pasta em Arquivos: da "
            "EFD-Contribuições sai a Consulta de Entradas, e da ECD sai o razão contábil.")
    total = len(contribuicoes) + len(ecds)
    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila", passo="Na fila",
                          arquivos_totais=total, criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Apuração de PIS/COFINS · {len(contribuicoes)} EFD-Contribuições e {len(ecds)} ECD",
        dados={"execucao_id": execucao.id, "contribuicoes": len(contribuicoes),
               "ecd": len(ecds)},
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
            except LeituraCancelada:
                log.warning("apuração de pis/cofins cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. O que ficou pela metade não vale.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Apuração de PIS/COFINS cancelada a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("apuração de pis/cofins falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Apuração de PIS/COFINS falhou · {type(erro).__name__}",
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

    contribuicoes, ecds = fontes_do_projeto(execucao.projeto_id, sessao)
    total = len(contribuicoes) + len(ecds)
    execucao.arquivos_totais = total
    diario.anotar("info", f"{milhar(len(contribuicoes))} EFD-Contribuições e "
                          f"{milhar(len(ecds))} ECD para confrontar.")
    if not contribuicoes:
        diario.anotar("aviso", "Nenhuma EFD-Contribuições no lote: não haverá Consulta de "
                               "Entradas, só o lado contábil.")
    if not ecds:
        diario.anotar("aviso", "Nenhuma ECD no lote: não haverá razão contábil, só o lado "
                               "fiscal. Sem os dois não há confronto.")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(a: Andamento) -> None:
        execucao.arquivos_lidos = a.arquivos
        execucao.documentos = a.entradas + a.razao
        execucao.fracao = min(0.99, a.arquivos / max(total, 1))
        execucao.passo = f"Apurando {a.arquivos} de {total}"
        diario.base["andamento"] = {"arquivos": a.arquivos, "entradas": a.entradas,
                                    "razao": a.razao}
        diario.salvar_de_vez_em_quando()

    resumo = confrontar(contribuicoes, ecds, destino, avisar=andou, deve_parar=parar)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.arquivos_lidos = resumo.arquivos
    execucao.documentos = resumo.entradas + resumo.linhas_do_razao
    diario.base.update(serializar(resumo))
    diario.base["segundos"] = segundos
    if resumo.ilegiveis:
        diario.anotar("aviso", f"{milhar(resumo.ilegiveis)} arquivos não deram para ler — "
                               "veja os avisos abaixo.")
    for aviso in resumo.avisos[:20]:
        diario.anotar("aviso", aviso)
    if resumo.contribuicoes and not resumo.entradas:
        diario.anotar("aviso", "Nenhuma entrada saiu das EFD-Contribuições. Confira se os "
                               "arquivos são do período certo e se têm bloco C.")
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info", f"Concluída em {duracao(segundos)}: {milhar(resumo.entradas)} entradas "
                          f"e {milhar(resumo.linhas_do_razao)} linhas de razão.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"PIS/COFINS apurado · {milhar(resumo.entradas)} entradas e "
        f"{milhar(resumo.linhas_do_razao)} linhas de razão",
        dados={"execucao_id": execucao.id, "arquivos": resumo.arquivos,
               "entradas": resumo.entradas, "razao": resumo.linhas_do_razao,
               "segundos": segundos}, autor_id=execucao.criada_por)

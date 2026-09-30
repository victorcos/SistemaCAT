"""Etapa: as exclusões da base do PIS/COFINS.

Calcula duas teses no mesmo parquet, separadas pela coluna `tese`: as próprias
contribuições fora da base, e o ICMS destacado fora da base — o Tema 69, que
sai também item a item, no formato do relatório 903.

**A primeira não depende de a Gestão ter rodado, mas agradece quando rodou.**
Se houver agregado de uma Gestão concluída, ela sai em segundos; se não houver,
lê os SPED ela mesma e deixa o agregado gravado, para que a próxima não pague
de novo.

**A segunda lê os SPED sempre**, porque se apura no item e agregado não tem
item. São duas leituras, e a tela diz qual está andando.

**O número do Tema 69 só existe com uma data ao lado.** A Selic acumulada
cresce a cada mês, então a etapa corrige até o mês em que se roda e grava qual
foi. Rodar de novo no mês que vem dá outro número — maior, e certo.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from decimal import Decimal

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
    FASE_DO_ICMS,
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


# quem deixa agregado em disco: a Gestão, ao montar os quadros, e a própria
# exclusão, quando precisou ler os SPED por não haver agregado nenhum
ETAPAS_QUE_AGREGAM = (apurar_contribuicoes.ETAPA, ETAPA)


def agregados_do_projeto(projeto_id: int, sessao: Session) -> str | None:
    """A pasta da rodada mais recente que deixou agregado em disco.

    A mais recente, e não a primeira que serve: se o trabalho rodou de novo —
    porque chegou arquivo, porque a leitura foi corrigida —, é daquela que a
    exclusão tem de partir. Agregado velho que bate com nada é pior que
    agregado nenhum.

    Vale o da Gestão e o de uma exclusão anterior: a primeira rodada que leu os
    SPED pagou a hora, e não há razão para a segunda pagar de novo.
    """
    execucoes = sessao.scalars(
        select(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == projeto_id,
               ExecucaoDB.etapa.in_(ETAPAS_QUE_AGREGAM),
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
    de_onde = ("de agregado já lido" if agregados
               else f"de {len(contribuicoes)} EFD-Contribuições")
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


def _anotar_o_icms(resumo, diario: Diario) -> None:
    """A linha do Tema 69 no diário — com a data da correção, sempre.

    Sem a data, o número não é conferível no mês seguinte: a Selic acumulada
    cresce, e quem reler a rodada antiga não vai saber por que o total mudou.
    """
    icms = resumo.icms
    if not icms:
        return
    ate = str(icms.get("ate", ""))
    mes = f"{ate[5:]}/{ate[:4]}" if len(ate) == 7 else ate
    volta = _reais(icms.get("total_atualizado", "0"))
    prescrito = _reais(icms.get("prescrito", "0"))
    diario.anotar("info",
                  f"ICMS fora da base (Tema 69): {milhar(int(icms.get('linhas', 0)))} "
                  f"itens de nota em {len(icms.get('competencias', []))} competências. "
                  f"Corrigido pela Selic até {mes}, há R$ {volta} a recuperar.")
    if icms.get("competencias_prescritas"):
        diario.anotar("aviso",
                      f"{icms['competencias_prescritas']} competência(s) do Tema 69 "
                      f"fora dos cinco anos, com R$ {prescrito} que o relatório mostra "
                      "e o total não soma.")


def _reais(valor: str) -> str:
    """"1234.5" -> "1.234,50". O motor entrega Decimal em texto."""
    try:
        return f"{Decimal(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ArithmeticError, ValueError):
        return str(valor)


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
        diario.anotar("info", "Partindo do agregado que uma rodada anterior deixou: sem reler os SPED.")
    else:
        diario.anotar("aviso", f"Nenhum agregado neste trabalho — os "
                               f"{milhar(total)} SPED serão lidos agora, e o agregado fica "
                               "gravado para as próximas teses.")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(a: Andamento) -> None:
        execucao.arquivos_lidos = a.arquivos
        execucao.documentos = a.grupos
        # a segunda tese é a segunda metade da barra: as duas leem tudo, e uma
        # barra que volta a zero no meio parece rodada travada
        andada = a.arquivos / max(total, 1) if total else 1.0
        cheia = (andada + 1) / 2 if a.fase == FASE_DO_ICMS else andada / 2
        execucao.fracao = min(0.99, cheia)
        do_icms = a.fase == FASE_DO_ICMS
        execucao.passo = (
            (f"Tema 69: {a.arquivos} de {total}" if do_icms
             else f"Lendo {a.arquivos} de {total}") if total else "Calculando")
        diario.base["andamento"] = {"arquivos": a.arquivos, "grupos": a.grupos,
                                    "fase": a.fase}
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
    _anotar_o_icms(resumo, diario)
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Exclusões apuradas · {milhar(resumo.grupos)} grupos em "
        f"{len(resumo.competencias)} competências",
        dados={"execucao_id": execucao.id, "grupos": resumo.grupos,
               "diferenca_centavos": resumo.diferenca, "fonte": resumo.fonte,
               "icms_total_atualizado": resumo.icms.get("total_atualizado", ""),
               "icms_ate": resumo.icms.get("ate", "")},
        autor_id=execucao.criada_por)
    diario.salvar()
    sessao.commit()

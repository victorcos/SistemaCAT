"""Etapa: o crédito de ICMS do combustível queimado como insumo.

Lê a EFD ICMS/IPI do lote, acha as compras, classifica cada item e apura quanto
vale. A regra está em três lugares, e nenhum deles é aqui:

* `sped/combustivel.py` lê o arquivo;
* `sped/classificador_de_combustivel.py` diz o que o item é;
* `sped/credito_de_combustivel.py` diz quanto ele vale, consultando as tabelas.

Esta etapa é a casca: prepara a execução, chama a rodada
(`analitico/combustivel.py`), escreve o diário que a tela lê e registra o que
aconteceu no histórico do trabalho.

**Não depende de etapa nenhuma.** Lê a EFD do lote direto, como a quebra de SPED
e o crédito outorgado. Quem importou a base já tem tudo o que ela precisa.

## O que a tela precisa saber, e por isso vai para o diário

**O crédito, e quanto dele é estimativa.** A era da substituição tributária sai
com a base no valor do item, porque o arquivo do destinatário não traz a base do
ST — medido: zero em 5.234 linhas de CST 60/61. Um total com estimativa dentro
não se apresenta sem dizer quanto.

**O que foi recusado, por motivo.** A competência sem ad rem conferida, o mês
partido, a compra que já veio com ICMS destacado. Nada disso vira zero: vira
linha no relatório com o porquê. O diário traz a contagem por motivo e **uma**
frase de exemplo de cada, porque a frase completa traz a competência dentro e
não serve de agrupamento.

**Quantas linhas pedem olho humano.** O classificador nunca recusa — ele emite
tudo com a confiança e o motivo, e marca o que precisa de revisão. Esse número
na tela é o tamanho do trabalho que sobra para o analista.

## O aviso que esta etapa dá e as outras não

Quando **nenhuma** linha de combustível aparece, o resumo não diz só "zero". Ele
distingue os dois casos que levam a zero, porque a providência é oposta:

* o lote tem EFD mas a empresa não comprou combustível no período — não há tese,
  e insistir é perder tempo;
* a empresa comprou, mas tudo veio com ICMS destacado — o crédito já foi tomado
  pelo caminho normal, e a tese aqui seria contar duas vezes.
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
from cat.aplicacao.casos_de_uso.historico_do_projeto import (
    exigir_que_ande,
    registrar_de_etapa,
)
from cat.aplicacao.casos_de_uso.rodada import (
    Diario,
    Freio,
    duracao,
    milhar,
    nome_de,
    reais,
)
from cat.dominio.lote import TipoDeArquivo
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.analitico.combustivel import Andamento, extrair, serializar
from cat.infraestrutura.analitico.escrita import LeituraCancelada
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB, ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "combustivel"
VERSAO_DO_RESUMO = 1

# Só a EFD ICMS/IPI. A de Contribuições não traz o CST de ICMS nem o CEST, e a
# ECD não traz item nenhum — ver `sped/registros_icms.py` sobre por que os dois
# leiautes não se misturam.
FONTES = (TipoDeArquivo.SPED_ICMS_IPI,)


class NadaParaApurar(ValueError):
    """Não há como rodar: falta a EFD ICMS/IPI no lote."""


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    """Põe a execução na fila, ou recusa dizendo o que falta."""
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "apurar o crédito de combustível")

    arquivos = caminhos_do_projeto(projeto_id, FONTES, sessao)
    if not arquivos:
        raise NadaParaApurar(
            "O lote não tem EFD ICMS/IPI. É dela que saem as compras de "
            "combustível — o CST, a quantidade e a unidade de cada item. A "
            "EFD-Contribuições não serve aqui: ela não traz o CST do ICMS.")

    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila",
                          passo="Na fila", arquivos_totais=len(arquivos),
                          criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Crédito de combustível · {milhar(len(arquivos))} EFD ICMS/IPI no lote",
        dados={"execucao_id": execucao.id, "arquivos": len(arquivos)},
        autor_id=usuario_id)
    return execucao


def executar(execucao_id: int) -> None:
    """O que a fila chama. Cancelamento e falha são estados, não exceções soltas."""
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
            except LeituraCancelada:
                log.warning("apuração de combustível cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. O que ficou "
                                       "pela metade não vale, e o parquet foi apagado.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Crédito de combustível cancelado a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("apuração de combustível falhou",
                              extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Crédito de combustível falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session,
           diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Abrindo a EFD ICMS/IPI"
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    arquivos = caminhos_do_projeto(execucao.projeto_id, FONTES, sessao)
    execucao.arquivos_totais = len(arquivos)
    diario.anotar("info", f"{milhar(len(arquivos))} EFD ICMS/IPI no lote. Uma por "
                          "estabelecimento e competência entra na conta; "
                          "retificadora vence a original.")

    inicio = time.time()
    parar = Freio(execucao.id)

    def andou(a: Andamento) -> None:
        execucao.arquivos_lidos = a.arquivos
        execucao.documentos = a.linhas
        execucao.fracao = (a.arquivos / len(arquivos)) if arquivos else 0.0
        execucao.passo = (f"Apurando {milhar(a.arquivos)} de "
                          f"{milhar(len(arquivos))}")
        diario.base["andamento"] = {"arquivos": a.arquivos, "linhas": a.linhas}
        diario.salvar_de_vez_em_quando()

    resumo = extrair(arquivos, destino, avisar=andou, deve_parar=parar)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.arquivos_lidos = resumo.arquivos_lidos
    execucao.documentos = resumo.linhas
    diario.base.update(serializar(resumo))
    diario.base["segundos"] = segundos
    diario.base["recusas_com_exemplo"] = {
        motivo: {"linhas": r.linhas, "exemplo": r.exemplo}
        for motivo, r in sorted(resumo.recusas.items())
    }
    _anotar(resumo, diario)
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar(
        "info",
        f"Concluída em {duracao(segundos)}: {milhar(resumo.linhas)} itens de "
        f"compra, {reais(resumo.credito)} de crédito apurado.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Crédito de combustível apurado · {reais(resumo.credito)} em "
        f"{len(resumo.competencias)} competência(s)",
        dados={"execucao_id": execucao.id, "linhas": resumo.linhas,
               "credito": str(resumo.credito),
               "credito_estimado": str(resumo.credito_estimado),
               "recusadas": resumo.linhas_recusadas,
               "a_revisar": resumo.a_revisar, "segundos": segundos},
        autor_id=execucao.criada_por)


def _anotar(resumo, diario: Diario) -> None:
    """Os avisos que mudam o que o analista faz a seguir.

    Cada um existe porque leva a uma providência diferente — e um "zero" sem
    explicação leva à providência errada.
    """
    if resumo.ignorados_por_duplicidade:
        diario.anotar("info", f"{milhar(resumo.ignorados_por_duplicidade)} "
                              "arquivo(s) ficaram de fora por repetirem "
                              "estabelecimento e competência. É o esperado "
                              "quando o lote aponta a pasta-mãe: o mesmo mês "
                              "costuma estar em mais de uma subpasta.")
    if resumo.ilegiveis:
        diario.anotar("aviso", f"{milhar(resumo.ilegiveis)} arquivo(s) não "
                               "deram para ler — veja os avisos abaixo.")
    for aviso in resumo.avisos[:20]:
        diario.anotar("aviso", aviso)

    if resumo.credito_estimado:
        diario.anotar(
            "aviso",
            f"{reais(resumo.credito_estimado)} do total são **estimativa**: "
            "na era da substituição tributária o arquivo do destinatário não "
            "traz a base do ST, e a base usada é o valor do item. A conferência "
            "é pelo XML (vICMSSTRet ÷ vBCSTRet).")

    if resumo.a_revisar:
        diario.anotar("info", f"{milhar(resumo.a_revisar)} linha(s) o "
                              "classificador marcou para revisão humana: NCM "
                              "ausente, ou descrição que discorda da NCM.")

    for motivo, recusa in sorted(resumo.recusas.items(),
                                 key=lambda kv: -kv[1].linhas):
        diario.anotar("aviso", f"{milhar(recusa.linhas)} linha(s) fora do total "
                               f"por \"{motivo}\": {recusa.exemplo[:220]}")

    if resumo.linhas and not resumo.creditos:
        # os dois caminhos para zero, e a providência é oposta em cada um
        if resumo.recusas:
            diario.anotar("aviso", "Nenhum crédito apurado, e **não** porque "
                                   "falte compra: tudo o que era da tese foi "
                                   "recusado. Veja os motivos acima — alguns se "
                                   "resolvem cadastrando tabela, outros são "
                                   "crédito que o documento já deu.")
        else:
            diario.anotar("info", "A empresa não comprou combustível no "
                                  "período, ou o comprou sem as marcas que esta "
                                  "tese reconhece. Não há o que pedir.")

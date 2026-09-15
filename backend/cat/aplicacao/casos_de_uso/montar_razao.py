"""Montar o razão dos itens — a Ficha 3 de cada mercadoria com ST.

Quinta etapa. Roda fora da requisição, como as anteriores:

    1. relatórios de saída do cliente → as saídas que a EFD não detalha
       (cupom e NFC-e vão à EFD só com o analítico);
    2. lançamentos de cada (estabelecimento, mercadoria): entradas da
       apuração do suportado, saídas da EFD e do relatório, abertura do
       bloco H;
    3. a ficha, pela regra do domínio, e o resumo no banco.

Depende das etapas 3 e 4 concluídas. Da 4, a apuração precisa ter gravado a
data e o CFOP de cada entrada — apuração de antes disso é recusada com o
pedido de rodar de novo, em vez de montar ficha sem data.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.apurar_suportado import ETAPA as ETAPA_SUPORTADO
from cat.aplicacao.casos_de_uso.apurar_suportado import movimentacao_concluida
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
from cat.infraestrutura.analitico.razao import (
    ARQUIVO_SAIDAS_DO_RELATORIO,
    Andamento,
    Fontes,
    SaidasExtraidas,
    extrair_saidas,
    montar,
    serializar,
)
from cat.infraestrutura.analitico.suportado import ARQUIVO_SUPORTADO, ApuracaoCancelada
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import (
    ArquivoDoLoteDB,
    ExecucaoDB,
    LoteDB,
    ProjetoDB,
)
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "razao"
VERSAO_DO_RESUMO = 1

FRACAO_DOS_RELATORIOS = 0.40
FRACAO_DA_MONTAGEM = 0.97


class NadaParaMontar(ValueError):
    """O trabalho não está pronto para esta etapa."""


def apuracao_concluida(projeto_id: int, sessao: Session) -> ExecucaoDB | None:
    return sessao.scalar(
        select(ExecucaoDB)
        .where(ExecucaoDB.projeto_id == projeto_id,
               ExecucaoDB.etapa == ETAPA_SUPORTADO,
               ExecucaoDB.situacao == "concluida")
        .order_by(ExecucaoDB.id.desc())
        .limit(1)
    )


def _exigir_fontes(projeto_id: int, sessao: Session) -> tuple[ExecucaoDB, ExecucaoDB]:
    movimentos = movimentacao_concluida(projeto_id, sessao)
    if movimentos is None or not movimentos.pasta_de_trabalho or not os.path.isdir(
            movimentos.pasta_de_trabalho):
        raise NadaParaMontar("Conclua a extração de movimentos antes: é dela a abertura e a "
                             "saída com item da EFD.")
    apuracao = apuracao_concluida(projeto_id, sessao)
    if apuracao is None or not apuracao.pasta_de_trabalho:
        raise NadaParaMontar("Conclua a apuração do ICMS suportado antes: é o suportado de cada "
                             "entrada que o razão carrega.")
    suportado = os.path.join(apuracao.pasta_de_trabalho, ARQUIVO_SUPORTADO)
    if not os.path.isfile(suportado):
        raise NadaParaMontar("Os arquivos da última apuração do suportado não estão mais em "
                             "disco. Rode a apuração de novo.")
    if "data" not in pq.read_schema(suportado).names:
        raise NadaParaMontar("A última apuração do suportado é de uma versão que não gravava a "
                             "data e o CFOP de cada entrada. Rode a apuração de novo.")
    return movimentos, apuracao


def preparar(projeto_id: int, usuario_id: int, sessao: Session) -> ExecucaoDB:
    projeto = sessao.get(ProjetoDB, projeto_id)
    if projeto is not None:
        exigir_que_ande(projeto, "montar o razão")
    movimentos, apuracao = _exigir_fontes(projeto_id, sessao)
    relatorios = caminhos_do_projeto(projeto_id, (TipoDeArquivo.GERENCIAL_MOVIMENTO,), sessao)

    execucao = ExecucaoDB(projeto_id=projeto_id, etapa=ETAPA, situacao="na_fila",
                          passo="Na fila", arquivos_totais=len(relatorios),
                          criada_por=usuario_id)
    sessao.add(execucao)
    sessao.commit()
    sessao.refresh(execucao)
    registrar_de_etapa(
        sessao, projeto_id, TipoDeEvento.ETAPA_INICIADA, ETAPA,
        f"Montagem do razão · {len(relatorios)} relatórios do cliente",
        dados={"execucao_id": execucao.id, "movimentos_execucao_id": movimentos.id,
               "apuracao_execucao_id": apuracao.id},
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
                log.warning("montagem do razão cancelada a pedido")
                sessao.refresh(execucao)
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("aviso", "Rodada cancelada a pedido. Nenhuma ficha ficou gravada.")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    "Montagem do razão cancelada a pedido",
                    dados={"execucao_id": execucao.id, "cancelada": True},
                    autor_id=execucao.criada_por)
            except Exception as erro:            # noqa: BLE001
                log.exception("montagem do razão falhou", extra={"erro": str(erro)})
                sessao.rollback()
                execucao.situacao = "falhou"
                execucao.erro = f"{type(erro).__name__}: {erro}"
                execucao.passo = "Falhou"
                execucao.terminada_em = datetime.now(timezone.utc)
                diario.anotar("erro", f"{type(erro).__name__}: {str(erro)[:300]}")
                registrar_de_etapa(
                    sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, ETAPA,
                    f"Montagem do razão falhou · {type(erro).__name__}",
                    dados={"execucao_id": execucao.id, "erro": str(erro)[:500]},
                    autor_id=execucao.criada_por)


def _rodar(execucao: ExecucaoDB, destino: str, sessao: Session, diario: Diario) -> None:
    os.makedirs(destino, exist_ok=True)
    if execucao.situacao != "cancelando":
        execucao.situacao = "rodando"
    execucao.pasta_de_trabalho = destino
    execucao.passo = "Lendo as saídas dos relatórios do cliente"
    diario.base["iniciada_por"] = nome_de(execucao.criada_por, sessao)
    sessao.commit()

    movimentos, apuracao = _exigir_fontes(execucao.projeto_id, sessao)
    diario.base["movimentos_execucao_id"] = movimentos.id
    diario.base["apuracao_execucao_id"] = apuracao.id
    relatorios = caminhos_do_projeto(execucao.projeto_id, (TipoDeArquivo.GERENCIAL_MOVIMENTO,), sessao)
    execucao.arquivos_totais = len(relatorios)
    diario.anotar("info", f"Rodada iniciada sobre a movimentação #{movimentos.id}, a apuração "
                          f"#{apuracao.id} e {len(relatorios)} relatórios do cliente.")

    inicio = time.time()
    parar = Freio(execucao.id)

    def relatorio_lido(n: int, total: int) -> None:
        execucao.arquivos_lidos = n
        execucao.fracao = FRACAO_DOS_RELATORIOS * n / max(total, 1)
        diario.salvar_de_vez_em_quando()

    caminho_saidas = os.path.join(destino, ARQUIVO_SAIDAS_DO_RELATORIO)
    saidas = extrair_saidas(relatorios, caminho_saidas, avisar=relatorio_lido, deve_parar=parar)
    _anotar_saidas(diario, saidas)

    execucao.passo = "Montando as fichas"
    execucao.fracao = FRACAO_DOS_RELATORIOS
    sessao.commit()

    def lancado(a: Andamento) -> None:
        execucao.documentos = a.linhas
        execucao.fracao = FRACAO_DOS_RELATORIOS + (
            (FRACAO_DA_MONTAGEM - FRACAO_DOS_RELATORIOS) * a.linhas / max(a.total, 1))
        diario.base["andamento"] = {"linhas": a.linhas, "total": a.total, "fichas": a.fichas}
        diario.salvar_de_vez_em_quando()

    fontes = Fontes(movimentacao=movimentos.pasta_de_trabalho,
                    apuracao=apuracao.pasta_de_trabalho,
                    saidas_do_relatorio=caminho_saidas)
    resumo = montar(fontes, destino, uf_por_cnpj=_ufs(execucao.projeto_id, sessao),
                    avisar=lancado, deve_parar=parar)

    segundos = round(time.time() - inicio, 1)
    execucao.situacao = "concluida"
    execucao.passo = "Concluída"
    execucao.fracao = 1.0
    execucao.documentos = resumo.linhas
    diario.base.update(serializar(resumo))
    diario.base["relatorios"] = vars(saidas)
    diario.base["segundos"] = segundos
    _anotar_pendencias(diario, resumo)
    execucao.terminada_em = datetime.now(timezone.utc)
    diario.anotar("info", f"Concluída em {duracao(segundos)}: {milhar(resumo.fichas)} fichas, "
                          f"{milhar(resumo.linhas)} linhas, {reais(resumo.ressarcimento)} de "
                          "ressarcimento.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Razão montado · {milhar(resumo.fichas)} fichas, {reais(resumo.ressarcimento)} de ressarcimento",
        dados={"execucao_id": execucao.id, "fichas": resumo.fichas, "linhas": resumo.linhas,
               "ressarcimento": str(resumo.ressarcimento), "segundos": segundos},
        autor_id=execucao.criada_por)


def _ufs(projeto_id: int, sessao: Session) -> dict[str, str]:
    """A UF de cada estabelecimento, pela EFD importada. A CAT 42 é paulista:
    a ficha de loja de outro estado é contada como fora de SP."""
    return {cnpj: uf for cnpj, uf in sessao.execute(
        select(ArquivoDoLoteDB.cnpj, ArquivoDoLoteDB.uf)
        .join(LoteDB, LoteDB.id == ArquivoDoLoteDB.lote_id)
        .where(LoteDB.projeto_id == projeto_id,
               ArquivoDoLoteDB.tipo == TipoDeArquivo.SPED_ICMS_IPI.value,
               ArquivoDoLoteDB.cnpj.is_not(None))
        .distinct()).all() if uf}


def _anotar_saidas(diario: Diario, s: SaidasExtraidas) -> None:
    if not s.arquivos:
        diario.anotar("aviso", "Nenhum relatório do cliente no trabalho: só entram as saídas com "
                               "item na EFD, que no varejo são quase nenhuma.")
        return
    diario.anotar("info", f"{s.arquivos} relatórios vistos · {milhar(s.linhas)} linhas de saída; "
                          f"{s.so_de_entradas} só de entradas, deixados de lado.")
    if s.linhas == 0:
        diario.anotar("aviso", "Nenhum relatório de saída no trabalho. Importe o relatório "
                               "gerencial de saídas: sem ele o cupom não entra na ficha.")
    if s.recusados:
        diario.anotar("aviso", f"{s.recusados} relatórios ilegíveis ou de outra espécie ficaram de fora.")


def _anotar_pendencias(diario: Diario, r) -> None:
    avisos = [
        (r.relatorio_sem_estabelecimento, "linhas do relatório sem loja identificável ficaram de fora"),
        (r.saidas_sem_aliquota, "saídas sem alíquota interna no cadastro: sem confronto, sem ressarcimento"),
        (r.saidas_indefinidas, "saídas com enquadramento indefinido"),
        (r.confronto_pendente, "saídas de enquadramento 2 ou 4: o confronto com o ICMS da entrada ainda não é apurado"),
        (r.fichas_negativas, "fichas que ficaram com estoque negativo — falta entrada ou abertura"),
        (r.fichas_abertura_sem_valor, "fichas abertas com quantidade e sem ICMS suportado: o inventário não traz o imposto"),
        (r.fichas_fora_de_sp, "fichas de estabelecimento fora de SP, que não entram na CAT 42"),
        (r.linhas_unidade_sem_fator, "linhas com unidade diferente da do inventário e sem fator "
                                     "de conversão (0220): quantidade mantida como veio"),
        (r.conferencia.get("suspeita_unidade", 0), "comparações com o inventário com diferença do "
                                                   "tamanho de um fator de embalagem — suspeita de unidade"),
    ]
    for n, texto in avisos:
        if n:
            diario.anotar("aviso", f"{milhar(n)} {texto}.")
    c = r.conferencia
    if c.get("com_estoque"):
        fecham = c["batem"] + c["proximas"]
        diario.anotar("info", f"Conferência com o inventário: {milhar(fecham)} de "
                              f"{milhar(c['com_estoque'])} comparações fecham (até 2%), em "
                              f"{c['datas']} datas de bloco H.")

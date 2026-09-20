"""Montar o razão dos itens — a Ficha 3 de cada mercadoria com ST.

Quinta etapa. Roda fora da requisição, como as anteriores:

    1. relatórios de saída do cliente → as saídas que a EFD não detalha
       (cupom e NFC-e vão à EFD só com o analítico);
    2. lançamentos de cada (estabelecimento, mercadoria): entradas da
       apuração do suportado, saídas da EFD e do relatório, abertura do
       bloco H;
    3. a ficha, pela regra do domínio, e o resumo no banco.

Os pares de de-para aprovados da empresa entram antes do passo 2: vão para
`depara.parquet` na pasta da rodada, que fica de rastro do que valeu.

Depende das etapas 3 e 4 concluídas. Da 4, a apuração precisa ter gravado a
data e o CFOP de cada entrada — apuração de antes disso é recusada com o
pedido de rodar de novo, em vez de montar ficha sem data.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pyarrow as pa
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
from cat.dominio.cat42.enquadramento import VendaAConsumidor
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
    CorrecaoDB,
    DeParaDB,
    ExecucaoDB,
    LoteDB,
    ProjetoDB,
)
from cat.log import contexto, obter_log

log = obter_log(__name__)

ETAPA = "razao"
ARQUIVO_DEPARA = "depara.parquet"
ARQUIVO_CORRECOES = "correcoes.parquet"
# 2: fichas com estoque negativo saem do total (15/09/2026)
VERSAO_DO_RESUMO = 2

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

    projeto = sessao.get(ProjetoDB, execucao.projeto_id)
    periodo = (projeto.competencia_ini, projeto.competencia_fim) if projeto is not None else None
    ufs = _ufs(execucao.projeto_id, sessao)
    depara = gravar_depara(projeto.empresa_id, list(ufs), os.path.join(destino, ARQUIVO_DEPARA), sessao)         if projeto is not None else 0
    if depara:
        diario.anotar("info", f"{milhar(depara)} pares de de-para aprovados entram na montagem.")
    correcoes = gravar_correcoes(execucao.projeto_id, os.path.join(destino, ARQUIVO_CORRECOES), sessao)
    if correcoes:
        diario.anotar("info", f"{milhar(correcoes)} correções à mão do trabalho entram na montagem.")
    fontes = Fontes(movimentacao=movimentos.pasta_de_trabalho,
                    apuracao=apuracao.pasta_de_trabalho,
                    saidas_do_relatorio=caminho_saidas,
                    periodo=periodo,
                    depara=os.path.join(destino, ARQUIVO_DEPARA) if depara else None,
                    correcoes=os.path.join(destino, ARQUIVO_CORRECOES) if correcoes else None)
    venda = venda_a_consumidor_do_projeto(execucao.projeto_id, sessao)
    diario.anotar("info", f"Venda a consumidor final: {venda.rotulo.lower()} (escolha do trabalho).")
    resumo = montar(fontes, destino, uf_por_cnpj=ufs,
                    avisar=lancado, deve_parar=parar, venda_a_consumidor=venda)

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
                          f"{milhar(resumo.fichas_retiradas)} retiradas do total; "
                          f"{reais(resumo.ressarcimento)} de ressarcimento nas válidas.")
    registrar_de_etapa(
        sessao, execucao.projeto_id, TipoDeEvento.ETAPA_CONCLUIDA, ETAPA,
        f"Razão montado · {milhar(resumo.fichas - resumo.fichas_retiradas)} fichas válidas, "
        f"{reais(resumo.ressarcimento)} de ressarcimento; {milhar(resumo.fichas_retiradas)} retiradas",
        dados={"execucao_id": execucao.id, "fichas": resumo.fichas, "linhas": resumo.linhas,
               "ressarcimento": str(resumo.ressarcimento), "segundos": segundos},
        autor_id=execucao.criada_por)


def gravar_depara(empresa_id: int, cnpjs: list[str], destino: str, sessao: Session) -> int:
    """Os pares aprovados da empresa, por estabelecimento, num parquet. Devolve quantos.

    O par sem CNPJ vale para todos; o do estabelecimento, quando há, vence.
    """
    aprovados = sessao.execute(
        select(DeParaDB.cnpj, DeParaDB.codigo_origem, DeParaDB.codigo_destino, DeParaDB.fator)
        .where(DeParaDB.empresa_id == empresa_id, DeParaDB.situacao == "aprovado")).all()
    pares: dict[tuple[str, str], tuple[str, object]] = {}
    for cnpj, origem, destino_, fator in sorted(aprovados, key=lambda p: p[0] != ""):
        for alvo in (cnpjs if cnpj == "" else [cnpj]):
            pares[(alvo, origem)] = (destino_, fator)
    if not pares:
        return 0
    pq.write_table(pa.Table.from_pylist(
        [{"cnpj": c, "codigo_origem": o, "codigo_destino": d, "fator": f} for (c, o), (d, f) in sorted(pares.items())],
        schema=pa.schema([("cnpj", pa.string()), ("codigo_origem", pa.string()),
                          ("codigo_destino", pa.string()), ("fator", pa.decimal128(24, 9))])), destino)
    log.info("de-para aplicado na montagem", extra={"empresa_id": empresa_id, "pares": len(pares)})
    return len(pares)


def gravar_correcoes(projeto_id: int, destino: str, sessao: Session) -> int:
    """As correções à mão ativas do trabalho, num parquet. Devolve quantas.

    São do trabalho, não da empresa: o de-para se herda, a correção não
    (decisão do Victor, 20/09/2026). Quem as aplica é o razão, em
    `_correcoes`; aqui só se traduz banco em arquivo, como no de-para.
    """
    ativas = sessao.execute(
        select(CorrecaoDB.campo, CorrecaoDB.cnpj, CorrecaoDB.codigo, CorrecaoDB.documento,
               CorrecaoDB.numero_item, CorrecaoDB.valor)
        .where(CorrecaoDB.projeto_id == projeto_id, CorrecaoDB.situacao == "ativa")
        .order_by(CorrecaoDB.campo, CorrecaoDB.codigo, CorrecaoDB.documento)).all()
    if not ativas:
        return 0
    pq.write_table(pa.Table.from_pylist(
        [{"campo": campo, "cnpj": cnpj or "", "codigo": codigo or "", "documento": documento or "",
          "numero_item": item, "valor": valor}
         for campo, cnpj, codigo, documento, item, valor in ativas],
        schema=pa.schema([("campo", pa.string()), ("cnpj", pa.string()), ("codigo", pa.string()),
                          ("documento", pa.string()), ("numero_item", pa.int32()),
                          ("valor", pa.string())])), destino)
    log.info("correções à mão na montagem", extra={"projeto_id": projeto_id, "correcoes": len(ativas)})
    return len(ativas)


def venda_a_consumidor_do_projeto(projeto_id: int, sessao: Session) -> VendaAConsumidor:
    """A escolha do trabalho. Valor que o domínio não conhece não vira padrão
    calado: falha, porque decide o enquadramento de quase todo o movimento."""
    valor = sessao.scalar(select(ProjetoDB.venda_a_consumidor).where(ProjetoDB.id == projeto_id))
    return VendaAConsumidor.de(valor)


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
        (r.fichas_retiradas, "fichas retiradas do total até os dados chegarem: o estoque ficou "
                             "negativo — falta entrada, abertura ou algum tipo de saída"),
        (r.fichas_abertura_sem_valor, "fichas abertas com quantidade e sem ICMS suportado: o inventário não traz o "
                                      "imposto e a base não tem entrada anterior ao inventário para valorar a abertura "
                                      "(item 3.3.8) — importe as EFD dos meses antes do período"),
        (r.fichas_abertura_parcial, "fichas com abertura valorada só em parte: as entradas anteriores ao inventário "
                                    "não cobriram a quantidade, e o resto foi pela média delas"),
        (r.fichas_fora_de_sp, "fichas de estabelecimento fora de SP, que não entram na CAT 42"),
        (r.linhas_unidade_sem_fator, "linhas com unidade diferente da do inventário e sem fator "
                                     "de conversão (0220): quantidade mantida como veio"),
        (r.conferencia.get("suspeita_unidade", 0), "comparações com o inventário com diferença do "
                                                   "tamanho de um fator de embalagem — suspeita de unidade"),
    ]
    for n, texto in avisos:
        if n:
            diario.anotar("aviso", f"{milhar(n)} {texto}.")
    if r.fichas_abertura_valorada:
        diario.anotar("info", f"{milhar(r.fichas_abertura_valorada)} fichas com a abertura valorada pelas entradas "
                              f"anteriores ao inventário: {reais(r.icms_da_abertura)} de ICMS suportado.")
    if r.linhas_com_depara:
        diario.anotar("info", f"{milhar(r.linhas_com_depara)} lançamentos de {milhar(r.codigos_trocados_pelo_depara)} "
                              "códigos passaram, pelo de-para, para o código da mercadoria.")
    if r.lancamentos_x949:
        diario.anotar("info", f"{milhar(r.lancamentos_x949)} lançamentos X.949 (outras entradas e saídas, como "
                              "remessa e retorno de armazém) ficaram fora da ficha.")
    if r.lancamentos_de_uso_e_consumo:
        diario.anotar("info", f"{milhar(r.lancamentos_de_uso_e_consumo)} lançamentos de uso e consumo ficaram fora da "
                              "ficha: não são estoque de comercialização.")
    if r.saidas_com_aliquota_do_mes:
        diario.anotar("info", f"{milhar(r.saidas_com_aliquota_do_mes)} saídas confrontadas com a alíquota do "
                              "cadastro do próprio mês, diferente da do fim do período.")
    c = r.conferencia
    if c.get("com_estoque"):
        fecham = c["batem"] + c["proximas"]
        diario.anotar("info", f"Conferência com o inventário: {milhar(fecham)} de "
                              f"{milhar(c['com_estoque'])} comparações fecham (até 2%), em "
                              f"{c['datas']} datas de bloco H.")

"""Fecha o período: ressarcimento, complemento e saldos, por loja e por mês.

A regra de quando uma competência está pronta é do domínio
(`cat.dominio.cat42.apuracao`). Aqui é a parte suja: agregar a Ficha 3 que a
etapa 5 gravou, casar com a conferência do inventário e deixar pronto o que a
etapa 7 vai escrever.

## Por que por estabelecimento e por mês

Porque é a unidade do arquivo digital: o registro 0000 leva CNPJ, IE e o
período `mmaaaa`. Apurar pela empresa inteira daria um número que não vira
arquivo nenhum.

## O que sai daqui

* `apuracao.parquet` — uma linha por (estabelecimento, competência), com o que
  se pede, o que se recolhe, o que trava e por quê;
* `saldos.parquet` — por (estabelecimento, competência, mercadoria): quantidade
  e ICMS suportado no início e no fim do mês. **É o registro 1050**, campo a
  campo, esperando a etapa 7.

O saldo inicial de um mês é o final do mês anterior da mesma ficha; no primeiro
mês em que a mercadoria se move, é a abertura do inventário. Não se recalcula
nada: os dois vêm da coluna de saldo da própria Ficha 3, que já é custo médio
ponderado móvel.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.cat42.apuracao import CompetenciaApurada, MotivoDeBloqueio
from cat.infraestrutura.analitico.confronto import _abrir, _escapar, _limpar
from cat.infraestrutura.analitico.razao import (
    ARQUIVO_CONFERENCIA_INVENTARIO,
    ARQUIVO_FICHA3,
    ARQUIVO_FICHAS,
)
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada, _leitura
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_APURACAO = "apuracao.parquet"
ARQUIVO_SALDOS = "saldos.parquet"

POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 200

_Q2 = Decimal("0.01")
_Q3 = Decimal("0.001")

ESQUEMA_APURACAO = pa.schema([
    ("cnpj", pa.string()),
    ("uf", pa.string()),
    ("competencia", pa.string()),          # "2021-05"
    ("ressarcimento", pa.decimal128(24, 2)),
    ("complemento", pa.decimal128(24, 2)),
    # coluna 27 da Ficha 3 (art. 271): a soma do crédito da operação própria nas saídas de
    # enquadramento 4 (v0.53); antes era preparada e zerada até o confronto dos
    # enquadramentos 2 e 4 existir
    ("credito_operacao_propria", pa.decimal128(24, 2)),
    ("itens", pa.int32()),
    ("linhas", pa.int32()),
    ("saldo_inicial_quantidade", pa.decimal128(24, 3)),
    ("saldo_inicial_icms", pa.decimal128(24, 2)),
    ("saldo_final_quantidade", pa.decimal128(24, 3)),
    ("saldo_final_icms", pa.decimal128(24, 2)),
    ("fichas_retiradas", pa.int32()),
    ("confronto_pendente", pa.int32()),
    ("sem_aliquota", pa.int32()),
    ("indefinidas", pa.int32()),
    ("inventarios_conferidos", pa.int32()),
    ("inventarios_divergentes", pa.int32()),
    ("apta", pa.bool_()),
    ("motivos", pa.string()),              # códigos separados por vírgula
])

# o registro 1050 da etapa 7, campo a campo
ESQUEMA_SALDOS = pa.schema([
    ("cnpj", pa.string()),
    ("competencia", pa.string()),
    ("codigo", pa.string()),
    ("qtd_ini", pa.decimal128(24, 3)),
    ("icms_tot_ini", pa.decimal128(24, 2)),
    ("qtd_fim", pa.decimal128(24, 3)),
    ("icms_tot_fim", pa.decimal128(24, 2)),
    ("retirada", pa.bool_()),
])

DeveParar = Callable[[], bool]


@dataclass
class Andamento:
    competencias: int = 0
    total: int = 0


@dataclass
class ResumoDoPeriodo:
    competencias: int = 0
    aptas: int = 0
    estabelecimentos: int = 0
    estabelecimentos_aptos: int = 0
    itens: int = 0
    linhas: int = 0
    ressarcimento: Decimal = Decimal(0)
    complemento: Decimal = Decimal(0)
    credito_operacao_propria: Decimal = Decimal(0)
    # o que dá para pedir hoje: só das competências sem pendência
    ressarcimento_apto: Decimal = Decimal(0)
    complemento_apto: Decimal = Decimal(0)
    por_competencia: dict = field(default_factory=dict)
    por_motivo: dict = field(default_factory=dict)
    saldos: int = 0


def _conferir(deve_parar: DeveParar | None) -> None:
    if deve_parar is not None and deve_parar():
        raise ApuracaoCancelada("A apuração do período foi cancelada por quem a pediu.")


def apurar(
    pasta_razao: str,
    destino: str,
    uf_por_cnpj: dict[str, str] | None = None,
    avisar: Callable[[Andamento], None] | None = None,
    deve_parar: DeveParar | None = None,
) -> ResumoDoPeriodo:
    """Fecha cada (estabelecimento, competência) a partir da Ficha 3."""
    uf_por_cnpj = uf_por_cnpj or {}
    ficha3 = os.path.join(pasta_razao, ARQUIVO_FICHA3)
    fichas = os.path.join(pasta_razao, ARQUIVO_FICHAS)
    if not os.path.isfile(ficha3) or not os.path.isfile(fichas):
        raise FileNotFoundError(
            f"{ARQUIVO_FICHA3} não está em {pasta_razao}: o razão precisa ter rodado antes."
        )
    conferencia = os.path.join(pasta_razao, ARQUIVO_CONFERENCIA_INVENTARIO)
    apuracao = os.path.join(destino, ARQUIVO_APURACAO)
    saldos = os.path.join(destino, ARQUIVO_SALDOS)

    resumo = ResumoDoPeriodo()
    con = _abrir(destino)
    try:
        _conferir(deve_parar)
        _preparar(con, ficha3, fichas, conferencia)
        _conferir(deve_parar)
        resumo.saldos = _gravar_saldos(con, saldos)
        _conferir(deve_parar)
        _gravar_apuracao(con, apuracao, uf_por_cnpj, resumo, avisar, deve_parar)
    except ApuracaoCancelada:
        con.close()
        for arquivo in (apuracao, saldos):
            if os.path.isfile(arquivo):
                os.remove(arquivo)
        raise
    finally:
        con.close()
        _limpar(destino)

    log.info("período apurado", extra={
        "competencias": resumo.competencias, "aptas": resumo.aptas,
        "ressarcimento": str(resumo.ressarcimento),
        "ressarcimento_apto": str(resumo.ressarcimento_apto),
        "complemento": str(resumo.complemento)})
    return resumo


def _preparar(con, ficha3: str, fichas: str, conferencia: str) -> None:
    """Tabelas de trabalho: linhas com competência, saldo por mês e conferência."""
    con.execute(f"""
        CREATE OR REPLACE TABLE linhas AS
        SELECT l.*, strftime(l.data, '%Y-%m') AS competencia, f.uf, f.retirada
        FROM read_parquet('{_escapar(ficha3)}') l
        JOIN read_parquet('{_escapar(fichas)}') f ON f.cnpj = l.cnpj AND f.codigo = l.codigo
    """)
    # razão de antes de a abertura ter valor (v0.52) não tem a coluna: vale zero, como era
    tem_valor = "abertura_valor" in pq.read_schema(fichas).names
    # nem, antes da v0.53, o crédito do art. 271: a coluna entra zerada
    if "credito_operacao_propria" not in pq.read_schema(ficha3).names:
        con.execute("ALTER TABLE linhas ADD COLUMN credito_operacao_propria DECIMAL(30, 15) DEFAULT 0")
    con.execute(f"""
        CREATE OR REPLACE TABLE aberturas AS
        SELECT cnpj, codigo, abertura_quantidade,
               {"abertura_valor" if tem_valor else "0::DECIMAL(30, 15)"} AS abertura_valor, retirada
        FROM read_parquet('{_escapar(fichas)}')
    """)
    # o saldo do mês é o da última linha do mês; o inicial é o final do mês
    # anterior, e no primeiro mês da mercadoria é a abertura do inventário
    con.execute("""
        CREATE OR REPLACE TABLE saldo_mes AS
        SELECT cnpj, codigo, competencia,
               arg_max(saldo_quantidade, numero) AS qtd_fim,
               arg_max(saldo_valor, numero) AS icms_fim
        FROM linhas GROUP BY 1, 2, 3
    """)
    con.execute("""
        CREATE OR REPLACE TABLE saldos_do_periodo AS
        SELECT s.cnpj, s.competencia, s.codigo,
               coalesce(lag(s.qtd_fim) OVER janela, a.abertura_quantidade, 0) AS qtd_ini,
               coalesce(lag(s.icms_fim) OVER janela, a.abertura_valor, 0) AS icms_tot_ini,
               s.qtd_fim, s.icms_fim AS icms_tot_fim, a.retirada
        FROM saldo_mes s
        LEFT JOIN aberturas a ON a.cnpj = s.cnpj AND a.codigo = s.codigo
        WINDOW janela AS (PARTITION BY s.cnpj, s.codigo ORDER BY s.competencia)
    """)
    if os.path.isfile(conferencia):
        con.execute(f"""
            CREATE OR REPLACE TABLE conferencia AS
            SELECT cnpj, strftime(data_inventario, '%Y-%m') AS competencia,
                   count(*) FILTER (saldo_ficha <> 0 OR inventario <> 0) AS conferidos,
                   count(*) FILTER (situacao IN ('divergente', 'suspeita_unidade')) AS divergentes
            FROM read_parquet('{_escapar(conferencia)}') GROUP BY 1, 2
        """)
    else:
        con.execute("CREATE OR REPLACE TABLE conferencia (cnpj VARCHAR, competencia VARCHAR, "
                    "conferidos BIGINT, divergentes BIGINT)")


def _gravar_saldos(con, destino: str) -> int:
    con.execute(f"""
        COPY (
            SELECT cnpj, competencia, codigo,
                   qtd_ini::DECIMAL(24, 3) AS qtd_ini,
                   icms_tot_ini::DECIMAL(24, 2) AS icms_tot_ini,
                   qtd_fim::DECIMAL(24, 3) AS qtd_fim,
                   icms_tot_fim::DECIMAL(24, 2) AS icms_tot_fim,
                   coalesce(retirada, false) AS retirada
            FROM saldos_do_periodo ORDER BY cnpj, competencia, codigo
        ) TO '{_escapar(destino)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    return con.execute(f"SELECT count(*) FROM read_parquet('{_escapar(destino)}')").fetchone()[0]


def _gravar_apuracao(con, destino: str, uf_por_cnpj: dict, resumo: ResumoDoPeriodo,
                     avisar, deve_parar) -> None:
    """Uma linha por (estabelecimento, competência), com a regra do domínio."""
    cursor = con.execute("""
        WITH movimento AS (
            SELECT cnpj, competencia,
                   count(DISTINCT codigo) AS itens,
                   count(*) AS linhas,
                   sum(CASE WHEN retirada THEN 0 ELSE ressarcimento END) AS ressarcimento,
                   sum(CASE WHEN retirada THEN 0 ELSE complemento END) AS complemento,
                   sum(CASE WHEN retirada THEN 0 ELSE coalesce(credito_operacao_propria, 0) END) AS credito,
                   count(DISTINCT codigo) FILTER (retirada) AS fichas_retiradas,
                   count(*) FILTER (especie = 'saida' AND NOT devolucao
                                    AND enquadramento IN (2, 4) AND icms_efetivo IS NULL) AS confronto_pendente,
                   count(*) FILTER (especie = 'saida' AND NOT devolucao
                                    AND enquadramento IN (1, 3)
                                    AND icms_efetivo IS NULL) AS sem_aliquota,
                   count(*) FILTER (enquadramento_indefinido) AS indefinidas
            FROM linhas GROUP BY 1, 2
        ),
        saldo AS (
            SELECT cnpj, competencia,
                   sum(qtd_ini) AS qtd_ini, sum(icms_tot_ini) AS icms_ini,
                   sum(qtd_fim) AS qtd_fim, sum(icms_tot_fim) AS icms_fim
            FROM saldos_do_periodo GROUP BY 1, 2
        )
        SELECT m.*, s.qtd_ini, s.icms_ini, s.qtd_fim, s.icms_fim,
               coalesce(c.conferidos, 0) AS conferidos, coalesce(c.divergentes, 0) AS divergentes
        FROM movimento m
        LEFT JOIN saldo s ON s.cnpj = m.cnpj AND s.competencia = m.competencia
        LEFT JOIN conferencia c ON c.cnpj = m.cnpj AND c.competencia = m.competencia
        ORDER BY m.cnpj, m.competencia
    """)
    nomes = [d[0] for d in cursor.description]
    escritor = pq.ParquetWriter(destino, ESQUEMA_APURACAO)
    lote: dict[str, list] = {c: [] for c in ESQUEMA_APURACAO.names}
    estabelecimentos: set[str] = set()
    aptos: dict[str, bool] = {}
    andamento = Andamento()
    try:
        for linha in cursor.fetchall():
            _conferir(deve_parar)
            d = dict(zip(nomes, linha))
            c = CompetenciaApurada(
                cnpj=d["cnpj"], uf=uf_por_cnpj.get(d["cnpj"], ""), competencia=d["competencia"],
                ressarcimento=Decimal(d["ressarcimento"] or 0),
                complemento=Decimal(d["complemento"] or 0),
                credito_operacao_propria=Decimal(d["credito"] or 0),
                itens=d["itens"], linhas=d["linhas"],
                fichas_retiradas=d["fichas_retiradas"], confronto_pendente=d["confronto_pendente"],
                sem_aliquota=d["sem_aliquota"], indefinidas=d["indefinidas"],
                inventarios_conferidos=d["conferidos"], inventarios_divergentes=d["divergentes"],
            )
            _acrescentar(lote, c, d)
            _somar(resumo, c)
            estabelecimentos.add(c.cnpj)
            aptos[c.cnpj] = aptos.get(c.cnpj, True) and c.apta
            andamento.competencias += 1
            if avisar is not None and andamento.competencias % 200 == 0:
                avisar(andamento)
            if len(lote["cnpj"]) >= 50_000:
                escritor.write_table(pa.Table.from_pydict(lote, schema=ESQUEMA_APURACAO))
                for k in lote:
                    lote[k].clear()
        if lote["cnpj"]:
            escritor.write_table(pa.Table.from_pydict(lote, schema=ESQUEMA_APURACAO))
    finally:
        escritor.close()
    resumo.estabelecimentos = len(estabelecimentos)
    resumo.estabelecimentos_aptos = sum(1 for apto in aptos.values() if apto)
    if avisar is not None:
        avisar(andamento)


def _acrescentar(lote: dict, c: CompetenciaApurada, d: dict) -> None:
    lote["cnpj"].append(c.cnpj)
    lote["uf"].append(c.uf)
    lote["competencia"].append(c.competencia)
    lote["ressarcimento"].append(c.ressarcimento.quantize(_Q2))
    lote["complemento"].append(c.complemento.quantize(_Q2))
    lote["credito_operacao_propria"].append(c.credito_operacao_propria.quantize(_Q2))
    lote["itens"].append(c.itens)
    lote["linhas"].append(c.linhas)
    lote["saldo_inicial_quantidade"].append(Decimal(d["qtd_ini"] or 0).quantize(_Q3))
    lote["saldo_inicial_icms"].append(Decimal(d["icms_ini"] or 0).quantize(_Q2))
    lote["saldo_final_quantidade"].append(Decimal(d["qtd_fim"] or 0).quantize(_Q3))
    lote["saldo_final_icms"].append(Decimal(d["icms_fim"] or 0).quantize(_Q2))
    lote["fichas_retiradas"].append(c.fichas_retiradas)
    lote["confronto_pendente"].append(c.confronto_pendente)
    lote["sem_aliquota"].append(c.sem_aliquota)
    lote["indefinidas"].append(c.indefinidas)
    lote["inventarios_conferidos"].append(c.inventarios_conferidos)
    lote["inventarios_divergentes"].append(c.inventarios_divergentes)
    lote["apta"].append(c.apta)
    lote["motivos"].append(",".join(m.value for m in c.motivos))


def _somar(resumo: ResumoDoPeriodo, c: CompetenciaApurada) -> None:
    # soma o que a competência grava, já com 2 casas: o pedido é por competência,
    # e o total tem de ser a soma das linhas da planilha e do arquivo — somar
    # sem arredondar dava um centavo de diferença no piloto (66.681,16 x ,15)
    ressarcimento = c.ressarcimento.quantize(_Q2)
    complemento = c.complemento.quantize(_Q2)
    resumo.competencias += 1
    resumo.itens += c.itens
    resumo.linhas += c.linhas
    resumo.ressarcimento += ressarcimento
    resumo.complemento += complemento
    resumo.credito_operacao_propria += c.credito_operacao_propria.quantize(_Q2)
    if c.apta:
        resumo.aptas += 1
        resumo.ressarcimento_apto += ressarcimento
        resumo.complemento_apto += complemento
    mes = resumo.por_competencia.setdefault(c.competencia, {
        "competencias": 0, "aptas": 0, "ressarcimento": Decimal(0), "complemento": Decimal(0)})
    mes["competencias"] += 1
    mes["aptas"] += c.apta
    mes["ressarcimento"] += ressarcimento
    mes["complemento"] += complemento
    for motivo in c.motivos:
        resumo.por_motivo[motivo.value] = resumo.por_motivo.get(motivo.value, 0) + 1


# ---------------------------------------------------------------------------
# o que a tela lê depois de pronto
# ---------------------------------------------------------------------------
def competencias(destino: str, so: str | None = None, busca: str | None = None,
                 pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """As competências apuradas, maior ressarcimento primeiro.

    `so` recorta: `aptas`, `bloqueadas` ou o código de um motivo de bloqueio.
    """
    recortes = {"aptas": "apta", "bloqueadas": "NOT apta"}
    recortes.update({m.value: f"motivos LIKE '%{m.value}%'" for m in MotivoDeBloqueio})
    if so and so not in recortes:
        raise ValueError(f"Recorte desconhecido: {so}.")
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))
    caminho = os.path.join(destino, ARQUIVO_APURACAO)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"{ARQUIVO_APURACAO} não está em {destino}.")

    filtros, parametros = [], []
    if so:
        filtros.append(recortes[so])
    if busca and busca.strip():
        filtros.append("(cnpj ILIKE ? OR competencia ILIKE ?)")
        parametros += [f"%{busca.strip()}%"] * 2
    onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    base = f"(SELECT * FROM read_parquet('{_escapar(caminho)}') {onde})"
    con = _leitura(destino)
    try:
        total = con.execute(f"SELECT count(*) FROM {base}", parametros).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY ressarcimento DESC, cnpj, competencia
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, parametros)
        nomes = [c[0] for c in cursor.description]
        linhas = [_legivel(dict(zip(nomes, r))) for r in cursor.fetchall()]
    finally:
        con.close()
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas}


def _legivel(linha: dict) -> dict:
    saida = {}
    for k, v in linha.items():
        saida[k] = format(v, "f") if isinstance(v, Decimal) else v
    codigos = [c for c in (linha.get("motivos") or "").split(",") if c]
    saida["motivos"] = [
        {"codigo": c, "rotulo": MotivoDeBloqueio(c).rotulo,
         "o_que_fazer": MotivoDeBloqueio(c).o_que_fazer}
        for c in codigos
    ]
    return saida


def serializar(resumo: ResumoDoPeriodo) -> dict:
    """O resumo vira JSON no banco. Decimal não é JSON: vai como texto."""
    def texto(v):
        return format(Decimal(v).quantize(_Q2), "f")

    return {
        "competencias": resumo.competencias,
        "aptas": resumo.aptas,
        "estabelecimentos": resumo.estabelecimentos,
        "estabelecimentos_aptos": resumo.estabelecimentos_aptos,
        "itens": resumo.itens,
        "linhas": resumo.linhas,
        "saldos": resumo.saldos,
        # ressarcimento se pede, complemento se recolhe: nunca somados
        "ressarcimento": texto(resumo.ressarcimento),
        "complemento": texto(resumo.complemento),
        "credito_operacao_propria": texto(resumo.credito_operacao_propria),
        "ressarcimento_apto": texto(resumo.ressarcimento_apto),
        "complemento_apto": texto(resumo.complemento_apto),
        "por_competencia": [
            {"competencia": k, "competencias": v["competencias"], "aptas": v["aptas"],
             "ressarcimento": texto(v["ressarcimento"]), "complemento": texto(v["complemento"])}
            for k, v in sorted(resumo.por_competencia.items())
        ],
        "por_motivo": [
            {"codigo": m.value, "rotulo": m.rotulo, "o_que_fazer": m.o_que_fazer,
             "competencias": resumo.por_motivo.get(m.value, 0)}
            for m in MotivoDeBloqueio if resumo.por_motivo.get(m.value)
        ],
    }

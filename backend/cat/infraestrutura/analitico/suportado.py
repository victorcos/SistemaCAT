"""Apura o ICMS suportado de cada item de entrada, juntando as fontes.

A regra de qual fonte vale está em `cat.dominio.cat42.suportado`. Aqui é a
parte suja: ler o relatório do cliente, casar com a EFD, gravar o resultado e
responder à tela — as quebras e o analítico paginado.

## Por que o relatório do cliente é indispensável

A EFD não tem o número em 99% dos itens. Medido na base real de 2021, com
8.761.002 itens de entrada, só 0,92% têm ICMS-ST destacado — e não é defeito do
arquivo: 42% das entradas são CST 60, mercadoria cujo imposto foi retido antes,
em que o remetente não destaca nada.

O relatório gerencial de entradas fecha esse buraco. Medido em 2021-05, um mês
inteiro com as três praças:

| | |
|---|---|
| Itens da EFD que casam por (chave, código) | 93,57% |
| Com imposto informado | 42,53% |
| CST 60 que casa | 94,2% |
| CST 60 com imposto informado | 92,7% |

Ou seja: o caso que a EFD zera é justamente o que o relatório preenche.

## A chave da junção

`(chave de acesso, código do item)`. A chave sozinha não serve — uma nota tem
muitos itens — e o código sozinho muito menos. Na base medida, 99,99% dos itens
de entrada da EFD têm chave de 44 dígitos e 99,83% das linhas do relatório
também, então a junção não perde quase nada por falta de chave.

## Quem soma o quê

O valor que o relatório informa **já vem somado pelo domínio do gerencial**:
`MovimentoGerencial.imposto_suportado` escolhe entre XML, ERP e retido
anteriormente, e sabe que no retido anterior não se soma o ICMS da operação —
a mercadoria já veio tributada, e somar contaria imposto que não é dela.
Refazer essa conta aqui seria ter duas verdades.

## Leitura numa pasta, gravação em outra

Os movimentos e o cadastro são da execução da etapa 3; o imposto informado e o
resultado são da execução desta etapa. Misturar os dois na mesma pasta faria a
apuração sobrescrever material de outra etapa, e rodar a apuração de novo
apagaria o que a movimentação produziu.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.cat42.suportado import (
    EntradaParaApurar,
    Fonte,
    Pendencia,
    ResumoDaApuracao,
    apurar as apurar_item,
)
import duckdb

from cat.config import obter_config
from cat.infraestrutura.analitico.confronto import _abrir, _escapar, _limpar
from cat.infraestrutura.analitico.movimentacao import ARQUIVO_ITENS, ARQUIVO_MOVIMENTOS
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_RETIDO = "retido_informado.parquet"
ARQUIVO_SUPORTADO = "suportado.parquet"
# o analítico por documento, já agrupado e numerado — geral e por fonte. Sem
# ele, cada página agrupava 8,7 milhões de itens: 17,7 s a primeira página e
# 26,2 s a de número 5.000, medido na base real de 2021
ARQUIVO_DOCUMENTOS = "suportado_documentos.parquet"

LINHAS_POR_LOTE = 200_000

# o analítico pagina no servidor: numa base real são 8,7 milhões de itens, e
# nenhuma tela aguenta receber isso
POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 200

# seis casas, não duas. O relatório do cliente traz ICMS com quatro casas
# ("2,3341" numa linha real), e um esquema de duas casas não grava esse valor:
# o pyarrow recusa com "Rescaling Decimal value would cause data loss". Truncar
# em silêncio seria pior — são centavos somados em milhões de itens.
ESQUEMA_RETIDO = pa.schema([
    ("chave", pa.string()),
    ("codigo", pa.string()),
    ("informado", pa.decimal128(18, 6)),
])

ESQUEMA_SUPORTADO = pa.schema([
    ("cnpj", pa.string()),
    ("competencia", pa.date32()),
    ("chave", pa.string()),
    ("numero_documento", pa.string()),
    ("modelo", pa.string()),
    ("participante", pa.string()),
    ("codigo", pa.string()),
    ("descricao", pa.string()),
    ("cst_icms", pa.string()),
    ("quantidade", pa.decimal128(18, 5)),
    ("bc_st", pa.decimal128(18, 6)),
    ("suportado", pa.decimal128(18, 6)),   # ver a nota do ESQUEMA_RETIDO
    ("fonte", pa.string()),
    ("pendencia", pa.string()),
    ("motivo", pa.string()),
])

# os nomes que a tela e o parquet usam para cada fonte
CODIGO_DA_FONTE = {f: f.name.lower() for f in Fonte}
FONTE_DO_CODIGO = {v: k for k, v in CODIGO_DA_FONTE.items()}


class ApuracaoCancelada(Exception):
    """Quem pediu mandou parar. Não é falha: é decisão de quem pediu."""


@dataclass
class Andamento:
    """O que a tela mostra enquanto a apuração roda."""

    itens: int = 0
    apurados: int = 0
    estabelecimentos: int = 0


@dataclass
class RetidoExtraido:
    """O que a leitura dos relatórios achou, para o log da tela."""

    arquivos: int = 0
    recusados: int = 0
    linhas_de_entrada: int = 0
    sem_chave: int = 0
    itens: int = 0


Aviso = Callable[[Andamento], None]
DeveParar = Callable[[], bool]


def _leitura(pasta: str):
    """Conexão só de leitura, em memória, para contar e para a tela.

    Não é o `_abrir` do confronto porque aquele grava um banco em arquivo na
    pasta — e aqui a pasta pode ser a da movimentação, que é de outra etapa, ou
    a de uma apuração que duas abas da tela consultam ao mesmo tempo. Continua
    com teto de memória e com onde derramar: agrupar 8,7 milhões de itens por
    documento não cabe em qualquer RAM.
    """
    cfg = obter_config()
    con = duckdb.connect()
    con.execute(f"SET temp_directory = '{_escapar(pasta)}'")
    con.execute(f"SET memory_limit = '{cfg.memoria_analitica}'")
    con.execute("SET preserve_insertion_order = false")
    if cfg.threads_analiticas:
        con.execute(f"SET threads = {cfg.threads_analiticas}")
    return con


def _conferir(deve_parar: DeveParar | None) -> None:
    if deve_parar is not None and deve_parar():
        raise ApuracaoCancelada("A apuração foi cancelada por quem a pediu.")


# ---------------------------------------------------------------------------
# fonte 2: o imposto que o cliente informou
# ---------------------------------------------------------------------------
def extrair_retido(
    relatorios: list[str],
    destino: str,
    avisar: Callable[[int, int], None] | None = None,
    deve_parar: DeveParar | None = None,
) -> RetidoExtraido:
    """Lê os relatórios do cliente e grava o imposto informado por item.

    Só entradas: a saída não carrega imposto suportado, ela o consome. E só
    linha com chave de 44 dígitos, porque sem chave não há como casar com a
    EFD — a linha existe, mas não serve a esta junção.

    Agrega por (chave, código) porque o mesmo item pode aparecer em mais de
    uma linha do relatório, e o que vale para a ficha é o total do item
    naquele documento.

    `avisar` recebe (arquivos lidos, total). `deve_parar` é consultado entre um
    arquivo e outro: cada relatório é lido inteiro, então é ali o ponto seguro
    de parar sem deixar meio parquet no disco.
    """
    from cat.dominio.gerencial.campos import Especie
    from cat.infraestrutura.arquivos.gerencial import Leitura

    acumulado: dict[tuple[str, str], Decimal] = {}
    lidos = recusados = sem_chave = 0

    for n, caminho in enumerate(relatorios, 1):
        _conferir(deve_parar)
        nome = os.path.basename(caminho)
        try:
            leitura = Leitura(caminho)
            if leitura.especie is not Especie.MOVIMENTO:
                recusados += 1
                log.warning("relatório não é de movimento, ignorado na apuração",
                            extra={"arquivo": nome, "especie": leitura.especie.value})
                continue
            for m in leitura.movimentos():
                if not m.e_entrada:
                    continue
                lidos += 1
                chave = (m.chave or "").strip()
                if len(chave) != 44 or not chave.isdigit():
                    sem_chave += 1
                    continue
                valor = m.imposto_suportado
                if valor <= 0:
                    continue
                alvo = (chave, (m.codigo_item or "").strip())
                acumulado[alvo] = acumulado.get(alvo, Decimal(0)) + valor
        except (OSError, ValueError) as erro:
            recusados += 1
            log.warning("relatório ilegível na apuração do suportado",
                        extra={"arquivo": nome, "motivo": str(erro)})
        finally:
            if avisar is not None:
                avisar(n, len(relatorios))

    _gravar_retido(acumulado, destino)
    extraido = RetidoExtraido(arquivos=len(relatorios), recusados=recusados,
                              linhas_de_entrada=lidos, sem_chave=sem_chave,
                              itens=len(acumulado))
    log.info("imposto informado pelo cliente extraído", extra=vars(extraido))
    return extraido


def contar_entradas(pasta_movimentos: str) -> int:
    """Quantos itens de entrada a apuração vai percorrer — é o denominador da
    barra. Contar no parquet custa um instante; descobrir no fim não serve."""
    movimentos = os.path.join(pasta_movimentos, ARQUIVO_MOVIMENTOS)
    if not os.path.isfile(movimentos):
        return 0
    con = _leitura(pasta_movimentos)
    try:
        return con.execute(
            f"SELECT count(*) FROM read_parquet('{_escapar(movimentos)}') "
            "WHERE operacao = 'entrada'").fetchone()[0]
    finally:
        con.close()


def _gravar_retido(acumulado: dict, destino: str) -> None:
    """Grava sempre, mesmo vazio: parquet ausente e parquet sem linha dizem
    coisas diferentes, e a apuração precisa distinguir 'não rodou' de 'rodou
    e o cliente não informou nada'."""
    itens = list(acumulado.items())
    escritor = pq.ParquetWriter(destino, ESQUEMA_RETIDO)
    try:
        for i in range(0, len(itens), LINHAS_POR_LOTE):
            fatia = itens[i:i + LINHAS_POR_LOTE]
            escritor.write_table(pa.Table.from_pydict({
                "chave": [c for (c, _), _ in fatia],
                "codigo": [k for (_, k), _ in fatia],
                "informado": [v for _, v in fatia],
            }, schema=ESQUEMA_RETIDO))
    finally:
        escritor.close()


# ---------------------------------------------------------------------------
# a cascata sobre cada item de entrada
# ---------------------------------------------------------------------------
def apurar(
    pasta_movimentos: str,
    destino: str | None = None,
    avisar: Aviso | None = None,
    deve_parar: DeveParar | None = None,
    ao_indexar: Callable[[], None] | None = None,
) -> ResumoDaApuracao:
    """Cruza EFD, imposto informado e cadastro, e grava o suportado por item.

    `pasta_movimentos` é onde a etapa 3 deixou os movimentos e o cadastro;
    `destino` é a pasta desta apuração, com o imposto informado e o resultado.
    Sem `destino`, as duas são a mesma — é o que os testes usam.

    `ao_indexar` avisa que a cascata acabou e começou o índice por documento:
    numa base real são mais de noventa segundos, e a barra parada com o passo
    antigo pareceria travada.

    A alíquota interna vem do 0200 do próprio estabelecimento, que é o único
    lugar onde ela existe por item. Serve à terceira fonte da cascata, a
    reconstrução — que na base medida não salvou nada, porque a BC ST também
    vem zerada no CST 60, mas existe para o cliente cujo arquivo a traga.
    """
    destino = destino or pasta_movimentos
    movimentos = os.path.join(pasta_movimentos, ARQUIVO_MOVIMENTOS)
    cadastro = os.path.join(pasta_movimentos, ARQUIVO_ITENS)
    retido = os.path.join(destino, ARQUIVO_RETIDO)
    saida = os.path.join(destino, ARQUIVO_SUPORTADO)

    if not os.path.isfile(movimentos):
        raise FileNotFoundError(
            f"{ARQUIVO_MOVIMENTOS} não está em {pasta_movimentos}: a etapa de "
            "movimentação precisa ter rodado antes."
        )

    tem_retido = os.path.isfile(retido)
    tem_cadastro = os.path.isfile(cadastro)
    con = _abrir(destino)
    try:
        con.execute(f"""
            CREATE OR REPLACE VIEW entradas AS
            SELECT m.cnpj, m.competencia, m.chave, m.numero_documento, m.modelo,
                   m.participante, m.codigo, m.descricao, m.cst_icms,
                   m.quantidade, m.valor_icms, m.valor_st, m.bc_st,
                   {'r.informado' if tem_retido else 'NULL'} AS informado,
                   {'i.aliq_icms' if tem_cadastro else 'NULL'} AS aliquota
            FROM read_parquet('{_escapar(movimentos)}') m
            {f"LEFT JOIN read_parquet('{_escapar(retido)}') r"
             " ON m.chave = r.chave AND m.codigo = r.codigo" if tem_retido else ""}
            {f"LEFT JOIN read_parquet('{_escapar(cadastro)}') i"
             " ON m.cnpj = i.cnpj AND m.codigo = i.codigo" if tem_cadastro else ""}
            WHERE m.operacao = 'entrada'
        """)
        resumo = _percorrer(con, saida, avisar, deve_parar)
        _conferir(deve_parar)
        if ao_indexar is not None:
            ao_indexar()
        _indexar_documentos(con, saida, os.path.join(destino, ARQUIVO_DOCUMENTOS))
    except ApuracaoCancelada:
        # meio parquet no disco seria lido depois como apuração inteira
        con.close()
        for arquivo in (saida, os.path.join(destino, ARQUIVO_DOCUMENTOS)):
            if os.path.isfile(arquivo):
                os.remove(arquivo)
        raise
    finally:
        con.close()
        _limpar(destino)

    log.info("ICMS suportado apurado",
             extra={"itens": resumo.itens, "apurados": resumo.itens_apurados,
                    "cobertura": round(resumo.cobertura, 4),
                    "valor": str(resumo.valor_total),
                    "documental": str(resumo.valor_documental),
                    "por_fonte": {f.value: n for f, n in resumo.por_fonte.items()}})
    return resumo


def _percorrer(con, saida: str, avisar: Aviso | None,
               deve_parar: DeveParar | None) -> ResumoDaApuracao:
    """Aplica a regra do domínio linha a linha e grava o parquet.

    Linha a linha, e não em SQL: a cascata é regra fiscal e mora no domínio.
    Reescrevê-la em SQL daria duas versões dela, que é como se começa a
    divergir sem ninguém perceber.
    """
    resumo = ResumoDaApuracao()
    andamento = Andamento()
    estabelecimentos: set[str] = set()
    escritor = pq.ParquetWriter(saida, ESQUEMA_SUPORTADO)
    lote = _Lote()
    try:
        leitor = con.execute("SELECT * FROM entradas").to_arrow_reader(LINHAS_POR_LOTE)
        for bloco in leitor:
            _conferir(deve_parar)
            d = bloco.to_pydict()
            for i in range(bloco.num_rows):
                r = apurar_item(EntradaParaApurar(
                    cst_icms=d["cst_icms"][i] or "",
                    valor_icms=d["valor_icms"][i] or Decimal(0),
                    valor_st=d["valor_st"][i] or Decimal(0),
                    bc_st=d["bc_st"][i] or Decimal(0),
                    retido_informado=d["informado"][i],
                    aliquota_interna=d["aliquota"][i],
                ))
                resumo.somar(r)
                lote.acrescentar(d, i, r)
                estabelecimentos.add(d["cnpj"][i])
            if lote.cheio:
                escritor.write_table(lote.tabela())
                lote = _Lote()
            if avisar is not None:
                andamento.itens = resumo.itens
                andamento.apurados = resumo.itens_apurados
                andamento.estabelecimentos = len(estabelecimentos)
                avisar(andamento)
        if lote.tem:
            escritor.write_table(lote.tabela())
    finally:
        escritor.close()
    return resumo


# as colunas de um documento, com o CST e a fonte que mais pesam: uma nota pode
# misturar itens, e a tela mostra o principal
_AGREGADO_DO_DOCUMENTO = """
    chave, any_value(numero_documento) AS numero_documento,
    any_value(modelo) AS modelo,
    min(competencia) AS competencia,
    any_value(participante) AS participante,
    count(*) AS itens, sum(bc_st) AS bc_st, sum(suportado) AS suportado,
    mode(right(coalesce(cst_icms, ''), 2)) AS cst,
    arg_max(fonte, suportado) AS fonte_valor,
    mode(fonte) AS fonte_itens
"""


def _indexar_documentos(con, saida: str, destino: str) -> None:
    """Agrupa por documento uma vez, e a tela só pagina.

    Duas partes no mesmo arquivo: `filtro_fonte` nulo é o analítico inteiro;
    com a fonte, é a nota com os itens daquela fonte. `ordem` numera cada parte
    na ordem da tela, e o arquivo sai ordenado por ela — uma página vira um
    intervalo de `ordem`, que o parquet acha pelas estatísticas do grupo de
    linhas sem ler o resto.
    """
    fonte = f"read_parquet('{_escapar(saida)}')"
    con.execute(f"""
        COPY (
            WITH juntos AS (
                SELECT NULL::VARCHAR AS filtro_fonte, {_AGREGADO_DO_DOCUMENTO}
                FROM {fonte} GROUP BY chave
                UNION ALL
                SELECT fonte AS filtro_fonte, {_AGREGADO_DO_DOCUMENTO}
                FROM {fonte} GROUP BY fonte, chave
            )
            SELECT *, row_number() OVER (
                       PARTITION BY filtro_fonte ORDER BY competencia, chave) AS ordem
            FROM juntos
            ORDER BY filtro_fonte NULLS FIRST, ordem
        ) TO '{_escapar(destino)}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 50000)
    """)


class _Lote:
    """Acumula linhas e vira tabela de uma vez: escrever de linha em linha
    num parquet de milhões de itens custa mais que o cálculo inteiro."""

    def __init__(self) -> None:
        self.colunas: dict[str, list] = {c: [] for c in ESQUEMA_SUPORTADO.names}

    def acrescentar(self, d: dict, i: int, r) -> None:
        for coluna in ("cnpj", "competencia", "chave", "numero_documento", "modelo",
                       "participante", "codigo", "descricao", "cst_icms",
                       "quantidade", "bc_st"):
            self.colunas[coluna].append(d[coluna][i])
        self.colunas["suportado"].append(r.valor)
        self.colunas["fonte"].append(CODIGO_DA_FONTE[r.fonte])
        self.colunas["pendencia"].append(r.pendencia.value if r.pendencia else None)
        self.colunas["motivo"].append(r.motivo)

    @property
    def tem(self) -> bool:
        return bool(self.colunas["chave"])

    @property
    def cheio(self) -> bool:
        return len(self.colunas["chave"]) >= LINHAS_POR_LOTE

    def tabela(self) -> pa.Table:
        return pa.Table.from_pydict(self.colunas, schema=ESQUEMA_SUPORTADO)


# ---------------------------------------------------------------------------
# o que a tela lê depois de pronto
# ---------------------------------------------------------------------------
def fatias_por_fonte(resumo: ResumoDaApuracao) -> list[dict]:
    """A cascata inteira, na ordem dela — inclusive a fonte que não apurou nada.

    A fonte com zero fica na lista de propósito: "reconstruído por alíquota:
    0" é informação, e é justamente a que diz que nada foi estimado.
    """
    return [
        {"codigo": CODIGO_DA_FONTE[f], "rotulo": f.rotulo,
         "itens": resumo.por_fonte[f],
         "valor": resumo.valor_por_fonte[f],
         "documental": f.e_documental if f is not Fonte.NAO_APURAVEL else None}
        for f in Fonte
    ]


def quebras(destino: str) -> dict:
    """Por CST, por competência, estabelecimentos e o CST que domina a pendência.

    Sai do parquet já gravado, numa passada do DuckDB cada. Por competência
    leva a cobertura do mês, porque um total mensal bom pode esconder um mês em
    que quase nada apurou.
    """
    saida = os.path.join(destino, ARQUIVO_SUPORTADO)
    fonte = f"read_parquet('{_escapar(saida)}')"
    con = _leitura(destino)
    try:
        por_cst = [
            {"cst": cst or "", "itens": itens, "valor": Decimal(str(valor or 0)),
             "apurados": apurados}
            for cst, itens, valor, apurados in con.execute(f"""
                SELECT right(coalesce(cst_icms, ''), 2) AS cst, count(*),
                       sum(suportado), count(*) FILTER (fonte <> 'nao_apuravel')
                FROM {fonte} GROUP BY 1 ORDER BY 3 DESC NULLS LAST, 2 DESC
            """).fetchall()
        ]
        por_competencia = [
            {"competencia": comp.isoformat()[:7] if comp else "",
             "itens": itens, "valor": Decimal(str(valor or 0)),
             "cobertura": round(apurados / itens, 4) if itens else 0.0}
            for comp, itens, valor, apurados in con.execute(f"""
                SELECT competencia, count(*), sum(suportado),
                       count(*) FILTER (fonte <> 'nao_apuravel')
                FROM {fonte} GROUP BY 1 ORDER BY 1
            """).fetchall()
        ]
        estabelecimentos = con.execute(
            f"SELECT count(DISTINCT cnpj) FROM {fonte}").fetchone()[0]
        dominante = con.execute(f"""
            SELECT right(coalesce(cst_icms, ''), 2), count(*)
            FROM {fonte} WHERE pendencia = '{Pendencia.SEM_O_QUE_APURAR.value}'
            GROUP BY 1 ORDER BY 2 DESC LIMIT 1
        """).fetchone()
    finally:
        con.close()
    return {
        "por_cst": por_cst,
        "por_competencia": por_competencia,
        "estabelecimentos": estabelecimentos,
        "cst_sem_o_que_apurar": ({"cst": dominante[0], "itens": dominante[1]}
                                 if dominante else None),
    }


def linhas(
    destino: str,
    escopo: str = "documento",
    fonte: str | None = None,
    busca: str | None = None,
    pagina: int = 1,
    por_pagina: int = POR_PAGINA_PADRAO,
) -> dict:
    """Uma página do analítico, montada no servidor.

    `escopo` é "documento" — uma linha por nota, com os itens dela — ou "item",
    a lista achatada. `fonte` filtra antes de agrupar: a nota aparece com os
    itens daquela fonte e o total deles, que é o que "filtrado por fonte" quer
    dizer. `busca` procura na chave, no número, no participante, no código e na
    descrição.
    """
    if escopo not in ("documento", "item"):
        raise ValueError(f"Escopo desconhecido: {escopo}. Vale documento ou item.")
    if fonte and fonte not in FONTE_DO_CODIGO:
        raise ValueError(f"Fonte desconhecida: {fonte}.")
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))

    saida = os.path.join(destino, ARQUIVO_SUPORTADO)
    if not os.path.isfile(saida):
        raise FileNotFoundError(f"{ARQUIVO_SUPORTADO} não está em {destino}.")

    filtros, parametros = [], []
    if fonte:
        filtros.append("fonte = ?")
        parametros.append(fonte)
    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        filtros.append("(chave ILIKE ? OR numero_documento ILIKE ? OR participante ILIKE ? "
                       "OR codigo ILIKE ? OR descricao ILIKE ?)")
        parametros.extend([termo] * 5)
    onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    base = f"(SELECT * FROM read_parquet('{_escapar(saida)}') {onde})"
    deslocamento = (pagina - 1) * por_pagina

    con = _leitura(destino)
    try:
        if escopo == "item":
            total = con.execute(f"SELECT count(*) FROM {base}", parametros).fetchone()[0]
            cursor = con.execute(f"""
                SELECT chave, numero_documento, modelo, competencia, participante, codigo,
                       descricao, cst_icms, fonte, bc_st, suportado, motivo
                FROM {base}
                ORDER BY competencia, chave, codigo
                LIMIT {por_pagina} OFFSET {deslocamento}
            """, parametros)
            nomes = [c[0] for c in cursor.description]
            itens = [_item(dict(zip(nomes, r))) for r in cursor.fetchall()]
            return {"escopo": escopo, "pagina": pagina, "por_pagina": por_pagina,
                    "total": total, "linhas": itens}

        indice = os.path.join(destino, ARQUIVO_DOCUMENTOS)
        colunas = ("chave, numero_documento, modelo, competencia, participante, itens, "
                   "bc_st, suportado, cst, fonte_valor, fonte_itens")
        if os.path.isfile(indice) and not (busca and busca.strip()):
            # sem busca, a página sai pronta do índice
            parte = "filtro_fonte = ?" if fonte else "filtro_fonte IS NULL"
            recorte = [fonte] if fonte else []
            idx = f"read_parquet('{_escapar(indice)}')"
            total = con.execute(f"SELECT count(*) FROM {idx} WHERE {parte}", recorte).fetchone()[0]
            documentos = con.execute(f"""
                SELECT {colunas} FROM {idx}
                WHERE {parte} AND ordem > {deslocamento} AND ordem <= {deslocamento + por_pagina}
                ORDER BY ordem
            """, recorte).fetchall()
        else:
            total = con.execute(
                f"SELECT count(DISTINCT chave) FROM {base}", parametros).fetchone()[0]
            documentos = con.execute(f"""
                SELECT {colunas} FROM (
                    SELECT {_AGREGADO_DO_DOCUMENTO} FROM {base} GROUP BY chave
                ) ORDER BY competencia, chave
                LIMIT {por_pagina} OFFSET {deslocamento}
            """, parametros).fetchall()
        chaves = [d[0] for d in documentos]
        filhos: dict[str, list[dict]] = {c: [] for c in chaves}
        if chaves:
            marcadores = ", ".join("?" * len(chaves))
            cursor = con.execute(f"""
                SELECT chave, numero_documento, modelo, competencia, participante, codigo,
                       descricao, cst_icms, fonte, bc_st, suportado, motivo
                FROM {base} WHERE chave IN ({marcadores})
                ORDER BY chave, codigo
            """, parametros + chaves)
            nomes = [c[0] for c in cursor.description]
            for r in cursor.fetchall():
                linha = dict(zip(nomes, r))
                filhos[linha["chave"]].append(_item(linha))
    finally:
        con.close()

    saida_docs = []
    for (chave, numero, modelo, comp, participante, n_itens, bc_st, suportado,
         cst, fonte_valor, fonte_itens) in documentos:
        principal = fonte_valor if (suportado or 0) > 0 else fonte_itens
        saida_docs.append({
            "chave": chave, "numero_documento": numero, "modelo": modelo or "",
            "competencia": comp.isoformat()[:7] if comp else "",
            "participante": participante, "cst": cst or "",
            "fonte": principal, "itens": n_itens,
            "bc_st": str(Decimal(str(bc_st or 0))),
            "suportado": str(Decimal(str(suportado or 0))),
            "filhos": filhos.get(chave, []),
        })
    return {"escopo": escopo, "pagina": pagina, "por_pagina": por_pagina,
            "total": total, "linhas": saida_docs}


def _item(linha: dict) -> dict:
    comp = linha.get("competencia")
    return {
        "chave": linha.get("chave"),
        "numero_documento": linha.get("numero_documento"),
        "modelo": linha.get("modelo") or "",
        "competencia": comp.isoformat()[:7] if comp else "",
        "participante": linha.get("participante"),
        "codigo": linha.get("codigo"),
        "descricao": linha.get("descricao"),
        "cst": (linha.get("cst_icms") or "")[-2:],
        "fonte": linha.get("fonte"),
        "bc_st": str(Decimal(str(linha.get("bc_st") or 0))),
        "suportado": str(Decimal(str(linha.get("suportado") or 0))),
        "motivo": linha.get("motivo") or "",
    }

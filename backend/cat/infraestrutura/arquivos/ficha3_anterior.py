"""A Ficha 3 de um período anterior, como o cliente a entregou: de onde a nossa
começa.

A Ficha 3 é contínua. O período novo transcreve o saldo de quantidade e de ICMS
suportado com que o anterior terminou (item 3.3.1 do manual). Quando o cliente
já transmitiu fichas feitas por outra ferramenta, a abertura do nosso período é
o saldo final delas, e não o inventário (decisão do Victor, 26/11/2026). O
inventário só entra no estabelecimento que não tem ficha anterior nenhuma.

## O arquivo

É a ficha "achatada", uma por estabelecimento e mês: TXT separado por `|`, em
latin-1, com uma linha de cabeçalho e uma linha por lançamento. A primeira linha
de cada item no mês é o saldo que veio do mês anterior (CFOP `0001`). As colunas
que interessam aqui:

| Cabeçalho | O que é |
|---|---|
| Código da Mercadoria (1ª) | código do item |
| UNID_INV | unidade da ficha |
| Número de Ordem | ordem do lançamento |
| Quantidade, Valor Unitário do Saldo, Valor Total do Saldo | o saldo depois da linha |
| MES_ANO | competência (mm/aaaa) |
| CNPJ_FILIAL | estabelecimento |

O cabeçalho repete "Quantidade" três vezes (entrada, saída e saldo). Por isso
as posições saem do cabeçalho a partir do "Valor Total do Saldo", e não do nome
"Quantidade".

## Qual mês vale

Para cada estabelecimento, vale o mês mais recente ANTES do início do período,
e dentro dele a última linha de cada item. É onde a ficha anterior terminou, e
é dali que a nossa continua (decisão do Victor, 27/11/2026). O item que esse
mês não lista não volta de um mês mais antigo. No projeto 1, a ficha da RVC
tira itens em três cortes: dez/2020, quando ela reiniciou o estoque, e set/2024
e jul/2025, quando retirou itens ainda com saldo. Continuar a RVC é continuar o
que ela transmitiu no fim, e não ressuscitar o que ela mesma deixou para trás.

O estabelecimento cujo último mês não é o imediatamente anterior ao período
(uma loja que fechou, um mês que falta) vale do mesmo jeito, com o último mês
dele, e é contado em `defasados`.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from datetime import date

ARQUIVO_SALDO_ANTERIOR = "saldo_da_ficha_anterior.parquet"

CODIFICACAO = "latin-1"


def _normal(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


@dataclass(frozen=True)
class Colunas:
    """Posições (a partir de 0) das colunas que a abertura usa."""

    codigo: int
    unidade: int
    ordem: int
    quantidade: int
    valor: int
    mes_ano: int
    cnpj: int
    total: int


def colunas_do_cabecalho(cabecalho: str) -> Colunas | None:
    """As posições, ou None quando o cabeçalho não é o da ficha achatada."""
    nomes = [_normal(c) for c in cabecalho.rstrip("\r\n").split("|")]

    def achar(prefixo: str) -> int | None:
        return next((i for i, n in enumerate(nomes) if n.startswith(prefixo)), None)

    valor = achar("valor total do saldo")
    unidade = achar("unid_inv")
    ordem = achar("numero de ordem")
    mes_ano = achar("mes_ano")
    cnpj = achar("cnpj_filial")
    if None in (valor, unidade, ordem, mes_ano, cnpj) or valor < 2:
        return None
    if not nomes[0].startswith("codigo da mercadoria") or nomes[valor - 2] != "quantidade":
        return None
    return Colunas(codigo=0, unidade=unidade, ordem=ordem, quantidade=valor - 2, valor=valor,
                   mes_ano=mes_ano, cnpj=cnpj, total=len(nomes))


def competencia_de(mes_ano: str) -> date | None:
    """`12/2025` -> 01/12/2025."""
    partes = (mes_ano or "").strip().split("/")
    if len(partes) != 2 or not all(p.isdigit() for p in partes):
        return None
    mes, ano = int(partes[0]), int(partes[1])
    return date(ano, mes, 1) if 1 <= mes <= 12 else None


@dataclass(frozen=True)
class Identificacao:
    cnpj: str
    competencia: date
    colunas: Colunas


def identificar(caminho: str) -> Identificacao | None:
    """CNPJ e competência pela primeira linha de dados. None se não for a ficha."""
    try:
        with open(caminho, encoding=CODIFICACAO, newline="") as f:
            colunas = colunas_do_cabecalho(f.readline())
            if colunas is None:
                return None
            for linha in f:
                campos = linha.rstrip("\r\n").split("|")
                if len(campos) < colunas.total - 1:
                    continue
                competencia = competencia_de(campos[colunas.mes_ano])
                cnpj = "".join(ch for ch in campos[colunas.cnpj] if ch.isdigit())
                if competencia is not None and len(cnpj) == 14:
                    return Identificacao(cnpj, competencia, colunas)
                return None
    except OSError:
        return None
    return None


@dataclass
class SaldosLidos:
    arquivos: int = 0                  # arquivos lidos: o último mês de cada estabelecimento
    ignorados: int = 0                 # não são a ficha achatada
    itens: int = 0
    icms: float = 0.0
    # estabelecimento cujo último mês não é o imediatamente anterior ao período
    defasados: dict = field(default_factory=dict)


def escolher_arquivos(caminhos: list[str], inicio: date
                      ) -> tuple[dict[str, list[tuple[date, str, Colunas]]], int]:
    """Por estabelecimento, todos os arquivos de antes de `inicio`, do mês mais
    recente para o mais antigo."""
    escolhidos: dict[str, list[tuple[date, str, Colunas]]] = {}
    ignorados = 0
    for caminho in caminhos:
        ident = identificar(caminho)
        if ident is None:
            ignorados += 1
            continue
        if ident.competencia >= inicio:
            continue
        escolhidos.setdefault(ident.cnpj, []).append((ident.competencia, caminho, ident.colunas))
    for lista in escolhidos.values():
        lista.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return escolhidos, ignorados


def _escapar(caminho: str) -> str:
    return caminho.replace("\\", "/").replace("'", "''")


def _ultimas_do_mes(cnpj: str, competencia: date, caminho: str, c: Colunas) -> str:
    """O INSERT da última linha de cada item de um arquivo."""
    col = {f"c{i:02d}": "VARCHAR" for i in range(c.total)}
    ordem = f"TRY_CAST(c{c.ordem:02d} AS BIGINT)"

    def num(i: int) -> str:
        return f"CAST(replace(nullif(trim(c{i:02d}), ''), ',', '.') AS DECIMAL(38, 15))"

    return f"""
        INSERT INTO ultimas
        SELECT * FROM (
            SELECT '{cnpj}' AS cnpj, trim(c{c.codigo:02d}) AS codigo,
                   arg_max(trim(c{c.unidade:02d}), {ordem}) AS unidade,
                   DATE '{competencia.isoformat()}' AS competencia,
                   arg_max({num(c.quantidade)}, {ordem}) AS quantidade,
                   arg_max({num(c.valor)}, {ordem}) AS valor
            FROM read_csv('{_escapar(caminho)}', delim='|', header=false, skip=1, quote='',
                          escape='', columns={col}, null_padding=true, encoding='latin-1')
            WHERE nullif(trim(c{c.codigo:02d}), '') IS NOT NULL
            GROUP BY 2) n"""


def gravar_saldos(caminhos: list[str], inicio: date, destino: str) -> SaldosLidos:
    """Grava `cnpj, codigo, unidade, competencia, quantidade, valor`: o saldo com
    que a ficha anterior terminou (a última linha de cada item no último mês do
    estabelecimento), um por item e estabelecimento."""
    import duckdb  # noqa: PLC0415
    import pyarrow as pa  # noqa: PLC0415
    import pyarrow.parquet as pq  # noqa: PLC0415

    resumo = SaldosLidos()
    escolhidos, resumo.ignorados = escolher_arquivos(caminhos, inicio)
    anterior = date(inicio.year - (inicio.month == 1), (inicio.month - 2) % 12 + 1, 1)
    esquema = pa.schema([("cnpj", pa.string()), ("codigo", pa.string()), ("unidade", pa.string()),
                         ("competencia", pa.date32()), ("quantidade", pa.decimal128(38, 9)),
                         ("valor", pa.decimal128(38, 15))])
    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    if not escolhidos:
        pq.write_table(esquema.empty_table(), destino)
        return resumo
    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE ultimas (cnpj VARCHAR, codigo VARCHAR, unidade VARCHAR, "
                    "competencia DATE, quantidade DECIMAL(38, 15), valor DECIMAL(38, 15))")
        for cnpj, arquivos in sorted(escolhidos.items()):
            if arquivos[0][0] != anterior:
                resumo.defasados[cnpj] = arquivos[0][0].isoformat()
            competencia, caminho, c = arquivos[0]
            resumo.arquivos += 1
            con.execute(_ultimas_do_mes(cnpj, competencia, caminho, c))
        con.execute(f"""COPY (SELECT cnpj, codigo, unidade, competencia,
                                     CAST(quantidade AS DECIMAL(38, 9)) AS quantidade, valor
                              FROM ultimas ORDER BY cnpj, codigo)
                        TO '{_escapar(destino)}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
        resumo.itens, icms = con.execute(
            f"SELECT count(*), coalesce(sum(valor), 0) FROM read_parquet('{_escapar(destino)}')").fetchone()
        resumo.icms = float(icms)
    finally:
        con.close()
    return resumo

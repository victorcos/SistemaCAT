"""Exporta a Ficha 3 **por estabelecimento**, no leiaute do papel de trabalho.

A Ficha 3 é escriturada por estabelecimento e por mercadoria, e é um histórico:
cada lançamento em ordem, com o saldo andando linha a linha. Um resumo de uma
linha por ficha serve para achar onde está o ressarcimento, não para entregar —
quem confere compara lançamento com lançamento.

Por isso este módulo **não** monta leiaute nenhum: ele usa o do sistema
(`planilhas/razao.gerar_ficha3`, com `COLUNAS_FICHA3`), que já traz as faixas
por bloco, o número do campo de (1) a (27), a quebra em abas de 900 mil linhas
e as duas colunas vazias da correção à mão. O que ele faz é o recorte:

* uma saída por CNPJ, porque a ficha é por estabelecimento;
* a ficha em ordem de histórico (`codigo`, `numero`), que é como se lê;
* opcionalmente só as mercadorias com entrada **e** saída no período — as de
  um lado só não têm confronto possível e poluem a conferência.

## Formato: CSV por padrão, e não é preguiça

Numa base real a filial grande passa de 4 milhões de lançamentos. Em xlsx isso
são 5 abas e alguns gigabytes de XML por filial, com meia hora de escrita cada
— e ninguém confere 4 milhões de linhas rolando a tela. O CSV sai em minutos,
não tem limite de linha e carrega em DuckDB, Power BI ou no sistema do cliente,
que é o que se faz com um arquivo desse tamanho. O xlsx continua disponível com
`--formato xlsx` para a filial que alguém vai realmente abrir.

Uso:
    exportar_ficha3_por_filial.py <pasta_do_razao> <pasta_de_destino>
        [--formato csv|xlsx] [--todas] [--filial CNPJ]

    --todas    inclui as mercadorias sem entrada ou sem saída no período
    --filial   só esse CNPJ (pode repetir)
"""
from __future__ import annotations

import argparse
import os
import time

import duckdb

from cat.infraestrutura.analitico.razao import ARQUIVO_FICHA3, ARQUIVO_FICHAS
from cat.infraestrutura.planilhas.razao import gerar_ficha3
from cat.log import configurar, obter_log

log = obter_log(__name__)


def _literal(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _como_sql(caminho: str) -> str:
    return _literal(caminho.replace("\\", "/"))


def estabelecimentos(ficha3: str, con: duckdb.DuckDBPyConnection) -> list[tuple[str, int]]:
    """Os CNPJ da ficha e quantos lançamentos cada um tem, do maior para o menor.

    Do maior para o menor de propósito: se o disco ou o tempo acabarem no meio,
    o que ficou pronto é o que mais pesa na apuração.
    """
    return con.execute(f"""
        SELECT cnpj, count(*) FROM read_parquet({_como_sql(ficha3)})
        GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()


def recortar(con: duckdb.DuckDBPyConnection, ficha3: str, cnpj: str,
             rascunho: str, so_com_par: bool) -> int:
    """Grava o parquet de uma filial, em ordem de histórico. Devolve as linhas."""
    filtro = ""
    if so_com_par:
        # semi-join com as fichas que têm os dois lados: é o recorte que o
        # Victor pediu, "os itens com entradas e saídas confirmadas"
        filtro = " AND EXISTS (SELECT 1 FROM par p WHERE p.cnpj = f.cnpj AND p.codigo = f.codigo)"
    con.execute(f"""
        COPY (
            SELECT f.* FROM read_parquet({_como_sql(ficha3)}) f
            WHERE f.cnpj = {_literal(cnpj)}{filtro}
            ORDER BY f.codigo, f.numero
        ) TO {_como_sql(rascunho)} (FORMAT parquet)
    """)
    return con.execute(f"SELECT count(*) FROM read_parquet({_como_sql(rascunho)})").fetchone()[0]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("razao")
    p.add_argument("destino")
    p.add_argument("--formato", default="csv", choices=("csv", "xlsx"))
    p.add_argument("--todas", action="store_true",
                   help="inclui mercadoria sem entrada ou sem saída no período")
    p.add_argument("--filial", action="append", default=[])
    # em xlsx a base inteira leva horas num processo só, e a máquina tem CPU
    # sobrando: `--fatia 1/3` em três processos divide as filiais em três
    # listas intercaladas pelo tamanho, o que as deixa com volume parecido
    p.add_argument("--fatia", default="", metavar="N/M")
    # com três processos a 4 GB cada, esta máquina (23,7 GB, ~9 GB livres)
    # levou um segmentation fault no meio da empresa 17. O recorte derrama em
    # disco sem reclamar; o que não se recupera é o processo morto na metade
    p.add_argument("--memoria", default="2GB")
    args = p.parse_args()
    # sem isto o log do projeto não tem handler e a exportação roda muda — e
    # esta roda horas em segundo plano, onde o log é a única forma de acompanhar
    configurar()

    ficha3 = os.path.join(args.razao, ARQUIVO_FICHA3)
    fichas = os.path.join(args.razao, ARQUIVO_FICHAS)
    for caminho in (ficha3, fichas):
        if not os.path.isfile(caminho):
            raise SystemExit(f"falta {os.path.basename(caminho)} em {args.razao}")
    os.makedirs(args.destino, exist_ok=True)
    rascunhos = os.path.join(args.destino, "_rascunho")
    os.makedirs(rascunhos, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"SET temp_directory = {_como_sql(rascunhos)}")
    con.execute(f"SET memory_limit = {_literal(args.memoria)}")
    con.execute("SET threads TO 2")
    con.execute("SET preserve_insertion_order = false")
    if not args.todas:
        con.execute(f"""CREATE TABLE par AS
            SELECT cnpj, codigo FROM read_parquet({_como_sql(fichas)})
            WHERE entradas > 0 AND saidas > 0""")
        log.info("fichas com entrada e saída: %s",
                 f"{con.execute('SELECT count(*) FROM par').fetchone()[0]:,}")

    lista = estabelecimentos(ficha3, con)
    if args.filial:
        pedidos = {c.strip() for c in args.filial}
        lista = [x for x in lista if x[0] in pedidos]
    if args.fatia:
        n, m = (int(x) for x in args.fatia.split("/"))
        if not 1 <= n <= m:
            raise SystemExit(f"--fatia fora de faixa: {args.fatia}")
        # a lista já vem do maior para o menor, então intercalar distribui as
        # filiais grandes entre as fatias em vez de amontoá-las numa só
        lista = lista[n - 1::m]
    log.info("estabelecimentos a exportar: %d, formato %s, recorte %s",
             len(lista), args.formato, "todas as mercadorias" if args.todas
             else "só com entrada e saída")

    inicio = time.time()
    gravadas = 0
    for i, (cnpj, total_bruto) in enumerate(lista, start=1):
        t0 = time.time()
        # o sufixo do CNPJ é o número da filial no ERP: é por ele que o cliente
        # pede "a ficha da loja 19", e é o que deixa a pasta legível
        nome = f"FICHA3_{cnpj[8:12]}_{cnpj}.{args.formato}"
        destino = os.path.join(args.destino, nome)
        # **retomada.** Uma filial grande leva 40 minutos, e a base inteira
        # horas: processo morto no meio não pode custar o que já estava pronto.
        # O nome final só aparece quando o arquivo fechou inteiro
        # (`materializando`), então existir é garantia de estar completo.
        if os.path.isfile(destino):
            log.info("[%d/%d] %s já está pronto (%.1f MB): pulando",
                     i, len(lista), cnpj, os.path.getsize(destino) / 1e6)
            continue
        rascunho = os.path.join(rascunhos, f"ficha3_{cnpj}.parquet")
        linhas = recortar(con, ficha3, cnpj, rascunho, not args.todas)
        if not linhas:
            log.warning("filial %s sem linha no recorte: %s lançamentos ao todo, "
                        "nenhum de mercadoria com os dois lados", cnpj, f"{total_bruto:,}")
            os.remove(rascunho)
            continue
        try:
            escritas = gerar_ficha3(rascunho, destino, formato=args.formato)
        finally:
            os.remove(rascunho)
        gravadas += escritas
        log.info("[%d/%d] %s: %s linhas em %.1f min (%.1f MB) — %s",
                 i, len(lista), cnpj, f"{escritas:,}", (time.time() - t0) / 60,
                 os.path.getsize(destino) / 1e6, nome)

    log.info("pronto: %d arquivos, %s linhas, %.1f min, em %s",
             len(lista), f"{gravadas:,}", (time.time() - inicio) / 60, args.destino)
    try:
        os.rmdir(rascunhos)
    except OSError:
        log.info("pasta de rascunho não ficou vazia: %s", rascunhos)


if __name__ == "__main__":
    main()

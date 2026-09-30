"""Carregar no banco a alíquota de ICMS por produto — só o que foge da regra.

O ICMS-ST presumido do relatório 839 precisa da alíquota de cada mercadoria.
A **regra** — interna do estado, ou a Resolução 22/1989 do Senado — é lei e
está no código. O que este comando carrega é a **exceção**: cesta básica a 12%,
supérfluo a 25%, isento a 0%, importado a 4%.

## Duas fontes, e a diferença entre elas importa

    # do relatório do escritório anterior, convertido em parquet
    python tools/carregar_aliquotas.py gabarito <parquet do 839>

    # do cadastro que o cliente mandou
    python tools/carregar_aliquotas.py csv <arquivo.csv>

A primeira é a mais rápida e a mais frágil: copia a classificação de quem fez o
trabalho antes, sem conferi-la. A segunda vem de quem responde pelo cadastro. O
banco guarda qual foi, em `fonte`, porque quem assinar o pedido tem o direito de
saber de onde saiu o número.

O CSV tem uma linha por exceção, com cabeçalho:

    cnpj;uf_origem;uf_destino;codigo_do_item;aliquota

**Não versiona dado de cliente.** Recebe o caminho por argumento e imprime só
contagens.
"""

from __future__ import annotations

import argparse
import collections
import csv
import sys
from decimal import Decimal, InvalidOperation

import pyarrow.parquet as pq

from cat.infraestrutura.aliquotas import repositorio
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.sped.tabelas import tab_aliquota_icms

FONTE_DO_GABARITO = "gabarito-839"
FONTE_DO_CLIENTE = "cliente"

# as colunas do relatório 839 de onde a exceção sai
CNPJ = "CNPJ"
UF = "UF Origem/Destino"
ITEM = "Código Item"
ALIQUOTA = "Alíquota Interna ICMS/UF Origem/Destino"


def do_gabarito(parquet: str) -> dict[repositorio.Chave, Decimal]:
    """As alíquotas do 839 que a regra **não** explica.

    Filtrar aqui é o ponto: carregar as que a regra já acerta encheria o banco
    com 6.720 linhas dizendo "18%, como manda a lei de Minas", e trocaria uma
    regra auditável por uma tabela opaca.
    """
    tabela = pq.read_table(parquet, columns=[CNPJ, UF, ITEM, ALIQUOTA])
    fora: dict[repositorio.Chave, Decimal] = {}
    for cnpj, uf, item, aliquota in zip(
            tabela.column(CNPJ).to_pylist(), tabela.column(UF).to_pylist(),
            tabela.column(ITEM).to_pylist(), tabela.column(ALIQUOTA).to_pylist()):
        origem, destino = (str(uf).split("/") + [""])[:2]
        try:
            do_ma = Decimal(str(aliquota))
        except InvalidOperation:
            continue
        try:
            if tab_aliquota_icms.da_regra(origem, destino) == do_ma:
                continue
        except tab_aliquota_icms.AliquotaDesconhecida:
            pass
        fora[(str(cnpj), origem, destino, str(item))] = do_ma
    return fora


def do_csv(caminho: str) -> dict[repositorio.Chave, Decimal]:
    """O cadastro que o cliente mandou. Linha torta vira aviso, não exceção."""
    fora: dict[repositorio.Chave, Decimal] = {}
    tortas = 0
    with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo, delimiter=";"):
            try:
                chave = (linha["cnpj"].strip(), linha["uf_origem"].strip().upper(),
                         linha["uf_destino"].strip().upper(),
                         linha["codigo_do_item"].strip())
                fora[chave] = Decimal(linha["aliquota"].strip().replace(",", "."))
            except (KeyError, AttributeError, InvalidOperation):
                tortas += 1
    if tortas:
        print(f"  {tortas} linha(s) sem sentido, ignoradas.")
    return fora


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origem", choices=["gabarito", "csv"],
                        help="de onde vem: o parquet do 839 ou o CSV do cliente")
    parser.add_argument("arquivo", help="o caminho do parquet ou do CSV")
    args = parser.parse_args()

    if args.origem == "gabarito":
        excecoes, fonte = do_gabarito(args.arquivo), FONTE_DO_GABARITO
    else:
        excecoes, fonte = do_csv(args.arquivo), FONTE_DO_CLIENTE

    if not excecoes:
        print("nenhuma exceção: a regra do estado explica tudo o que veio.")
        return 0

    print(f"{len(excecoes):,} exceção(ões), em {len({c for c, _, _, _ in excecoes})} "
          f"estabelecimento(s):".replace(",", "."))
    for aliquota, quantas in collections.Counter(excecoes.values()).most_common():
        print(f"   {aliquota}%  {quantas:,} item(ns)".replace(",", "."))

    with Sessao() as sessao:
        mexidas = repositorio.gravar(sessao, excecoes, fonte)
    print(f"\ngravadas ou atualizadas: {mexidas:,}".replace(",", "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())

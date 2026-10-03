"""Descobrir, pela amostra, qual campo do SPED alimenta cada coluna do 047.

O relatório 047 do Sistema MA tem 53 colunas e nenhum documento diz de onde
vem cada uma. O que existe é um par: **o CSV que o MA gerou** e **o SPED que o
originou**. Esta ferramenta cruza os dois e deixa a própria amostra responder.

## Como

1. lê o SPED e monta, para cada C170, o registro inteiro com o contexto que o
   leiaute amarra pela posição — 0000, 0140, C010, C100 — e pelas tabelas de
   cadastro — 0150 (participante), 0200 (item), 0400 (natureza);
2. lê as linhas do CSV daquele período e casa cada uma com o seu C170, pela
   chave da nota e pelo número do item;
3. para cada uma das 53 colunas, guarda **quais campos do SPED têm aquele mesmo
   valor** naquela linha, e vai intersectando linha a linha.

O que sobra na interseção depois de centenas de linhas é o campo que alimenta a
coluna. Coluna que fica sem candidato é coluna **derivada** — um de-para, uma
conta, um rótulo — e aparece na saída como "sem campo direto", que é a
informação que interessa: é ali que mora regra, e não cópia.

**Não versiona dado de cliente.** Recebe os dois caminhos por argumento e
imprime só nomes de coluna e de campo — nunca valores.

    python tools/inferir_047.py <csv do MA> <arquivo SPED> [--linhas 500]

## O que a primeira rodada respondeu (empresa F, 10/2025, 3.000 linhas)

Quarenta e seis das 53 colunas são **cópia direta**, e sete são **derivadas**:

* `Registros` — o rótulo da combinação ("C100/C170 - Documento - Nota Fiscal");
* `UF Origem/Destino` — "MG/MG": a UF do estabelecimento e a do participante,
  que no SPED só existem como código de município (tab_municipio);
* `Tipo Item` — "00 Mercadoria para Revenda": código **e** rótulo
  (tab_tipo_item, sobre o 0200);
* `Descrição CFOP` — tab_cfop, sobre o C170;
* `Natureza` — Venda, Devolução de compra, Outras saídas/prestações,
  Lançamento de valor: sai do CFOP;
* `Faturamento` — "Faturamento" quando a natureza é Venda, vazio nas demais;
* `Situação` — é o C100_COD_SIT; aparece aqui como "sempre vazia" só porque
  nesta base é sempre "00", e o filtro de valor informativo descarta zero.

## Isto é o andaime, não a obra

A 047 existe desde 29/09/2026 em `sped/saidas.py`, conferida linha a linha
contra as 7.784.121 do gabarito. **É lá que está o mapa verdadeiro**, e em
alguns pontos ele não é o que esta ferramenta havia sugerido: a UF sai
estabelecimento/participante e não o contrário, o cadastro do item pende do
0140 e não do arquivo, e a nota cancelada rende linha — menos a NFC-e.

Esta ferramenta fica porque o método serve para o próximo relatório do MA que
precisar ser portado sem documentação. Quem a rodar de novo, leia o resultado
como hipótese a conferir, nunca como resposta.
"""

from __future__ import annotations

import argparse
import collections
import sys

from cat.infraestrutura.sped.leitor import campos_da_linha
from cat.infraestrutura.sped.registros import campos_de

# o que o MA escreve em volta do valor para o Excel não comer zero à esquerda
def limpar(bruto: str) -> str:
    texto = bruto.strip()
    if texto.startswith('="') and texto.endswith('"'):
        texto = texto[2:-1]
    elif texto.startswith('"') and texto.endswith('"'):
        texto = texto[1:-1]
    return texto.strip()


def formas(valor: str) -> set[str]:
    """As caras que o mesmo dado tem nos dois lados.

    O SPED grava data como `15102025` e o MA como `15/10/2025`; o SPED grava
    `1234,56` e o MA às vezes `1.234,56`. Comparar só o texto cru perderia o
    par — e perder o par faria a coluna parecer derivada quando é cópia.
    """
    v = valor.strip()
    if not v:
        return set()
    saida = {v, v.replace(".", "")}
    digitos = "".join(c for c in v if c.isdigit())
    if len(digitos) == 8 and v.isdigit():
        saida.add(f"{v[:2]}/{v[2:4]}/{v[4:]}")
    if len(v) == 10 and v[2] == "/" and v[5] == "/":
        saida.add(v[:2] + v[3:5] + v[6:])
    # "1,6500" e "1,65" são o mesmo número para quem confere
    if "," in v:
        saida.add(v.rstrip("0").rstrip(",") or "0")
    return saida


def ler_sped(caminho: str, codificacao: str = "cp1252") -> dict[tuple[str, str], dict[str, str]]:
    """Um dicionário por item do C170, com todo o contexto, pela chave e nº do item."""
    contexto: dict[str, list[str]] = {}
    tabelas: dict[str, dict[str, list[str]]] = {"0150": {}, "0200": {}, "0400": {}}
    chaves_da_tabela = {"0150": "COD_PART", "0200": "COD_ITEM", "0400": "COD_NAT"}
    itens: dict[tuple[str, str], dict[str, str]] = {}

    def nomear(destino: dict[str, str], registro: str, valores: list[str]) -> None:
        for i, campo in enumerate(campos_de(registro, len(valores))):
            destino[f"{registro}_{campo}"] = valores[i] if i < len(valores) else ""

    def valor(registro: str, campo: str) -> str:
        valores = contexto.get(registro, [])
        nomes = campos_de(registro, len(valores))
        return valores[nomes.index(campo)] if campo in nomes else ""

    with open(caminho, "rb") as arquivo:
        for bruto in arquivo:
            if not bruto.startswith(b"|"):
                continue
            fim = bruto.find(b"|", 1)
            if fim < 2:
                continue
            registro = bruto[1:fim].decode("ascii", "replace")
            if registro not in ("0000", "0140", "0150", "0200", "0400", "C010", "C100", "C170"):
                continue
            valores = campos_da_linha(bruto, codificacao)
            if registro in tabelas:
                codigo = valor_do(registro, valores, chaves_da_tabela[registro])
                if codigo:
                    tabelas[registro][codigo] = valores
                continue
            if registro != "C170":
                contexto[registro] = valores
                continue

            linha: dict[str, str] = {}
            for pai in ("0000", "0140", "C010", "C100"):
                nomear(linha, pai, contexto.get(pai, []))
            nomear(linha, "C170", valores)
            for tabela, campo_de_ligacao in chaves_da_tabela.items():
                codigo = (valor_do("C170", valores, campo_de_ligacao)
                          or valor("C100", campo_de_ligacao))
                nomear(linha, tabela, tabelas[tabela].get(codigo, []))
            chave = (linha.get("C100_CHV_NFE", ""), linha.get("C170_NUM_ITEM", ""))
            itens[chave] = linha
    return itens


def valor_do(registro: str, valores: list[str], campo: str) -> str:
    nomes = campos_de(registro, len(valores))
    return valores[nomes.index(campo)] if campo in nomes else ""


def informativo(valor: str) -> bool:
    """Se o valor distingue alguma coisa. `0,00` e vazio não distinguem nada."""
    texto = (valor or "").strip()
    if not texto:
        return False
    return texto.replace("0", "").replace(",", "").replace(".", "") != ""


def inferir(csv: str, itens: dict, limite: int):
    # quantas vezes cada campo do SPED teve o mesmo valor que cada coluna.
    #
    # **Frequência, e não interseção.** Intersectar candidatos linha a linha
    # parece mais rigoroso e é pior: um único item cujo cadastro não foi achado
    # zera o conjunto, e a coluna passa a parecer derivada para sempre. Foi o
    # que escondeu o NCM e o código de barra na primeira versão desta
    # ferramenta, em 29/09/2026.
    candidatos: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter)
    vistos: collections.Counter[str] = collections.Counter()
    casadas = 0
    with open(csv, "rb") as arquivo:
        cabecalho = [limpar(c) for c in
                     arquivo.readline().decode("utf-8-sig", "replace").rstrip().split(";")]
        for bruto in arquivo:
            if casadas >= limite:
                break
            valores = [limpar(v) for v in
                       bruto.decode("utf-8-sig", "replace").rstrip("\r\n").split(";")]
            if len(valores) != len(cabecalho):
                continue
            linha = dict(zip(cabecalho, valores))
            if "C100/C170" not in linha.get("Registros", ""):
                continue
            item = itens.get((linha.get("Chave NF-e", ""), linha.get("Número Item", "")))
            if item is None:
                continue
            casadas += 1
            for coluna, valor in linha.items():
                # a linha só conta para a coluna quando ela diz alguma coisa:
                # com o zero no denominador, a coluna de PIS cheia de isentos
                # afundava o campo certo abaixo do corte
                if not informativo(valor):
                    continue
                vistos[coluna] += 1
                # do lado do SPED, zero e vazio casam com meia dúzia de campos
                # por acaso — e o acaso viraria candidato
                for campo, bruto_sped in item.items():
                    if informativo(bruto_sped) and formas(bruto_sped) & formas(valor):
                        candidatos[coluna][campo] += 1
    return cabecalho, candidatos, vistos, casadas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv")
    parser.add_argument("sped")
    parser.add_argument("--linhas", type=int, default=500)
    args = parser.parse_args()

    itens = ler_sped(args.sped)
    print(f"{len(itens):,} itens do C170 lidos do SPED".replace(",", "."))
    cabecalho, candidatos, vistos, casadas = inferir(args.csv, itens, args.linhas)
    print(f"{casadas} linhas do 047 casadas com o SPED\n")

    print(f"{'COLUNA DO 047':<28}{'LINHAS':>7}  DE ONDE VEM (e em quantas por cento delas)")
    for coluna in cabecalho:
        quantas = vistos.get(coluna, 0)
        if quantas == 0:
            print(f"{coluna:<28}{'—':>7}  sempre vazia na amostra")
            continue
        fortes = [(campo, n) for campo, n in candidatos[coluna].most_common(4)
                  if n / quantas >= 0.5]
        if not fortes:
            print(f"{coluna:<28}{quantas:>7}  DERIVADA — nenhum campo do SPED tem este valor")
        else:
            dito = ", ".join(f"{campo} ({100 * n // quantas}%)" for campo, n in fortes)
            print(f"{coluna:<28}{quantas:>7}  {dito}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Conferir a nossa exclusão do ICMS contra o gabarito do MA, linha a linha.

A terceira da família — `validar_037.py` e `validar_047.py` são as outras — e a
primeira que confere **conta**, e não cópia. As duas anteriores mediam se
sabíamos ler o arquivo; esta mede se sabemos calcular a restituição.

## O que muda por ser cálculo

**A Selic precisa do mês da restituição.** A acumulada de uma competência cresce
a cada mês que passa, então comparar exige saber até quando o gabarito acumulou.
Não dá para adivinhar do arquivo: passa-se `--ate aaaa-mm`. Errar esse mês faz
**todas** as linhas divergirem na Selic e nos totais — e é assim que tem de ser,
porque um relatório corrigido até o mês errado é um pedido de restituição errado.

**O número se compara como número.** O xlsx guarda `7.6` onde nós escrevemos
`7,60`; a comparação passa por `Decimal` nas colunas de valor e alíquota, e por
texto no resto.

    python tools/validar_903.py <pasta dos SPED> <parquet do gabarito> --ate 2026-09
    python tools/validar_903.py <pasta> <parquet> --ate 2026-09 --competencia 01/10/2024

**Não versiona dado de cliente.** Recebe os caminhos por argumento e imprime
nomes de coluna, contagens e, no modo detalhado, no máximo três exemplos por
coluna divergente.
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import sys
import time
from decimal import Decimal, InvalidOperation

import pyarrow.parquet as pq

from cat.infraestrutura.sped.exclusao_do_icms import colunas_da_exclusao, exclusoes_do_icms
from cat.infraestrutura.sped.leitor import codificacao_de

# a coluna do MA e o nosso campo, na ordem em que o MA exporta
MAPA: tuple[tuple[str, str], ...] = (
    ("CNPJ", "cnpj"),
    ("Período", "periodo"),
    ("Código Participante", "codigo_do_participante"),
    ("Situação", "situacao"),
    ("Número Documento", "numero_do_documento"),
    ("Chave NF-e", "chave"),
    ("Data Documento", "data_do_documento"),
    ("Data Entrada/Saída", "data_de_entrada_ou_saida"),
    ("Número Item", "numero_do_item"),
    ("Código Item", "codigo_do_item"),
    ("CFOP", "cfop"),
    ("CFOP Faturamento", "cfop_faturamento"),
    ("CST PIS/Cofins", "cst"),
    ("Vlr Item", "valor_do_item"),
    ("Vlr Desconto Item", "desconto_do_item"),
    ("Vlr Base Cálculo ICMS", "base_do_icms"),
    ("Alíquota ICMS", "aliquota_do_icms"),
    ("Vlr ICMS", "icms"),
    ("Vlr ICMS C/ Pagamento PIS/Cofins", "icms_com_pagamento"),
    ("Vlr Rateio Frete/Seguro/DA", "rateio"),
    ("Valor IPI", "ipi"),
    ("Vlr Base Cálculo PIS/Cofins", "base"),
    ("Vlr Base Cálculo Recalculada", "base_recalculada"),
    ("Vlr Diferença Base Recalculada", "diferenca_da_base_recalculada"),
    ("Vlr Base Cálculo - STF", "base_stf"),
    ("Vlr Diferença Base", "diferenca_da_base"),
    ("SELIC Acumulada", "selic_acumulada"),
    ("Alíquota PIS", "aliquota_do_pis"),
    ("Vlr PIS", "pis"),
    ("Vlr PIS - STF", "pis_stf"),
    ("Vlr Diferença PIS", "diferenca_do_pis"),
    ("Vlr SELIC S/PIS", "selic_sobre_o_pis"),
    ("Vlr Total PIS Recuperar", "total_do_pis_a_recuperar"),
    ("Alíquota Cofins", "aliquota_da_cofins"),
    ("Vlr Cofins", "cofins"),
    ("Vlr Cofins - STF", "cofins_stf"),
    ("Vlr Diferença Cofins", "diferenca_da_cofins"),
    ("Vlr SELIC S/Cofins", "selic_sobre_a_cofins"),
    ("Vlr Total Cofins Recuperar", "total_da_cofins_a_recuperar"),
    ("Vlr Total Recuperar Atualizado", "total_a_recuperar_atualizado"),
)

COLUNAS_DO_MA = tuple(coluna for coluna, _ in MAPA)
NOSSAS = tuple(campo for _, campo in MAPA)

assert set(NOSSAS) == set(colunas_da_exclusao()), (
    "o mapa e o dataclass discordam: "
    f"{set(NOSSAS) ^ set(colunas_da_exclusao())}")

# tudo o que é número. Fora daqui a comparação é de texto — código de item, CST
# e CFOP têm zero à esquerda que significa coisa
TEXTOS = frozenset({
    "cnpj", "periodo", "codigo_do_participante", "situacao", "numero_do_documento",
    "chave", "data_do_documento", "data_de_entrada_ou_saida", "numero_do_item",
    "codigo_do_item", "cfop", "cfop_faturamento", "cst",
})


def numero(bruto: str) -> Decimal | None:
    texto = (bruto or "").strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def comparavel(campo: str, valor: str) -> str:
    if campo in TEXTOS:
        return (valor or "").strip()
    n = numero(valor)
    return "" if n is None else format(n.normalize(), "f")


def linhas_do_ma(parquet: str, competencia: str | None):
    tabela = pq.read_table(parquet)
    faltam = set(COLUNAS_DO_MA) - set(tabela.column_names)
    if faltam:
        raise SystemExit(f"o parquet do gabarito não tem: {sorted(faltam)}")
    colunas = [tabela.column(nome).to_pylist() for nome in COLUNAS_DO_MA]
    onde = COLUNAS_DO_MA.index("Período")
    for i in range(tabela.num_rows):
        if competencia is not None and colunas[onde][i] != competencia:
            continue
        yield tuple(comparavel(NOSSAS[j], colunas[j][i] or "")
                    for j in range(len(COLUNAS_DO_MA)))


def selic_do_gabarito(parquet: str) -> dict[str, Decimal]:
    """A Selic acumulada que o gabarito usou, por competência.

    A série de `tab_selic` termina onde o gabarito termina — os últimos onze
    meses vêm nele como um número só, que não se separa. Sem isto, **todas** as
    linhas divergiriam na Selic e nos totais, e a conferência não diria nada
    sobre o resto do cálculo, que é o que importa medir agora.

    Quando a série estiver completa, esta função sai e a tabela responde.
    """
    tabela = pq.read_table(parquet, columns=["Período", "SELIC Acumulada"])
    por: dict[str, Decimal] = {}
    for p, s in zip(tabela.column("Período").to_pylist(),
                    tabela.column("SELIC Acumulada").to_pylist()):
        dia, mes, ano = p.split("/")
        por[f"{ano}-{mes}"] = Decimal(s)
    return por


def nossas_linhas(pasta: str, ate: str, competencia: str | None,
                  acumulada: dict[str, Decimal] | None = None):
    arquivos = ([pasta] if os.path.isfile(pasta)
                else sorted(glob.glob(os.path.join(pasta, "*.txt"))))
    if not arquivos:
        raise SystemExit(f"nenhum SPED em {pasta}")
    for caminho in arquivos:
        for linha in exclusoes_do_icms(caminho, codificacao_de(caminho), ate, acumulada):
            valores = linha.como_dicionario()
            if competencia is not None and valores["periodo"] != competencia:
                continue
            yield tuple(comparavel(campo, valores[campo]) for campo in NOSSAS)


def conferir_tudo(pasta_sped: str, parquet: str, ate: str,
                  acumulada: dict[str, Decimal] | None = None) -> int:
    print("lendo o gabarito…", flush=True)
    inicio = time.time()
    do_ma: collections.Counter[tuple[str, int]] = collections.Counter()
    for linha in linhas_do_ma(parquet, None):
        do_ma[(linha[1], hash(linha))] += 1
    print(f"  {sum(do_ma.values()):,} linhas em {time.time() - inicio:.0f}s".replace(",", "."))

    print("lendo os SPED…", flush=True)
    inicio = time.time()
    nossos: collections.Counter[tuple[str, int]] = collections.Counter()
    for linha in nossas_linhas(pasta_sped, ate, None, acumulada):
        nossos[(linha[1], hash(linha))] += 1
    print(f"  {sum(nossos.values()):,} linhas em {time.time() - inicio:.0f}s".replace(",", "."))

    faltando = do_ma - nossos
    sobrando = nossos - do_ma
    iguais = sum((do_ma & nossos).values())
    total = sum(do_ma.values())
    print(f"\n{'IGUAIS':<12}{iguais:>12,}  {100 * iguais / max(total, 1):.4f}% do gabarito"
          .replace(",", "."))
    print(f"{'SÓ DO MA':<12}{sum(faltando.values()):>12,}  o gabarito tem e nós não"
          .replace(",", "."))
    print(f"{'SÓ NOSSAS':<12}{sum(sobrando.values()):>12,}  geramos a mais".replace(",", "."))

    # **as duas colunas, e não só a das que faltam.** Numa conferência de cópia
    # os dois lados têm sempre a mesma contagem, e olhar uma bastava; num
    # cálculo com filtro, **sobrar** é o modo de errar mais provável — e foi
    # assim que 9.184 linhas a mais passaram por "cinquenta e poucas
    # divergências" numa leitura apressada desta saída.
    faltam: collections.Counter[str] = collections.Counter()
    sobram: collections.Counter[str] = collections.Counter()
    for (competencia, _), quantas in faltando.items():
        faltam[competencia] += quantas
    for (competencia, _), quantas in sobrando.items():
        sobram[competencia] += quantas
    competencias = sorted(set(faltam) | set(sobram),
                          key=lambda c: -(faltam[c] + sobram[c]))
    if competencias:
        print(f"\nCOMPETÊNCIAS COM DIFERENÇA ({len(competencias)} de "
              f"{len({c for c, _ in do_ma})}):")
        print(f"  {'competência':<14}{'faltam':>8}{'sobram':>9}")
        for competencia in competencias[:20]:
            print(f"  {competencia:<14}{faltam[competencia]:>8,}{sobram[competencia]:>9,}"
                  .replace(",", "."))
        if len(competencias) > 20:
            print(f"  … e mais {len(competencias) - 20}")
        print("\nRode --competencia numa delas para saber qual coluna.")
    else:
        print("\nBate inteiro.")
    return 0 if not faltando and not sobrando else 1


def conferir_competencia(pasta_sped: str, parquet: str, ate: str, competencia: str,
                         acumulada: dict[str, Decimal] | None = None) -> int:
    do_ma = collections.Counter(linhas_do_ma(parquet, competencia))
    nossas = collections.Counter(nossas_linhas(pasta_sped, ate, competencia, acumulada))
    print(f"{competencia}: gabarito {sum(do_ma.values()):,} linhas, "
          f"nós {sum(nossas.values()):,}".replace(",", "."))
    iguais = sum((do_ma & nossas).values())
    print(f"iguais: {iguais:,}".replace(",", "."))
    sobrando_do_ma = do_ma - nossas
    sobrando_nossas = nossas - do_ma
    if not sobrando_do_ma and not sobrando_nossas:
        print("bate inteiro.")
        return 0

    def chave(l: tuple[str, ...]) -> tuple[str, ...]:
        # documento e item: o par é o mesmo item da mesma nota
        return (l[0], l[5] or l[4], l[8], l[9], l[10])

    por_chave: dict[tuple[str, ...], list[tuple[str, ...]]] = collections.defaultdict(list)
    for linha in sobrando_do_ma.elements():
        por_chave[chave(linha)].append(linha)

    colunas_ruins: collections.Counter[str] = collections.Counter()
    exemplos: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    sem_par = 0
    for nossa in sobrando_nossas.elements():
        candidatas = por_chave.get(chave(nossa))
        if not candidatas:
            sem_par += 1
            continue
        dela = candidatas.pop()
        for i, (minha, sua) in enumerate(zip(nossa, dela)):
            if minha != sua:
                colunas_ruins[NOSSAS[i]] += 1
                if len(exemplos[NOSSAS[i]]) < 3:
                    exemplos[NOSSAS[i]].append((minha, sua))

    print(f"\nlinhas nossas sem par no gabarito: {sem_par:,}".replace(",", "."))
    print(f"linhas do gabarito sem par nossa:  "
          f"{sum(len(v) for v in por_chave.values()):,}".replace(",", "."))
    if colunas_ruins:
        print("\nCOLUNAS QUE DIVERGEM:")
        for coluna, quantas in colunas_ruins.most_common():
            print(f"  {coluna:<34}{quantas:>9,}".replace(",", "."))
            for nosso, dele in exemplos[coluna]:
                print(f"      nosso={nosso!r}  MA={dele!r}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sped", help="pasta dos SPED — ou um arquivo só")
    parser.add_argument("gabarito", help="parquet do gabarito do 903")
    parser.add_argument("--ate", required=True,
                        help="aaaa-mm: o mês da restituição, até onde a Selic acumula")
    parser.add_argument("--competencia", help="dd/mm/aaaa — confere só esta, e diz qual coluna")
    parser.add_argument("--selic-do-gabarito", action="store_true",
                        help="usa a Selic acumulada do próprio gabarito, para conferir o "
                             "cálculo sem depender da série de tab_selic")
    args = parser.parse_args()
    acumulada = selic_do_gabarito(args.gabarito) if args.selic_do_gabarito else None
    if args.competencia:
        return conferir_competencia(args.sped, args.gabarito, args.ate, args.competencia,
                                    acumulada)
    return conferir_tudo(args.sped, args.gabarito, args.ate, acumulada)


if __name__ == "__main__":
    sys.exit(main())

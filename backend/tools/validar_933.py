"""Conferir a nossa exclusão do ISS contra o gabarito do MA, linha a linha.

A quinta da família, e a menor: 33 linhas na base de referência, das quais
**uma** tem ISS. O `VL_ISS` do registro A100 é facultativo, e quando vem vazio
o valor está na NFS-e, que este motor ainda não lê — a linha sai com exclusão
zero, visível em vez de silenciosa.

Uma linha só com ISS parece pouco para conferir, e não é: é ela que exerce a
conta inteira — rateio, base STF, diferença, Selic e total. As outras 32 exercem
o outro caminho, o de não haver o que excluir, que é o que acontece na maioria
das notas de serviço deste país.

    python tools/validar_933.py <pasta dos SPED> <parquet do gabarito> --ate 2026-09
    python tools/validar_933.py <pasta> <parquet> --ate 2026-09 --competencia 01/09/2024

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

from cat.infraestrutura.sped.exclusao_do_iss import (
    colunas_da_exclusao_iss,
    exclusoes_do_iss,
)
from cat.infraestrutura.sped.leitor import codificacao_de

# a coluna do MA e o nosso campo, na ordem em que o MA exporta
MAPA: tuple[tuple[str, str], ...] = (
    ("CNPJ", "cnpj"),
    ("Período", "periodo"),
    ("Situação", "situacao"),
    ("Número Documento", "numero_do_documento"),
    ("Chave/Código Verificação NFS-e", "chave"),
    ("Data Documento", "data_do_documento"),
    ("Data Execução Serviço", "data_de_execucao_do_servico"),
    ("CST PIS/Cofins", "cst"),
    ("Vlr Documento", "valor_do_documento"),
    ("Vlr Desconto Documento", "desconto_do_documento"),
    ("Vlr Item", "valor_do_item"),
    ("Vlr Desconto Item", "desconto_do_item"),
    ("Percentual Rateio", "percentual_do_rateio"),
    ("Vlr ISS - Rateio", "iss_rateado"),
    ("Vlr Base Cálculo PIS/Cofins", "base"),
    ("Vlr Base Cálculo - Recalculada", "base_recalculada"),
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

assert set(NOSSAS) == set(colunas_da_exclusao_iss()), (
    "o mapa e o dataclass discordam: "
    f"{set(NOSSAS) ^ set(colunas_da_exclusao_iss())}")

# tudo o que é número. Fora daqui a comparação é de texto — código de item, CST,
# CFOP e EAN têm zero à esquerda que significa coisa
TEXTOS = frozenset({
    "cnpj", "periodo", "situacao", "numero_do_documento", "chave",
    "data_do_documento", "data_de_execucao_do_servico", "cst",
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

    Serve para conferir **o cálculo** sem depender da série — como no 903.
    Depois que a série do banco passou a cobrir o período, deixou de ser
    necessário; fica porque é a primeira coisa a ligar quando a Selic muda e a
    conferência inteira vermelha.
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
        for linha in exclusoes_do_iss(caminho, codificacao_de(caminho), ate, acumulada):
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

    indice = {campo: i for i, campo in enumerate(NOSSAS)}

    def chave(l: tuple[str, ...]) -> tuple[str, ...]:
        # a nota de serviço: um documento, um item
        return (l[indice["cnpj"]], l[indice["periodo"]],
                l[indice["chave"]] or l[indice["numero_do_documento"]])

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
    parser.add_argument("gabarito", help="parquet do gabarito do 933")
    parser.add_argument("--ate", required=True,
                        help="aaaa-mm: o mês da restituição, até onde a Selic acumula")
    parser.add_argument("--competencia", help="dd/mm/aaaa — confere só esta, e diz qual coluna")
    parser.add_argument("--selic-do-gabarito", action="store_true",
                        help="usa a Selic acumulada do próprio gabarito, para conferir o "
                             "cálculo sem depender da série")
    args = parser.parse_args()
    acumulada = selic_do_gabarito(args.gabarito) if args.selic_do_gabarito else None
    if args.competencia:
        return conferir_competencia(args.sped, args.gabarito, args.ate, args.competencia,
                                    acumulada)
    return conferir_tudo(args.sped, args.gabarito, args.ate, acumulada)


if __name__ == "__main__":
    sys.exit(main())

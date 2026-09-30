"""O mapa de valores: o que geramos contra o que o arquivo base traz.

Os conferidores (`validar_903.py`, `validar_839.py`, `validar_933.py`) comparam
**linha a linha**, e é assim que um defeito é encontrado. Este comando faz a
outra pergunta, a que se responde antes de entregar: **os totais batem?**

## Por que as duas coisas, e não uma

Conferência linha a linha que fecha 100% já garante o total — mas ela exige o
gabarito inteiro e leva minutos. O mapa de valores cabe numa página, mostra a
competência em que o dinheiro está, e é o que se põe ao lado do relatório do
escritório anterior numa reunião. Uma serve ao desenvolvedor, a outra a quem
assina.

E há um caso em que só o mapa responde: quando o gabarito **não existe**. Um
cliente novo não tem relatório anterior nenhum, e aí o mapa vira o retrato do
que produzimos — total por tese, por competência, e o que prescreveu.

    # com gabarito: compara
    python tools/mapear_valores.py <pasta dos SPED> --ate 2026-09 \\
        --903 <parquet> --839 <parquet> --933 <parquet>

    # sem gabarito: só retrata
    python tools/mapear_valores.py <pasta dos SPED> --ate 2026-09

**Não versiona dado de cliente.** Recebe os caminhos por argumento e imprime
totais — nunca uma linha de nota fiscal.
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import pyarrow.parquet as pq

from cat.infraestrutura.aliquotas import excecoes_de
from cat.infraestrutura.analitico import (
    exclusao_do_icms,
    exclusao_do_icms_st,
    exclusao_do_iss,
)
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.selic import serie

ZERO = Decimal(0)


@dataclass(frozen=True)
class Tese:
    """Uma exclusão, e onde o dinheiro dela mora no arquivo base."""

    codigo: str
    nome: str
    # a coluna do gabarito com o total a recuperar. É a mesma nas três, e é por
    # ela que o mapa compara: o número que o cliente vê no fim
    total_do_ma: str = "Vlr Total Recuperar Atualizado"


TESES = (
    Tese("903", "ICMS fora da base"),
    Tese("839", "ICMS-ST fora da base"),
    Tese("933", "ISS fora da base"),
)


def _d(valor) -> Decimal:
    texto = str(valor or "").strip()
    if not texto:
        return ZERO
    try:
        return Decimal(texto.replace(",", ".") if "," in texto else texto)
    except InvalidOperation:
        return ZERO


def reais(valor: Decimal) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def do_gabarito(parquet: str, tese: Tese) -> tuple[int, dict[str, Decimal], Decimal]:
    """Linhas, total por competência e total geral do arquivo base."""
    tabela = pq.read_table(parquet, columns=["Período", tese.total_do_ma])
    por: collections.Counter[str] = collections.Counter()
    for periodo, total in zip(tabela.column("Período").to_pylist(),
                              tabela.column(tese.total_do_ma).to_pylist()):
        por[str(periodo)] += _d(total)
    return tabela.num_rows, dict(por), sum(por.values(), ZERO)


def nossos(resumo) -> tuple[int, dict[str, Decimal], Decimal]:
    """O mesmo, do nosso resumo. O total soma o prescrito, como o MA faz."""
    por = {
        f"01/{c['competencia'][5:]}/{c['competencia'][:4]}": _d(c["total_atualizado"])
        for c in resumo.por_competencia
    }
    return resumo.linhas, por, sum(por.values(), ZERO)


def apurar_tudo(pasta: str, ate: str, referencia: date, destino: str) -> dict:
    """Roda as três teses sobre os mesmos SPED, com a Selic e as alíquotas do banco."""
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.txt")))
    if not arquivos:
        raise SystemExit(f"nenhum SPED em {pasta}")
    print(f"lendo {len(arquivos)} arquivos…", flush=True)

    mensal = serie(ate)
    resultados = {}
    resultados["903"] = exclusao_do_icms.apurar(
        arquivos, destino, ate=ate, referencia=referencia, mensal=mensal)

    with Sessao() as sessao:
        excecoes = excecoes_de(sessao, resultados["903"].estabelecimentos)
    print(f"  Selic: {len(mensal)} meses · alíquotas de exceção: {len(excecoes)}",
          flush=True)

    resultados["839"] = exclusao_do_icms_st.apurar(
        arquivos, destino, ate=ate, referencia=referencia, mensal=mensal,
        excecoes=excecoes)
    resultados["933"] = exclusao_do_iss.apurar(
        arquivos, destino, ate=ate, referencia=referencia, mensal=mensal)
    return resultados


def imprimir(tese: Tese, resumo, parquet: str | None) -> bool:
    """Uma tese no mapa. Devolve se ela fecha — ou True quando não há com quê."""
    linhas, por_nosso, total_nosso = nossos(resumo)
    print(f"\n{'-' * 78}")
    print(f"{tese.codigo} — {tese.nome}")
    print(f"{'-' * 78}")

    if parquet is None:
        print(f"  {'linhas':<28}{linhas:>14,}".replace(",", "."))
        print(f"  {'a recuperar, no prazo':<28}{reais(_d(resumo.total_atualizado)):>14}")
        print(f"  {'prescrito, fora do total':<28}{reais(_d(resumo.prescrito)):>14}")
        print(f"  {'TOTAL GERADO':<28}{reais(total_nosso):>14}")
        print("\n  (sem arquivo base: retrato, não conferência)")
        return True

    linhas_ma, por_ma, total_ma = do_gabarito(parquet, tese)
    fecha = linhas == linhas_ma and total_nosso == total_ma
    print(f"  {'':<28}{'nosso':>16}{'arquivo base':>16}{'diferença':>14}")
    print(f"  {'linhas':<28}{linhas:>16,}{linhas_ma:>16,}"
          f"{linhas - linhas_ma:>14,}".replace(",", "."))
    print(f"  {'total a recuperar':<28}{reais(total_nosso):>16}{reais(total_ma):>16}"
          f"{reais(total_nosso - total_ma):>14}")
    print(f"  {'  — no prazo':<28}{reais(_d(resumo.total_atualizado)):>16}")
    print(f"  {'  — prescrito':<28}{reais(_d(resumo.prescrito)):>16}"
          f"{'':>16}{'(o MA soma junto)':>14}")

    diferentes = sorted(
        (c for c in set(por_nosso) | set(por_ma)
         if por_nosso.get(c, ZERO) != por_ma.get(c, ZERO)),
        key=lambda c: (c[6:], c[3:5]))
    if diferentes:
        print(f"\n  COMPETÊNCIAS QUE NÃO FECHAM ({len(diferentes)}):")
        print(f"    {'competência':<14}{'nosso':>16}{'arquivo base':>16}{'diferença':>14}")
        for c in diferentes[:20]:
            n, m = por_nosso.get(c, ZERO), por_ma.get(c, ZERO)
            print(f"    {c:<14}{reais(n):>16}{reais(m):>16}{reais(n - m):>14}")
        if len(diferentes) > 20:
            print(f"    … e mais {len(diferentes) - 20}")
    else:
        print(f"\n  as {len(por_nosso)} competências fecham uma a uma.")
    return fecha


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sped", help="pasta dos SPED")
    parser.add_argument("--ate", required=True,
                        help="aaaa-mm: o mês da restituição, até onde a Selic acumula")
    parser.add_argument("--referencia", help="aaaa-mm-dd: a data do pedido, que decide "
                                             "o que prescreveu. Padrão: hoje")
    for tese in TESES:
        parser.add_argument(f"--{tese.codigo}", help=f"parquet do gabarito do {tese.codigo}")
    parser.add_argument("--destino", help="onde gravar os parquets. Padrão: pasta temporária")
    args = parser.parse_args()

    referencia = (date.fromisoformat(args.referencia) if args.referencia
                  else date.today())
    destino = args.destino or os.path.join(tempfile.gettempdir(), "cat-mapa-de-valores")

    resultados = apurar_tudo(args.sped, args.ate, referencia, destino)

    print(f"\n{'=' * 78}")
    print(f"MAPA DE VALORES · corrigido até {args.ate[5:]}/{args.ate[:4]} · "
          f"prescrição contada de {referencia.strftime('%d/%m/%Y')}")
    print(f"{'=' * 78}")

    fecham = []
    for tese in TESES:
        fecham.append(imprimir(tese, resultados[tese.codigo],
                               getattr(args, tese.codigo)))

    total = sum((_d(r.total_atualizado) for r in resultados.values()), ZERO)
    prescrito = sum((_d(r.prescrito) for r in resultados.values()), ZERO)
    print(f"\n{'=' * 78}")
    print(f"  {'AS TRÊS TESES, NO PRAZO':<34}{reais(total):>16}")
    print(f"  {'prescrito, mostrado e não somado':<34}{reais(prescrito):>16}")
    print(f"{'=' * 78}")

    if all(fecham):
        print("\nTudo o que tinha arquivo base para comparar fechou.")
        return 0
    print("\nHá tese que não fecha. Rode o conferidor dela para achar a linha.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

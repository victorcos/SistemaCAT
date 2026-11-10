"""Segunda passada do teste de custo (①), com o preço sem transferências e a métrica custo × custo.

Uso: python medir_custo_v2.py <pasta_de_movimentos> <csv_da_primeira_medicao>
"""
from __future__ import annotations

import csv
import logging
import sys
from collections import Counter

import duckdb

from cat.dominio.icms.cat42.enquadramento import CFOP_DEVOLUCAO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("medir_custo_v2")

# transferência entre estabelecimentos: sai a preço de custo, não é venda
TRANSFERENCIA = ("152", "409", "151", "408", "155", "156", "557", "552")
FAIXA_PRECO = (0.30, 1.20)
FAIXA_CUSTO = (0.50, 2.00)


def faixa(r, f):
    if r is None:
        return "sem_dado"
    return "coerente" if f[0] <= r <= f[1] else "incoerente"


def main(pasta: str, csv_pares: str) -> None:
    pasta = pasta.replace("\\", "/")
    devol = ",".join(f"'{c}'" for c in CFOP_DEVOLUCAO)
    transf = " OR ".join(f"cfop LIKE '_{t}'" for t in TRANSFERENCIA)
    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    dados = {(r[0], r[1]): r[2:] for r in con.execute(f"""
        SELECT cnpj, codigo,
          sum(valor - coalesce(desconto,0)) FILTER (WHERE operacao='entrada' AND cfop NOT IN ({devol})),
          sum(quantidade) FILTER (WHERE operacao='entrada' AND cfop NOT IN ({devol})),
          sum(valor - coalesce(desconto,0)) FILTER (WHERE operacao='saida' AND cfop NOT IN ({devol}) AND NOT ({transf})),
          sum(quantidade) FILTER (WHERE operacao='saida' AND cfop NOT IN ({devol}) AND NOT ({transf}))
        FROM read_parquet('{pasta}/movimentos.parquet') GROUP BY 1, 2""").fetchall()}
    log.info("agregado: %d códigos", len(dados))

    cont, razoes = Counter(), {"preco": [], "custo": []}
    with open(csv_pares, encoding="utf-8-sig") as f:
        for p in csv.DictReader(f, delimiter=";"):
            fator = float(p["fator"])
            o = dados.get((p["cnpj"], p["origem"]), (None,) * 4)
            d = dados.get((p["cnpj"], p["destino"]), (None,) * 4)
            co = o[0] / o[1] if o[0] and o[1] else None
            pv = d[2] / d[3] if d[2] and d[3] else None
            cd = d[0] / d[1] if d[0] and d[1] else None
            r_preco = float(co) / fator / float(pv) if co and pv else None
            r_custo = float(co) / fator / float(cd) if co and cd else None
            sp, sc = faixa(r_preco, FAIXA_PRECO), faixa(r_custo, FAIXA_CUSTO)
            # o que a regra faria: custo × custo quando há, senão o preço de venda
            final = sc if sc != "sem_dado" else sp
            m = p["motivo"]
            cont[("preco_sem_transf", m, sp)] += 1
            cont[("custo_x_custo", m, sc)] += 1
            cont[("combinado", m, final)] += 1
            if p["vale_sozinho"] == "True":
                cont[("sozinho", "total")] += 1
                cont[("sozinho", "combinado", final)] += 1
                if final == "incoerente" and p["ncm_diferente"] == "True":
                    cont[("sozinho", "incoerente_e_ncm_diferente")] += 1
            if "gtin" in m:
                if r_preco is not None:
                    razoes["preco"].append(r_preco)
                if r_custo is not None:
                    razoes["custo"].append(r_custo)

    for k in sorted(cont, key=str):
        print("\t".join(map(str, k)), cont[k], sep="\t")
    for nome, v in razoes.items():
        v.sort()
        n = len(v)
        if n:
            q = lambda x: v[min(n - 1, int(x * n))]
            print(f"razao GTIN {nome}: n={n} p05={q(.05):.2f} p25={q(.25):.2f} p50={q(.5):.2f} "
                  f"p75={q(.75):.2f} p95={q(.95):.2f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

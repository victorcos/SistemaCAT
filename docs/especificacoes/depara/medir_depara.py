"""Mede, sem gravar nada, o efeito dos reforços ①③④ do de-para num trabalho real.

Uso: python medir_depara.py <pasta_de_movimentos> <saida.csv>
Roda com o venv do backend do SistemaCAT (importa `cat`).
"""
from __future__ import annotations

import csv
import logging
import sys
import time
from collections import Counter
from decimal import Decimal

import duckdb

from cat.dominio.depara.candidatos import propor, vale_sozinho
from cat.dominio.icms.cat42.enquadramento import CFOP_DEVOLUCAO
from cat.infraestrutura.analitico.depara import itens_para_casar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("medir_depara")

FAIXA = (0.30, 1.20)


def main(pasta: str, saida: str) -> None:
    t0 = time.time()
    pasta = pasta.replace("\\", "/")
    itens = itens_para_casar(pasta)
    log.info("itens lidos: %d estabelecimentos, %d códigos (%.0fs)",
             len(itens), sum(len(v) for v in itens.values()), time.time() - t0)

    devol = ",".join(f"'{c}'" for c in CFOP_DEVOLUCAO)
    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    agg = con.execute(f"""
        SELECT cnpj, codigo,
               sum(valor - coalesce(desconto, 0)) FILTER (WHERE operacao='entrada' AND cfop NOT IN ({devol})) ve,
               sum(quantidade) FILTER (WHERE operacao='entrada' AND cfop NOT IN ({devol})) qe,
               sum(valor - coalesce(desconto, 0)) FILTER (WHERE operacao='saida' AND cfop NOT IN ({devol})) vs,
               sum(quantidade) FILTER (WHERE operacao='saida' AND cfop NOT IN ({devol})) qs,
               mode(nullif(cest, '')) cest, mode(nullif(cest_xml, '')) cest_xml
        FROM read_parquet('{pasta}/movimentos.parquet') GROUP BY 1, 2
    """).fetchall()
    dados = {(r[0], r[1]): r[2:] for r in agg}
    log.info("agregado de custo/preço/CEST: %d códigos (%.0fs)", len(dados), time.time() - t0)

    linhas, cont = [], Counter()
    razoes_gtin = []
    for cnpj, lista in itens.items():
        ncm = {i.codigo: i.ncm for i in lista}
        for par in propor(lista):
            motivo = "+".join(m.value for m in par.motivos)
            sozinho = vale_sozinho(par)
            o = dados.get((cnpj, par.origem), (None,) * 6)
            d = dados.get((cnpj, par.destino), (None,) * 6)
            custo = (o[0] / o[1]) if o[0] and o[1] else None
            preco = (d[2] / d[3]) if d[2] and d[3] else None
            if custo is not None and preco:
                razao = float(Decimal(custo) / par.fator / Decimal(preco))
                selo = "coerente" if FAIXA[0] <= razao <= FAIXA[1] else "incoerente"
            else:
                razao, selo = None, "sem_preco"
            cest_o, cest_d = (o[4] or o[5]), (d[4] or d[5])
            cest_dif = bool(cest_o and cest_d and cest_o != cest_d)
            ncm_dif = bool(ncm.get(par.origem) and ncm.get(par.destino)
                           and ncm[par.origem] != ncm[par.destino])

            cont[("pares", motivo)] += 1
            cont[("custo", motivo, selo)] += 1
            if sozinho:
                cont[("sozinho", "total")] += 1
                if selo == "incoerente":
                    cont[("sozinho", "cai_por_custo")] += 1
                if cest_dif:
                    cont[("sozinho", "cai_por_cest")] += 1
            if "gtin" in motivo and razao is not None:
                razoes_gtin.append(razao)
            if cest_dif:
                cont[("cest_dif", motivo)] += 1
            if ncm_dif:
                cont[("ncm_dif", motivo)] += 1
            linhas.append([cnpj, par.origem, par.destino, str(par.fator), motivo, par.confianca.value,
                           sozinho, selo, f"{razao:.3f}" if razao is not None else "",
                           cest_o or "", cest_d or "", cest_dif,
                           ncm.get(par.origem, ""), ncm.get(par.destino, ""), ncm_dif])

    with open(saida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["cnpj", "origem", "destino", "fator", "motivo", "confianca", "vale_sozinho",
                    "custo", "razao_custo_preco", "cest_origem", "cest_destino", "cest_diferente",
                    "ncm_origem", "ncm_destino", "ncm_diferente"])
        w.writerows(linhas)

    for k in sorted(cont, key=str):
        print("\t".join(map(str, k)), cont[k], sep="\t")
    if razoes_gtin:
        razoes_gtin.sort()
        n = len(razoes_gtin)
        q = lambda p: razoes_gtin[min(n - 1, int(p * n))]
        print(f"razao GTIN: n={n} p05={q(.05):.2f} p25={q(.25):.2f} p50={q(.5):.2f} "
              f"p75={q(.75):.2f} p95={q(.95):.2f}")
    log.info("fim: %d pares, %.0fs, csv em %s", len(linhas), time.time() - t0, saida)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

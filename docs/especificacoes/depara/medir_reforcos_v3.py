"""Mede, sem gravar nada, as regras novas ⑥–⑩ do de-para e compara com a medição anterior (①③④).

Uso: python medir_reforcos_v3.py <pasta_de_movimentos> <csv_da_primeira_medicao> <saida.csv>
Roda com o venv do backend do SistemaCAT (importa `cat`).

Regras medidas:
  ⑥ GTIN contaminado: o GTIN do par está, no mesmo CNPJ, em códigos de capítulos de NCM diferentes
  ⑦ convivência: origem e destino vendem (ou compram) nas mesmas semanas
  ⑧ gramatura: peso/volume na descrição diferente, sem bater com o fator
  ⑨ unidade: família de unidade diferente com fator 1
  ⑩ XML do fornecedor: o cEAN da nota confirma ou contradiz o GTIN do 0200
  higiene: GTIN com dígito inválido, de balança (prefixo 2) ou zerado
"""
from __future__ import annotations

import csv
import logging
import re
import sys
import time
from collections import Counter, defaultdict

import duckdb

from cat.dominio.depara.candidatos import gtin_valido as gtin_valido_sistema
from cat.dominio.icms.cat42.enquadramento import CFOP_DEVOLUCAO
from cat.infraestrutura.analitico.depara import itens_para_casar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("medir_reforcos_v3")

TRANSFERENCIA = ("152", "409", "151", "408", "155", "156", "557", "552")
FAIXA_PRECO = (0.30, 1.20)
FAIXA_CUSTO = (0.50, 2.00)
SEMANAS_JUNTAS = 3  # ⑦: a partir de quantas semanas em comum os dois "convivem"

FAMILIA_UNIDADE = {
    "UN": "un", "UND": "un", "UNID": "un", "PC": "un", "PÇ": "un", "PA": "un", "BJ": "un", "MC": "un",
    "KG": "kg", "G": "kg", "GR": "kg",
    "L": "l", "LT": "l", "ML": "l",
    "CX": "emb", "FD": "emb", "PT": "emb", "PCT": "emb", "DZ": "emb", "SC": "emb", "CT": "emb",
}
# ⑧: número + unidade de massa/volume na descrição
RE_MEDIDA = re.compile(r"(\d+(?:[.,]\d+)?)\s*(KG|KGS|GR|GRS|G|MG|LT|LTS|L|ML)\b")
PARA_BASE = {"KG": ("massa", 1000), "KGS": ("massa", 1000), "G": ("massa", 1), "GR": ("massa", 1),
             "GRS": ("massa", 1), "MG": ("massa", 0.001), "L": ("vol", 1000), "LT": ("vol", 1000),
             "LTS": ("vol", 1000), "ML": ("vol", 1)}


def gtin_valido(g: str) -> bool:
    if not g or not g.isdigit() or len(g) not in (8, 12, 13, 14) or set(g) == {"0"}:
        return False
    d = [int(c) for c in g]
    soma = sum(x * (3 if i % 2 == 0 else 1) for i, x in enumerate(reversed(d[:-1])))
    return (10 - soma % 10) % 10 == d[-1]


def higiene(g: str) -> str | None:
    if not g or set(g) == {"0"}:
        return "zerado"
    if not gtin_valido(g):
        return "digito_invalido"
    if len(g) == 13 and g.startswith("2") or len(g) == 12 and g.startswith("2"):
        return "balanca"
    return None


def medidas(desc: str) -> dict[str, float]:
    out = {}
    for num, un in RE_MEDIDA.findall((desc or "").upper()):
        tipo, mult = PARA_BASE[un]
        out.setdefault(tipo, float(num.replace(",", ".")) * mult)
    return out


def faixa(r, f):
    if r is None:
        return "sem_dado"
    return "coerente" if f[0] <= r <= f[1] else "incoerente"


def main(pasta: str, csv_pares: str, saida: str) -> None:
    t0 = time.time()
    pasta = pasta.replace("\\", "/")
    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    devol = ",".join(f"'{c}'" for c in CFOP_DEVOLUCAO)
    transf = " OR ".join(f"cfop LIKE '_{t}'" for t in TRANSFERENCIA)

    pares = list(csv.DictReader(open(csv_pares, encoding="utf-8-sig"), delimiter=";"))
    cods = {(p["cnpj"], c) for p in pares for c in (p["origem"], p["destino"])}
    cnpjs = sorted({c for c, _ in cods})
    lista_cnpj = ",".join(f"'{c}'" for c in cnpjs)
    log.info("pares: %d, códigos envolvidos: %d, CNPJs: %d", len(pares), len(cods), len(cnpjs))

    # cadastro 0200 (descrição, unidade) e, do jeito do sistema, NCM e GTINs (0200 + XML, sem zero à esquerda)
    cad = {}
    for cnpj, cod, desc, un, ncm in con.execute(f"""
        SELECT cnpj, codigo, descricao, unidade, ncm
        FROM read_parquet('{pasta}/itens.parquet') WHERE cnpj IN ({lista_cnpj})
        ORDER BY competencia""").fetchall():
        cad[(cnpj, cod)] = (desc, un, ncm)
    gtins_do_cod, xml_do_cod, ncm_do_cod = {}, {}, {}
    for cnpj, lista in itens_para_casar(pasta).items():
        if cnpj not in cnpjs:
            continue
        for i in lista:
            gtins_do_cod[(cnpj, i.codigo)] = {g.strip().lstrip("0") for g in i.gtins | i.gtins_do_xml
                                              if gtin_valido_sistema(g)}
            xml_do_cod[(cnpj, i.codigo)] = {g.strip().lstrip("0") for g in i.gtins_do_xml if gtin_valido_sistema(g)}
            ncm_do_cod[(cnpj, i.codigo)] = i.ncm or ""
    # ⑥ capítulos de NCM e códigos por GTIN, por CNPJ
    caps_do_gtin, cods_do_gtin = defaultdict(set), defaultdict(set)
    for (cnpj, cod), gs in gtins_do_cod.items():
        ncm = ncm_do_cod.get((cnpj, cod), "")
        for g in gs:
            cods_do_gtin[(cnpj, g)].add(cod)
            if len(ncm) >= 2 and ncm != "11111111":
                caps_do_gtin[(cnpj, g)].add(ncm[:2])
    log.info("cadastro lido: %d códigos (%.0fs)", len(cad), time.time() - t0)

    # ⑦ semanas com saída / entrada por código; custo e preço como na v2; ⑩ GTIN do XML
    semanas = defaultdict(lambda: (set(), set()))
    for cnpj, cod, sem_s, sem_e in con.execute(f"""
        SELECT cnpj, codigo,
          list(DISTINCT date_trunc('week', data)) FILTER (WHERE operacao='saida' AND cfop NOT IN ({devol})),
          list(DISTINCT date_trunc('week', data)) FILTER (WHERE operacao='entrada' AND cfop NOT IN ({devol}))
        FROM read_parquet('{pasta}/movimentos.parquet') WHERE cnpj IN ({lista_cnpj})
        GROUP BY 1, 2""").fetchall():
        if (cnpj, cod) in cods:
            semanas[(cnpj, cod)] = (set(sem_s or []), set(sem_e or []))
    precos = {(r[0], r[1]): r[2:] for r in con.execute(f"""
        SELECT cnpj, codigo,
          sum(valor - coalesce(desconto,0)) FILTER (WHERE operacao='entrada' AND cfop NOT IN ({devol})),
          sum(quantidade) FILTER (WHERE operacao='entrada' AND cfop NOT IN ({devol})),
          sum(valor - coalesce(desconto,0)) FILTER (WHERE operacao='saida' AND cfop NOT IN ({devol}) AND NOT ({transf})),
          sum(quantidade) FILTER (WHERE operacao='saida' AND cfop NOT IN ({devol}) AND NOT ({transf}))
        FROM read_parquet('{pasta}/movimentos.parquet') WHERE cnpj IN ({lista_cnpj}) GROUP BY 1, 2""").fetchall()}
    log.info("movimentos agregados (%.0fs)", time.time() - t0)

    cont = Counter()
    linhas = []
    for p in pares:
        cnpj, o, d, m = p["cnpj"], p["origem"], p["destino"], p["motivo"]
        fator = float(p["fator"])
        sozinho = p["vale_sozinho"] == "True"
        ncm_o, ncm_d = p["ncm_origem"], p["ncm_destino"]

        # --- medição anterior (①③④) ---
        cap_dif = bool(ncm_o and ncm_d and ncm_o[:2] != ncm_d[:2])
        cest_dif = p["cest_diferente"] == "True"
        po, pd = precos.get((cnpj, o), (None,) * 4), precos.get((cnpj, d), (None,) * 4)
        co = po[0] / po[1] if po[0] and po[1] else None
        cd = pd[0] / pd[1] if pd[0] and pd[1] else None
        pv = pd[2] / pd[3] if pd[2] and pd[3] else None
        sc = faixa(float(co) / fator / float(cd) if co and cd else None, FAIXA_CUSTO)
        custo = sc if sc != "sem_dado" else faixa(float(co) / fator / float(pv) if co and pv else None, FAIXA_PRECO)
        antes = cap_dif or cest_dif or custo == "incoerente"
        suspeito = cap_dif or cest_dif  # grupo de "provavelmente errado" da medição anterior

        # --- regras novas ---
        comuns = gtins_do_cod.get((cnpj, o), set()) & gtins_do_cod.get((cnpj, d), set())
        hig = sorted({h for g in comuns if (h := higiene(g))})
        contaminado = any(len(caps_do_gtin[(cnpj, g)]) >= 2 for g in comuns)
        max_cods = max((len(cods_do_gtin[(cnpj, g)]) for g in comuns), default=0)

        so, eo = semanas[(cnpj, o)]
        sd, ed = semanas[(cnpj, d)]
        juntas_s, juntas_e = len(so & sd), len(eo & ed)
        convivem = juntas_s >= SEMANAS_JUNTAS or juntas_e >= SEMANAS_JUNTAS

        mo, md = medidas((cad.get((cnpj, o)) or ("",))[0]), medidas((cad.get((cnpj, d)) or ("",))[0])
        gram = "sem_medida"
        for tipo in mo.keys() & md.keys():
            r = mo[tipo] / md[tipo] if md[tipo] else None
            gram = "bate" if r and abs(r - fator) / fator < 0.02 else "diverge"
            if gram == "diverge":
                break

        uo = FAMILIA_UNIDADE.get(((cad.get((cnpj, o)) or ("", ""))[1] or "").upper(), "?")
        ud = FAMILIA_UNIDADE.get(((cad.get((cnpj, d)) or ("", ""))[1] or "").upper(), "?")
        un_dif = fator == 1 and "?" not in (uo, ud) and uo != ud and "emb" not in (uo, ud)

        xo, xd = xml_do_cod.get((cnpj, o), set()), xml_do_cod.get((cnpj, d), set())
        if not comuns:
            xml = "sem_gtin_no_par"
        elif not xo and not xd:
            xml = "sem_xml"
        elif any(g in xo for g in comuns) and any(g in xd for g in comuns):
            xml = "confirma_os_dois"
        elif any(g in xo | xd for g in comuns):
            xml = "confirma_um"
        else:
            xml = "contradiz"

        regras = {
            "⑥ gtin_contaminado": contaminado,
            "⑦ convivem": convivem,
            "⑧ gramatura_diverge": gram == "diverge",
            "⑨ unidade_diferente": un_dif,
            "⑩ xml_contradiz": xml == "contradiz",
            "higiene_gtin": bool(hig),
        }
        depois = antes or any(regras.values())

        grupo = "todos"
        for g in (["todos"] + (["sozinho"] if sozinho else [])):
            cont[(g, "pares")] += 1
            cont[(g, "antes_pega")] += antes
            cont[(g, "depois_pega")] += depois
            cont[(g, "suspeitos")] += suspeito
            cont[(g, "limpos_antes")] += not antes
            for nome, v in regras.items():
                if v:
                    cont[(g, nome, "pega")] += 1
                    cont[(g, nome, "dos_suspeitos")] += suspeito
                    cont[(g, nome, "dos_limpos")] += not antes
                    cont[(g, nome, "so_ela")] += not antes and sum(regras.values()) == 1
            cont[(g, "xml", xml)] += 1
            cont[(g, "gramatura", gram)] += 1
            for h in hig:
                cont[(g, "higiene", h)] += 1
            if not suspeito and convivem:
                cont[(g, "⑦ convivem_sem_suspeita_semanas_s", min(juntas_s, 10))] += 1

        linhas.append([cnpj, o, d, p["fator"], m, sozinho, ncm_o, ncm_d, cap_dif, cest_dif, custo, antes,
                       "|".join(sorted(comuns)), max_cods, contaminado, juntas_s, juntas_e, convivem,
                       (cad.get((cnpj, o)) or ("",))[0], (cad.get((cnpj, d)) or ("",))[0], gram,
                       uo, ud, un_dif, xml, "|".join(hig), depois])

    with open(saida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["cnpj", "origem", "destino", "fator", "motivo", "vale_sozinho", "ncm_origem", "ncm_destino",
                    "ncm_capitulo_diferente", "cest_diferente", "custo", "pego_antes", "gtins_comuns",
                    "codigos_com_o_gtin", "gtin_contaminado", "semanas_juntas_saida", "semanas_juntas_entrada",
                    "convivem", "descricao_origem", "descricao_destino", "gramatura", "unidade_origem",
                    "unidade_destino", "unidade_diferente", "xml_fornecedor", "higiene_gtin", "pego_depois"])
        w.writerows(linhas)

    for k in sorted(cont, key=str):
        print("\t".join(map(str, k)), cont[k], sep="\t")
    log.info("fim: %d pares, %.0fs, csv em %s", len(linhas), time.time() - t0, saida)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

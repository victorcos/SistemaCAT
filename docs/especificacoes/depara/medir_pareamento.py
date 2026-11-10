"""O GTIN que chega pelo XML pareado ao C170 só vale se o XML 'combina' com o 0200 do código (mesmo capítulo de NCM
ou palavras em comum na descrição). Mede o acerto da regra contra o gabarito. Uso: <pasta> <csv_v3> <gabarito.py>"""
import csv, re, sys, duckdb
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")
pasta, arq = sys.argv[1].replace("\\", "/"), sys.argv[2]
c = duckdb.connect(); c.execute("SET enable_progress_bar=false")
PAL = lambda s: {w for w in re.findall(r"[a-zà-ú]{3,}", (s or "").lower())}
cad = {(a, b): (d, n) for a, b, d, n in c.execute(f"select cnpj, codigo, last(descricao order by competencia), last(ncm order by competencia) from read_parquet('{pasta}/itens.parquet') group by 1,2").fetchall()}
ok = {}   # (cnpj, cod, gtin) -> fontes válidas
linhas = c.execute(f"""select cnpj, codigo, ltrim(trim(gtin_xml),'0'), fonte_item, ncm_xml, descricao_xml, count(*)
    from read_parquet('{pasta}/movimentos.parquet') where gtin_xml is not null group by all""").fetchall()
linhas += [(a, b, g, "cadastro", None, None, n) for a, b, g, n in c.execute(f"""select cnpj, codigo, ltrim(trim(codigo_barras),'0'), count(*)
    from read_parquet('{pasta}/movimentos.parquet') where codigo_barras is not null and coalesce(cadastro_da_efd,true) group by all""").fetchall()]
for cnpj, cod, g, fonte, ncm_x, desc_x, n in linhas:
    s = ok.setdefault((cnpj, cod, g), {"valido": False, "pareado_incoerente": 0})
    if fonte != "efd":
        s["valido"] = True; continue
    desc_c, ncm_c = cad.get((cnpj, cod), ("", ""))
    coerente = bool((ncm_x and ncm_c and ncm_x[:2] == ncm_c[:2]) or (PAL(desc_x) & PAL(desc_c)) or not desc_c)
    if coerente: s["valido"] = True
    else: s["pareado_incoerente"] += n
exec(open(sys.argv[3], encoding="utf-8").read().split("L = [")[0])
todos = [p for p in csv.DictReader(open(arq, encoding="utf-8-sig"), delimiter=";") if p["vale_sozinho"] == "True"]
cont = Counter(); exemplos = []
for i, p in enumerate(todos):
    gab = R.get(i, "D")
    if not p["gtins_comuns"]:
        cont[("sem_gtin", gab)] += 1; continue
    sustenta = any(all(ok.get((p["cnpj"], cod, g), {}).get("valido") for cod in (p["origem"], p["destino"])) for g in p["gtins_comuns"].split("|"))
    cont[("gtin_sustenta" if sustenta else "gtin_cai", gab)] += 1
    if not sustenta and gab == "S": exemplos.append((p["descricao_origem"][:35], p["descricao_destino"][:35]))
for k in sorted(cont): print(k, cont[k])
import json; json.dump([i for i, p in enumerate(todos) if p["gtins_comuns"] and not any(all(ok.get((p["cnpj"], cod, g), {}).get("valido") for cod in (p["origem"], p["destino"])) for g in p["gtins_comuns"].split("|"))], open(sys.argv[4], "w")) if len(sys.argv) > 4 else None
print("certos que cairiam:", exemplos[:10])

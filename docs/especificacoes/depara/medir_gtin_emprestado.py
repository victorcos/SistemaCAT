"""Quantos pares de GTIN vêm de um GTIN 'emprestado': o lado só tem o GTIN pelo XML pareado ao C170 (o código ali é
o do fornecedor), não pelo 0200 nem pelo XML do próprio item. Uso: medir_gtin_emprestado.py <pasta> <csv_v3> [gabarito]"""
import csv, sys, duckdb
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")
pasta, arq = sys.argv[1].replace("\\", "/"), sys.argv[2]
c = duckdb.connect(); c.execute("SET enable_progress_bar=false")
print("fonte_item:", c.execute(f"select fonte_item, registro, count(*) from read_parquet('{pasta}/movimentos.parquet') group by all").fetchall())
fonte = {}
for cnpj, cod, g, origem in c.execute(f"""
    select cnpj, codigo, ltrim(trim(g),'0'), origem from (
      select cnpj, codigo, codigo_barras g, 'cadastro' origem from read_parquet('{pasta}/movimentos.parquet') where codigo_barras is not null and coalesce(cadastro_da_efd, true)
      union all
      select cnpj, codigo, gtin_xml, case when fonte_item='xml' then 'xml_proprio' else 'xml_pareado_c170' end
      from read_parquet('{pasta}/movimentos.parquet') where gtin_xml is not null)
    group by all""").fetchall():
    fonte.setdefault((cnpj, cod, g), set()).add(origem)
L = [p for p in csv.DictReader(open(arq, encoding="utf-8-sig"), delimiter=";") if p["vale_sozinho"] == "True" and p["gtins_comuns"]]
gab = {}
if len(sys.argv) > 3:
    exec(open(sys.argv[3], encoding="utf-8").read().split("L = [")[0]); 
    todos = [p for p in csv.DictReader(open(arq, encoding="utf-8-sig"), delimiter=";") if p["vale_sozinho"] == "True"]
    for i, p in enumerate(todos): gab[(p["cnpj"], p["origem"], p["destino"])] = R.get(i, "D")
cont = Counter()
for p in L:
    emprestado = False
    for g in p["gtins_comuns"].split("|"):
        for cod in (p["origem"], p["destino"]):
            if fonte.get((p["cnpj"], cod, g), set()) <= {"xml_pareado_c170"}:
                emprestado = True
    cont[("emprestado" if emprestado else "proprio", gab.get((p["cnpj"], p["origem"], p["destino"]), "?"))] += 1
for k in sorted(cont): print(k, cont[k])

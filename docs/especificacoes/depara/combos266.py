import re, sys
sys.stdout.reconfigure(encoding="utf-8")
exec(open("gabarito266.py", encoding="utf-8").read().split('print("gabarito:"')[0])
T = lambda v: v == "True"
def pal(s): return {w for w in re.findall(r"[a-z]{3,}", (s or "").lower())}
def sem_palavra_comum(p):  # sufixo com descrições sem nenhuma palavra em comum
    a, b = pal(p["descricao_origem"]), pal(p["descricao_destino"])
    return p["motivo"].startswith("sufixo") and a and b and not (a & b)
r = {"①": lambda p: p["custo"] == "incoerente", "③": lambda p: T(p["cest_diferente"]),
     "④": lambda p: T(p["ncm_capitulo_diferente"]), "⑥": lambda p: T(p["gtin_contaminado"]),
     "⑦": lambda p: T(p["convivem"]), "⑧": lambda p: p["gramatura"] == "diverge", "suf": sem_palavra_comum}
combos = ["", "①③④", "⑥⑦⑧", "⑥⑦⑧suf", "①⑥⑦⑧suf", "③⑥⑦⑧suf", "①③⑥⑦⑧suf", "①③④⑥⑦⑧suf"]
nS = sum(p["gab"] == "S" for p in L); nD = sum(p["gab"] == "D" for p in L)
print(f"{'regras':16} {'aceitos':>7} {'certos':>6} {'errados':>7} {'acerto':>7} | {'erros barrados':>14} {'certos barrados':>15}")
for c in combos:
    ks = ["suf"] if c.endswith("suf") else []
    ks += [ch for ch in c.replace("suf", "")]
    barra = lambda p: any(r[k](p) for k in ks)
    ac = [p for p in L if p["gab"] != "I" and not barra(p)]
    s = sum(p["gab"] == "S" for p in ac)
    db = sum(p["gab"] == "D" and barra(p) for p in L); sb = sum(p["gab"] == "S" and barra(p) for p in L)
    print(f"{c or 'nenhuma':16} {len(ac):7} {s:6} {len(ac)-s:7} {100*s/len(ac):6.1f}% | {db:5} de {nD} {sb:8} de {nS}")

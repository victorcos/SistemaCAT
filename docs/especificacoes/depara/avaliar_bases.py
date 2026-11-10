"""Acerto das regras do de-para em duas bases rotuladas (empresa 29 = 266 pares; execução 227 = amostra de 150),
com sensibilidade dos limites e a regra ⑪ (sabor/versão)."""
import csv, re, sys
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")
sys.argv = ["x"]
exec(open("medir_reforcos_v3.py", encoding="utf-8").read().split("def faixa")[0].split("logging.basicConfig")[0].replace("from cat.", "#from cat."))
exec("\n".join(l for l in open("medir_reforcos_v3.py", encoding="utf-8").read().split("\n") if l.startswith(("RE_MEDIDA", "PARA_BASE")) or l.startswith('             "') ))
def medidas(desc):
    out = {}
    for num, un in RE_MEDIDA.findall((desc or "").upper()):
        tipo, mult = PARA_BASE[un]; out.setdefault(tipo, float(num.replace(",", ".")) * mult)
    return out

# --- empresa 29: gabarito de gabarito266.py
src = open("gabarito266.py", encoding="utf-8").read()
exec(src.split('print("gabarito:"')[0])
base29 = L
# --- execução 227: amostra rotulada
S227 = {102,177,284,585,895,898,899,902,914,938,952,953,1010,1200,1202,1482,1839,2390,2633}
I227 = {700,787,814,858,864,870,881}
r = [p for p in csv.DictReader(open("pares_execucao-227_v3.csv", encoding="utf-8-sig"), delimiter=";") if p["vale_sozinho"] == "True"]
idx = [int(x) for x in open("amostra227.txt").read().split(",")]
base227 = []
for i in idx:
    p = r[i]; p["gab"] = "S" if i in S227 else "I" if i in I227 else "D"; base227.append(p)

PAL = lambda s: {w for w in re.findall(r"[a-zà-ú]{3,}", (s or "").lower())}
def jac(p):
    a, b = PAL(p["descricao_origem"]), PAL(p["descricao_destino"])
    return None if not a or not b else len(a & b) / len(a | b)
def gram(p, tol):
    mo, md = medidas(p["descricao_origem"]), medidas(p["descricao_destino"]); f = float(p["fator"])
    for t in mo.keys() & md.keys():
        if md[t] and abs(mo[t] / md[t] - f) / f > tol: return True
    return False
def variante(p):  # ⑪ mesma medida, troca de 1-2 palavras dos dois lados, com 2+ em comum
    mo, md = medidas(p["descricao_origem"]), medidas(p["descricao_destino"])
    if not (mo and mo == md): return False
    a, b = PAL(p["descricao_origem"]), PAL(p["descricao_destino"])
    so_a, so_b = a - b, b - a
    return len(a & b) >= 2 and 1 <= len(so_a) <= 2 and 1 <= len(so_b) <= 2
T = lambda v: v == "True"
def regras(sem=3, tol=0.02, jmin=0.0, sufixo_qualquer=False, com11=False, base=("6", "7", "8", "suf")):
    def barra(p):
        b = []
        if "6" in base: b.append(T(p["gtin_contaminado"]))
        if "7" in base: b.append(int(p["semanas_juntas_saida"]) >= sem or int(p["semanas_juntas_entrada"]) >= sem)
        if "8" in base: b.append(gram(p, tol))
        if "suf" in base:
            j = jac(p)
            alvo = ("sufixo" in p["motivo"]) if sufixo_qualquer else p["motivo"].startswith("sufixo")
            b.append(alvo and j is not None and j <= jmin)
        if "1" in base: b.append(p["custo"] == "incoerente")
        if "3" in base: b.append(T(p["cest_diferente"]))
        if "4" in base: b.append(T(p["ncm_capitulo_diferente"]))
        if com11: b.append(variante(p))
        return any(b)
    return barra
def aval(L, barra):
    ac = [p for p in L if p["gab"] != "I" and not barra(p)]
    s = sum(p["gab"] == "S" for p in ac)
    sb = sum(p["gab"] == "S" and barra(p) for p in L); nS = sum(p["gab"] == "S" for p in L)
    nD = sum(p["gab"] == "D" for p in L); db = sum(p["gab"] == "D" and barra(p) for p in L)
    return f"{100*s/len(ac) if ac else 0:5.1f}% ({s}/{len(ac)}) erros barr {db}/{nD} certos barr {sb}/{nS}"
for nome, L in (("empresa 29", base29), ("exec 227", base227)):
    print(f"\n=== {nome}: {Counter(p['gab'] for p in L)}")
    print(f"  {'atual':42} {aval(L, lambda p: False)}")
    print(f"  {'①③④ (cinco reforços)':42} {aval(L, regras(base=('1','3','4')))}")
    print(f"  {'⑥⑦⑧ + sufixo (recomendado ontem)':42} {aval(L, regras())}")
    print(f"  {'  + sufixo também em gtin+sufixo':42} {aval(L, regras(sufixo_qualquer=True))}")
    for j in (0.1, 0.2, 0.3):
        print(f"  {f'  + sufixo qualquer, palavras <= {j}':42} {aval(L, regras(sufixo_qualquer=True, jmin=j))}")
    print(f"  {'  + ⑪ variante':42} {aval(L, regras(sufixo_qualquer=True, jmin=0.2, com11=True))}")
    for s in (2, 3, 4, 6):
        print(f"  {f'  ⑦ com {s} semanas':42} {aval(L, regras(sem=s, sufixo_qualquer=True, jmin=0.2))}")
    for t in (0.02, 0.10, 0.25):
        print(f"  {f'  ⑧ tolerância {t:.0%}':42} {aval(L, regras(tol=t, sufixo_qualquer=True, jmin=0.2))}")
    print("  precisão de cada regra (erros / tudo o que barra):")
    for k, f in {"⑥": regras(base=("6",)), "⑦": regras(base=("7",)), "⑧": regras(base=("8",)),
                 "suf (qualquer, <=0.2)": regras(base=("suf",), sufixo_qualquer=True, jmin=0.2),
                 "⑪": regras(base=(), com11=True), "①": regras(base=("1",)), "③": regras(base=("3",)), "④": regras(base=("4",))}.items():
        d = sum(p["gab"] == "D" and f(p) for p in L); s = sum(p["gab"] == "S" and f(p) for p in L)
        print(f"    {k:22} barra {d:3} errados e {s:3} certos" + (f"  ({100*d/(d+s):.0f}%)" if d + s else ""))

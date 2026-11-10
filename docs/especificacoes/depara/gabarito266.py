"""Gabarito manual (leitura das descrições) dos 266 pares que valem sozinhos na empresa 29, e o acerto de cada metodologia.
S = mesmo produto, D = produto diferente, I = não dá para dizer (descrição vazia, genérico, dúvida real).
Componente de cesta de Natal com a mesma descrição/tamanho do produto de marca conta como S."""
import csv, sys
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")
R = {}
def m(rotulo, *idx):
    for i in idx:
        if isinstance(i, range):
            for j in i: R[j] = rotulo
        else: R[i] = rotulo
m("S", 4,5,10,14,21,28,34,36,40,58,59,62,69,70,75,76,78,84,86,87,89,100,103,107,110, range(112,140),
  165,166,169,170,176,177,183,185,186,187,189,190,191,193,209,210,211,212,214,219,220,221,223,224,226,229,
  233,238,240,243,246,255,256,258,259,261,263)
m("I", 1,6,8,11,61,64,72,79,80,81,94, range(140,164),167,168,171,179,180,181,188,205,217,225,230,231,249,251,253,257,262)
L = [p for p in csv.DictReader(open("depara_medicao_v3.csv", encoding="utf-8-sig"), delimiter=";") if p["vale_sozinho"] == "True"]
for i in range(len(L)):
    R.setdefault(i, "D")
for i, p in enumerate(L): p["gab"] = R[i]
print("gabarito:", Counter(p["gab"] for p in L))
T = lambda v: v == "True"
metodos = {
    "0 atual (vale sozinho)": lambda p: False,
    "1 cinco reforços (①③④)": lambda p: T(p["pego_antes"]),
    "2 reforços + ⑥": lambda p: T(p["pego_antes"]) or T(p["gtin_contaminado"]),
    "3 reforços + ⑥⑦": lambda p: T(p["pego_antes"]) or T(p["gtin_contaminado"]) or T(p["convivem"]),
    "4 reforços + ⑥⑦⑧": lambda p: T(p["pego_antes"]) or T(p["gtin_contaminado"]) or T(p["convivem"]) or p["gramatura"] == "diverge",
    "só ⑥⑦⑧ (sem ①③④)": lambda p: T(p["gtin_contaminado"]) or T(p["convivem"]) or p["gramatura"] == "diverge",
}
print(f"{'metodologia':28} {'aceitos':>7} {'certos':>6} {'errados':>7} {'acerto':>7} | {'D barrados':>10} {'S barrados':>10}")
nS = sum(p["gab"] == "S" for p in L); nD = sum(p["gab"] == "D" for p in L)
for nome, barra in metodos.items():
    ac = [p for p in L if p["gab"] != "I" and not barra(p)]
    s = sum(p["gab"] == "S" for p in ac); d = len(ac) - s
    db = sum(p["gab"] == "D" and barra(p) for p in L); sb = sum(p["gab"] == "S" and barra(p) for p in L)
    print(f"{nome:28} {len(ac):7} {s:6} {d:7} {100*s/len(ac) if ac else 0:6.1f}% | {db:4} de {nD:3} {sb:4} de {nS:3}")
print("\npor regra (sobre os rotulados S/D):")
regras = {"① custo incoerente": lambda p: p["custo"] == "incoerente",
          "③ CEST diferente": lambda p: T(p["cest_diferente"]),
          "④ NCM capítulo dif.": lambda p: T(p["ncm_capitulo_diferente"]),
          "⑥ GTIN contaminado": lambda p: T(p["gtin_contaminado"]),
          "⑦ convivem": lambda p: T(p["convivem"]),
          "⑧ gramatura diverge": lambda p: p["gramatura"] == "diverge"}
for n, f in regras.items():
    d = sum(p["gab"] == "D" and f(p) for p in L); s = sum(p["gab"] == "S" and f(p) for p in L)
    print(f"  {n:22} pega {d:3} errados e {s:3} certos  (precisão {100*d/(d+s) if d+s else 0:5.1f}%)")
print("\nS barrados pelo ④:", [ (p["descricao_origem"][:25], p["descricao_destino"][:30]) for p in L if p["gab"]=="S" and T(p["ncm_capitulo_diferente"])][:5])
print("D que passam em tudo (método 4):")
for p in L:
    if p["gab"] == "D" and not metodos["4 reforços + ⑥⑦⑧"](p):
        print("  ", p["descricao_origem"][:40], "||", p["descricao_destino"][:40])

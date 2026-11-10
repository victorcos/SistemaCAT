import sys
src = open("avaliar_bases.py", encoding="utf-8").read().split("for nome, L in")[0]
exec(src)
cands = {
 "A ⑥⑦⑧ + sufixo ≤0,2 (3 sem.)":            dict(sufixo_qualquer=True, jmin=0.2),
 "B ⑥⑦⑧ + sufixo ≤0,2 (2 sem.)":            dict(sem=2, sufixo_qualquer=True, jmin=0.2),
 "C B + tolerância 10%":                     dict(sem=2, tol=0.10, sufixo_qualquer=True, jmin=0.2),
 "D C + ① custo":                            dict(sem=2, tol=0.10, sufixo_qualquer=True, jmin=0.2, base=("6","7","8","suf","1")),
 "E C + sufixo ≤0,3":                        dict(sem=2, tol=0.10, sufixo_qualquer=True, jmin=0.3),
 "F D + ③ CEST":                             dict(sem=2, tol=0.10, sufixo_qualquer=True, jmin=0.2, base=("6","7","8","suf","1","3")),
}
for k, c in cands.items():
    print(f"{k:32} 29: {aval(base29, regras(**c))}\n{'':32} 227: {aval(base227, regras(**c))}")

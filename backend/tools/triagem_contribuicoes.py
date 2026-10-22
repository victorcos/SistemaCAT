"""Triagem da rede: em que cliente há ISS de saída para tirar da base do PIS/COFINS.

Varre as pastas autorizadas, identifica cada EFD-Contribuições pelo conteúdo e
diz, por CNPJ, em que competências há bloco A — sem ler os arquivos inteiros.
O cálculo continua sendo do 933, no lote cadastrado: isto só aponta onde
cadastrar. Ver `cat/infraestrutura/arquivos/inventario_contribuicoes.py`.

    # 1. varrer (retomável; reexecução só lê o que mudou)
    python tools/triagem_contribuicoes.py varrer --inventario D:\\triagem\\inv.sqlite \\
        --raiz \\\\192.168.88.22\\FISCALSP\\<cliente> [--raiz ...] [--limite-segundos 600]

    # 2. separar saída de entrada, lendo só até o A990 de quem declara A100
    python tools/triagem_contribuicoes.py bloco-a --inventario D:\\triagem\\inv.sqlite

    # 3. o relatório, um CNPJ por linha, em ordem de potencial
    python tools/triagem_contribuicoes.py relatorio --inventario D:\\triagem\\inv.sqlite \\
        --saida D:\\triagem\\triagem.csv [--versoes D:\\triagem\\versoes.csv]

**Inventário local, nunca na rede**: o Y: perde gravação, e o SQLite em
compartilhamento corrompe. **Prefira o caminho por IP** ao `Z:` — o nome
`fileserver` resolve também para um endereço morto e cada pasta nova paga o
timeout.

Não versiona dado de cliente: recebe os caminhos por argumento e grava a saída
onde for mandado.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

from cat.infraestrutura.arquivos.inventario_contribuicoes import Interrompida, Inventario, triagem, versoes
from cat.log import contexto, obter_log

log = obter_log("triagem_contribuicoes")


def _gravar_csv(caminho: str, linhas: list[dict]) -> None:
    if not linhas:
        log.warning("nada a gravar", extra={"saida": caminho})
        return
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), delimiter=";")
        w.writeheader()
        w.writerows(linhas)


def _avisar_se_na_rede(caminho: str) -> None:
    unidade = os.path.splitdrive(os.path.abspath(caminho))[0]
    na_rede = unidade.startswith("\\\\")
    if not na_rede and os.name == "nt" and unidade:
        import ctypes
        # 4 = DRIVE_REMOTE: o Y: e o Z: são letras, mas são rede
        na_rede = ctypes.windll.kernel32.GetDriveTypeW(unidade + "\\") == 4
    if na_rede:
        log.warning("inventário em unidade de rede: grave em disco local", extra={"inventario": caminho})
        print(f"aviso: {caminho} está em unidade de rede; prefira disco local", file=sys.stderr)


def varrer(a: argparse.Namespace) -> int:
    _avisar_se_na_rede(a.inventario)
    inv = Inventario(a.inventario)
    raizes = inv.retomar_execucao(a.retomar) if a.retomar else list(a.raiz)
    if not raizes:
        print("informe --raiz ou --retomar", file=sys.stderr)
        return 2
    if not a.retomar:
        inv.abrir_execucao(raizes)
    if a.limite_segundos is not None:
        inv.prazo = time.monotonic() + a.limite_segundos
    t0 = time.perf_counter()
    with contexto(execucao_id=f"triagem-{inv.execucao_id}", etapa="varredura"):
        try:
            for raiz in raizes:
                inv.varrer(raiz)
        except (Interrompida, KeyboardInterrupt):
            inv.fechar_execucao(time.perf_counter() - t0, "interrompida")
            log.warning("varredura interrompida", extra={"execucao": inv.execucao_id})
            print(f"interrompida: continue com --retomar {inv.execucao_id}")
            return 3
        inv.fechar_execucao(time.perf_counter() - t0, "concluida")
        resumo = {"execucao": inv.execucao_id, **inv.c.__dict__, "segundos": round(time.perf_counter() - t0, 2)}
        log.info("varredura concluída", extra=resumo)
    print(json.dumps(resumo, ensure_ascii=False))
    return 0


def bloco_a(a: argparse.Namespace) -> int:
    inv = Inventario(a.inventario)
    if a.limite_segundos is not None:
        inv.prazo = time.monotonic() + a.limite_segundos
    t0 = time.perf_counter()
    with contexto(etapa="bloco_a"):
        try:
            lidos = inv.ler_blocos_a(a.raiz or None)
        except (Interrompida, KeyboardInterrupt):
            print("interrompida: rode de novo, o que já foi lido não se relê")
            return 3
    print(json.dumps({"arquivos_lidos": lidos, "erros": inv.c.erros,
                      "segundos": round(time.perf_counter() - t0, 2)}))
    return 0


def relatorio(a: argparse.Namespace) -> int:
    inv = Inventario(a.inventario)
    linhas = triagem(inv.db)
    _gravar_csv(a.saida, linhas)
    if a.versoes:
        _gravar_csv(a.versoes, versoes(inv.db))
    log.info("relatório gravado", extra={"saida": a.saida, "cnpjs": len(linhas)})
    print(f"{len(linhas)} CNPJ -> {os.path.abspath(a.saida)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="comando", required=True)
    v = sub.add_parser("varrer", help="inventariar as pastas")
    v.add_argument("--inventario", required=True)
    v.add_argument("--raiz", action="append", default=[], help="raiz autorizada (repetível)")
    v.add_argument("--retomar", type=int, help="id da execução interrompida")
    v.add_argument("--limite-segundos", type=float)
    v.set_defaults(func=varrer)
    b = sub.add_parser("bloco-a", help="ler até o A990 quem declara A100")
    b.add_argument("--inventario", required=True)
    b.add_argument("--limite-segundos", type=float)
    b.add_argument("--raiz", action="append", default=[],
                   help="só os arquivos que vieram desta raiz (prefixo; repetível)")
    b.set_defaults(func=bloco_a)
    r = sub.add_parser("relatorio", help="um CNPJ por linha, em ordem de potencial")
    r.add_argument("--inventario", required=True)
    r.add_argument("--saida", required=True)
    r.add_argument("--versoes", help="CSV opcional com a versão escolhida de cada período")
    r.set_defaults(func=relatorio)
    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())

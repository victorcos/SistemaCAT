"""Razão contábil de uma lista de contas, a partir de ECD soltas, pela linha de comando.

Faz por script o que a etapa de apuração faz na fila, sem projeto, banco nem
API: `indexar_ecd` + `razao` de cada ECD, uma parte parquet por arquivo (como
`analitico/piscofins.py`), e a planilha "Razão Contábil" do padrão da casa por
`planilhas/quebra_de_sped.gerar_razao_contabil`, recortada nas contas pedidas.

Existe para a conferência rápida que o fluxo completo não atende: alguém já tem a
lista de contas e os arquivos numa pasta, e quer o razão delas — inclusive para
confrontar com o que outro motor (o projeto Quebra de SPED) produz da mesma base.
`--excluir` tira contas da quebra sem mexer na lista principal.

Uso (do backend, com a venv):
    .venv/Scripts/python tools/razao_contabil_ecd.py --ecds <pasta> --contas contas.txt
        [--excluir excluir.txt] --saida <pasta> --nome "Razão" [--processos 3]

Nos arquivos de contas, "#" inicia comentário. Cada ECD vai num processo (o
índice de uma ECD grande passa de 1 GB; com pouca memória, use --processos 1).
A guarda `__main__` é obrigatória: o `spawn` do Windows reimporta este módulo
em cada filho (ver o aviso em `piscofins._ler_as_ecd`).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from cat.infraestrutura.analitico.escrita import Escritor
from cat.infraestrutura.analitico.piscofins import COLUNAS_DO_RAZAO
from cat.infraestrutura.planilhas.quebra_de_sped import gerar_razao_contabil
from cat.infraestrutura.sped.ecd import indexar_ecd, razao

log = logging.getLogger("razao_contabil_ecd")


def ler_lista(caminho: Path) -> list[str]:
    """Um código por linha; "#" comenta; duplicados caem."""
    codigos: list[str] = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        codigo = linha.split("#", 1)[0].strip()
        if codigo and codigo not in codigos:
            codigos.append(codigo)
    return codigos


def configurar_log(pasta: Path, nome: str) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    arquivo = logging.FileHandler(pasta / f"{nome}.log", encoding="utf-8")
    console = logging.StreamHandler(sys.stdout)
    for h in (arquivo, console):
        h.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[arquivo, console])
    logging.getLogger("cat").setLevel(logging.INFO)


def como_linha(linha) -> dict:
    """A partida no formato do parquet — o mesmo de `piscofins._como_linha`."""
    return {
        "cnpj": linha.cnpj, "conta": linha.conta, "descricao": linha.descricao,
        "conta_referencial": linha.conta_referencial, "competencia": linha.competencia,
        "data": linha.data, "numero": linha.numero,
        "valor_do_lancamento": f"{linha.valor_do_lancamento:.2f}",
        "centro_de_custo": linha.centro_de_custo, "valor": f"{linha.valor:.2f}",
        "debito_ou_credito": linha.debito_ou_credito, "historico": linha.historico,
        "codigo_do_historico": linha.codigo_do_historico,
        "participante": linha.participante, "tipo": linha.tipo,
        "saldo": f"{linha.saldo:.2f}", "arquivo": linha.arquivo,
    }


def uma_ecd(tarefa: dict) -> dict:
    """Roda noutro processo: indexa a ECD e grava a parte do razão das contas pedidas.

    Devolve só contagens e identificação; o parquet já está em disco.
    """
    caminho, parte, contas, excluir = (tarefa["caminho"], tarefa["parte"],
                                      tarefa["contas"], tarefa["excluir"])
    t0 = time.time()
    indice = indexar_ecd(caminho)
    codigos_do_plano = {c.codigo for c in indice.contas}
    alvos = [c for c in contas if c in codigos_do_plano and c not in excluir]
    partidas_excluidas = {c: indice.partidas_de(c) for c in excluir if indice.partidas_de(c)}
    escritor = Escritor(parte, COLUNAS_DO_RAZAO)
    por_conta: dict[str, int] = {}
    try:
        for linha in razao(caminho, indice, contas=alvos):
            escritor.escrever(como_linha(linha))
            por_conta[linha.conta] = por_conta.get(linha.conta, 0) + 1
    finally:
        escritor.fechar()
    return {
        "arquivo": os.path.basename(caminho), "cnpj": indice.cnpj, "inicio": indice.inicio,
        "fim": indice.fim, "contas_do_plano": len(indice.contas),
        "lancamentos": indice.lancamentos, "partidas": indice.partidas,
        "contas_alvo": alvos, "linhas": escritor.gravadas, "linhas_por_conta": por_conta,
        "partidas_excluidas": partidas_excluidas, "segundos": round(time.time() - t0, 1),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ecds", required=True, help="pasta com os arquivos *-SPED-ECD.txt")
    p.add_argument("--contas", required=True, help="arquivo com um código de conta por linha")
    p.add_argument("--excluir", help="arquivo com códigos a remover da quebra")
    p.add_argument("--saida", required=True, help="pasta de saída")
    p.add_argument("--nome", required=True, help="nome base da planilha")
    p.add_argument("--processos", type=int, default=3, help="ECD lidas ao mesmo tempo")
    args = p.parse_args()

    saida = Path(args.saida)
    pasta_razao = saida / "razao"
    pasta_razao.mkdir(parents=True, exist_ok=True)
    configurar_log(saida, args.nome)
    inicio = time.time()

    ecds = sorted(str(c) for c in Path(args.ecds).glob("*-SPED-ECD.txt"))
    if not ecds:
        log.error("nenhum ECD em %s", args.ecds)
        return 2
    contas = ler_lista(Path(args.contas))
    excluir = ler_lista(Path(args.excluir)) if args.excluir else []
    log.info("inicio | ecds=%d contas=%d excluir=%s processos=%d", len(ecds), len(contas),
             excluir, args.processos)

    tarefas = [{"caminho": c, "parte": str(pasta_razao / f"parte-{i:04d}.parquet"),
                "contas": contas, "excluir": excluir} for i, c in enumerate(ecds)]
    feitos: list[dict] = []
    with ProcessPoolExecutor(max_workers=max(1, min(args.processos, len(tarefas)))) as pool:
        futuros = {pool.submit(uma_ecd, t): t for t in tarefas}
        for futuro in as_completed(futuros):
            feito = futuro.result()
            feitos.append(feito)
            log.info("ecd | %s", json.dumps({k: v for k, v in feito.items()
                                             if k != "linhas_por_conta"}, ensure_ascii=False))
            log.info("ecd linhas_por_conta | %s | %s", feito["arquivo"][15:40],
                     feito["linhas_por_conta"])
    feitos.sort(key=lambda f: f["arquivo"])

    total = sum(f["linhas"] for f in feitos)
    destino = saida / f"{args.nome}.xlsx"
    gravadas = gerar_razao_contabil(str(pasta_razao / "*.parquet"), str(destino),
                                    classificacoes=frozenset(contas) - frozenset(excluir))
    log.info("xlsx | arquivo=%s linhas=%d (parquet=%d) seg=%.0f", destino, gravadas, total,
             time.time() - inicio)

    linhas_por_conta: dict[str, int] = {}
    for f in feitos:
        for c, q in f["linhas_por_conta"].items():
            linhas_por_conta[c] = linhas_por_conta.get(c, 0) + q
    resumo = {
        "motor": "CRM Fiscal (cat.infraestrutura.sped.ecd)", "arquivo": str(destino),
        "linhas": gravadas, "contas_pedidas": contas, "contas_removidas": excluir,
        "linhas_por_conta": dict(sorted(linhas_por_conta.items())),
        "linhas_por_arquivo": {f["arquivo"]: f["linhas"] for f in feitos},
        "partidas_excluidas_por_arquivo": {f["arquivo"]: f["partidas_excluidas"] for f in feitos},
        "segundos": round(time.time() - inicio, 1),
    }
    (saida / f"{args.nome}.resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("fim | linhas=%d seg=%.0f", gravadas, time.time() - inicio)
    return 0


if __name__ == "__main__":
    sys.exit(main())

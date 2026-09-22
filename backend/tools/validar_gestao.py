"""Confere a Gestão gerada aqui contra o export CSV da Gestão do Sistema MA.

É o teste contra dado real: lê os SPED do cliente, monta os 36 quadros e
compara **linha a linha, mês a mês** com o CSV que o MA exporta. Serve para
revalidar as regras depois de mexer no código, e para checar um cliente novo.

    python tools/validar_gestao.py PIS    "D:\\...\\PIS.csv"    "D:\\...\\EFD-Contrib"
    python tools/validar_gestao.py COFINS "D:\\...\\COFINS.csv" "D:\\...\\EFD-Contrib"

**Nenhum dado de cliente entra no repositório**: os caminhos vêm por argumento
e o resultado sai na tela. É por isso que isto é uma ferramenta e não um teste
automatizado — o gabarito é a apuração de uma empresa real, e ela não se
versiona.

Sai com código 1 se houver qualquer divergência, para servir de portão.

Tolerância: **zero**. Centavo de diferença é divergência — foi assim que a
validação de 59 competências achou as duas únicas de R$ 0,01 que existiam.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cat.infraestrutura.gestao.montagem import ler, montar  # noqa: E402
from cat.infraestrutura.gestao.modelos import Relatorio  # noqa: E402

MESES = {"JAN": "01", "FEV": "02", "MAR": "03", "ABR": "04", "MAI": "05", "JUN": "06",
         "JUL": "07", "AGO": "08", "SET": "09", "OUT": "10", "NOV": "11", "DEZ": "12"}
TOLERANCIA_CENTAVOS = 0


def _periodo(coluna: str) -> str:
    """"JUL/2021" -> "2021-07"."""
    mes, ano = coluna.split("/")
    return f"{ano}-{MESES[mes]}"


def _centavos(texto: str) -> int:
    texto = texto.strip()
    if not texto:
        return 0
    return round(float(texto.replace(".", "").replace(",", ".")) * 100)


def _normalizar(rotulo: str) -> str:
    return re.sub(r"\s+", " ", rotulo).strip()


def arquivos_em(pasta: str) -> list[str]:
    if not os.path.isdir(pasta):
        raise NotADirectoryError(f"pasta não encontrada: {pasta}")
    return sorted(os.path.join(pasta, n) for n in os.listdir(pasta)
                  if n.lower().endswith(".txt") and os.path.isfile(os.path.join(pasta, n)))


def ler_export_ma(caminho: str) -> dict[str, dict[str, dict[str, int]]]:
    """CSV do MA -> {número do quadro: {rótulo: {período: centavos}}}."""
    quadros: dict[str, dict[str, dict[str, int]]] = {}
    titulo: list[str] = []
    atual: dict[str, dict[str, int]] | None = None
    colunas: list[str] = []
    with open(caminho, encoding="utf-8-sig") as arquivo:
        for linha in arquivo.read().splitlines():
            partes = linha.split(";")
            if len(partes) == 1:
                if linha.strip():
                    titulo.append(linha.strip())
                continue
            if partes[0] == "DESCRIÇÃO":
                colunas = partes[1:]
                texto = " ".join(titulo)
                achado = re.search(r"-\s*(\d+)[.\s-]", texto)
                atual = quadros.setdefault(achado.group(1) if achado else texto[:20], {})
                titulo = []
                continue
            if atual is None or not linha.strip(";").strip():
                continue
            atual[_normalizar(partes[0])] = {
                _periodo(c): _centavos(v) for c, v in zip(colunas, partes[1:])
            }
    return quadros


def comparar(relatorio: Relatorio, ma: dict[str, dict[str, dict[str, int]]],
             ) -> tuple[int, list[str], list[str]]:
    """Devolve (valores conferidos, divergências, quadros ausentes no export).

    Quadro ausente **não** é divergência: o export do MA nem sempre traz todos
    — o de PIS, por exemplo, não traz o 13, que o de COFINS traz.
    """
    conferidos = 0
    problemas: list[str] = []
    ausentes: list[str] = []
    periodos = set(relatorio.periodos)
    for quadro in relatorio.quadros:
        quadro_ma = ma.get(quadro.numero)
        if quadro_ma is None:
            ausentes.append(quadro.numero)
            continue
        nossas = {_normalizar(l.rotulo): l for l in quadro.linhas}
        for rotulo, valores in quadro_ma.items():
            valores = {p: v for p, v in valores.items() if p in periodos}
            linha = nossas.get(rotulo)
            if linha is None:
                if any(valores.values()):
                    problemas.append(f"[{quadro.numero}] só no MA: {rotulo!r}")
                continue
            for periodo, esperado in valores.items():
                obtido = linha.valores.get(periodo)
                if obtido is None:      # linha de fonte externa (DCTF/e-CAC)
                    continue
                if abs(obtido - esperado) > TOLERANCIA_CENTAVOS:
                    problemas.append(
                        f"[{quadro.numero}] {periodo} {rotulo!r}: "
                        f"nosso {obtido / 100:,.2f} x MA {esperado / 100:,.2f} "
                        f"(dif {(obtido - esperado) / 100:,.2f})")
                else:
                    conferidos += 1
        for rotulo, linha in nossas.items():
            if rotulo not in quadro_ma and any(v for v in linha.valores.values() if v):
                problemas.append(f"[{quadro.numero}] só nosso: {rotulo!r}")
    return conferidos, problemas, ausentes


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tributo", choices=["PIS", "COFINS"])
    p.add_argument("export_ma", help="CSV exportado da Gestão do MA")
    p.add_argument("pasta_efd", help="pasta com os arquivos da EFD-Contribuições")
    p.add_argument("--limite", type=int, default=50, help="máximo de divergências exibidas")
    args = p.parse_args()

    caminhos = arquivos_em(args.pasta_efd)
    print(f"{len(caminhos)} arquivo(s) de EFD-Contribuições — lendo…", flush=True)

    def andou(apuracao, i, total):
        print(f"  {i}/{total} {os.path.basename(apuracao.arquivo)} "
              f"· {apuracao.periodo} · {apuracao.segundos}s", flush=True)

    apuracoes, avisos = ler(caminhos, avisar=andou)
    for aviso in avisos:
        print(f"  ! {aviso}")
    relatorios = montar(apuracoes, avisos)
    if not relatorios:
        print("nenhuma apuração: nada a comparar")
        return 1
    relatorio = next(r for r in relatorios if r.tributo == args.tributo)

    conferidos, problemas, ausentes = comparar(relatorio, ler_export_ma(args.export_ma))
    if ausentes:
        print(f"(quadros que o export do MA não traz, não conferidos: {', '.join(ausentes)})")
    for problema in problemas[: args.limite]:
        print(problema)
    if len(problemas) > args.limite:
        print(f"… e mais {len(problemas) - args.limite} divergência(s)")
    print(f"== {args.tributo}: {conferidos} valores conferidos, {len(problemas)} divergência(s), "
          f"{len(relatorio.periodos)} competência(s)")
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())

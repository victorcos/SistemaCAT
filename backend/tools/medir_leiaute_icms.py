"""O leiaute da EFD ICMS/IPI medido contra arquivo de cliente.

`sped/registros_icms.py` diz quantos campos cada registro tem, e a tabela só
vale porque foi **contada em arquivo real** — 40 EFD ICMS/IPI, 02/2023 a
03/2026. Este comando é o que a conta, e é o que torna a tabela conferível por
quem desconfiar dela.

## Por que medir em vez de ler o Guia Prático

Porque o Guia descreve o leiaute que deveria existir, e o PVA gera o que
existe. Já aconteceu nesta casa, no `0140` da EFD-Contribuições: o Guia trazia
um `IND_SIT_INI_PER` que o arquivo não tem, e ele empurrava o `IND_ATIV` para
uma coluna vazia. O erro não aparece sozinho — o campo ao lado também é texto e
também parece um indicador.

A medição pegou duas coisas que a leitura não pegaria: o `0200` da ICMS/IPI tem
mesmo 13 campos, com o `CEST` que o da Contribuições não tem; e o `C110` dos
arquivos medidos tem um terceiro campo com o texto, que o leiaute antigo põe no
`0450`.

## O que ele faz

Varre os `.txt` da pasta, conta os campos de cada linha por registro e compara
com `registros_icms.CAMPOS`. Reporta três coisas:

* **divergência** — registro cuja contagem no arquivo não é a da tabela. É o
  achado que importa: ou o cliente usa outra versão do PVA, ou a tabela está
  errada;
* **não medido** — registro que aparece no arquivo e não está na tabela, com
  destaque para os três do combustível (`0206`, `0220`, `C171`) que se espera
  encontrar algum dia;
* **confirmado** — o que bateu, com quantas linhas.

    python tools/medir_leiaute_icms.py <pasta com EFD ICMS/IPI>
    python tools/medir_leiaute_icms.py <pasta> --todos
    python tools/medir_leiaute_icms.py <pasta> --amostra 12

`--todos` lista também os registros que não interessam à tese; sem ele, só os
de `CAMPOS` e os três esperados. `--amostra` limita quantos arquivos ler, que é
o que se usa quando a pasta está num compartilhamento lento.

**Não versiona nem imprime dado de cliente.** Imprime contagem de campos e de
linhas; nunca o conteúdo de um campo. O caminho vem por argumento.
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cat.infraestrutura.sped import registros_icms  # noqa: E402

# o SPED é cp1252; acento mal lido não atrapalha a contagem de campos
CODIFICACAO = "cp1252"


def medir(caminhos: list[str], todos: bool) -> tuple[dict, int, int]:
    """Quantas linhas de cada (registro, tamanho). Uma passada por arquivo."""
    contagem: dict[tuple[str, int], int] = collections.Counter()
    lidos = falhos = 0
    interessa = set(registros_icms.CAMPOS) | set(registros_icms.NAO_MEDIDOS)

    for caminho in caminhos:
        try:
            with open(caminho, encoding=CODIFICACAO, errors="replace") as arquivo:
                for linha in arquivo:
                    if not linha.startswith("|"):
                        continue
                    partes = linha.rstrip("\r\n").split("|")
                    if len(partes) < 3:
                        continue
                    registro = partes[1]
                    if not todos and registro not in interessa:
                        continue
                    contagem[(registro, len(partes) - 2)] += 1
            lidos += 1
        except OSError as erro:
            print(f"  não deu para ler {os.path.basename(caminho)}: {erro}",
                  file=sys.stderr)
            falhos += 1
    return contagem, lidos, falhos


def relatar(contagem: dict[tuple[str, int], int]) -> int:
    """Imprime o que divergiu, o que falta medir e o que bateu.

    Devolve quantas divergências houve, para servir de código de saída: zero
    significa que a tabela descreve estes arquivos.
    """
    por_registro: dict[str, dict[int, int]] = collections.defaultdict(dict)
    for (registro, tamanho), quantas in contagem.items():
        por_registro[registro][tamanho] = quantas

    divergencias: list[str] = []
    faltam: list[str] = []
    confirmados: list[str] = []

    for registro in sorted(por_registro):
        tamanhos = por_registro[registro]
        linhas = sum(tamanhos.values())
        esperado = len(registros_icms.CAMPOS.get(registro, ()))
        vistos = ", ".join(f"{t} ({q} linhas)" for t, q in sorted(tamanhos.items()))

        if esperado == 0:
            motivo = registros_icms.NAO_MEDIDOS.get(registro)
            faltam.append(
                f"  {registro}: {vistos}"
                + (f"\n      esperado algum dia — {motivo}" if motivo else ""))
        elif set(tamanhos) == {esperado}:
            confirmados.append(f"  {registro}: {esperado} campos, {linhas} linhas")
        else:
            divergencias.append(
                f"  {registro}: a tabela diz {esperado} campos, o arquivo traz "
                f"{vistos}")

    if divergencias:
        print("\nDIVERGÊNCIA — a tabela não descreve estes arquivos:")
        print("\n".join(divergencias))
        print("\n  Antes de mexer na tabela: confira se não são arquivos de")
        print("  versões diferentes do PVA. `registros.py` resolve isso com")
        print("  `CAMPOS_ANTIGOS`, chaveado por (registro, tamanho) — e é por")
        print("  tamanho, e não por data, porque retificadora de 2018")
        print("  transmitida em 2024 sai no leiaute novo.")

    if faltam:
        print("\nNÃO MEDIDOS — aparecem no arquivo e não estão na tabela:")
        print("\n".join(faltam))

    if confirmados:
        print(f"\nCONFIRMADOS ({len(confirmados)}):")
        print("\n".join(confirmados))

    return len(divergencias)


def main() -> int:
    analisador = argparse.ArgumentParser(
        description="Mede o leiaute da EFD ICMS/IPI contra arquivo de cliente.")
    analisador.add_argument("pasta", help="pasta com os .txt da EFD ICMS/IPI")
    analisador.add_argument("--todos", action="store_true",
                            help="inclui registros que não interessam à tese")
    analisador.add_argument("--amostra", type=int, default=0,
                            help="lê só os N primeiros arquivos")
    args = analisador.parse_args()

    caminhos = sorted(glob.glob(os.path.join(args.pasta, "**", "*.txt"),
                                recursive=True))
    if not caminhos:
        print(f"Nenhum .txt em {args.pasta}", file=sys.stderr)
        return 2
    if args.amostra:
        caminhos = caminhos[:args.amostra]

    print(f"{len(caminhos)} arquivos a ler em {args.pasta}")
    contagem, lidos, falhos = medir(caminhos, args.todos)
    print(f"{lidos} lidos" + (f", {falhos} falharam" if falhos else ""))
    if not contagem:
        print("Nenhuma linha de registro conhecido. A pasta é de EFD ICMS/IPI?",
              file=sys.stderr)
        return 2

    divergencias = relatar(contagem)
    print()
    if divergencias:
        print(f"{divergencias} divergência(s). A tabela precisa de revisão — "
              f"e de medição, não de leitura do Guia.")
        return 1
    print("Sem divergência: `registros_icms.CAMPOS` descreve estes arquivos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

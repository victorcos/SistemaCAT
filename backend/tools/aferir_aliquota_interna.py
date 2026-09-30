"""Que alíquota interna o cliente cobrou — a prova que não vem do MA.

O ICMS-ST presumido do relatório 839 se calcula com a alíquota interna do
estado, e ela precisa estar **conferida** antes de valer
(`sped/tabelas/tab_aliquota_icms.py`). Este comando produz metade da prova.

## Por que não conferir pelo relatório do escritório anterior

Porque seria circular. O relatório do MA traz a alíquota que **ele** atribuiu a
cada produto; conferir a nossa contra a dele é copiar a classificação alheia com
aparência de medição. A outra metade da prova é o ato legal do estado, que vai
escrito na linha da tabela; esta metade é o que o próprio cliente escriturou.

## O que ele mede

As saídas **internas tributadas integralmente** da EFD ICMS/IPI — CFOP 5xxx com
CST de ICMS 00 —, agrupadas por ano. A alíquota geral do estado é a que domina:
na DMINAS, 18% responde por 56% a 59% das linhas em todos os anos de 2021 a
2025, e as outras são produtos de alíquota reduzida ou majorada.

**Ler o degrau é o ponto.** Um estado que subiu a interna aparece aqui como
mudança de ano para ano, e é isso que diz quantas vigências a tabela precisa
ter. Uma tabela com um número só aplicaria a alíquota de hoje a uma operação de
2021, calada.

    python tools/aferir_aliquota_interna.py <pasta da EFD ICMS/IPI>
    python tools/aferir_aliquota_interna.py <pasta> --por-mes

**Isto é evidência, não decisão.** A moda das vendas de um cliente não é a lei:
um cliente cujo catálogo seja todo de cesta básica mostraria 12% como dominante.
Quem escreve a linha na tabela confronta este número com a legislação e assume o
que assinou.

**Não versiona dado de cliente.** Recebe o caminho por argumento e imprime
percentuais e contagens.
"""

from __future__ import annotations

import argparse
import collections
import glob
import os
import sys
from decimal import Decimal, InvalidOperation

from cat.infraestrutura.sped.leitor import BUFFER_DE_REDE, campos, codificacao_de, registro_de

# o leiaute do C190 da **EFD ICMS/IPI**, que não é o da EFD-Contribuições. Ver
# DECISOES de 22/09/2026: um leitor só para dois leiautes já devolveu a UF no
# lugar do CNPJ sem erro nenhum
C190 = ("REG", "CST_ICMS", "CFOP", "ALIQ_ICMS", "VL_OPR", "VL_BC_ICMS", "VL_ICMS",
        "VL_BC_ICMS_ST", "VL_ICMS_ST", "VL_RED_BC", "VL_IPI", "COD_OBS")

# tributada integralmente: é a operação em que a alíquota aparece limpa
CST_INTEGRAL = "00"


def _nomeado(valores: list[str]) -> dict[str, str]:
    completos = list(valores) + [""] * max(0, len(C190) - len(valores))
    return dict(zip(C190, completos))


def _numero(bruto: str) -> Decimal:
    texto = (bruto or "").strip()
    if not texto:
        return Decimal(0)
    try:
        return Decimal(texto.replace(".", "").replace(",", ".") if "," in texto else texto)
    except InvalidOperation:
        return Decimal(0)


def _quando(nome: str, por_mes: bool) -> str:
    """O ano — ou o mês — do nome do arquivo da EFD ICMS/IPI.

    O nome traz `…-aaaammdd-aaaammdd-…`, e é o começo do período que interessa.
    """
    for pedaco in nome.split("-"):
        if len(pedaco) == 8 and pedaco.isdigit():
            return f"{pedaco[:4]}-{pedaco[4:6]}" if por_mes else pedaco[:4]
    return "?"


def aferir(pasta: str, por_mes: bool) -> dict[str, collections.Counter]:
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.txt")))
    if not arquivos:
        raise SystemExit(f"nenhuma EFD ICMS/IPI em {pasta}")
    print(f"lendo {len(arquivos)} arquivos…", flush=True)

    por_periodo: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    for caminho in arquivos:
        periodo = _quando(os.path.basename(caminho), por_mes)
        codificacao = codificacao_de(caminho)
        with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
            for linha in arquivo:
                if registro_de(linha) != b"C190":
                    continue
                d = _nomeado(campos(linha.decode(codificacao, errors="replace")))
                if not d["CFOP"].startswith("5"):
                    continue
                if d["CST_ICMS"][-2:] != CST_INTEGRAL:
                    continue
                aliquota = _numero(d["ALIQ_ICMS"])
                if aliquota > 0:
                    por_periodo[periodo][str(aliquota.normalize())] += 1
    return por_periodo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("efd", help="pasta da EFD ICMS/IPI do cliente")
    parser.add_argument("--por-mes", action="store_true",
                        help="mês a mês, em vez de ano a ano — para achar o mês "
                             "exato em que a alíquota mudou")
    args = parser.parse_args()

    por_periodo = aferir(args.efd, args.por_mes)
    if not por_periodo:
        print("nenhuma saída interna tributada integralmente: não há o que aferir.")
        return 1

    print("\nalíquota nas saídas internas tributadas integralmente "
          "(CFOP 5xxx, CST 00):\n")
    print(f"  {'período':<10}{'linhas':>10}   as mais usadas")
    dominantes = []
    for periodo in sorted(por_periodo):
        contagem = por_periodo[periodo]
        total = sum(contagem.values())
        maiores = contagem.most_common(4)
        dominantes.append((periodo, maiores[0][0]))
        texto = "   ".join(f"{a}%: {100 * q / total:5.1f}%" for a, q in maiores)
        print(f"  {periodo:<10}{total:>10,}   {texto}".replace(",", "."))

    degraus = [(p, a) for (p, a), (_, anterior) in
               zip(dominantes[1:], dominantes) if a != anterior]
    print()
    if degraus:
        print("  DEGRAU: a alíquota dominante mudou em " +
              ", ".join(f"{p} (para {a}%)" for p, a in degraus))
        print("  A tabela precisa de uma vigência para cada um deles.")
    else:
        print(f"  Sem degrau: {dominantes[0][1]}% domina o período inteiro.")
    print("\n  Isto é evidência, não decisão. Confronte com a lei do estado antes "
          "de escrever a linha em `tab_aliquota_icms.INTERNA`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Leitor da ECF (Escrituração Contábil Fiscal) para a gestão de IRPJ/CSLL.

A ECF é pequena (poucos MB por ano), então é lida inteira em uma passada,
sem índice nem cache.

O que interessa à gestão:

- ``0000``/``0010`` — empresa, ano, forma de tributação e de apuração;
- ``M010``/``M500`` — contas da Parte B do e-Lalur/e-Lacs e seus saldos;
- ``M300``/``M350`` — Parte A do e-Lalur (IRPJ) e do e-Lacs (CSLL):
  lucro líquido, adições, exclusões e compensações;
- ``N500``/``N630`` (IRPJ) e ``N650``/``N670`` (CSLL) — cálculo do imposto.

Os códigos das linhas mudam de leiaute para leiaute (0008 a 0012 neste
projeto), mas a descrição é estável. Por isso as linhas-chave são
localizadas pela descrição normalizada (sem acento, em maiúsculas), com o
código apenas como desempate.

Portado do projeto Quebra de SPED em 22/09/2026. O registro 0000 passou a ser
lido pelo domínio, como todo 0000 nesta casa — e a ECF obrigou o domínio a
crescer: ela é o único dos quatro leiautes em que o CNPJ e o nome vêm **antes**
das datas, e em que pode haver uma terceira data (DT_SIT_ESP) colada ao par do
período. Ver `dominio/sped/cabecalho.py`.
"""
from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from cat.dominio.sped.cabecalho import (
    ArquivoNaoReconhecido,
    TipoSped,
    ler_cabecalho,
)
from cat.infraestrutura.gestao.numeros import ValorInvalido, centavos
from cat.log import obter_log

log = obter_log(__name__)

# Um período de apuração da ECF -> mês da coluna do relatório
_MES_DO_TRIMESTRE = {"T01": "03", "T02": "06", "T03": "09", "T04": "12"}


def normalizar(texto: str) -> str:
    """Sem acento, em maiúsculas e com espaços colapsados."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.upper().split())


@dataclass
class LinhaLalur:
    """Linha da Parte A do e-Lalur (M300) ou do e-Lacs (M350)."""
    codigo: str
    descricao: str
    tipo: str            # R rótulo, L linha calculada, A adição, E exclusão, P compensação
    ind_relacao: str     # 1..4 (vazio nas linhas de total)
    valor: int           # centavos
    rural: bool = False


@dataclass
class ContaParteB:
    codigo: str
    descricao: str
    tributo: str         # "I" (IRPJ) ou "C" (CSLL)
    saldo_final: int     # centavos, já com sinal (D positivo, C negativo)


@dataclass
class PeriodoECF:
    codigo: str          # T01..T04, A00, A01..A12
    mes: str             # "AAAA-MM" — coluna do relatório
    dt_ini: str = ""
    dt_fin: str = ""
    lalur: list[LinhaLalur] = field(default_factory=list)   # M300 (IRPJ)
    lacs: list[LinhaLalur] = field(default_factory=list)    # M350 (CSLL)
    # código da linha -> (descrição, valor em centavos)
    n500: dict[str, tuple[str, int]] = field(default_factory=dict)
    n630: dict[str, tuple[str, int]] = field(default_factory=dict)
    n650: dict[str, tuple[str, int]] = field(default_factory=dict)
    n670: dict[str, tuple[str, int]] = field(default_factory=dict)
    parte_b: list[ContaParteB] = field(default_factory=list)


@dataclass
class ApuracaoECF:
    arquivo: str
    cnpj: str = ""
    razao_social: str = ""
    dt_ini: str = ""
    dt_fin: str = ""
    cod_ver: str = ""
    forma_tributacao: str = ""   # 0010: 1 = Lucro Real
    forma_apuracao: str = ""     # 0010: T trimestral, A anual
    periodos: list[PeriodoECF] = field(default_factory=list)
    descartes: dict[str, int] = field(default_factory=dict)


class ArquivoECFInvalido(Exception):
    """O arquivo não tem registro 0000 de ECF (|0000|LECF|...)."""


def _detectar_encoding(path: Path) -> str:
    with open(path, "rb") as f:
        return "utf-8-sig" if f.read(3) == b"\xef\xbb\xbf" else "cp1252"


def _identificar(ap: ApuracaoECF, linha: str, nome: str) -> None:
    """A empresa e o exercício, pelo leitor do domínio.

    Quem conhece os leiautes do 0000 é `dominio/sped/cabecalho.py`, que acha
    cada campo pela forma. Ler por posição aqui é o erro que este projeto já
    cometeu duas vezes noutros leiautes.
    """
    try:
        c = ler_cabecalho(linha)
    except ArquivoNaoReconhecido as erro:
        raise ArquivoECFInvalido(f"{nome}: registro 0000 não reconhecido — {erro.motivo}") from erro
    if c.tipo is not TipoSped.ECF:
        raise ArquivoECFInvalido(f"{nome}: o 0000 é de {c.tipo.rotulo}, não de ECF")
    ap.cod_ver = c.versao_leiaute
    ap.cnpj = c.cnpj.valor if c.cnpj is not None else ""
    ap.razao_social = c.nome
    ap.dt_ini = c.inicio.strftime("%d%m%Y")
    ap.dt_fin = c.fim.strftime("%d%m%Y")


def _sinal(valor: int, indicador: str) -> int:
    """Saldo da Parte B: "D" (devedor) é positivo; "C" (credor), negativo.

    Confirmado contra o export do MA: prejuízo fiscal (saldo D) aparece
    positivo e reserva de subvenção (saldo C), negativa.
    """
    return -valor if (indicador or "").strip().upper() == "C" else valor


def ler_ecf(path: str | Path) -> ApuracaoECF:
    path = Path(path)
    encoding = _detectar_encoding(path)
    ap = ApuracaoECF(arquivo=str(path))
    nome = os.path.basename(str(path))
    log.info("gestão começou a ler a ecf", extra={"arquivo": nome, "codificacao": encoding})

    descricoes_b: dict[tuple[str, str], str] = {}   # (cod_cta_b, tributo) -> descrição
    periodo_m: PeriodoECF | None = None
    periodo_n: PeriodoECF | None = None
    periodos: dict[str, PeriodoECF] = {}
    secao_rural_m300 = False
    secao_rural_m350 = False

    def descartar(motivo: str, nlinha: int, **ctx) -> None:
        """Nunca em silêncio, mas também sem encher o log: as vinte primeiras."""
        ap.descartes[motivo] = ap.descartes.get(motivo, 0) + 1
        if ap.descartes[motivo] <= 20:
            log.warning("linha da ecf descartada na gestão", extra={
                "arquivo": nome, "motivo": motivo, "linha": nlinha, **ctx})

    def periodo(codigo: str) -> PeriodoECF:
        if codigo not in periodos:
            periodos[codigo] = PeriodoECF(codigo=codigo, mes=_mes_do_periodo(codigo, ap.dt_fin))
        return periodos[codigo]

    with open(path, "rb") as f:
        for nlinha, linha_b in enumerate(f, 1):
            if not linha_b.startswith(b"|"):
                continue
            linha = linha_b.rstrip(b"\r\n").decode(encoding, errors="replace")
            c = linha.split("|")[1:-1]
            if not c:
                continue
            reg = c[0]
            try:
                if reg == "0000":
                    _identificar(ap, linha, path.name)
                elif reg == "0010":
                    ap.forma_tributacao = c[3] if len(c) > 3 else ""
                    ap.forma_apuracao = c[4] if len(c) > 4 else ""
                elif reg == "M010":
                    descricoes_b[(c[1], c[6] if len(c) > 6 else "")] = c[2]
                elif reg in ("M030", "N030"):
                    p = periodo(c[3])
                    p.dt_ini, p.dt_fin = c[1], c[2]
                    if reg == "M030":
                        periodo_m, secao_rural_m300, secao_rural_m350 = p, False, False
                    else:
                        periodo_n = p
                elif reg in ("M300", "M350") and periodo_m is not None:
                    tipo = c[3] if len(c) > 3 else ""
                    desc = c[2] if len(c) > 2 else ""
                    rural_desc = "RURAL" in normalizar(desc)
                    if tipo == "R":  # rótulo: separa Atividade Geral de Atividade Rural
                        if reg == "M300":
                            secao_rural_m300 = rural_desc
                        else:
                            secao_rural_m350 = rural_desc
                        continue
                    secao_rural = secao_rural_m300 if reg == "M300" else secao_rural_m350
                    item = LinhaLalur(
                        codigo=c[1], descricao=desc, tipo=tipo,
                        ind_relacao=c[4] if len(c) > 4 else "",
                        valor=centavos(c[5]) if len(c) > 5 else 0,
                        rural=secao_rural or rural_desc,
                    )
                    (periodo_m.lalur if reg == "M300" else periodo_m.lacs).append(item)
                elif reg == "M500" and periodo_m is not None:
                    periodo_m.parte_b.append(ContaParteB(
                        codigo=c[1], descricao=descricoes_b.get((c[1], c[2]), ""),
                        tributo=c[2],
                        saldo_final=_sinal(centavos(c[9]), c[10] if len(c) > 10 else ""),
                    ))
                elif reg in ("N500", "N630", "N650", "N670") and periodo_n is not None:
                    destino = {"N500": periodo_n.n500, "N630": periodo_n.n630,
                               "N650": periodo_n.n650, "N670": periodo_n.n670}[reg]
                    destino[c[1]] = (c[2] if len(c) > 2 else "",
                                     centavos(c[3]) if len(c) > 3 else 0)
            except ArquivoECFInvalido:
                raise
            except (IndexError, ValorInvalido) as exc:
                descartar("linha_invalida", nlinha, registro=reg, erro=str(exc)[:120])

    if not ap.cnpj:
        raise ArquivoECFInvalido(f"{path.name}: registro 0000 de ECF não encontrado")

    ap.periodos = sorted(periodos.values(), key=lambda p: (p.mes, p.codigo))
    log.info("gestão terminou de ler a ecf", extra={
        "arquivo": nome, "cnpj": ap.cnpj, "ano": ap.dt_fin[-4:],
        "periodos": [p.codigo for p in ap.periodos],
        "forma_tributacao": ap.forma_tributacao, "forma_apuracao": ap.forma_apuracao,
        "descartes": ap.descartes,
    })
    return ap


def _mes_do_periodo(codigo: str, dt_fin: str) -> str:
    """T01 -> março; A00 -> dezembro; A01..A12 -> o próprio mês."""
    ano = dt_fin[-4:] if len(dt_fin) == 8 else ""
    codigo = (codigo or "").strip().upper()
    if codigo in _MES_DO_TRIMESTRE:
        return f"{ano}-{_MES_DO_TRIMESTRE[codigo]}"
    if codigo.startswith("A"):
        mes = codigo[1:]
        if mes.isdigit() and 1 <= int(mes) <= 12:
            return f"{ano}-{int(mes):02d}"
        return f"{ano}-12"
    return f"{ano}-12"

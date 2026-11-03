"""Bonificação na EFD-Contribuições: quanto de PIS/COFINS foi destacado num CFOP.

Lê todas as EFD-Contribuições de um grupo de empresas, filtra um conjunto de
CFOP (por padrão 5910/6910, remessa em bonificação, doação ou brinde) e devolve
os valores de PIS/COFINS **exatamente como escriturados**, por empresa, mês,
estabelecimento, CST e nota. Nasceu em 03/11/2026 para um grupo de 11 empresas
(empresas 25 a 35 do registro local) e espelha o trabalho de ICMS que já existia
para elas — mas a EFD-Contribuições tem três formas de escriturar a mesma saída,
e o leitor cobre as três:

```
C010 > C100 (IND_OPER=1) > C170     item a item, com CFOP por item
C010 > C100 (IND_OPER=1) > C175     NFC-e consolidada por CFOP dentro da nota
C010 > C180 > C181 + C185           consolidado por produto × CFOP × CST, SEM nota
```

**O casamento C181 × C185 não é por posição.** `sped/consolidado.py` casa pela
posição, com base no dado em que nasceu. Na empresa 28 isso falha: os filhos de
PIS vêm numa ordem e os de COFINS em outra, e um 5102 do PIS caía ao lado de um
5910 do COFINS — o resultado saía inflado em duzentas vezes. Aqui cada C181 de
CFOP alvo procura, dentro do mesmo C180, o C185 de mesmo CFOP e mesmo valor
(depois, só mesmo CFOP); o que sobra sai com o outro lado em branco. Conferido
ao centavo contra uma recontagem lado a lado (175.801 linhas, 03/11/2026).

**Zero no filtro de CFOP não quer dizer "sem bonificação".** Na empresa 32 a EFD
ICMS/IPI tem 350 mil notas 5910 e a EFD-Contribuições não tem nenhuma — nem por
chave, nem por série/número. O subcomando `cruzar` recebe um CSV de chaves (de
onde quer que tenham vindo) e diz, nota a nota, se a nota existe na
Contribuições, com que CFOP e CST, e quanto destacou. Só vale no mês escriturado
item a item; no mês consolidado não há nota para procurar, e ele diz isso.

    # 1. ler tudo e gravar a planilha (leitura em paralelo, um pickle por arquivo, retomável)
    python tools/bonificacao_contribuicoes.py extrair --grupo \\\\192.168.88.22\\FISCALSP\\<grupo> \\
        --trabalho D:\\trabalho\\bonif --saida D:\\trabalho\\bonif\\Bonificacao_PISCOFINS.xlsx [--cfop 5910,6910]

    # 2. cruzar chaves de NF-e (CSV ; com colunas empresa;cnpj;competencia;chave, demais colunas passam)
    python tools/bonificacao_contribuicoes.py cruzar --grupo ... --trabalho ... \\
        --chaves D:\\trabalho\\chaves.csv --saida D:\\trabalho\\bonif\\Cruzamento.xlsx

Regras que vêm da rede, não da teoria: o mês com mais de um arquivo usa o de
transmissão mais recente (data no nome `PISCOFINS_<ini>_<fim>_<CNPJ>_<tipo>_<AAAAMMDDhhmmss>_<hash>.txt`,
senão a data do arquivo); caminho acima de 260 caracteres abre com `\\\\?\\UNC\\`;
o arquivo é lido até o 9999 e conferido contra QTD_LIN; a assinatura binária
depois do 9999 é ignorada. Prefira o caminho por IP ao `Z:`.

Sem pandas de propósito: a pilha do motor é DuckDB + xlsxwriter (ARQUITETURA
§7), e a agregação aqui cabe em dicionário. Não versiona dado de cliente: recebe
os caminhos por argumento e grava a saída onde for mandado.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import logging
import os
import pickle
import re
import sys
import time
import traceback
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

import xlsxwriter

from cat.infraestrutura.arquivos.inventario_contribuicoes import caminho_longo
from cat.log import FormatadorJson, configurar, contexto, obter_log

log = obter_log("bonificacao_contribuicoes")

CFOP_PADRAO = ("5910", "6910")
VENDA = frozenset({"5101", "5102", "5401", "5403", "5405", "6101", "6102", "6401", "6403", "6404", "5104", "5106",
                   "6106", "5117", "6117", "5119", "5120", "6108", "6107"})
SIT_INVALIDA = frozenset({"02", "03", "04", "05"})  # cancelada, cancelada extemporânea, denegada, inutilizada
LIMITE_EXCEL = 1_048_576 - 1
PASTA_SPED_PADRAO = os.path.join("6. RECEITANET BX", "SPED Contribuições")
RE_NOME = re.compile(r"PISCOFINS_(\d{8})_(\d{8})_(\d{14})_(Original|Retificadora)_(\d{14})_", re.I)
CST_DESCR = {
    "01": "Tributável (alíquota básica)", "02": "Tributável (alíquota diferenciada)",
    "03": "Tributável (alíquota por unidade)", "04": "Monofásico - alíquota zero",
    "05": "Substituição tributária", "06": "Alíquota zero", "07": "Isenta",
    "08": "Sem incidência", "09": "Suspensão", "49": "Outras saídas",
}
COL_NOTAS = ["Empresa", "CNPJ emitente", "UF", "Competência", "Fonte", "Emissão", "Modelo", "Situação", "Série",
             "Número", "Chave", "Cliente", "CNPJ/CPF cliente", "CFOPs da nota", "Tipo de nota", "CFOP alvo",
             "CST PIS", "CST COFINS", "Alíq. PIS", "Alíq. COFINS", "Valor da nota", "Itens no CFOP",
             "Valor no CFOP", "Desconto", "BC PIS", "PIS", "BC COFINS", "COFINS", "PIS da nota (C100)",
             "COFINS da nota (C100)"]
COL_CONS = ["Empresa", "CNPJ estabelecimento", "UF", "Competência", "Período ini (C180)", "Período fim (C180)",
            "Cód. item", "Descrição (0200)", "NCM", "Total do item no mês (C180)", "CFOP",
            "CST PIS", "Valor (C181)", "Desconto (C181)", "BC PIS", "Alíq. PIS", "PIS",
            "CST COFINS", "Valor (C185)", "Desconto (C185)", "BC COFINS", "Alíq. COFINS", "COFINS", "Observação"]
VALORES = ["Valor no CFOP", "BC PIS", "PIS", "BC COFINS", "COFINS"]


# --------------------------------------------------------------------------- utilidades
def _num(bruto: str, cont: Counter, amostras: list, arquivo: str, linha: int, campo: str) -> float:
    """Número do SPED (vírgula decimal). Valor inválido conta e guarda amostra — nunca some em silêncio."""
    if not bruto:
        return 0.0
    try:
        return float(bruto.replace(",", "."))
    except ValueError:
        cont["valor_invalido"] += 1
        if len(amostras) < 20:
            amostras.append({"arquivo": arquivo, "linha": linha, "campo": campo, "valor": bruto})
        return 0.0


def _data(bruto: str) -> _dt.date | None:
    try:
        return _dt.date(int(bruto[4:]), int(bruto[2:4]), int(bruto[:2]))
    except (ValueError, IndexError):
        return None


def competencia_de(dt_ini: str) -> str:
    return f"{dt_ini[2:4]}/{dt_ini[4:]}"


def _ord(comp: str) -> str:
    """'MM/AAAA' -> 'AAAAMM', para ordenar."""
    return comp[3:] + comp[:2]


def prazo_prescricional(comp: str) -> _dt.date:
    """Vencimento de PIS/COFINS = dia 25 do mês seguinte; prazo conservador = 5 anos dali."""
    m, a = int(comp[:2]), int(comp[3:])
    m += 1
    if m == 13:
        m, a = 1, a + 1
    return _dt.date(a + 5, m, 25)


def _fmt_set(valores) -> str:
    return "/".join(sorted(v for v in valores if v))


def _fmt_aliq(valores) -> str:
    return "/".join(sorted({v.replace(".", ",") for v in valores if v}, key=lambda s: float(s.replace(",", "."))))


def _classe(cfops: set[str], alvo: tuple[str, ...]) -> str:
    if not cfops:
        return "sem item"
    if cfops & set(alvo):
        return "/".join(alvo) + " (CFOP alvo)"
    if cfops & VENDA:
        return "CFOP de venda (" + "/".join(sorted(cfops & VENDA)) + ")"
    return "outro CFOP (" + "/".join(sorted(cfops)) + ")"


class _Soma:
    """Soma por chave, n colunas numéricas. É o group-by deste módulo."""

    def __init__(self, n: int):
        self.n = n
        self.d: dict[tuple, list[float]] = {}

    def add(self, chave: tuple, *valores: float) -> None:
        a = self.d.setdefault(chave, [0.0] * self.n)
        for i, v in enumerate(valores):
            a[i] += v

    def linhas(self, ordem=None) -> list[tuple]:
        return sorted(((k, v) for k, v in self.d.items()), key=ordem or (lambda kv: kv[0]))


# --------------------------------------------------------------------------- inventário
def cabecalho(caminho: str) -> dict | None:
    with open(caminho_longo(caminho), "rb") as fh:
        primeira = fh.readline(4096)
    f = primeira.decode("latin-1").rstrip("\r\n").split("|")
    if len(f) < 10 or f[1] != "0000":
        return None
    return {"cod_ver": f[2], "tipo_escrit": f[3], "dt_ini": f[6], "dt_fin": f[7], "nome": f[8], "cnpj": f[9],
            "uf": f[10] if len(f) > 10 else ""}


def escolher_arquivos(grupo: str, pasta_sped: str = PASTA_SPED_PADRAO) -> tuple[list[dict], list[dict]]:
    """Uma pasta por empresa (`<nome>_<CNPJ>` ou só `<nome>`), e dentro dela a pasta dos SPED.

    Devolve (usados, todos): um arquivo por (CNPJ do 0000, competência) — o de transmissão
    mais recente — e a lista completa com a situação de cada um.
    """
    escolhidos: dict[tuple, dict] = {}
    todos: list[dict] = []
    for pasta in sorted(os.listdir(grupo)):
        if not os.path.isdir(os.path.join(grupo, pasta)):
            continue
        m = re.match(r"^(.*)_(\d{14})$", pasta)
        empresa, cnpj_pasta = (m.group(1), m.group(2)) if m else (pasta, "")
        dir_sped = os.path.join(grupo, pasta, pasta_sped)
        if not os.path.isdir(dir_sped):
            if not m:  # nem sufixo de CNPJ nem SPED: é pasta de análise, não de empresa
                log.debug("pasta ignorada: não parece empresa", extra={"pasta": pasta})
                continue
            log.warning("empresa sem pasta de SPED Contribuições", extra={"empresa": empresa, "pasta": dir_sped})
            todos.append({"empresa": empresa, "cnpj_pasta": cnpj_pasta, "caminho": "", "situacao": "sem pasta"})
            continue
        arquivos = [a for a in os.listdir(dir_sped) if a.lower().endswith(".txt")]
        if not arquivos:
            log.warning("pasta de SPED Contribuições vazia", extra={"empresa": empresa, "pasta": dir_sped})
            todos.append({"empresa": empresa, "cnpj_pasta": cnpj_pasta, "caminho": "", "situacao": "pasta vazia"})
            continue
        for a in sorted(arquivos):
            p = os.path.join(dir_sped, a)
            try:
                st = os.stat(caminho_longo(p))
                cab = cabecalho(p)
            except OSError as e:
                log.error("não consegui abrir o arquivo", extra={"empresa": empresa, "arquivo": p, "erro": str(e)})
                todos.append({"empresa": empresa, "cnpj_pasta": cnpj_pasta, "caminho": p, "situacao": f"erro: {e}"})
                continue
            if cab is None:
                log.warning("arquivo sem registro 0000 na primeira linha", extra={"empresa": empresa, "arquivo": p})
                todos.append({"empresa": empresa, "cnpj_pasta": cnpj_pasta, "caminho": p, "situacao": "sem 0000"})
                continue
            mn = RE_NOME.search(a)
            transmissao = mn.group(5) if mn else _dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y%m%d%H%M%S")
            info = {"empresa": empresa, "cnpj_pasta": cnpj_pasta, "caminho": p, "tamanho": st.st_size,
                    "transmissao": transmissao, "nome_arquivo": a, **cab,
                    "competencia": competencia_de(cab["dt_ini"]), "situacao": ""}
            chave = (cab["cnpj"], cab["dt_ini"][4:] + cab["dt_ini"][2:4])
            atual = escolhidos.get(chave)
            if atual is None or transmissao > atual["transmissao"]:
                if atual is not None:
                    atual["situacao"] = "substituído por versão mais recente"
                escolhidos[chave] = info
            else:
                info["situacao"] = "substituído por versão mais recente"
            todos.append(info)
    usados = sorted(escolhidos.values(), key=lambda i: (i["empresa"], i["dt_ini"][4:] + i["dt_ini"][2:4]))
    for u in usados:
        u["situacao"] = "usado"
    log.info("inventário fechado", extra={"arquivos": len([t for t in todos if t["caminho"]]), "usados": len(usados),
                                        "empresas": len({u["empresa"] for u in usados})})
    return usados, todos


# --------------------------------------------------------------------------- leitura de 1 arquivo
def ler_arquivo(info: dict, alvo: tuple[str, ...] = CFOP_PADRAO) -> dict:
    """Lê uma EFD-Contribuições inteira e devolve só o que interessa aos CFOP alvo.

    Roda em processo filho: não loga, devolve contadores e amostras para quem chamou logar.
    """
    caminho, empresa, comp = info["caminho"], info["empresa"], info["competencia"]
    alvo_b = tuple(f"|{c}|".encode() for c in alvo)
    cont: Counter = Counter()
    amostras: list = []
    avisos: list = []
    part: dict[str, tuple[str, str]] = {}
    itens0200: dict[str, tuple[str, str]] = {}
    uf_estab: dict[str, str] = {}
    estab = info["cnpj"]
    notas: list = []
    itens_cst: dict = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    consolidado: list = []
    apuracao: dict = {"pis": {}, "cofins": {}}
    qtd_lin_9999 = None
    linhas = 0
    nota = None
    nota_itens: list = []
    nota_cfops: set = set()
    c180 = None
    c181: list = []
    c185: list = []

    def dec(raw: bytes) -> list[str]:
        return raw.decode("latin-1").rstrip("\r\n").split("|")

    def fechar_nota():
        nonlocal nota, nota_itens, nota_cfops
        if nota is not None and nota_itens:
            tipo = "Junto com a venda" if nota_cfops & VENDA else "Nota própria"
            notas.append((empresa, estab, uf_estab.get(estab, ""), comp, nota["fonte"], nota["dt"], nota["mod"],
                          nota["sit"], nota["ser"], nota["num"], nota["chv"], nota["cli_nome"], nota["cli_doc"],
                          _fmt_set(nota_cfops), tipo, _fmt_set(i[10] for i in nota_itens),
                          _fmt_set(i[0] for i in nota_itens), _fmt_set(i[1] for i in nota_itens),
                          _fmt_aliq(i[2] for i in nota_itens), _fmt_aliq(i[3] for i in nota_itens),
                          nota["vl_doc"], len(nota_itens), sum(i[4] for i in nota_itens), sum(i[5] for i in nota_itens),
                          sum(i[6] for i in nota_itens), sum(i[7] for i in nota_itens), sum(i[8] for i in nota_itens),
                          sum(i[9] for i in nota_itens), nota["vl_pis_doc"], nota["vl_cof_doc"]))
            cont[f"notas_{nota['fonte']}"] += 1
            for i in nota_itens:
                ag = itens_cst[(empresa, estab, comp, nota["fonte"], i[10], i[0], i[2], i[1], i[3])]
                ag[0] += 1
                for pos, val in zip(range(1, 7), i[4:10]):
                    ag[pos] += val
        nota = None
        nota_itens = []
        nota_cfops = set()

    def fechar_c180():
        nonlocal c180, c181, c185
        if c180 is not None and (c181 or c185):
            if len(c181) != len(c185):
                cont["c180_filhos_desbalanceados"] += 1
                if len(avisos) < 20:
                    avisos.append({"arquivo": caminho, "cod_item": c180["cod_item"], "c181": len(c181), "c185": len(c185)})
            # casamento por CFOP e valor, nunca por posição (ver o topo do módulo)
            pares: list = []
            livres_b = [b for b in c185 if b[1] in alvo]
            for a in c181:
                if a[1] not in alvo:
                    continue
                par = next((b for b in livres_b if b[1] == a[1] and abs(a[2] - b[2]) <= 0.005 and abs(a[3] - b[3]) <= 0.005), None)
                if par is None:
                    par = next((b for b in livres_b if b[1] == a[1]), None)
                if par is not None:
                    livres_b.remove(par)
                pares.append((a, par))
            pares.extend((None, b) for b in livres_b)
            descr, ncm = itens0200.get(c180["cod_item"], ("", ""))
            for a, b in pares:
                if a and b:
                    diverg = "VL_ITEM difere entre C181 e C185" if abs(a[2] - b[2]) > 0.005 else ""
                    if diverg:
                        cont["c181_c185_valor_divergente"] += 1
                elif a is None:
                    diverg = "sem C181 correspondente (só COFINS)"
                    cont["c185_sem_c181"] += 1
                else:
                    diverg = "sem C185 correspondente (só PIS)"
                    cont["c181_sem_c185"] += 1
                consolidado.append((empresa, estab, uf_estab.get(estab, ""), comp, c180["dt_ini"], c180["dt_fin"],
                                    c180["cod_item"], descr, ncm, c180["vl_tot_item"], (a or b)[1],
                                    a[0] if a else "", a[2] if a else 0.0, a[3] if a else 0.0,
                                    a[4] if a else 0.0, a[5] if a else "", a[6] if a else 0.0,
                                    b[0] if b else "", b[2] if b else 0.0, b[3] if b else 0.0,
                                    b[4] if b else 0.0, b[5] if b else "", b[6] if b else 0.0, diverg))
                cont["linhas_consolidadas"] += 1
        c180 = None
        c181 = []
        c185 = []

    t0 = time.time()
    with open(caminho_longo(caminho), "rb", buffering=4 * 1024 * 1024) as fh:
        for raw in fh:
            if not raw.startswith(b"|"):
                cont["linha_fora_do_padrao"] += 1
                continue
            linhas += 1
            reg = raw[1:5]
            if reg == b"C170":
                if nota is None:
                    continue
                if not any(a in raw for a in alvo_b):
                    try:  # só o CFOP, para saber se a nota é "junto com a venda"
                        nota_cfops.add(raw.split(b"|", 12)[11].decode("latin-1"))
                    except IndexError:
                        cont["c170_curto"] += 1
                    continue
                f = dec(raw)
                if len(f) < 37:
                    cont["c170_curto"] += 1
                    continue
                cfop = f[11]
                nota_cfops.add(cfop)
                if cfop not in alvo:
                    continue
                n = lambda i, c: _num(f[i], cont, amostras, caminho, linhas, c)  # noqa: E731
                nota_itens.append((f[25], f[31], f[27], f[33], n(7, "VL_ITEM"), n(8, "VL_DESC"),
                                   n(26, "VL_BC_PIS"), n(30, "VL_PIS"), n(32, "VL_BC_COFINS"), n(36, "VL_COFINS"), cfop))
                cont["itens_alvo_c170"] += 1
            elif reg == b"C175":
                if nota is None:
                    continue
                f = dec(raw)
                if len(f) < 17:
                    cont["c175_curto"] += 1
                    continue
                cfop = f[2]
                nota_cfops.add(cfop)
                if cfop not in alvo:
                    continue
                n = lambda i, c: _num(f[i], cont, amostras, caminho, linhas, c)  # noqa: E731
                nota["fonte"] = "C175"
                nota_itens.append((f[5], f[11], f[7], f[13], n(3, "VL_OPR"), n(4, "VL_DESC"),
                                   n(6, "VL_BC_PIS"), n(10, "VL_PIS"), n(12, "VL_BC_COFINS"), n(16, "VL_COFINS"), cfop))
                cont["linhas_alvo_c175"] += 1
            elif reg == b"C100":
                fechar_nota()
                f = dec(raw)
                if len(f) < 28:
                    cont["c100_curto"] += 1
                    continue
                if f[2] != "1":
                    cont["c100_entrada"] += 1
                    continue
                if f[6] in SIT_INVALIDA:
                    cont[f"c100_saida_descartada_sit_{f[6]}"] += 1
                    continue
                cont["c100_saida"] += 1
                cli = part.get(f[4], ("", ""))
                n = lambda i, c: _num(f[i], cont, amostras, caminho, linhas, c)  # noqa: E731
                nota = {"fonte": "C170", "dt": _data(f[10]), "mod": f[5], "sit": f[6], "ser": f[7], "num": f[8],
                        "chv": f[9], "cli_nome": cli[0], "cli_doc": cli[1], "vl_doc": n(12, "VL_DOC"),
                        "vl_pis_doc": n(26, "VL_PIS"), "vl_cof_doc": n(27, "VL_COFINS")}
            elif reg == b"C181" or reg == b"C185":
                if c180 is None:
                    cont["c18x_sem_c180"] += 1
                    continue
                f = dec(raw)
                if len(f) < 11:
                    cont["c18x_curto"] += 1
                    continue
                n = lambda i, c: _num(f[i], cont, amostras, caminho, linhas, c)  # noqa: E731
                filho = (f[2], f[3], n(4, "VL_ITEM"), n(5, "VL_DESC"), n(6, "VL_BC"), f[7], n(10, "VL_CONTRIB"))
                (c181 if reg == b"C181" else c185).append(filho)
            elif reg == b"C180":
                fechar_c180()
                f = dec(raw)
                if len(f) < 9:
                    cont["c180_curto"] += 1
                    continue
                c180 = {"cod_item": f[5], "dt_ini": f[3], "dt_fin": f[4],
                        "vl_tot_item": _num(f[8], cont, amostras, caminho, linhas, "VL_TOT_ITEM")}
                cont["c180"] += 1
            elif reg == b"C010":
                fechar_nota()
                fechar_c180()
                estab = dec(raw)[2]
                cont["estabelecimentos"] += 1
            elif reg == b"0150":
                f = dec(raw)
                if len(f) >= 7:
                    part[f[2]] = (f[3], f[5] or f[6])
            elif reg == b"0200":
                f = dec(raw)
                if len(f) >= 9:
                    itens0200[f[2]] = (f[3], f[8])
            elif reg == b"0140":
                f = dec(raw)
                if len(f) >= 6:
                    uf_estab[f[4]] = f[5]
            elif reg in (b"C190", b"C990", b"C001"):
                fechar_nota()
                fechar_c180()
            elif reg == b"M200" or reg == b"M600":
                f = dec(raw)
                if len(f) >= 14:
                    n = lambda i, c: _num(f[i], cont, amostras, caminho, linhas, c)  # noqa: E731
                    apuracao["pis" if reg == b"M200" else "cofins"] = {
                        "nc_periodo": n(2, "VL_TOT_CONT_NC_PER"), "cred_desc": n(3, "VL_TOT_CRED_DESC"),
                        "nc_recolher": n(8, "VL_CONT_NC_REC"), "cum_recolher": n(12, "VL_CONT_CUM_REC"),
                        "total_recolher": n(13, "VL_TOT_CONT_REC")}
            elif reg == b"9999":
                f = dec(raw)
                try:
                    qtd_lin_9999 = int(f[2])
                except (ValueError, IndexError):
                    qtd_lin_9999 = None
                break
    fechar_nota()
    fechar_c180()
    cont["linhas_lidas"] = linhas
    valido = qtd_lin_9999 is not None and qtd_lin_9999 == linhas
    if not valido:
        cont["arquivo_qtd_lin_divergente"] += 1
    return {"info": info, "notas": notas, "itens_cst": dict(itens_cst), "consolidado": consolidado,
            "apuracao": apuracao, "contadores": dict(cont), "amostras_invalidas": amostras, "avisos": avisos,
            "qtd_lin_9999": qtd_lin_9999, "linhas": linhas, "valido": valido, "segundos": round(time.time() - t0, 1)}


def _tarefa_ler(args: tuple) -> dict:
    info, pasta_pickle, alvo = args
    destino = os.path.join(pasta_pickle, f"{info['cnpj']}_{info['dt_ini'][4:]}{info['dt_ini'][2:4]}.pkl")
    if os.path.exists(destino):
        with open(destino, "rb") as fh:
            antigo = pickle.load(fh)
        if antigo["info"]["caminho"] == info["caminho"] and antigo["info"]["tamanho"] == info["tamanho"] \
                and antigo.get("alvo") == tuple(alvo):
            antigo["reaproveitado"] = True
            return antigo
    try:
        res = ler_arquivo(info, alvo)
    except Exception:  # o filho não loga: devolve o traceback para o pai registrar
        return {"info": info, "erro": traceback.format_exc()}
    res["alvo"] = tuple(alvo)
    with open(destino, "wb") as fh:
        pickle.dump(res, fh, protocol=pickle.HIGHEST_PROTOCOL)
    res["reaproveitado"] = False
    return res


def extrair(usados: list[dict], pasta_trabalho: str, workers: int, alvo: tuple[str, ...]) -> list[dict]:
    pasta_pickle = os.path.join(pasta_trabalho, "_leitura")
    os.makedirs(pasta_pickle, exist_ok=True)
    total_bytes = sum(u["tamanho"] for u in usados)
    feitos = 0
    resultados: list[dict] = []
    t0 = time.time()
    log.info("leitura: início", extra={"arquivos": len(usados), "gb": round(total_bytes / 1e9, 2), "workers": workers})
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futuros = {ex.submit(_tarefa_ler, (u, pasta_pickle, alvo)): u for u in sorted(usados, key=lambda u: -u["tamanho"])}
        for fut in as_completed(futuros):
            u = futuros[fut]
            feitos += u["tamanho"]
            try:
                res = fut.result()
            except Exception as e:  # pool quebrado
                log.error("worker falhou", extra={"arquivo": u["caminho"], "erro": repr(e)})
                resultados.append({"info": u, "erro": repr(e)})
                continue
            if "erro" in res:
                log.error("falha ao ler o arquivo", extra={"empresa": u["empresa"], "arquivo": u["caminho"],
                                                          "erro": res["erro"][-800:]})
            else:
                c = res["contadores"]
                nivel = logging.WARNING if (not res["valido"] or c.get("valor_invalido")) else logging.DEBUG
                log.log(nivel, "arquivo lido", extra={
                    "empresa": u["empresa"], "competencia": u["competencia"], "arquivo": u["nome_arquivo"],
                    "mb": round(u["tamanho"] / 1e6, 1), "segundos": res["segundos"], "reaproveitado": res.get("reaproveitado"),
                    "linhas": res["linhas"], "qtd_lin_9999": res["qtd_lin_9999"], "valido": res["valido"],
                    "notas_c170": c.get("notas_C170", 0), "notas_c175": c.get("notas_C175", 0),
                    "consolidado": c.get("linhas_consolidadas", 0), "valores_invalidos": c.get("valor_invalido", 0),
                    "amostras": res["amostras_invalidas"][:5]})
            resultados.append(res)
            print(f"  progresso {feitos / total_bytes * 100 if total_bytes else 100:5.1f}%  "
                  f"{len(resultados)}/{len(usados)} arquivos  {time.time() - t0:6.0f}s", file=sys.stderr, flush=True)
    log.info("leitura: fim", extra={"segundos": round(time.time() - t0), "arquivos": len(resultados),
                                   "com_erro": sum(1 for r in resultados if "erro" in r)})
    return resultados


def carregar_leituras(usados: list[dict], pasta_trabalho: str) -> list[dict]:
    pasta_pickle = os.path.join(pasta_trabalho, "_leitura")
    resultados = []
    for u in usados:
        p = os.path.join(pasta_pickle, f"{u['cnpj']}_{u['dt_ini'][4:]}{u['dt_ini'][2:4]}.pkl")
        if os.path.exists(p):
            with open(p, "rb") as fh:
                resultados.append(pickle.load(fh))
        else:
            log.warning("arquivo sem leitura gravada — rode sem --so-planilha", extra={"arquivo": u["caminho"]})
    return resultados


# --------------------------------------------------------------------------- escrita do Excel
class _Excel:
    """Abas de um xlsxwriter: cabeçalho fixo, filtro, largura e formato por tipo de coluna."""

    def __init__(self, caminho: str):
        os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
        self.caminho = caminho
        self.wb = xlsxwriter.Workbook(caminho, {"constant_memory": False})
        self.f_num = self.wb.add_format({"num_format": "#,##0.00"})
        self.f_int = self.wb.add_format({"num_format": "#,##0"})
        self.f_data = self.wb.add_format({"num_format": "dd/mm/yyyy"})
        self.f_hdr = self.wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True,
                                         "valign": "top", "border": 1})
        self.abas: dict[str, int] = {}

    def aba(self, nome: str, colunas: list[str], linhas: list, larguras: dict | None = None) -> None:
        if len(linhas) > LIMITE_EXCEL:
            csv_ = os.path.join(os.path.dirname(os.path.abspath(self.caminho)),
                                f"{os.path.splitext(os.path.basename(self.caminho))[0]}_{nome}.csv")
            log.warning("aba acima do limite do Excel — gravada até o limite; CSV completo ao lado",
                        extra={"aba": nome, "linhas": len(linhas), "csv": csv_})
            with open(csv_, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow(colunas)
                for l in linhas:
                    w.writerow([str(v).replace(".", ",") if isinstance(v, float) else v for v in l])
            linhas = linhas[:LIMITE_EXCEL]
        ws = self.wb.add_worksheet(nome)
        tipos: list = [None] * len(colunas)
        larg = [len(c) + 2 for c in colunas]
        for l in linhas[:5000]:
            for j, v in enumerate(l):
                if v is None or v == "":
                    continue
                if tipos[j] is None:
                    tipos[j] = type(v)
                larg[j] = max(larg[j], min(len(str(v)) + 2, 60))
        for j, c in enumerate(colunas):
            ws.write(0, j, c, self.f_hdr)
            t = tipos[j]
            fmt = self.f_num if t is float else self.f_int if t is int else self.f_data if t in (_dt.date, _dt.datetime) else None
            ws.set_column(j, j, (larguras or {}).get(c) or max(larg[j], 14 if t is float else 12), fmt)
        for i, l in enumerate(linhas, 1):
            for j, v in enumerate(l):
                if isinstance(v, (_dt.date, _dt.datetime)):
                    ws.write_datetime(i, j, v if isinstance(v, _dt.datetime) else _dt.datetime(v.year, v.month, v.day), self.f_data)
                elif v is None:
                    pass
                else:
                    ws.write(i, j, v)
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, max(len(linhas), 1), len(colunas) - 1)
        self.abas[nome] = len(linhas)
        log.info("aba gravada", extra={"aba": nome, "linhas": len(linhas)})

    def fechar(self) -> None:
        self.wb.close()


# --------------------------------------------------------------------------- planilha
def planilha(resultados: list[dict], todos: list[dict], saida: str, grupo: str, alvo: tuple[str, ...],
             hoje: _dt.date | None = None) -> dict:
    hoje = hoje or _dt.date.today()
    ok = [r for r in resultados if "erro" not in r]
    cfops = "/".join(alvo)
    notas = [list(n) for r in ok for n in r["notas"]]
    cons = [list(c) for r in ok for c in r["consolidado"]]
    for c in cons:
        c.append(c[12] if c[12] else c[18])  # valor do lado que existe (col. 24, de trabalho)

    # ---- por CFOP × CST, e mensal por estabelecimento
    cst = _Soma(7)   # linhas, valor, desconto, bc_pis, pis, bc_cof, cof
    mensal = _Soma(6)  # linhas, valor, bc_pis, pis, bc_cof, cof
    for r in ok:
        for k, v in r["itens_cst"].items():
            cst.add((k[0], k[3], k[4], k[5], k[6], k[7], k[8]), *v)
    for n in notas:
        mensal.add((n[0], n[1], n[3], n[4]), 1, n[22], n[24], n[25], n[26], n[27])
    for c in cons:
        cst.add((c[0], "C181/C185", c[10], c[11], c[15], c[17], c[21]), 1, c[24], c[13], c[14], c[16], c[20], c[22])
        mensal.add((c[0], c[1], c[3], "C181/C185"), 1, c[24], c[14], c[16], c[20], c[22])
    apur = {}
    for r in ok:
        apur.setdefault((r["info"]["empresa"], r["info"]["competencia"]), (
            r["apuracao"]["pis"].get("total_recolher", 0.0), r["apuracao"]["cofins"].get("total_recolher", 0.0),
            r["apuracao"]["pis"].get("nc_periodo", 0.0), r["apuracao"]["cofins"].get("nc_periodo", 0.0)))

    col_mensal = ["Empresa", "CNPJ", "Competência", "Fonte", "Linhas", *VALORES, "PIS + COFINS",
                  "PIS a recolher no mês (M200)", "COFINS a recolher no mês (M600)", "PIS apurado no mês (M200)",
                  "COFINS apurado no mês (M600)", "Situação do mês", "Prazo prescricional (conservador)", "Dias até prescrever"]
    l_mensal = []
    for (emp, cnpj, comp, fonte), v in mensal.linhas(lambda kv: (kv[0][0], kv[0][1], _ord(kv[0][2]), kv[0][3])):
        a = apur.get((emp, comp), (0.0, 0.0, 0.0, 0.0))
        prazo = prazo_prescricional(comp)
        l_mensal.append([emp, cnpj, comp, fonte, int(v[0]), v[1], v[2], v[3], v[4], v[5], v[3] + v[5], a[0], a[1], a[2], a[3],
                         "Houve PIS/COFINS a recolher" if a[0] + a[1] > 0 else "Sem contribuição a recolher (crédito ≥ débito)",
                         prazo, (prazo - hoje).days])

    # ---- painel por empresa
    empresas = sorted({t["empresa"] for t in todos})
    sem_arquivo = {t["empresa"]: t["situacao"] for t in todos if not t["caminho"]}
    com_bloco_c = {r["info"]["empresa"] for r in ok if r["contadores"].get("c100_saida") or r["contadores"].get("c180")}
    lidas = {r["info"]["empresa"] for r in ok}
    com_alvo = {l[0] for l in l_mensal}
    col_painel = ["Empresa", "Fonte(s)", "1ª competência", "Última competência", "Notas (C170/C175)",
                  "Linhas consolidadas (C181/C185)", *VALORES, "PIS + COFINS", "PIS + COFINS que prescreve em 180 dias",
                  "1º prazo prescricional", "Observação"]
    l_painel = []
    for emp in empresas:
        g = [l for l in l_mensal if l[0] == emp]
        comps = sorted({l[2] for l in g}, key=_ord)
        obs = (f"Sem EFD-Contribuições na pasta ({sem_arquivo[emp]})" if emp in sem_arquivo
               else "EFD-Contribuições sem bloco C (nenhum C100/C180)" if emp in lidas and emp not in com_bloco_c
               else f"Sem CFOP {cfops} em nenhum arquivo" if emp in lidas and emp not in com_alvo else "")
        l_painel.append([emp, "/".join(sorted({l[3] for l in g})), comps[0] if comps else "", comps[-1] if comps else "",
                         sum(l[4] for l in g if l[3] != "C181/C185"), sum(l[4] for l in g if l[3] == "C181/C185"),
                         *[sum(l[i] for l in g) for i in range(5, 11)],
                         sum(l[10] for l in g if l[17] <= 180), min((l[16] for l in g), default=None), obs])
    l_painel.append(["TOTAL", "", "", "", *[sum(l[i] for l in l_painel) for i in range(4, 13)], None, ""])

    # ---- por ano
    por_ano = _Soma(8)
    for l in l_mensal:
        por_ano.add((l[0], l[2][3:]), l[4], l[5], l[6], l[7], l[8], l[9], l[10], l[10] if l[17] <= 180 else 0.0)
    l_ano = [[k[0], k[1], int(v[0]), *v[1:]] for k, v in por_ano.linhas()]
    col_ano = ["Empresa", "Ano", "Linhas", *VALORES, "PIS + COFINS", "PIS + COFINS que prescreve em 180 dias"]

    # ---- por CFOP × CST
    col_cst = ["Empresa", "Fonte", "CFOP", "CST PIS", "Descrição CST PIS", "Alíq. PIS", "CST COFINS", "Descrição CST COFINS",
               "Alíq. COFINS", "Linhas", "Valor no CFOP", "Desconto", "BC PIS", "PIS", "BC COFINS", "COFINS", "PIS + COFINS"]
    l_cst = [[k[0], k[1], k[2], k[3], CST_DESCR.get(k[3], ""), str(k[4]).replace(".", ","), k[5], CST_DESCR.get(k[5], ""),
              str(k[6]).replace(".", ","), int(v[0]), *v[1:], v[4] + v[6]]
             for k, v in cst.linhas(lambda kv: (kv[0][0], -(kv[1][4] + kv[1][6]), kv[0]))]

    # ---- por cliente (só C170/C175 com participante)
    cli = _Soma(4)
    for n in notas:
        if n[11]:
            cli.add((n[0], n[12], n[11]), 1, n[22], n[25], n[27])
    l_cli = [[k[0], k[1], k[2], int(v[0]), v[1], v[2], v[3], v[2] + v[3]]
             for k, v in cli.linhas(lambda kv: (-(kv[1][2] + kv[1][3]), kv[0]))]
    col_cli = ["Empresa", "CNPJ/CPF cliente", "Cliente", "Notas", "Valor no CFOP", "PIS", "COFINS", "PIS + COFINS"]

    # ---- arquivos
    lidos = {r["info"]["caminho"]: r for r in resultados}
    contagens = [("Estabelecimentos", "estabelecimentos"), ("C100 saída", "c100_saida"), ("C100 entrada (ignorado)", "c100_entrada"),
                 ("Notas alvo C170", "notas_C170"), ("Notas alvo C175", "notas_C175"), ("Itens alvo C170", "itens_alvo_c170"),
                 ("C180", "c180"), ("Linhas alvo C181/C185", "linhas_consolidadas"), ("C181≠C185 (qtde)", "c180_filhos_desbalanceados"),
                 ("Só PIS", "c181_sem_c185"), ("Só COFINS", "c185_sem_c181"), ("Valores inválidos", "valor_invalido")]
    col_arq = ["Empresa", "CNPJ (pasta)", "Arquivo", "CNPJ (0000)", "Razão social (0000)", "Competência", "Tipo",
               "Transmissão (nome)", "MB", "Situação", "Caminho", "Linhas lidas", "QTD_LIN (9999)", "Íntegro", "Segundos",
               *[c for c, _ in contagens]]
    l_arq = []
    descartes: Counter = Counter()
    for t in todos:
        r = lidos.get(t["caminho"]) if t["caminho"] else None
        base = [t["empresa"], t["cnpj_pasta"], t.get("nome_arquivo", ""), t.get("cnpj", ""), t.get("nome", ""),
                t.get("competencia", ""), {"0": "Original", "1": "Retificadora"}.get(t.get("tipo_escrit", ""), t.get("tipo_escrit", "")),
                t.get("transmissao", ""), round(t.get("tamanho", 0) / 1e6, 1), t["situacao"], t["caminho"]]
        if r is None:
            l_arq.append(base + [None, None, "", None] + [None] * len(contagens))
        elif "erro" in r:
            l_arq.append(base + [None, None, "ERRO", None] + [None] * len(contagens))
        else:
            c = r["contadores"]
            l_arq.append(base + [r["linhas"], r["qtd_lin_9999"], "sim" if r["valido"] else "não", r["segundos"]]
                         + [c.get(k, 0) for _, k in contagens])
            for k, v in c.items():
                if k.startswith("c100_saida_descartada") or k in ("c170_curto", "c175_curto", "c18x_sem_c180", "c18x_curto",
                                                                  "linha_fora_do_padrao", "arquivo_qtd_lin_divergente"):
                    descartes[k] += v

    premissas = [
        ("Escopo", f"{len(empresas)} empresas na pasta {grupo}; todas as competências com EFD-Contribuições disponível."),
        ("Fonte", "EFD-Contribuições. Mês com mais de um arquivo: vale o transmitido por último (data no nome do arquivo; senão, data de modificação)."),
        ("Critério", f"CFOP {cfops} nas saídas. Valores de PIS/COFINS exatamente como escriturados: VL_BC_PIS, VL_PIS, VL_BC_COFINS, VL_COFINS."),
        ("Três fontes", "C170 (item a item, dentro do C100 de saída, situação ≠ cancelada/denegada/inutilizada); C175 (NFC-e consolidada por CFOP dentro do C100); C181/C185 (consolidado por produto × CFOP × CST do C180 — não há nota, só produto e mês)."),
        ("C181/C185", "Dentro de cada C180, o C181 (PIS) casa com o C185 (COFINS) de mesmo CFOP e mesmo valor — não pela posição, porque há escrituração em que a ordem dos dois lados não coincide. O lado sem par sai com o outro em branco (coluna Observação da aba 7)."),
        ("Tipo de nota", "'Junto com a venda' quando a mesma nota também tem CFOP de venda; senão 'Nota própria'. Só nas fontes C170/C175."),
        ("Apuração do mês", "M200/M600: contribuição apurada e a recolher no mês do arquivo (CNPJ matriz), para contextualizar se o débito foi efetivamente pago."),
        ("Prescrição", f"Vencimento de PIS/COFINS = dia 25 do mês seguinte; prazo conservador = 5 anos contados dali. 'Dias até prescrever' calculado em {hoje:%d/%m/%Y}."),
        ("Integridade", "Cada arquivo lido até o 9999 e conferido contra QTD_LIN (aba 8, coluna Íntegro). Linhas descartadas e valores inválidos estão contados por arquivo."),
        ("Zero não é ausência", "Zero no filtro de CFOP não quer dizer 'sem bonificação': a nota pode não constar da EFD-Contribuições (conferir com o subcomando cruzar, pela chave da NF-e) ou o mês pode ser consolidado (C180), sem nota."),
        ("Descartes no grupo", "; ".join(f"{k}={v}" for k, v in sorted(descartes.items())) or "nenhum"),
    ]

    notas.sort(key=lambda n: (n[0], _ord(n[3]), n[5] or _dt.date.min, n[9]))
    cons.sort(key=lambda c: (c[0], _ord(c[3]), c[6]))
    x = _Excel(saida)
    x.aba("0_Premissas", ["Tema", "Premissa"], premissas, {"Premissa": 150})
    x.aba("1_Painel", col_painel, l_painel)
    x.aba("2_Resumo_por_ano", col_ano, l_ano)
    x.aba("3_Mensal_por_estab", col_mensal, l_mensal)
    x.aba("4_Por_CFOP_CST", col_cst, l_cst)
    x.aba("5_Por_cliente", col_cli, l_cli)
    x.aba("6_Notas", COL_NOTAS, notas)
    x.aba("7_Consolidado_C181_C185", COL_CONS, [c[:24] for c in cons])
    x.aba("8_Arquivos", col_arq, l_arq, {"Caminho": 80})
    x.fechar()
    log.info("planilha gravada", extra={"caminho": saida, "notas": len(notas), "consolidado": len(cons),
                                       "mensal": len(l_mensal), "empresas": len(empresas)})
    return {"abas": x.abas, "painel": {l[0]: dict(zip(col_painel, l)) for l in l_painel}}


# --------------------------------------------------------------------------- cruzamento por chave
def cruzar_um(args: tuple) -> dict:
    """Procura as chaves pedidas nos C100 de um arquivo e devolve CFOP/CST/PIS/COFINS de cada nota achada."""
    info, chaves, alvo = args
    caminho = info["caminho"]
    cont: Counter = Counter()
    amostras: list = []
    achadas: dict[str, dict] = {}
    nota = None
    linhas = 0
    tem_c170 = tem_c180 = False
    try:
        with open(caminho_longo(caminho), "rb", buffering=4 * 1024 * 1024) as fh:
            for raw in fh:
                if not raw.startswith(b"|"):
                    continue
                linhas += 1
                reg = raw[1:5]
                if reg == b"C170" or reg == b"C175":
                    tem_c170 = True
                    if nota is None:
                        continue
                    f = raw.decode("latin-1").rstrip("\r\n").split("|")
                    if reg == b"C170":
                        if len(f) < 37:
                            cont["c170_curto"] += 1
                            continue
                        cfop, i_vl, i_cst_pis, i_bc_pis, i_pis, i_cst_cof, i_bc_cof, i_cof = f[11], 7, 25, 26, 30, 31, 32, 36
                    else:
                        if len(f) < 17:
                            cont["c175_curto"] += 1
                            continue
                        nota["fonte"] = "C175"
                        cfop, i_vl, i_cst_pis, i_bc_pis, i_pis, i_cst_cof, i_bc_cof, i_cof = f[2], 3, 5, 6, 10, 11, 12, 16
                    n = lambda i, c: _num(f[i], cont, amostras, caminho, linhas, c)  # noqa: E731
                    nota["cfops"].add(cfop)
                    nota["cst_pis"].add(f[i_cst_pis])
                    nota["cst_cof"].add(f[i_cst_cof])
                    nota["itens"] += 1
                    nota["vl_item"] += n(i_vl, "VL_ITEM")
                    nota["bc_pis"] += n(i_bc_pis, "VL_BC_PIS")
                    nota["pis"] += n(i_pis, "VL_PIS")
                    nota["bc_cof"] += n(i_bc_cof, "VL_BC_COFINS")
                    nota["cof"] += n(i_cof, "VL_COFINS")
                    if cfop in alvo:
                        nota["vl_alvo"] += n(i_vl, "VL_ITEM")
                        nota["pis_alvo"] += n(i_pis, "VL_PIS")
                        nota["cof_alvo"] += n(i_cof, "VL_COFINS")
                elif reg == b"C100":
                    nota = None
                    f = raw.decode("latin-1").rstrip("\r\n").split("|")
                    if len(f) < 28:
                        cont["c100_curto"] += 1
                        continue
                    cont["c100"] += 1
                    if f[9] in chaves:
                        n = lambda i, c: _num(f[i], cont, amostras, caminho, linhas, c)  # noqa: E731
                        nota = {"fonte": "C170", "ind_oper": f[2], "sit": f[6], "mod": f[5], "vl_doc": n(12, "VL_DOC"),
                                "vl_pis_doc": n(26, "VL_PIS"), "vl_cof_doc": n(27, "VL_COFINS"), "cfops": set(),
                                "cst_pis": set(), "cst_cof": set(), "itens": 0, "vl_item": 0.0, "bc_pis": 0.0,
                                "pis": 0.0, "bc_cof": 0.0, "cof": 0.0, "vl_alvo": 0.0, "pis_alvo": 0.0, "cof_alvo": 0.0}
                        achadas[f[9]] = nota
                        cont["achadas"] += 1
                elif reg == b"C180":
                    tem_c180 = True
                elif reg in (b"C190", b"C990", b"C010"):
                    nota = None
                elif reg == b"9999":
                    break
    except Exception:
        return {"info": info, "erro": traceback.format_exc()}
    return {"info": info, "achadas": achadas, "contadores": dict(cont), "amostras": amostras,
            "tem_c170": tem_c170, "tem_c180": tem_c180, "linhas": linhas}


def modo_do_mes(tem_c170: bool, tem_c180: bool) -> str:
    """Mês com C180 é consolidado mesmo com algumas notas C100 (NFC-e, devolução): a nota alvo não está lá."""
    if tem_c180:
        return "consolidado (C180/C181/C185)" + (" + poucas notas C100" if tem_c170 else "")
    return "item a item (C170/C175)" if tem_c170 else "sem bloco C"


COL_CRUZ = ["Situação", "Escrituração do mês", "Fonte", "IND_OPER", "COD_SIT", "CFOPs na Contribuições",
            "Classificação na Contribuições", "CST PIS", "CST COFINS", "Itens", "Valor itens (Contrib.)",
            "Valor da nota (C100)", "BC PIS", "PIS (itens)", "BC COFINS", "COFINS (itens)", "PIS (C100)", "COFINS (C100)",
            "Valor no CFOP alvo", "PIS no CFOP alvo", "COFINS no CFOP alvo", "Tributada no PIS/COFINS"]
COL_RESUMO_CRUZ = ["Notas no CSV", "Meses cruzáveis (item a item)", "Não cruzável (mês consolidado C180)",
                   "Não cruzável (sem EFD-Contribuições)", "Encontradas na Contribuições", "NÃO encontradas (mês item a item)",
                   "Encontradas com CFOP alvo", "Encontradas com CFOP de venda", "Encontradas com outro CFOP",
                   "Encontradas tributadas (PIS/COFINS > 0)", "Valor itens (Contrib.) das encontradas", "PIS nas encontradas",
                   "COFINS nas encontradas", "PIS + COFINS nas encontradas"]


def cruzar(chaves_csv: str, usados: list[dict], saida: str, workers: int, alvo: tuple[str, ...]) -> dict:
    with open(chaves_csv, encoding="utf-8-sig", newline="") as fh:
        leitor = csv.DictReader(fh, delimiter=";")
        colunas_csv = list(leitor.fieldnames or [])
        faltam = {"empresa", "cnpj", "competencia", "chave"} - set(colunas_csv)
        if faltam:
            raise SystemExit(f"o CSV de chaves precisa das colunas {sorted(faltam)}; tem {colunas_csv}")
        entrada = [dict(r) for r in leitor]
    invalidas = sum(1 for r in entrada if len(r["chave"]) != 44)
    if invalidas:
        log.warning("chaves com tamanho diferente de 44 (não vão casar)", extra={"quantas": invalidas})
    por_arquivo: dict[tuple, set] = defaultdict(set)
    for r in entrada:
        por_arquivo[(r["chave"][6:14], _ord(r["competencia"]))].add(r["chave"])
    tarefas, sem_arquivo = [], []
    for (raiz, aamm), chaves in por_arquivo.items():
        cand = [u for u in usados if u["cnpj"][:8] == raiz and u["dt_ini"][4:] + u["dt_ini"][2:4] == aamm]
        if cand:
            tarefas.append((cand[0], chaves, alvo))
        else:
            sem_arquivo.append((raiz, aamm, len(chaves)))
    log.info("cruzamento: tarefas", extra={"notas": len(entrada), "arquivos": len(tarefas),
                                          "grupos_sem_efd": len(sem_arquivo), "notas_sem_efd": sum(s[2] for s in sem_arquivo)})
    t0 = time.time()
    resultados = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(cruzar_um, t): t[0] for t in sorted(tarefas, key=lambda t: -t[0]["tamanho"])}
        for i, fut in enumerate(as_completed(futs), 1):
            u = futs[fut]
            r = fut.result()
            if "erro" in r:
                log.error("falha ao ler", extra={"arquivo": u["caminho"], "erro": r["erro"][-600:]})
            else:
                log.debug("arquivo cruzado", extra={"empresa": u["empresa"], "competencia": u["competencia"],
                                                    "achadas": r["contadores"].get("achadas", 0),
                                                    "c100": r["contadores"].get("c100", 0), "amostras": r["amostras"][:3]})
            resultados.append(r)
            print(f"  {i}/{len(tarefas)}  {time.time() - t0:5.0f}s", file=sys.stderr, flush=True)
    log.info("cruzamento: leitura concluída", extra={"segundos": round(time.time() - t0), "arquivos": len(resultados),
                                                    "com_erro": sum(1 for r in resultados if "erro" in r)})
    modo: dict[tuple, str] = {}
    achadas: dict[str, dict] = {}
    for r in resultados:
        u = r["info"]
        k = (u["cnpj"][:8], u["dt_ini"][4:] + u["dt_ini"][2:4])
        if "erro" in r:
            modo[k] = "erro de leitura"
            continue
        modo[k] = modo_do_mes(r["tem_c170"], r["tem_c180"])
        achadas.update(r["achadas"])
    for raiz, aamm, _ in sem_arquivo:
        modo[(raiz, aamm)] = "sem EFD-Contribuições na pasta"

    notas = []
    for r in entrada:
        m = modo.get((r["chave"][6:14], _ord(r["competencia"])), "sem EFD-Contribuições na pasta")
        a = achadas.get(r["chave"])
        base = [r[c] for c in colunas_csv]
        if a is None:
            sit = "nota NÃO encontrada na EFD-Contribuições" if m.startswith("item") else f"não cruzável — {m}"
            notas.append(base + [sit, m, "", "", "", "", "", "", "", 0] + [0.0] * 11 + ["não"])
        else:
            notas.append(base + ["encontrada", m, a["fonte"], a["ind_oper"], a["sit"], "/".join(sorted(a["cfops"])),
                                 _classe(a["cfops"], alvo), "/".join(sorted(a["cst_pis"])), "/".join(sorted(a["cst_cof"])),
                                 a["itens"], a["vl_item"], a["vl_doc"], a["bc_pis"], a["pis"], a["bc_cof"], a["cof"],
                                 a["vl_pis_doc"], a["vl_cof_doc"], a["vl_alvo"], a["pis_alvo"], a["cof_alvo"],
                                 "sim" if a["pis"] + a["cof"] > 0 else "não"])
    i_emp, i_comp = colunas_csv.index("empresa"), colunas_csv.index("competencia")
    b = len(colunas_csv)  # as colunas do cruzamento começam aqui

    def resumo(chave_fn):
        s = _Soma(14)
        for n in notas:
            sit, m, cls = n[b], n[b + 1], n[b + 6]
            enc = sit == "encontrada"
            pis, cof, vl = n[b + 13], n[b + 15], n[b + 10]
            s.add(chave_fn(n), 1, m.startswith("item"), m.startswith("consolidado"), m.startswith("sem EFD"), enc,
                  sit.startswith("nota NÃO"), enc and cls.endswith("(CFOP alvo)"), enc and cls.startswith("CFOP de venda"),
                  enc and cls.startswith("outro"), enc and pis + cof > 0, vl if enc else 0.0, pis if enc else 0.0,
                  cof if enc else 0.0, pis + cof if enc else 0.0)
        return [[*k, *[int(x) for x in v[:10]], *v[10:]] for k, v in s.linhas()]

    l_emp = resumo(lambda n: (n[i_emp],))
    l_emp.append(["TOTAL", *[sum(l[i] for l in l_emp) for i in range(1, 15)]])
    l_ano = resumo(lambda n: (n[i_emp], n[i_comp][3:]))
    cls = _Soma(4)
    for n in notas:
        if n[b] == "encontrada":
            cls.add((n[i_emp], n[b + 6], n[b + 7], n[b + 8], n[b + 21]), 1, n[b + 10], n[b + 13], n[b + 15])
    l_cls = [[*k, int(v[0]), v[1], v[2], v[3], v[2] + v[3]] for k, v in cls.linhas()]
    premissas = [
        ("O que é", "Cruzamento, pela chave da NF-e, das notas do CSV informado com a EFD-Contribuições do mesmo mês (CNPJ raiz da chave × competência do CSV)."),
        ("Pergunta que responde", "A nota existe na EFD-Contribuições? Com que CFOP e CST? Destacou PIS/COFINS? — o filtro direto de CFOP não responde quando a nota foi omitida ou escriturada com outro CFOP."),
        ("Limite", "Só é cruzável no mês escriturado item a item (C100/C170 ou C175). No mês consolidado (C180/C181/C185) não há nota, e a chave não tem onde ser procurada."),
        ("Valores", f"PIS/COFINS (itens) = soma de todos os C170/C175 da nota, qualquer CFOP. 'No CFOP alvo' = só dos itens com CFOP {'/'.join(alvo)}."),
        ("Gerado em", f"{_dt.datetime.now():%d/%m/%Y %H:%M}"),
    ]
    notas.sort(key=lambda n: (n[i_emp], _ord(n[i_comp])))
    x = _Excel(saida)
    x.aba("0_Premissas", ["Tema", "Premissa"], premissas, {"Premissa": 160})
    x.aba("1_Resumo_por_empresa", ["Empresa", *COL_RESUMO_CRUZ], l_emp)
    x.aba("2_Resumo_por_ano", ["Empresa", "Ano", *COL_RESUMO_CRUZ], l_ano)
    x.aba("3_Por_classificacao_CST", ["Empresa", "Classificação na Contribuições", "CST PIS", "CST COFINS",
                                      "Tributada no PIS/COFINS", "Notas", "Valor itens (Contrib.)", "PIS (itens)",
                                      "COFINS (itens)", "PIS + COFINS"], l_cls)
    x.aba("4_Notas", colunas_csv + COL_CRUZ, notas)
    x.fechar()
    log.info("cruzamento: planilha gravada", extra={"caminho": saida, "notas": len(notas)})
    return {"resumo": {l[0]: dict(zip(COL_RESUMO_CRUZ, l[1:])) for l in l_emp}, "notas": notas, "colunas": colunas_csv + COL_CRUZ}


# --------------------------------------------------------------------------- linha de comando
def _ligar_log(pasta_trabalho: str) -> None:
    configurar()
    os.makedirs(pasta_trabalho, exist_ok=True)
    arquivo = logging.FileHandler(os.path.join(pasta_trabalho, "bonificacao_contribuicoes.log.jsonl"), encoding="utf-8")
    arquivo.setFormatter(FormatadorJson())
    arquivo.setLevel(logging.DEBUG)
    raiz = logging.getLogger()
    for h in raiz.handlers:
        h.setLevel(logging.INFO)
    raiz.addHandler(arquivo)
    raiz.setLevel(logging.DEBUG)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", required=True)
    for nome in ("extrair", "cruzar"):
        s = sub.add_parser(nome)
        s.add_argument("--grupo", required=True, help="pasta com uma subpasta por empresa (prefira o caminho por IP)")
        s.add_argument("--trabalho", required=True, help="pasta local de trabalho (pickles, log)")
        s.add_argument("--saida", required=True, help="caminho do .xlsx")
        s.add_argument("--pasta-sped", default=PASTA_SPED_PADRAO, help="subpasta dos SPED dentro de cada empresa")
        s.add_argument("--cfop", default=",".join(CFOP_PADRAO), help="CFOP alvo, separados por vírgula")
        s.add_argument("--workers", type=int, default=6)
        s.add_argument("--empresa", help="só as pastas cujo nome começa assim (teste)")
    sub.choices["extrair"].add_argument("--so-planilha", action="store_true", help="não relê: usa os pickles de --trabalho")
    sub.choices["cruzar"].add_argument("--chaves", required=True, help="CSV ; com empresa;cnpj;competencia(MM/AAAA);chave")
    a = ap.parse_args(argv)
    alvo = tuple(c.strip() for c in a.cfop.split(",") if c.strip())
    _ligar_log(a.trabalho)
    execucao = _dt.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    with contexto(execucao_id=execucao, etapa=a.comando, usuario=os.environ.get("USERNAME", "")):
        log.info("execução iniciada", extra={"argumentos": vars(a), "cfop": alvo, "python": sys.version.split()[0]})
        try:
            usados, todos = escolher_arquivos(a.grupo, a.pasta_sped)
            if a.empresa:
                usados = [u for u in usados if u["empresa"].upper().startswith(a.empresa.upper())]
                todos = [t for t in todos if t["empresa"].upper().startswith(a.empresa.upper())]
            with open(os.path.join(a.trabalho, "inventario.json"), "w", encoding="utf-8") as fh:
                json.dump(todos, fh, ensure_ascii=False, indent=1, default=str)
            if a.comando == "extrair":
                resultados = carregar_leituras(usados, a.trabalho) if a.so_planilha else extrair(usados, a.trabalho, a.workers, alvo)
                planilha(resultados, todos, a.saida, a.grupo, alvo)
            else:
                cruzar(a.chaves, usados, a.saida, a.workers, alvo)
        except Exception:
            log.exception("execução abortada")
            return 1
        log.info("execução concluída", extra={"saida": a.saida})
    print(f"\nPlanilha: {a.saida}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

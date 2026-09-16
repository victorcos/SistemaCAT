"""Monta a entrega: relatório executivo, dossiê por estabelecimento e pacote.

A leitura dos resumos e a situação de cada competência são do domínio
(`cat.dominio.cat42.entrega`). Aqui é juntar o que as etapas deixaram em
disco e escrever o que sai do escritório.

## O que sai

| Arquivo | Conteúdo |
|---|---|
| `relatorio_da_entrega.xlsx` | resumo, filial x competência (todas, prontas ou não, com o que falta), por filial, por mês, pendências de todas as etapas e a trilha das execuções |
| `dossie/<CNPJ>/` | só dos estabelecimentos com competência pronta: os TXT de envio, a Ficha 3 (CSV), os saldos do 1050, a apuração e a pré-validação daquelas competências |
| `MANIFESTO.txt` | de onde saiu (execuções), e tamanho e SHA-256 de cada arquivo do pacote |
| `pacote_de_entrega.zip` | os três acima, que é o que se baixa |

## O TXT do dossiê é o que foi pré-validado

Cada arquivo de envio é copiado da pasta da etapa 7 e o SHA-256 da cópia é
conferido contra o que a geração gravou. Se não bate, o arquivo mudou depois
de pré-validado, e a entrega falha em vez de levar um arquivo que ninguém
conferiu.

## Ficha 3 em CSV

A Ficha 3 de uma filial num ano passa com folga do que o Excel aguenta (a BOA
tem 875 mil linhas num mês de uma loja). O resto do dossiê é xlsx.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import xlsxwriter

from cat.dominio.cat42.apuracao import MotivoDeBloqueio
from cat.dominio.cat42.arquivo_digital import TravaDoArquivo
from cat.dominio.cat42.entrega import NOME_DA_ETAPA, Gravidade, Pendencia, SituacaoDaCompetencia, pendencias
from cat.infraestrutura.analitico.apuracao import ARQUIVO_APURACAO, ARQUIVO_SALDOS
from cat.infraestrutura.analitico.arquivo_digital import ARQUIVO_ARQUIVOS, ARQUIVO_OCORRENCIAS, PASTA_ENVIO
from cat.infraestrutura.analitico.confronto import _escapar
from cat.infraestrutura.analitico.razao import ARQUIVO_FICHA3
from cat.infraestrutura.analitico.suportado import ApuracaoCancelada, _leitura
from cat.infraestrutura.planilhas.apuracao import gerar_apuracao, gerar_saldos
from cat.infraestrutura.planilhas.arquivo_digital import gerar_ocorrencias
from cat.infraestrutura.planilhas.razao import gerar_ficha3
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_COMPETENCIAS = "competencias_da_entrega.parquet"
ARQUIVO_ESTABELECIMENTOS = "estabelecimentos_da_entrega.parquet"
ARQUIVO_RELATORIO = "relatorio_da_entrega.xlsx"
ARQUIVO_MANIFESTO = "MANIFESTO.txt"
ARQUIVO_PACOTE = "pacote_de_entrega.zip"
PASTA_DOSSIE = "dossie"

POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 200
_Q2 = Decimal("0.01")
_ZERO = Decimal(0)

ESQUEMA_COMPETENCIAS = pa.schema([
    ("cnpj", pa.string()),
    ("uf", pa.string()),
    ("competencia", pa.string()),
    ("situacao", pa.string()),                 # envio | previa | fora_de_sp | sem_arquivo
    ("ressarcimento", pa.decimal128(24, 2)),
    ("complemento", pa.decimal128(24, 2)),
    ("apta", pa.bool_()),
    ("motivos", pa.string()),                  # etapa 6, códigos por vírgula
    ("travas", pa.string()),                   # etapa 7, códigos por vírgula
    ("arquivo", pa.string()),
    ("linhas", pa.int64()),
    ("erros", pa.int64()),
    ("avisos", pa.int64()),
    ("bytes", pa.int64()),
    ("sha256", pa.string()),
])

ESQUEMA_ESTABELECIMENTOS = pa.schema([
    ("cnpj", pa.string()),
    ("uf", pa.string()),
    ("competencias", pa.int32()),
    ("para_envio", pa.int32()),
    ("previas", pa.int32()),
    ("fora_de_sp", pa.bool_()),
    ("ressarcimento", pa.decimal128(24, 2)),
    ("complemento", pa.decimal128(24, 2)),
    ("ressarcimento_para_envio", pa.decimal128(24, 2)),
    ("complemento_para_envio", pa.decimal128(24, 2)),
    ("no_dossie", pa.bool_()),
    ("arquivos_no_dossie", pa.int32()),
    ("bytes_no_dossie", pa.int64()),
])

DeveParar = Callable[[], bool]


class ArquivoAlterado(ValueError):
    """O TXT de envio não é mais o que a pré-validação leu."""


def _conferir(deve_parar: DeveParar | None) -> None:
    if deve_parar is not None and deve_parar():
        raise ApuracaoCancelada("A montagem da entrega foi cancelada por quem a pediu.")


@dataclass
class Fontes:
    arquivo_digital: str          # pasta da etapa 7
    apuracao: str                 # pasta da etapa 6
    razao: str                    # pasta da etapa 5


@dataclass
class Contexto:
    """O que o relatório e o manifesto dizem sobre o trabalho e de onde ele saiu."""

    empresa: str = ""
    cnpj_matriz: str = ""
    trabalho: str = ""
    periodo: str = ""             # o do cadastro do trabalho
    periodo_apurado: str = ""     # o dos dados, pelo razão: quando difere do cadastro, é bom que se veja
    venda_a_consumidor: str = ""
    gerado_por: str = ""
    gerado_em: datetime | None = None
    versao_do_sistema: str = ""
    resumos: dict[str, dict] = field(default_factory=dict)       # etapa -> resumo usado
    # [{"etapa", "execucao_id", "terminada_em" (datetime), "iniciada_por", "segundos"}]
    trilha: list[dict] = field(default_factory=list)


@dataclass
class Andamento:
    passo: str = ""
    estabelecimentos: int = 0
    total: int = 0


@dataclass
class ResumoDaEntrega:
    competencias: int = 0
    competencias_de_sp: int = 0
    para_envio: int = 0
    previas: int = 0
    fora_de_sp: int = 0
    sem_arquivo: int = 0
    estabelecimentos: int = 0
    estabelecimentos_no_dossie: int = 0
    ressarcimento: Decimal = _ZERO
    complemento: Decimal = _ZERO
    ressarcimento_para_envio: Decimal = _ZERO
    complemento_para_envio: Decimal = _ZERO
    arquivos_no_dossie: int = 0
    arquivos_no_pacote: int = 0
    bytes_do_pacote: int = 0
    sha256_do_pacote: str = ""
    pendencias: list[Pendencia] = field(default_factory=list)


# ---------------------------------------------------------------------------
# a montagem
# ---------------------------------------------------------------------------
def montar(
    fontes: Fontes,
    destino: str,
    contexto: Contexto,
    avisar: Callable[[Andamento], None] | None = None,
    deve_parar: DeveParar | None = None,
) -> ResumoDaEntrega:
    apuracao = os.path.join(fontes.apuracao, ARQUIVO_APURACAO)
    saldos = os.path.join(fontes.apuracao, ARQUIVO_SALDOS)
    arquivos = os.path.join(fontes.arquivo_digital, ARQUIVO_ARQUIVOS)
    ocorrencias = os.path.join(fontes.arquivo_digital, ARQUIVO_OCORRENCIAS)
    ficha3 = os.path.join(fontes.razao, ARQUIVO_FICHA3)
    for obrigatorio in (apuracao, saldos, arquivos, ocorrencias, ficha3):
        if not os.path.isfile(obrigatorio):
            raise FileNotFoundError(f"{os.path.basename(obrigatorio)} não está em {os.path.dirname(obrigatorio)}.")

    os.makedirs(destino, exist_ok=True)
    resumo = ResumoDaEntrega(pendencias=pendencias(contexto.resumos))
    andamento = Andamento()

    def avancar(passo: str) -> None:
        andamento.passo = passo
        if avisar is not None:
            avisar(andamento)

    try:
        avancar("Cruzando a apuração com os arquivos gerados")
        competencias = _competencias(apuracao, arquivos, resumo)
        estabelecimentos = _estabelecimentos(competencias, resumo)
        _gravar(os.path.join(destino, ARQUIVO_COMPETENCIAS), competencias, ESQUEMA_COMPETENCIAS)

        no_dossie = [e for e in estabelecimentos if e["para_envio"]]
        andamento.total = len(no_dossie)
        for est in no_dossie:
            _conferir(deve_parar)
            avancar("Montando o dossiê de cada estabelecimento")
            linhas = [c for c in competencias if c["cnpj"] == est["cnpj"]
                      and c["situacao"] == SituacaoDaCompetencia.ENVIO.value]
            est["arquivos_no_dossie"], est["bytes_no_dossie"] = _dossie(
                destino, fontes, est["cnpj"], linhas, ficha3, saldos, apuracao, ocorrencias)
            resumo.arquivos_no_dossie += len(linhas)
            andamento.estabelecimentos += 1
        _gravar(os.path.join(destino, ARQUIVO_ESTABELECIMENTOS), estabelecimentos, ESQUEMA_ESTABELECIMENTOS)

        _conferir(deve_parar)
        avancar("Escrevendo o relatório e o manifesto")
        _relatorio(os.path.join(destino, ARQUIVO_RELATORIO), contexto, resumo, competencias, estabelecimentos)
        _manifesto(destino, contexto, resumo)
        avancar("Empacotando")
        _empacotar(destino, resumo)
    except ApuracaoCancelada:
        _desfazer(destino)
        raise

    log.info("entrega montada", extra={
        "competencias": resumo.competencias, "para_envio": resumo.para_envio,
        "estabelecimentos_no_dossie": resumo.estabelecimentos_no_dossie,
        "arquivos_no_pacote": resumo.arquivos_no_pacote, "bytes_do_pacote": resumo.bytes_do_pacote,
        "pendencias": len(resumo.pendencias)})
    return resumo


def _desfazer(destino: str) -> None:
    """Cancelada, não fica pacote pela metade para alguém baixar."""
    for nome in (ARQUIVO_COMPETENCIAS, ARQUIVO_ESTABELECIMENTOS, ARQUIVO_RELATORIO, ARQUIVO_MANIFESTO,
                 ARQUIVO_PACOTE, ARQUIVO_PACOTE + ".tmp"):
        caminho = os.path.join(destino, nome)
        if os.path.isfile(caminho):
            os.remove(caminho)
    shutil.rmtree(os.path.join(destino, PASTA_DOSSIE), ignore_errors=True)


def _competencias(apuracao: str, arquivos: str, resumo: ResumoDaEntrega) -> list[dict]:
    """Toda competência apurada, com o arquivo da etapa 7 quando há."""
    gerados = {(a["cnpj"], a["competencia"]): a for a in pq.read_table(arquivos, columns=[
        "cnpj", "competencia", "nome", "destino", "travas", "linhas", "erros", "avisos", "bytes", "sha256"]).to_pylist()}
    saida = []
    for a in pq.read_table(apuracao, columns=[
            "cnpj", "uf", "competencia", "ressarcimento", "complemento", "apta", "motivos"]).to_pylist():
        d = gerados.get((a["cnpj"], a["competencia"])) or {}
        situacao = SituacaoDaCompetencia.de(a["uf"], d.get("destino"))
        linha = {
            "cnpj": a["cnpj"], "uf": a["uf"] or "", "competencia": a["competencia"], "situacao": situacao.value,
            "ressarcimento": Decimal(a["ressarcimento"] or 0).quantize(_Q2),
            "complemento": Decimal(a["complemento"] or 0).quantize(_Q2),
            "apta": bool(a["apta"]), "motivos": a["motivos"] or "", "travas": d.get("travas") or "",
            "arquivo": d.get("nome") or "", "linhas": d.get("linhas") or 0, "erros": d.get("erros") or 0,
            "avisos": d.get("avisos") or 0, "bytes": d.get("bytes") or 0, "sha256": d.get("sha256") or "",
        }
        saida.append(linha)
        resumo.competencias += 1
        resumo.ressarcimento += linha["ressarcimento"]
        resumo.complemento += linha["complemento"]
        if situacao is SituacaoDaCompetencia.FORA_DE_SP:
            resumo.fora_de_sp += 1
            continue
        resumo.competencias_de_sp += 1
        if situacao is SituacaoDaCompetencia.ENVIO:
            resumo.para_envio += 1
            resumo.ressarcimento_para_envio += linha["ressarcimento"]
            resumo.complemento_para_envio += linha["complemento"]
        elif situacao is SituacaoDaCompetencia.PREVIA:
            resumo.previas += 1
        else:
            resumo.sem_arquivo += 1
    ordem = {s.value: i for i, s in enumerate(SituacaoDaCompetencia)}
    return sorted(saida, key=lambda c: (ordem[c["situacao"]], c["cnpj"], c["competencia"]))


def _estabelecimentos(competencias: list[dict], resumo: ResumoDaEntrega) -> list[dict]:
    por_cnpj: dict[str, dict] = {}
    for c in competencias:
        e = por_cnpj.setdefault(c["cnpj"], {
            "cnpj": c["cnpj"], "uf": c["uf"], "competencias": 0, "para_envio": 0, "previas": 0,
            "fora_de_sp": c["situacao"] == SituacaoDaCompetencia.FORA_DE_SP.value,
            "ressarcimento": _ZERO, "complemento": _ZERO, "ressarcimento_para_envio": _ZERO,
            "complemento_para_envio": _ZERO, "no_dossie": False, "arquivos_no_dossie": 0, "bytes_no_dossie": 0})
        e["competencias"] += 1
        e["ressarcimento"] += c["ressarcimento"]
        e["complemento"] += c["complemento"]
        if c["situacao"] == SituacaoDaCompetencia.ENVIO.value:
            e["para_envio"] += 1
            e["no_dossie"] = True
            e["ressarcimento_para_envio"] += c["ressarcimento"]
            e["complemento_para_envio"] += c["complemento"]
        elif c["situacao"] == SituacaoDaCompetencia.PREVIA.value:
            e["previas"] += 1
    saida = sorted(por_cnpj.values(), key=lambda e: (not e["no_dossie"], -e["ressarcimento_para_envio"],
                                                   -e["ressarcimento"], e["cnpj"]))
    resumo.estabelecimentos = len(saida)
    resumo.estabelecimentos_no_dossie = sum(1 for e in saida if e["no_dossie"])
    return saida


def _gravar(caminho: str, linhas: list[dict], esquema: pa.Schema) -> None:
    pq.write_table(pa.Table.from_pylist(linhas, schema=esquema), caminho)


# ---------------------------------------------------------------------------
# o dossiê de um estabelecimento
# ---------------------------------------------------------------------------
def _lista(valores) -> str:
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in valores)


def _hash(caminho: str) -> tuple[int, str]:
    h = hashlib.sha256()
    tamanho = 0
    with open(caminho, "rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
            tamanho += len(bloco)
    return tamanho, h.hexdigest()


def _dossie(destino: str, fontes: Fontes, cnpj: str, linhas: list[dict], ficha3: str, saldos: str,
            apuracao: str, ocorrencias: str) -> tuple[int, int]:
    pasta = os.path.join(destino, PASTA_DOSSIE, cnpj)
    pasta_txt = os.path.join(pasta, "arquivo_digital")
    os.makedirs(pasta_txt, exist_ok=True)
    bytes_ = 0
    for l in linhas:
        origem = os.path.join(fontes.arquivo_digital, PASTA_ENVIO, l["arquivo"])
        if not os.path.isfile(origem):
            raise FileNotFoundError(f"O arquivo de envio {l['arquivo']} não está mais em {os.path.dirname(origem)}. "
                                    "Gere o arquivo digital de novo.")
        copia = os.path.join(pasta_txt, l["arquivo"])
        shutil.copyfile(origem, copia)
        tamanho, sha = _hash(copia)
        if sha != l["sha256"]:
            log.error("arquivo de envio diferente do pré-validado",
                      extra={"arquivo": l["arquivo"], "sha_gravado": l["sha256"], "sha_da_copia": sha})
            raise ArquivoAlterado(f"O arquivo {l['arquivo']} mudou depois de pré-validado (SHA-256 diferente). "
                                  "Gere o arquivo digital de novo.")
        bytes_ += tamanho

    meses = sorted({l["competencia"] for l in linhas})
    nomes = [l["arquivo"] for l in linhas]
    recortes = (
        (ficha3, f"SELECT * FROM read_parquet('{_escapar(ficha3)}') WHERE cnpj = '{cnpj}' "
                 f"AND strftime(data, '%Y-%m') IN ({_lista(meses)}) ORDER BY codigo, data, numero",
         f"ficha3_{cnpj}.csv", lambda p, d: gerar_ficha3(p, d, formato="csv")),
        (saldos, f"SELECT * FROM read_parquet('{_escapar(saldos)}') WHERE cnpj = '{cnpj}' "
                 f"AND competencia IN ({_lista(meses)}) ORDER BY competencia, codigo",
         f"saldos_1050_{cnpj}.xlsx", gerar_saldos),
        (apuracao, f"SELECT * FROM read_parquet('{_escapar(apuracao)}') WHERE cnpj = '{cnpj}' "
                   f"AND competencia IN ({_lista(meses)}) ORDER BY competencia",
         f"apuracao_{cnpj}.xlsx", gerar_apuracao),
        (ocorrencias, f"SELECT * FROM read_parquet('{_escapar(ocorrencias)}') WHERE nome IN ({_lista(nomes)}) "
                      "ORDER BY nome, severidade = 'aviso', regra, linha",
         f"pre_validacao_{cnpj}.xlsx", gerar_ocorrencias),
    )
    con = _leitura(destino)
    try:
        for _, sql, nome, gerador in recortes:
            recorte = os.path.join(pasta, f".{nome}.parquet")
            con.execute(f"COPY ({sql}) TO '{_escapar(recorte)}' (FORMAT PARQUET)")
            try:
                gerador(recorte, os.path.join(pasta, nome))
            finally:
                os.remove(recorte)
            bytes_ += os.path.getsize(os.path.join(pasta, nome))
    finally:
        con.close()
    log.info("dossiê do estabelecimento montado",
             extra={"cnpj": cnpj, "competencias": len(meses), "arquivos": len(nomes), "bytes": bytes_})
    return len(nomes), bytes_


# ---------------------------------------------------------------------------
# o relatório executivo
# ---------------------------------------------------------------------------
def _local(momento: datetime | None) -> datetime | None:
    """O xlsxwriter não escreve data com fuso: vai no horário da máquina."""
    if momento is None:
        return None
    return momento.astimezone().replace(tzinfo=None) if momento.tzinfo else momento


def _rotulos_de_motivos(codigos: str) -> str:
    saida = []
    for c in (codigos or "").split(","):
        if not c:
            continue
        try:
            saida.append(MotivoDeBloqueio(c).rotulo)
        except ValueError:
            saida.append(c)
    return "; ".join(saida)


def _rotulos_de_travas(codigos: str) -> str:
    saida = []
    for c in (codigos or "").split(","):
        if not c:
            continue
        try:
            saida.append(TravaDoArquivo[c.upper()].rotulo)
        except KeyError:
            saida.append(c)
    return "; ".join(saida)


def _relatorio(caminho: str, contexto: Contexto, resumo: ResumoDaEntrega, competencias: list[dict],
               estabelecimentos: list[dict]) -> None:
    livro = xlsxwriter.Workbook(caminho, {"constant_memory": True,
                                          "tmpdir": os.path.dirname(os.path.abspath(caminho))})
    f = {
        "titulo": livro.add_format({"bold": True, "font_size": 16, "font_color": "#021D44"}),
        "sub": livro.add_format({"font_color": "#5A6478"}),
        "rotulo": livro.add_format({"bold": True}),
        "cabecalho": livro.add_format({"bold": True, "bg_color": "#021D44", "font_color": "#FFFFFF", "border": 1,
                                       "valign": "vcenter"}),
        "texto": livro.add_format({"num_format": "@"}),
        "dinheiro": livro.add_format({"num_format": "#,##0.00"}),
        "inteiro": livro.add_format({"num_format": "#,##0"}),
        "quando": livro.add_format({"num_format": "dd/mm/yyyy hh:mm"}),
        "nota": livro.add_format({"italic": True, "font_color": "#5A6478", "text_wrap": True, "valign": "top"}),
        "trava": livro.add_format({"bold": True, "font_color": "#B42318"}),
        "atencao": livro.add_format({"bold": True, "font_color": "#B54708"}),
        "informacao": livro.add_format({"font_color": "#5A6478"}),
    }

    # --- Resumo -------------------------------------------------------------
    aba = livro.add_worksheet("Resumo")
    aba.set_column(0, 0, 52)
    aba.set_column(1, 1, 36)
    aba.write(0, 0, "Relatório da entrega — CAT 42", f["titulo"])
    aba.write(1, 0, f"{contexto.empresa} · CNPJ {contexto.cnpj_matriz}".strip(" ·"), f["sub"])
    linha = 3
    travas = sum(1 for p in resumo.pendencias if p.gravidade is Gravidade.TRAVA)
    atencao = sum(1 for p in resumo.pendencias if p.gravidade is Gravidade.ATENCAO)
    pares: list[tuple[str, object, str]] = [
        ("Trabalho", contexto.trabalho, "texto"),
        ("Período do trabalho (cadastro)", contexto.periodo, "texto"),
        ("Período apurado (dados)", contexto.periodo_apurado, "texto"),
        ("Venda a consumidor final", contexto.venda_a_consumidor, "texto"),
        ("Gerado em", _local(contexto.gerado_em), "quando"),
        ("Gerado por", contexto.gerado_por, "texto"),
        ("Versão do sistema", contexto.versao_do_sistema, "texto"),
        ("", None, ""),
        ("Competências apuradas", resumo.competencias, "inteiro"),
        ("De São Paulo", resumo.competencias_de_sp, "inteiro"),
        ("Prontas para envio (no dossiê)", resumo.para_envio, "inteiro"),
        ("Prévias, com pendência (só no relatório)", resumo.previas, "inteiro"),
        ("Fora de SP (não geram arquivo)", resumo.fora_de_sp, "inteiro"),
        ("Estabelecimentos", resumo.estabelecimentos, "inteiro"),
        ("Estabelecimentos no dossiê", resumo.estabelecimentos_no_dossie, "inteiro"),
        ("", None, ""),
        ("Ressarcimento nas competências prontas para envio", resumo.ressarcimento_para_envio, "dinheiro"),
        ("Complemento nas competências prontas para envio", resumo.complemento_para_envio, "dinheiro"),
        ("Ressarcimento apurado em todas as competências", resumo.ressarcimento, "dinheiro"),
        ("Complemento apurado em todas as competências", resumo.complemento, "dinheiro"),
        ("", None, ""),
        ("Pendências que travam o envio", travas, "inteiro"),
        ("Pendências de atenção", atencao, "inteiro"),
    ]
    for rotulo, valor, formato in pares:
        if rotulo:
            aba.write(linha, 0, rotulo, f["rotulo"])
            if valor is None or valor == "":
                aba.write_blank(linha, 1, None)
            elif formato == "texto":
                aba.write_string(linha, 1, str(valor), f["texto"])
            elif formato == "quando":
                aba.write_datetime(linha, 1, valor, f["quando"])
            else:
                aba.write_number(linha, 1, float(valor), f[formato])
        linha += 1
    linha += 1
    for nota in (
        "Ressarcimento e complemento não se compensam: um se pede, o outro se recolhe.",
        "O dossiê leva só as competências prontas para envio. As outras estão na aba «Filial x competência», "
        "com o que falta em cada uma, e na aba «Pendências».",
        "Gerar o pacote não é entregar: a entrega conclui quando um revisor ou gestor a aprova no sistema.",
    ):
        aba.write_string(linha, 0, nota, f["nota"])
        linha += 1

    # --- Filial x competência -----------------------------------------------
    colunas = (("CNPJ do estabelecimento", 20), ("UF", 5), ("Competência", 12), ("Situação", 22),
               ("Ressarcimento", 16), ("Complemento", 16), ("Apta na apuração", 10),
               ("Pendências da apuração (etapa 6)", 50), ("O que trava o envio (etapa 7)", 50),
               ("Arquivo digital", 40), ("Linhas do arquivo", 12), ("Erros da pré-validação", 12),
               ("Avisos da pré-validação", 12), ("SHA-256 do arquivo", 66))
    aba = _aba_com_cabecalho(livro, "Filial x competência", colunas, f)
    for i, c in enumerate(competencias, 1):
        aba.write_string(i, 0, c["cnpj"], f["texto"])
        aba.write_string(i, 1, c["uf"], f["texto"])
        aba.write_string(i, 2, c["competencia"], f["texto"])
        aba.write_string(i, 3, SituacaoDaCompetencia(c["situacao"]).rotulo)
        aba.write_number(i, 4, float(c["ressarcimento"]), f["dinheiro"])
        aba.write_number(i, 5, float(c["complemento"]), f["dinheiro"])
        aba.write_string(i, 6, "Sim" if c["apta"] else "Não")
        aba.write_string(i, 7, _rotulos_de_motivos(c["motivos"]))
        aba.write_string(i, 8, _rotulos_de_travas(c["travas"]))
        aba.write_string(i, 9, c["arquivo"], f["texto"])
        aba.write_number(i, 10, c["linhas"], f["inteiro"])
        aba.write_number(i, 11, c["erros"], f["inteiro"])
        aba.write_number(i, 12, c["avisos"], f["inteiro"])
        aba.write_string(i, 13, c["sha256"], f["texto"])

    # --- Por filial -----------------------------------------------------------
    colunas = (("CNPJ do estabelecimento", 20), ("UF", 5), ("Competências", 12), ("Prontas para envio", 12),
               ("Prévias", 10), ("Ressarcimento para envio", 18), ("Complemento para envio", 18),
               ("Ressarcimento apurado", 18), ("Complemento apurado", 18), ("No dossiê", 10))
    aba = _aba_com_cabecalho(livro, "Por filial", colunas, f)
    for i, e in enumerate(estabelecimentos, 1):
        aba.write_string(i, 0, e["cnpj"], f["texto"])
        aba.write_string(i, 1, e["uf"], f["texto"])
        aba.write_number(i, 2, e["competencias"], f["inteiro"])
        aba.write_number(i, 3, e["para_envio"], f["inteiro"])
        aba.write_number(i, 4, e["previas"], f["inteiro"])
        aba.write_number(i, 5, float(e["ressarcimento_para_envio"]), f["dinheiro"])
        aba.write_number(i, 6, float(e["complemento_para_envio"]), f["dinheiro"])
        aba.write_number(i, 7, float(e["ressarcimento"]), f["dinheiro"])
        aba.write_number(i, 8, float(e["complemento"]), f["dinheiro"])
        aba.write_string(i, 9, "Sim" if e["no_dossie"] else "Não")

    # --- Por mês --------------------------------------------------------------
    por_mes: dict[str, dict] = {}
    for c in competencias:
        m = por_mes.setdefault(c["competencia"], {"competencias": 0, "envio": 0, "previa": 0, "fora_de_sp": 0,
                                                  "ressarcimento": _ZERO, "complemento": _ZERO,
                                                  "ressarcimento_para_envio": _ZERO})
        m["competencias"] += 1
        m["ressarcimento"] += c["ressarcimento"]
        m["complemento"] += c["complemento"]
        if c["situacao"] in m:
            m[c["situacao"]] += 1
        if c["situacao"] == SituacaoDaCompetencia.ENVIO.value:
            m["ressarcimento_para_envio"] += c["ressarcimento"]
    colunas = (("Competência", 12), ("Estabelecimentos", 14), ("Prontas para envio", 14), ("Prévias", 10),
               ("Fora de SP", 10), ("Ressarcimento para envio", 18), ("Ressarcimento apurado", 18),
               ("Complemento apurado", 18))
    aba = _aba_com_cabecalho(livro, "Por mês", colunas, f)
    for i, (mes, m) in enumerate(sorted(por_mes.items()), 1):
        aba.write_string(i, 0, mes, f["texto"])
        aba.write_number(i, 1, m["competencias"], f["inteiro"])
        aba.write_number(i, 2, m["envio"], f["inteiro"])
        aba.write_number(i, 3, m["previa"], f["inteiro"])
        aba.write_number(i, 4, m["fora_de_sp"], f["inteiro"])
        aba.write_number(i, 5, float(m["ressarcimento_para_envio"]), f["dinheiro"])
        aba.write_number(i, 6, float(m["ressarcimento"]), f["dinheiro"])
        aba.write_number(i, 7, float(m["complemento"]), f["dinheiro"])

    # --- Pendências -----------------------------------------------------------
    colunas = (("Gravidade", 16), ("Etapa onde se resolve", 32), ("Pendência", 56), ("Quantidade", 14),
               ("De quê", 14), ("Como cada etapa viu", 60), ("O que fazer", 90))
    aba = _aba_com_cabecalho(livro, "Pendências", colunas, f)
    for i, p in enumerate(resumo.pendencias, 1):
        aba.write_string(i, 0, p.gravidade.rotulo, f[p.gravidade.value])
        aba.write_string(i, 1, p.nome_da_etapa)
        aba.write_string(i, 2, p.rotulo)
        aba.write_number(i, 3, p.quantidade, f["inteiro"])
        aba.write_string(i, 4, p.unidade)
        aba.write_string(i, 5, " · ".join(
            f"{m.quantidade:,} {m.unidade} ({m.nome_da_etapa.lower()})".replace(",", ".") for m in p.medidas))
        aba.write_string(i, 6, p.o_que_fazer)

    # --- Trilha ---------------------------------------------------------------
    colunas = (("Etapa", 36), ("Execução", 10), ("Concluída em", 18), ("Iniciada por", 24), ("Duração (s)", 12))
    aba = _aba_com_cabecalho(livro, "Trilha", colunas, f)
    for i, t in enumerate(contexto.trilha, 1):
        aba.write_string(i, 0, NOME_DA_ETAPA.get(t["etapa"], t["etapa"]))
        aba.write_number(i, 1, t["execucao_id"], f["inteiro"])
        quando = _local(t.get("terminada_em"))
        if quando is not None:
            aba.write_datetime(i, 2, quando, f["quando"])
        aba.write_string(i, 3, t.get("iniciada_por") or "")
        if t.get("segundos") is not None:
            aba.write_number(i, 4, float(t["segundos"]), f["inteiro"])

    livro.close()
    log.info("relatório da entrega escrito",
             extra={"competencias": len(competencias), "estabelecimentos": len(estabelecimentos),
                    "pendencias": len(resumo.pendencias)})


def _aba_com_cabecalho(livro, titulo: str, colunas, f):
    aba = livro.add_worksheet(titulo[:31])
    for i, (nome, largura) in enumerate(colunas):
        aba.set_column(i, i, largura)
        aba.write_string(0, i, nome, f["cabecalho"])
    aba.freeze_panes(1, 0)
    return aba


# ---------------------------------------------------------------------------
# o manifesto e o pacote
# ---------------------------------------------------------------------------
def _reais(valor: Decimal) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _arquivos_do_pacote(destino: str) -> list[str]:
    """Os caminhos relativos, com `/`: é como ficam no zip e no manifesto."""
    saida = [ARQUIVO_RELATORIO]
    raiz = os.path.join(destino, PASTA_DOSSIE)
    for pasta, _, nomes in os.walk(raiz):
        for nome in nomes:
            relativo = os.path.relpath(os.path.join(pasta, nome), destino)
            saida.append(relativo.replace(os.sep, "/"))
    return sorted(saida, key=lambda c: (c != ARQUIVO_RELATORIO, c))


def _manifesto(destino: str, contexto: Contexto, resumo: ResumoDaEntrega) -> None:
    quando = _local(contexto.gerado_em)
    linhas = [
        "MANIFESTO DA ENTREGA - CAT 42",
        "",
        f"Empresa: {contexto.empresa} (CNPJ {contexto.cnpj_matriz})",
        f"Trabalho: {contexto.trabalho}",
        f"Periodo do trabalho: {contexto.periodo}",
        f"Periodo apurado: {contexto.periodo_apurado}",
        f"Venda a consumidor final: {contexto.venda_a_consumidor}",
        f"Gerado em: {quando:%d/%m/%Y %H:%M} por {contexto.gerado_por}" if quando else
        f"Gerado por: {contexto.gerado_por}",
        f"Sistema CAT {contexto.versao_do_sistema}",
        "",
        f"Competencias apuradas: {resumo.competencias} (SP: {resumo.competencias_de_sp}; fora de SP: {resumo.fora_de_sp})",
        f"Prontas para envio, no dossie: {resumo.para_envio}; previas, so no relatorio: {resumo.previas}",
        f"Ressarcimento nas competencias para envio: {_reais(resumo.ressarcimento_para_envio)}",
        f"Complemento nas competencias para envio: {_reais(resumo.complemento_para_envio)}",
        "",
        "De onde saiu (execucoes usadas):",
    ]
    for t in contexto.trilha:
        concluida = _local(t.get("terminada_em"))
        linhas.append(f"  {NOME_DA_ETAPA.get(t['etapa'], t['etapa'])} - execucao #{t['execucao_id']}"
                      + (f" - concluida em {concluida:%d/%m/%Y %H:%M}" if concluida else "")
                      + (f" por {t['iniciada_por']}" if t.get("iniciada_por") else ""))
    linhas += ["", "Arquivos do pacote (caminho | bytes | SHA-256):"]
    for relativo in _arquivos_do_pacote(destino):
        tamanho, sha = _hash(os.path.join(destino, *relativo.split("/")))
        linhas.append(f"  {relativo} | {tamanho} | {sha}")
    with open(os.path.join(destino, ARQUIVO_MANIFESTO), "w", encoding="utf-8", newline="\r\n") as saida:
        saida.write("\n".join(linhas) + "\n")


def _empacotar(destino: str, resumo: ResumoDaEntrega) -> None:
    provisorio = os.path.join(destino, ARQUIVO_PACOTE + ".tmp")
    nomes = [ARQUIVO_MANIFESTO, *_arquivos_do_pacote(destino)]
    with zipfile.ZipFile(provisorio, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for relativo in nomes:
            z.write(os.path.join(destino, *relativo.split("/")), arcname=relativo)
    final = os.path.join(destino, ARQUIVO_PACOTE)
    os.replace(provisorio, final)
    resumo.arquivos_no_pacote = len(nomes)
    resumo.bytes_do_pacote, resumo.sha256_do_pacote = _hash(final)
    log.info("pacote de entrega empacotado",
             extra={"arquivos": len(nomes), "bytes": resumo.bytes_do_pacote, "sha256": resumo.sha256_do_pacote})


# ---------------------------------------------------------------------------
# o que a tela lê
# ---------------------------------------------------------------------------
_RECORTES = {
    "no_dossie": "no_dossie",
    "fora_do_dossie": "NOT no_dossie",
    "com_previa": "previas > 0",
    "fora_de_sp": "fora_de_sp",
}


def estabelecimentos(destino: str, so: str | None = None, busca: str | None = None,
                     pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """Os estabelecimentos da entrega: os do dossiê primeiro, maior ressarcimento para envio."""
    if so and so not in _RECORTES:
        raise ValueError(f"Recorte desconhecido: {so}.")
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))
    caminho = os.path.join(destino, ARQUIVO_ESTABELECIMENTOS)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"{ARQUIVO_ESTABELECIMENTOS} não está em {destino}.")
    filtros, parametros = [], []
    if so:
        filtros.append(_RECORTES[so])
    if busca and busca.strip():
        filtros.append("cnpj ILIKE ?")
        parametros.append(f"%{busca.strip()}%")
    onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    base = f"(SELECT * FROM read_parquet('{_escapar(caminho)}') {onde})"
    con = _leitura(destino)
    try:
        total = con.execute(f"SELECT count(*) FROM {base}", parametros).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base}
            ORDER BY no_dossie DESC, ressarcimento_para_envio DESC, ressarcimento DESC, cnpj
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, parametros)
        nomes = [c[0] for c in cursor.description]
        linhas = [{k: (format(v, "f") if isinstance(v, Decimal) else v) for k, v in zip(nomes, r)}
                  for r in cursor.fetchall()]
    finally:
        con.close()
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas}


def serializar(resumo: ResumoDaEntrega) -> dict:
    def texto(v: Decimal) -> str:
        return format(Decimal(v).quantize(_Q2), "f")

    return {
        "competencias": resumo.competencias,
        "competencias_de_sp": resumo.competencias_de_sp,
        "para_envio": resumo.para_envio,
        "previas": resumo.previas,
        "fora_de_sp": resumo.fora_de_sp,
        "sem_arquivo": resumo.sem_arquivo,
        "estabelecimentos": resumo.estabelecimentos,
        "estabelecimentos_no_dossie": resumo.estabelecimentos_no_dossie,
        "ressarcimento": texto(resumo.ressarcimento),
        "complemento": texto(resumo.complemento),
        "ressarcimento_para_envio": texto(resumo.ressarcimento_para_envio),
        "complemento_para_envio": texto(resumo.complemento_para_envio),
        "arquivos_no_dossie": resumo.arquivos_no_dossie,
        "arquivos_no_pacote": resumo.arquivos_no_pacote,
        "bytes_do_pacote": resumo.bytes_do_pacote,
        "sha256_do_pacote": resumo.sha256_do_pacote,
        "por_gravidade": {g.value: sum(1 for p in resumo.pendencias if p.gravidade is g) for g in Gravidade},
        "pendencias": [
            {"etapa": p.etapa, "nome_da_etapa": p.nome_da_etapa, "codigo": p.codigo, "rotulo": p.rotulo,
             "quantidade": p.quantidade, "unidade": p.unidade, "gravidade": p.gravidade.value,
             "gravidade_rotulo": p.gravidade.rotulo, "o_que_fazer": p.o_que_fazer,
             "medidas": [{"quantidade": m.quantidade, "unidade": m.unidade, "etapa": m.etapa,
                          "nome_da_etapa": m.nome_da_etapa} for m in p.medidas]}
            for p in resumo.pendencias
        ],
    }

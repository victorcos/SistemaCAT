"""Extrair para parquet o que a EFD diz de cada mercadoria.

Uma passada por arquivo, em binário, comparando prefixo antes de quebrar a
linha (as duas regras de `extracao.py`, que valeram 2,4 vezes numa varredura
de 119,82 GB). Saem cinco parquets por execução:

* ``documentos.parquet`` — cada C100/C800, com quantos itens e quantos
  analíticos vieram embaixo dele. É o que permite dizer "esta saída não tem
  item na EFD" em vez de descobrir isso no razão;
* ``_movimentos_brutos.parquet`` — cada C170/C810, já amarrado ao documento
  pai (chave, data, operação). O registro filho não repete a chave; quem
  amarra é a leitura, pela ordem do arquivo;
* ``analitico.parquet`` — cada C190/C850: total por CST/CFOP/alíquota, já
  com ``tem_item``: se o documento pai trouxe C170/C810. Sai pronto daqui
  porque descobrir isso depois custaria uma junção de 100 milhões de
  analíticos contra 38 milhões de documentos — e aqui é de graça: os
  analíticos de um documento esperam em memória (são dois ou três) até o
  documento fechar, quando já se sabe quantos itens ele teve;
* ``itens_da_efd.parquet`` — cada 0200, por arquivo (o cadastro se repete a
  cada período; a consolidação escolhe o mais recente);
* ``inventario.parquet`` — cada H010, com a data e o motivo do H005.

A amarração filho→pai depende da ordem do arquivo, que o leiaute garante: o
C170 vem logo abaixo do seu C100. Um C170 sem C100 antes é arquivo quebrado e
vai para o log, não para o parquet.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal

import pyarrow as pa

from cat.dominio.sped.fiscais import DocumentoEscriturado, ler_documento
from cat.dominio.sped.itens import LEITORES, PREFIXOS_DE_ITENS, Inventario
from cat.infraestrutura.analitico.extracao import (
    CODIFICACAO,
    Aviso,
    Progresso,
    _Escritor,
    _identificacao,
    _tamanho,
)
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_DOCUMENTOS = "documentos.parquet"
ARQUIVO_MOVIMENTOS_BRUTOS = "_movimentos_brutos.parquet"
ARQUIVO_ANALITICO = "analitico.parquet"
ARQUIVO_ITENS_DA_EFD = "itens_da_efd.parquet"
ARQUIVO_INVENTARIO = "inventario.parquet"

PREFIXOS = (b"|C100|", b"|C800|") + PREFIXOS_DE_ITENS

# escalas do parquet: quantidade tem 5 casas na EFD, dinheiro 2, alíquota 2
# (4 por folga), valor unitário do inventário 6
_Q5 = Decimal("0.00001")
_Q2 = Decimal("0.01")
_Q4 = Decimal("0.0001")
_Q6 = Decimal("0.000001")

_DOCUMENTO = [
    ("cnpj", pa.string()),
    ("competencia", pa.date32()),
    ("arquivo", pa.string()),
    ("chave", pa.string()),
    ("modelo", pa.string()),
    ("situacao", pa.string()),
    ("numero_documento", pa.string()),
    ("data", pa.date32()),
    ("operacao", pa.string()),
    ("emitente", pa.string()),
    ("participante", pa.string()),
]

ESQUEMA_DOCUMENTOS = pa.schema(_DOCUMENTO + [
    ("valor", pa.decimal128(18, 2)),
    ("itens", pa.int32()),
    ("analiticos", pa.int32()),
])

ESQUEMA_MOVIMENTOS = pa.schema(_DOCUMENTO + [
    ("registro", pa.string()),
    ("numero_item", pa.int32()),
    ("codigo", pa.string()),
    ("descricao_complementar", pa.string()),
    ("quantidade", pa.decimal128(20, 5)),
    ("unidade", pa.string()),
    ("valor", pa.decimal128(18, 2)),
    ("desconto", pa.decimal128(18, 2)),
    ("ind_mov", pa.string()),
    ("cst_icms", pa.string()),
    ("cfop", pa.string()),
    ("bc_icms", pa.decimal128(18, 2)),
    ("aliq_icms", pa.decimal128(9, 4)),
    ("valor_icms", pa.decimal128(18, 2)),
    ("bc_st", pa.decimal128(18, 2)),
    ("aliq_st", pa.decimal128(9, 4)),
    ("valor_st", pa.decimal128(18, 2)),
])

ESQUEMA_ANALITICO = pa.schema(_DOCUMENTO + [
    ("registro", pa.string()),
    ("cst_icms", pa.string()),
    ("cfop", pa.string()),
    ("aliq_icms", pa.decimal128(9, 4)),
    ("valor_operacao", pa.decimal128(18, 2)),
    ("bc_icms", pa.decimal128(18, 2)),
    ("valor_icms", pa.decimal128(18, 2)),
    ("bc_st", pa.decimal128(18, 2)),
    ("valor_st", pa.decimal128(18, 2)),
    ("valor_red_bc", pa.decimal128(18, 2)),
    ("valor_ipi", pa.decimal128(18, 2)),
    ("tem_item", pa.bool_()),          # o documento pai trouxe C170/C810
])

ESQUEMA_ITENS = pa.schema([
    ("cnpj", pa.string()),
    ("competencia", pa.date32()),
    ("arquivo", pa.string()),
    ("codigo", pa.string()),
    ("descricao", pa.string()),
    ("codigo_barras", pa.string()),
    ("codigo_anterior", pa.string()),
    ("unidade", pa.string()),
    ("tipo_item", pa.string()),
    ("ncm", pa.string()),
    ("ex_ipi", pa.string()),
    ("cod_gen", pa.string()),
    ("cod_lst", pa.string()),
    ("aliq_icms", pa.decimal128(9, 4)),
    ("cest", pa.string()),
])

ESQUEMA_INVENTARIO = pa.schema([
    ("cnpj", pa.string()),
    ("competencia", pa.date32()),
    ("arquivo", pa.string()),
    ("data_inventario", pa.date32()),
    ("motivo", pa.string()),
    ("valor_total", pa.decimal128(18, 2)),
    ("codigo", pa.string()),
    ("unidade", pa.string()),
    ("quantidade", pa.decimal128(20, 5)),
    ("valor_unitario", pa.decimal128(20, 6)),
    ("valor", pa.decimal128(18, 2)),
    ("ind_prop", pa.string()),
    ("participante", pa.string()),
    ("cod_cta", pa.string()),
])


@dataclass
class ProgressoDeItens(Progresso):
    """O `Progresso` de sempre mais o que esta extração conta."""

    movimentos: int = 0
    analiticos: int = 0
    itens_cadastrados: int = 0
    em_estoque: int = 0
    documentos_com_item: int = 0
    orfaos: int = 0                    # C170/C190 sem C100 antes: arquivo quebrado
    arquivos_com_orfaos: list[str] = field(default_factory=list)


def _q(valor: Decimal, casas: Decimal) -> Decimal:
    return valor.quantize(casas)


class _Contexto:
    """O documento aberto e o inventário aberto, por arquivo."""

    def __init__(self, cnpj: str, competencia, arquivo: str) -> None:
        self.base = {"cnpj": cnpj, "competencia": competencia, "arquivo": arquivo}
        self.doc: DocumentoEscriturado | None = None
        self.itens = 0
        # os analíticos esperam o documento fechar para sair com `tem_item`
        self.analiticos: list[dict] = []
        self.inventario: Inventario | None = None

    def do_documento(self) -> dict:
        d = self.doc
        assert d is not None
        return {
            **self.base,
            "chave": d.chave, "modelo": d.modelo, "situacao": d.situacao,
            "numero_documento": d.numero, "data": d.data,
            "operacao": d.operacao.value, "emitente": d.emitente.value,
            "participante": d.participante,
        }


def extrair_movimentos(caminhos: list[str], destino: str,
                       avisar: Aviso | None = None) -> ProgressoDeItens:
    """Lê as EFD e grava os cinco parquets em `destino`."""
    os.makedirs(destino, exist_ok=True)
    progresso = ProgressoDeItens(arquivos_totais=len(caminhos))
    escritores = {
        "documentos": _Escritor(os.path.join(destino, ARQUIVO_DOCUMENTOS),
                                ESQUEMA_DOCUMENTOS),
        "movimentos": _Escritor(os.path.join(destino, ARQUIVO_MOVIMENTOS_BRUTOS),
                                ESQUEMA_MOVIMENTOS),
        "analitico": _Escritor(os.path.join(destino, ARQUIVO_ANALITICO),
                               ESQUEMA_ANALITICO),
        "itens": _Escritor(os.path.join(destino, ARQUIVO_ITENS_DA_EFD),
                           ESQUEMA_ITENS),
        "inventario": _Escritor(os.path.join(destino, ARQUIVO_INVENTARIO),
                                ESQUEMA_INVENTARIO),
    }

    for caminho in caminhos:
        nome = os.path.basename(caminho)
        cnpj, competencia = _identificacao(caminho)
        ctx = _Contexto(cnpj, competencia, nome)
        try:
            _ler_arquivo(caminho, ctx, escritores, progresso)
        except OSError as erro:
            progresso.recusados.append(f"{nome}: {erro}")
            log.warning("arquivo de EFD ilegível na extração de movimentos",
                        extra={"arquivo": nome, "motivo": str(erro)})
        else:
            progresso.bytes_lidos += _tamanho(caminho)

        progresso.arquivos_lidos += 1
        if avisar is not None:
            avisar(progresso)

    for escritor in escritores.values():
        escritor.fechar()
    log.info("movimentos extraídos",
             extra={"arquivos": progresso.arquivos_lidos,
                    "documentos": progresso.documentos,
                    "com_item": progresso.documentos_com_item,
                    "movimentos": progresso.movimentos,
                    "analiticos": progresso.analiticos,
                    "itens_cadastrados": progresso.itens_cadastrados,
                    "em_estoque": progresso.em_estoque,
                    "orfaos": progresso.orfaos})
    return progresso


def _ler_arquivo(caminho: str, ctx: _Contexto, escritores: dict,
                 progresso: ProgressoDeItens) -> None:
    orfaos_aqui = 0
    with open(caminho, "rb") as f:
        for bruto in f:
            if not bruto.startswith(PREFIXOS):
                continue
            linha = bruto.decode(CODIFICACAO).rstrip("\r\n")
            campos = linha.split("|")
            registro = campos[1]

            if registro in ("C100", "C800"):
                _fechar_documento(ctx, escritores, progresso)
                ctx.doc = ler_documento(linha)
                ctx.itens = 0
                progresso.documentos += 1
                continue

            lido = LEITORES[registro](campos)

            if registro in ("C170", "C810"):
                if ctx.doc is None:
                    orfaos_aqui += 1
                    continue
                escritores["movimentos"].acrescentar({
                    **ctx.do_documento(),
                    "registro": lido.registro, "numero_item": lido.numero,
                    "codigo": lido.codigo,
                    "descricao_complementar": lido.descricao_complementar,
                    "quantidade": _q(lido.quantidade, _Q5),
                    "unidade": lido.unidade,
                    "valor": _q(lido.valor, _Q2), "desconto": _q(lido.desconto, _Q2),
                    "ind_mov": lido.ind_mov, "cst_icms": lido.cst_icms,
                    "cfop": lido.cfop,
                    "bc_icms": _q(lido.bc_icms, _Q2),
                    "aliq_icms": _q(lido.aliq_icms, _Q4),
                    "valor_icms": _q(lido.valor_icms, _Q2),
                    "bc_st": _q(lido.bc_st, _Q2), "aliq_st": _q(lido.aliq_st, _Q4),
                    "valor_st": _q(lido.valor_st, _Q2),
                })
                ctx.itens += 1
                progresso.movimentos += 1

            elif registro in ("C190", "C850"):
                if ctx.doc is None:
                    orfaos_aqui += 1
                    continue
                ctx.analiticos.append({
                    "registro": lido.registro, "cst_icms": lido.cst_icms,
                    "cfop": lido.cfop, "aliq_icms": _q(lido.aliq_icms, _Q4),
                    "valor_operacao": _q(lido.valor_operacao, _Q2),
                    "bc_icms": _q(lido.bc_icms, _Q2),
                    "valor_icms": _q(lido.valor_icms, _Q2),
                    "bc_st": _q(lido.bc_st, _Q2), "valor_st": _q(lido.valor_st, _Q2),
                    "valor_red_bc": _q(lido.valor_red_bc, _Q2),
                    "valor_ipi": _q(lido.valor_ipi, _Q2),
                })
                progresso.analiticos += 1

            elif registro == "0200":
                escritores["itens"].acrescentar({
                    **ctx.base,
                    "codigo": lido.codigo, "descricao": lido.descricao,
                    "codigo_barras": lido.codigo_barras,
                    "codigo_anterior": lido.codigo_anterior,
                    "unidade": lido.unidade, "tipo_item": lido.tipo_item,
                    "ncm": lido.ncm, "ex_ipi": lido.ex_ipi, "cod_gen": lido.cod_gen,
                    "cod_lst": lido.cod_lst, "aliq_icms": _q(lido.aliq_icms, _Q4),
                    "cest": lido.cest,
                })
                progresso.itens_cadastrados += 1

            elif registro == "H005":
                ctx.inventario = lido

            elif registro == "H010":
                inv = ctx.inventario
                escritores["inventario"].acrescentar({
                    **ctx.base,
                    "data_inventario": inv.data if inv else None,
                    "motivo": inv.motivo if inv else "",
                    "valor_total": _q(inv.valor_total, _Q2) if inv else None,
                    "codigo": lido.codigo, "unidade": lido.unidade,
                    "quantidade": _q(lido.quantidade, _Q5),
                    "valor_unitario": _q(lido.valor_unitario, _Q6),
                    "valor": _q(lido.valor, _Q2), "ind_prop": lido.ind_prop,
                    "participante": lido.participante, "cod_cta": lido.cod_cta,
                })
                progresso.em_estoque += 1

    _fechar_documento(ctx, escritores, progresso)
    if orfaos_aqui:
        progresso.orfaos += orfaos_aqui
        progresso.arquivos_com_orfaos.append(ctx.base["arquivo"])
        log.warning("registro filho sem documento pai: arquivo fora de ordem",
                    extra={"arquivo": ctx.base["arquivo"], "linhas": orfaos_aqui})


def _fechar_documento(ctx: _Contexto, escritores: dict,
                      progresso: ProgressoDeItens) -> None:
    if ctx.doc is None:
        return
    documento = ctx.do_documento()
    escritores["documentos"].acrescentar({
        **documento,
        "valor": _q(ctx.doc.valor, _Q2),
        "itens": ctx.itens, "analiticos": len(ctx.analiticos),
    })
    for analitico in ctx.analiticos:
        escritores["analitico"].acrescentar(
            {**documento, **analitico, "tem_item": ctx.itens > 0})
    if ctx.itens:
        progresso.documentos_com_item += 1
    ctx.doc = None
    ctx.analiticos = []

"""Extrair para parquet o item de cada XML do trabalho.

É a outra metade da etapa 3. A EFD dá o item de entrada (C170) e quase nada de
saída; o XML dá o item de qualquer documento que o cliente entregou. Sai daqui
``itens_do_xml.parquet``, uma linha por item, e a consolidação decide o que
fazer com ele (`movimentacao.py`): completar o documento que a EFD escriturou
sem item, e pôr os valores do XML ao lado do C170 que já existe — o XML vence.

Um documento por chave. O mesmo XML aparece mais de uma vez quando o cliente
manda a pasta do mês e a do trimestre: vale o primeiro arquivo lido, e os
outros são contados. O que não é documento (evento de cancelamento, carta de
correção, inutilização) e o que não abre ficam contados e no log, sem derrubar
a leitura dos outros milhares.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

import pyarrow as pa

from cat.dominio.notafiscal.xml import DocumentoXml, XmlIlegivel, ler_documento_xml
from cat.infraestrutura.analitico.extracao import Aviso, Progresso, _Escritor
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_ITENS_DO_XML = "itens_do_xml.parquet"

_Q2 = Decimal("0.01")
_Q4 = Decimal("0.0001")
_Q5 = Decimal("0.00001")

ESQUEMA_ITENS_DO_XML = pa.schema([
    ("chave", pa.string()),
    ("modelo", pa.string()),
    ("tipo", pa.string()),                  # tpNF: 0 entrada, 1 saída, de quem emitiu
    ("emitente", pa.string()),
    ("destinatario", pa.string()),
    ("numero_documento", pa.string()),
    ("serie", pa.string()),
    ("emissao", pa.date32()),
    # indFinal da NF-e; NFC-e e CF-e são de consumidor final
    ("consumidor_final", pa.bool_()),
    ("arquivo", pa.string()),
    ("numero_item", pa.int32()),
    ("codigo", pa.string()),
    ("gtin", pa.string()),
    ("descricao", pa.string()),
    ("ncm", pa.string()),
    ("cest", pa.string()),
    ("cfop", pa.string()),
    ("unidade", pa.string()),
    ("quantidade", pa.decimal128(20, 5)),
    ("valor", pa.decimal128(18, 2)),
    ("desconto", pa.decimal128(18, 2)),
    ("cst_icms", pa.string()),
    ("bc_icms", pa.decimal128(18, 2)),
    ("aliq_icms", pa.decimal128(9, 4)),
    ("valor_icms", pa.decimal128(18, 2)),
    ("bc_st", pa.decimal128(18, 2)),
    ("aliq_st", pa.decimal128(9, 4)),
    ("valor_st", pa.decimal128(18, 2)),
    ("fcp_st", pa.decimal128(18, 2)),
    ("bc_st_retido", pa.decimal128(18, 2)),
    # o ICMS suportado antes, como a NF-e informa no CST 60: substituto + retido + FCP
    ("retido_informado", pa.decimal128(18, 2)),
])


@dataclass
class ProgressoDoXml(Progresso):
    """O `Progresso` de sempre mais o que a leitura dos XML conta."""

    itens: int = 0
    repetidos: int = 0
    nao_sao_documento: int = 0
    ilegiveis: int = 0
    sem_item: int = 0
    exemplos_ilegiveis: list[str] = field(default_factory=list)


def _q(valor: Decimal, casas: Decimal) -> Decimal:
    return valor.quantize(casas, rounding=ROUND_HALF_UP)


def extrair_itens_do_xml(xmls: list[str], destino: str, avisar: Aviso | None = None,
                         progresso: ProgressoDoXml | None = None) -> ProgressoDoXml:
    """Grava `itens_do_xml.parquet` em `destino` com o item de cada XML."""
    return extrair_itens_de_conteudos(((c, None) for c in xmls), destino, avisar,
                                      progresso or ProgressoDoXml(arquivos_totais=len(xmls)))


def extrair_itens_de_conteudos(fontes: Iterable[tuple[str, bytes | None]], destino: str,
                               avisar: Aviso | None = None,
                               progresso: ProgressoDoXml | None = None) -> ProgressoDoXml:
    """O mesmo, a partir de (nome, conteúdo). Conteúdo None: lê do disco pelo nome.

    É por aqui que um XML de dentro de zip entra sem ser extraído para o disco.
    """
    os.makedirs(destino, exist_ok=True)
    progresso = progresso or ProgressoDoXml()
    escritor = _Escritor(os.path.join(destino, ARQUIVO_ITENS_DO_XML), ESQUEMA_ITENS_DO_XML)
    vistas: set[str] = set()
    try:
        for nome, conteudo in fontes:
            _ler_um(nome, conteudo, escritor, vistas, progresso)
            progresso.arquivos_lidos += 1
            if avisar is not None:
                avisar(progresso)
    finally:
        escritor.fechar()
    log.info("itens dos XML extraídos", extra={
        "arquivos": progresso.arquivos_lidos, "documentos": progresso.documentos,
        "itens": progresso.itens, "repetidos": progresso.repetidos,
        "nao_sao_documento": progresso.nao_sao_documento, "ilegiveis": progresso.ilegiveis,
        "sem_item": progresso.sem_item})
    return progresso


def _ler_um(caminho: str, conteudo: bytes | None, escritor: _Escritor, vistas: set[str],
            progresso: ProgressoDoXml) -> None:
    nome = os.path.basename(caminho)
    try:
        if conteudo is None:
            with open(caminho, "rb") as f:
                conteudo = f.read()
        progresso.bytes_lidos += len(conteudo)
        doc = ler_documento_xml(conteudo)
    except (OSError, XmlIlegivel) as erro:
        _ilegivel(nome, erro, progresso)
        return
    if doc is None:
        progresso.nao_sao_documento += 1
        return
    if len(doc.chave) != 44 or not doc.chave.isdigit():
        _ilegivel(nome, ValueError(f"chave de acesso inválida: {doc.chave!r}"), progresso)
        return
    if doc.chave in vistas:
        progresso.repetidos += 1
        return
    try:
        linhas = [_linha(doc, nome, item) for item in doc.itens]
    except (ArithmeticError, ValueError) as erro:
        # valor que não cabe no esquema: o arquivo inteiro fica de fora, avisado
        _ilegivel(nome, erro, progresso)
        return
    vistas.add(doc.chave)
    progresso.documentos += 1
    if not linhas:
        progresso.sem_item += 1
    for linha in linhas:
        escritor.acrescentar(linha)
    progresso.itens += len(linhas)


def _linha(doc: DocumentoXml, arquivo: str, item) -> dict:
    return {
        "chave": doc.chave, "modelo": doc.modelo, "tipo": doc.tipo, "emitente": doc.emitente,
        "destinatario": doc.destinatario, "numero_documento": doc.numero, "serie": doc.serie,
        "emissao": doc.emissao, "consumidor_final": doc.consumidor_final, "arquivo": arquivo,
        "numero_item": item.numero, "codigo": item.codigo, "gtin": item.gtin,
        "descricao": item.descricao, "ncm": item.ncm, "cest": item.cest, "cfop": item.cfop,
        "unidade": item.unidade, "quantidade": _q(item.quantidade, _Q5),
        "valor": _q(item.valor, _Q2), "desconto": _q(item.desconto, _Q2),
        "cst_icms": item.cst_icms,
        "bc_icms": _q(item.bc_icms, _Q2), "aliq_icms": _q(item.aliq_icms, _Q4),
        "valor_icms": _q(item.valor_icms, _Q2),
        "bc_st": _q(item.bc_st, _Q2), "aliq_st": _q(item.aliq_st, _Q4),
        "valor_st": _q(item.valor_st, _Q2), "fcp_st": _q(item.fcp_st, _Q2),
        "bc_st_retido": _q(item.bc_st_retido, _Q2),
        "retido_informado": _q(item.retido_informado, _Q2) if item.retido_informado is not None else None,
    }


def _ilegivel(nome: str, erro: Exception, progresso: ProgressoDoXml) -> None:
    progresso.ilegiveis += 1
    if len(progresso.exemplos_ilegiveis) < 20:
        progresso.exemplos_ilegiveis.append(f"{nome}: {erro}")
    log.warning("XML ilegível na extração de itens", extra={"arquivo": nome, "motivo": str(erro)})

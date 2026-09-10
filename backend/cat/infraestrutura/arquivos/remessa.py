"""Leitura da remessa enviada pela tela de importação.

Aceita o arquivo solto ou compactado, porque as duas formas aparecem: os SPED
chegam um por competência e por filial, e uma empresa com 101 estabelecimentos
e 84 competências entrega isso num zip.

O que este módulo NÃO faz é ler o arquivo inteiro. Para descobrir de quem é o
arquivo basta a primeira linha, e são milhares deles. Ler tudo levaria minutos
para responder o que a primeira linha já responde.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Iterator

from cat.log import obter_log

log = obter_log(__name__)

# O SPED é gerado em ISO 8859-1. Tentamos UTF-8 antes porque alguns
# geradores fogem do padrão, e latin-1 nunca falha — aceita qualquer byte.
CODIFICACOES = ("utf-8-sig", "utf-8", "latin-1")

LIMITE_REMESSA = 2 * 1024 * 1024 * 1024   # 2 GB
LIMITE_ARQUIVOS = 20_000
EXTENSOES_TEXTO = (".txt", ".sped", ".efd")


class RemessaInvalida(ValueError):
    pass


@dataclass(frozen=True)
class ArquivoDaRemessa:
    """Um arquivo de dentro da remessa, com só o que basta para identificá-lo."""

    nome: str
    caminho_interno: str
    tamanho: int
    primeira_linha: str


def _decodificar(bruto: bytes) -> str:
    for cod in CODIFICACOES:
        try:
            return bruto.decode(cod)
        except UnicodeDecodeError:
            continue
    # inalcançável: latin-1 aceita qualquer byte. Fica como rede de segurança.
    return bruto.decode("latin-1", errors="replace")


def _primeira_linha(fluxo, limite: int = 8192) -> str:
    """Lê só o começo. O registro 0000 é a primeira linha e é curto."""
    pedaco = fluxo.read(limite)
    if not pedaco:
        return ""
    texto = _decodificar(pedaco)
    return texto.splitlines()[0] if texto.splitlines() else ""


def _e_texto(nome: str) -> bool:
    return nome.lower().endswith(EXTENSOES_TEXTO)


def percorrer(conteudo: bytes, nome_enviado: str) -> Iterator[ArquivoDaRemessa]:
    """Percorre a remessa, seja ela um arquivo só ou um zip.

    Não extrai nada para disco: lê o cabeçalho de dentro do próprio zip.
    """
    if zipfile.is_zipfile(io.BytesIO(conteudo)):
        yield from _percorrer_zip(conteudo, nome_enviado)
        return

    if not _e_texto(nome_enviado):
        raise RemessaInvalida(
            f"'{nome_enviado}' não é texto nem compactado. "
            f"Aceito {', '.join(EXTENSOES_TEXTO)} ou .zip."
        )
    yield ArquivoDaRemessa(
        nome=nome_enviado,
        caminho_interno=nome_enviado,
        tamanho=len(conteudo),
        primeira_linha=_primeira_linha(io.BytesIO(conteudo)),
    )


def _percorrer_zip(conteudo: bytes, nome_enviado: str) -> Iterator[ArquivoDaRemessa]:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        entradas = [i for i in z.infolist() if not i.is_dir() and _e_texto(i.filename)]

        if not entradas:
            raise RemessaInvalida(
                f"'{nome_enviado}' não tem nenhum arquivo de texto dentro."
            )
        if len(entradas) > LIMITE_ARQUIVOS:
            raise RemessaInvalida(
                f"a remessa tem {len(entradas):,} arquivos, acima do limite de "
                f"{LIMITE_ARQUIVOS:,}. Divida em partes."
            )

        # um zip pequeno que se expande em gigabytes é o ataque clássico
        descomprimido = sum(i.file_size for i in entradas)
        if descomprimido > LIMITE_REMESSA:
            raise RemessaInvalida(
                f"a remessa expande para {descomprimido / 1e9:.1f} GB, acima do "
                f"limite de {LIMITE_REMESSA / 1e9:.0f} GB."
            )

        log.info(
            "remessa compactada aberta",
            extra={"remessa": nome_enviado, "arquivos": len(entradas),
                   "bytes_descomprimidos": descomprimido},
        )

        for info in entradas:
            with z.open(info) as fh:
                yield ArquivoDaRemessa(
                    nome=info.filename.rsplit("/", 1)[-1],
                    caminho_interno=info.filename,
                    tamanho=info.file_size,
                    primeira_linha=_primeira_linha(fh),
                )

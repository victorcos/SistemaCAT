"""XML dentro de zip, lido sem extrair para o disco.

A empresa D entregou as notas assim: 357.950 XML em zips baixados do portal.
Extrair para ler custou mais que ler — o antivírus examina cada arquivo que
nasce, e o disco de rede perde gravação. O zip entra no lote como um arquivo só
(`xml_compactado`), e as etapas leem os membros direto do zip, na memória, um
por vez.

Só `.zip`: é o que o portal e o Windows geram. **Um nível de zip dentro de zip é
aberto** — na empresa D, 290 mil das notas estavam em 60 zips dentro dos
zips. O zip de dentro gravado sem compressão (o caso medido) é lido direto do
de fora, por posição; o comprimido vai para a memória, até 256 MB.

O nome de um membro, para log e planilha, é ``lote.zip > nota.xml`` — sem barra,
para o `basename` de quem mostra não cortar o nome do zip fora.
"""

from __future__ import annotations

import io
import os
import zipfile
from collections.abc import Iterable, Iterator

from cat.dominio.lote import caminho_de_certificado
from cat.log import obter_log

log = obter_log(__name__)

EXTENSAO_ZIP = ".zip"
LIMITE_DO_ZIP_INTERNO_COMPRIMIDO = 256 * 1024 * 1024
_ERROS_DE_ZIP = (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, EOFError, ValueError)


def e_zip(caminho: str) -> bool:
    return caminho.lower().endswith(EXTENSAO_ZIP)


def nome_do_membro(caminho: str, membro: str) -> str:
    return f"{caminho} > {os.path.basename(membro)}"


def _abrir_interno(externo: zipfile.ZipFile, info: zipfile.ZipInfo) -> zipfile.ZipFile:
    if info.compress_type == zipfile.ZIP_STORED:
        return zipfile.ZipFile(externo.open(info))
    if info.file_size > LIMITE_DO_ZIP_INTERNO_COMPRIMIDO:
        raise ValueError(f"zip interno comprimido de {info.file_size // 2**20} MB passa do limite")
    return zipfile.ZipFile(io.BytesIO(externo.read(info)))


def membros_xml(arquivo: zipfile.ZipFile, nome: str,
                recusados: list[str] | None = None,
                nivel: int = 0) -> Iterator[tuple[str, zipfile.ZipFile, zipfile.ZipInfo]]:
    """(nome de exibição, zip que contém, membro) de cada XML, entrando um nível."""
    for info in arquivo.infolist():
        minusculo = info.filename.lower()
        if info.is_dir() or caminho_de_certificado(info.filename):
            # certificado dentro do zip: não se abre, e o nome não vai a log nem a recusados
            continue
        if minusculo.endswith(".xml"):
            yield nome_do_membro(nome, info.filename), arquivo, info
        elif minusculo.endswith(EXTENSAO_ZIP) and nivel == 0:
            interno_nome = nome_do_membro(nome, info.filename)
            try:
                interno = _abrir_interno(arquivo, info)
            except _ERROS_DE_ZIP as erro:
                _recusar(interno_nome, erro, recusados)
                continue
            with interno:
                yield from membros_xml(interno, interno_nome, recusados, nivel + 1)


def contar_xml(caminhos: Iterable[str]) -> int:
    """Quantos XML há: um por arquivo solto, um por membro de zip.

    Só os diretórios centrais são lidos, não os membros. É o total da barra de
    andamento.
    """
    total = 0
    for caminho in caminhos:
        if not e_zip(caminho):
            total += 1
            continue
        try:
            with zipfile.ZipFile(caminho) as arquivo:
                total += sum(1 for _ in membros_xml(arquivo, caminho))
        except _ERROS_DE_ZIP as erro:
            log.warning("zip de XML ilegível ao contar", extra={"arquivo": caminho, "motivo": str(erro)})
    return total


def conteudos_de_xml(caminhos: Iterable[str], limite: int | None = None,
                     recusados: list[str] | None = None) -> Iterator[tuple[str, bytes | None]]:
    """(nome, conteúdo) de cada XML. Solto vai com conteúdo None: quem lê abre.

    `limite` lê só o começo de cada membro — a etapa 2 só precisa da chave.
    Zip ou membro quebrado vai para `recusados`, e a leitura segue.
    """
    for caminho in caminhos:
        if not e_zip(caminho):
            yield caminho, None
            continue
        try:
            with zipfile.ZipFile(caminho) as arquivo:
                for nome, dono, info in membros_xml(arquivo, caminho, recusados):
                    try:
                        with dono.open(info) as f:
                            conteudo = f.read(limite) if limite else f.read()
                    except _ERROS_DE_ZIP as erro:
                        # membro corrompido ou cifrado: os outros do zip seguem
                        _recusar(nome, erro, recusados)
                        continue
                    yield nome, conteudo
        except _ERROS_DE_ZIP as erro:
            _recusar(caminho, erro, recusados)


def _recusar(nome: str, erro: Exception, recusados: list[str] | None) -> None:
    log.warning("zip de XML ilegível", extra={"arquivo": nome, "motivo": str(erro)})
    if recusados is not None:
        recusados.append(f"{os.path.basename(nome)}: {erro}")

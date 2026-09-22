"""Ler SPED em fluxo, sabendo onde cada linha está.

Portado do projeto Quebra de SPED (22/09/2026), que resolveu o mesmo problema
que `analitico/extracao.py` resolve aqui — e chegou às mesmas duas regras:
**filtrar antes de quebrar a linha** e **comparar em bytes**. O que ele tem a
mais, e é o motivo do porte, é a **posição**: guardando onde cada registro
começa, qualquer bloco volta depois com um `seek`, sem reler o arquivo.

## Por que `readline()` e não `for linha in arquivo`

Porque é preciso saber a posição **antes** de consumir a linha. O `for` do
CPython lê por buffer interno, e `tell()` devolveria o fim do buffer — não o
começo da linha que acabou de sair. Com `readline()` a posição é exata, e é
dela que o índice inteiro depende.

## Codificação

SPED é gerado no Windows e vem em CP1252. Só se declara UTF-8 quando há BOM
explícito: tentar adivinhar por amostra é falso-positivo garantido — os
primeiros 4 KB podem não ter um acento sequer, e o nome com "Ç" lá pelo meio do
arquivo sai corrompido. Errar para o lado do CP1252 é errar para o lado que
sempre decodifica.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from cat.log import obter_log

log = obter_log(__name__)

# 1 MiB equilibra vazão e memória na leitura sequencial; 8 MiB é para quando o
# arquivo está em disco de rede, onde o que custa é a ida e volta, não o byte
BUFFER = 1 << 20
BUFFER_DE_REDE = 8 << 20

MARCA_UTF8 = b"\xef\xbb\xbf"
CODIFICACAO_PADRAO = "cp1252"


def codificacao_de(caminho: str) -> str:
    """CP1252, salvo BOM explícito de UTF-8. Ver o porquê no topo do módulo."""
    try:
        with open(caminho, "rb") as arquivo:
            comeco = arquivo.read(len(MARCA_UTF8))
    except OSError:
        return CODIFICACAO_PADRAO
    return "utf-8-sig" if comeco.startswith(MARCA_UTF8) else CODIFICACAO_PADRAO


def linhas_com_posicao(caminho: str, buffer: int = BUFFER) -> Iterator[tuple[int, bytes]]:
    """Cada linha do arquivo e a posição em bytes onde ela começa."""
    with open(caminho, "rb", buffering=buffer) as arquivo:
        while True:
            posicao = arquivo.tell()
            linha = arquivo.readline()
            if not linha:
                return
            yield posicao, linha


def registro_de(linha: bytes) -> bytes | None:
    """O código do registro, em bytes, sem decodificar a linha inteira.

    A linha do SPED é `|REG|campo|campo|`. Achar o segundo `|` é muito mais
    barato que uma expressão regular, e numa base de dez milhões de linhas essa
    diferença é o tempo da etapa.
    """
    if not linha.startswith(b"|"):
        return None
    fim = linha.find(b"|", 1)
    return linha[1:fim] if fim > 1 else None


def campos(linha: str) -> list[str]:
    """A linha quebrada nos campos, sem o vazio do começo nem o do fim.

    Linha torta volta como veio: recusar o arquivo inteiro por causa de uma
    linha malformada seria pior — SPED de cliente tem preâmbulo de exportador,
    linha em branco e coisa pior.
    """
    linha = linha.rstrip("\r\n")
    if not linha.startswith("|") or not linha.endswith("|"):
        return linha.split("|")
    return linha[1:-1].split("|")


def campos_da_linha(linha: bytes, codificacao: str) -> list[str]:
    """Decodifica e quebra — só para a linha que já passou pelo filtro."""
    return campos(linha.decode(codificacao, errors="replace"))


def tamanho_de(caminho: str) -> int:
    try:
        return os.path.getsize(caminho)
    except OSError as erro:
        log.warning("não deu para medir o arquivo",
                    extra={"arquivo": os.path.basename(caminho), "motivo": str(erro)})
        return 0

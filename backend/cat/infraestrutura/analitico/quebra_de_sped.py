"""Quebrar os SPED do trabalho: abrir os arquivos e dizer o que há dentro.

Uma passada por arquivo, e dela saem três coisas:

| `arquivos.parquet`  | uma ficha por SPED: empresa, período, tamanho, linhas |
| `contagens.parquet` | quantos de cada registro cada arquivo tem             |
| `indices/`          | a posição em bytes de cada registro, por arquivo      |

O índice é o que importa depois: com ele, extrair o C170 de um arquivo de 5 GB
custa um `seek` e uma leitura, em vez de reler tudo. É a diferença entre olhar
um registro em segundos e em minutos.

## O que saiu daqui em 23/09/2026

A **Consulta de Entradas (037)** e o **razão contábil da ECD** vinham nesta
mesma rodada, porque portei as duas no mesmo dia. Não são quebra: são o
confronto entre o fiscal e o contábil, e mudaram para
`analitico/piscofins.py`. Quem quer olhar um registro não quer esperar a 037 de
um ano inteiro.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.parquet as pq

from cat.infraestrutura.analitico.escrita import (
    LeituraCancelada,
    anotar_identificacao,
    arquivo_ilegivel,
    parar_se_pedirem,
    pasta_do_indice,
)
from cat.infraestrutura.sped.ecd import EcdInvalida, indexar_ecd
from cat.infraestrutura.sped.indice import indice_de
from cat.infraestrutura.sped.leitor import codificacao_de
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_DOS_ARQUIVOS = "arquivos.parquet"
ARQUIVO_DAS_CONTAGENS = "contagens.parquet"
PASTA_DOS_INDICES = "indices"

LINHAS_POR_LOTE = 50_000

ESQUEMA_ARQUIVOS = pa.schema([
    ("nome", pa.string()), ("caminho", pa.string()), ("tipo", pa.string()),
    ("cnpj", pa.string()), ("empresa", pa.string()),
    ("inicio", pa.string()), ("fim", pa.string()),
    ("bytes", pa.int64()), ("linhas", pa.int64()), ("registros", pa.int32()),
    # o que cada tipo de arquivo rende
    ("itens", pa.int64()), ("consolidacoes", pa.int64()),
    ("contas", pa.int32()), ("lancamentos", pa.int64()), ("partidas", pa.int64()),
    ("erro", pa.string()),
])

ESQUEMA_CONTAGENS = pa.schema([
    ("arquivo", pa.string()), ("registro", pa.string()), ("quantidade", pa.int64()),
])


# o nome antigo da exceção, mantido porque o caso de uso o importa
QuebraCancelada = LeituraCancelada


@dataclass
class Andamento:
    arquivos: int = 0
    bytes: int = 0
    registros: int = 0


@dataclass
class Resumo:
    """O que a quebra achou, para a tela e para o histórico."""

    arquivos: int = 0
    contribuicoes: int = 0
    ecd: int = 0
    ilegiveis: int = 0
    bytes: int = 0
    linhas: int = 0
    # quantos registros distintos apareceram em todos os arquivos somados
    registros: int = 0
    estabelecimentos: list[str] = field(default_factory=list)
    competencias: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def serializar(r: Resumo) -> dict:
    return {
        "versao": 2, "arquivos": r.arquivos, "contribuicoes": r.contribuicoes, "ecd": r.ecd,
        "ilegiveis": r.ilegiveis, "bytes": r.bytes, "linhas": r.linhas,
        "registros": r.registros,
        "estabelecimentos": sorted(r.estabelecimentos), "competencias": sorted(r.competencias),
        "avisos": r.avisos,
    }


def quebrar(contribuicoes: list[str], ecds: list[str], destino: str,
            avisar: Callable[[Andamento], None] | None = None,
            deve_parar: Callable[[], bool] | None = None) -> Resumo:
    """Indexa todos os SPED do trabalho e escreve a ficha e as contagens."""
    os.makedirs(destino, exist_ok=True)
    indices = os.path.join(destino, PASTA_DOS_INDICES)
    resumo = Resumo()
    andamento = Andamento()
    linhas_de_arquivo: list[dict] = []
    contagens: list[tuple[str, str, int]] = []

    for caminho in contribuicoes:
        parar_se_pedirem(deve_parar)
        linhas_de_arquivo.append(
            _uma_contribuicao(caminho, indices, contagens, resumo, andamento))
        if avisar:
            avisar(andamento)
    for caminho in ecds:
        parar_se_pedirem(deve_parar)
        linhas_de_arquivo.append(_uma_ecd(caminho, contagens, resumo, andamento))
        if avisar:
            avisar(andamento)

    resumo.registros = len({registro for _, registro, _ in contagens})
    _gravar_arquivos(linhas_de_arquivo, os.path.join(destino, ARQUIVO_DOS_ARQUIVOS))
    _gravar_contagens(contagens, os.path.join(destino, ARQUIVO_DAS_CONTAGENS))
    log.info("quebra de sped concluída", extra=serializar(resumo))
    return resumo


def _uma_contribuicao(caminho: str, indices: str, contagens: list,
                      resumo: Resumo, andamento: Andamento) -> dict:
    """Indexa a EFD-Contribuições: contagem por registro e posição de cada um."""
    nome = os.path.basename(caminho)
    try:
        indice = indice_de(caminho, os.path.join(indices, pasta_do_indice(caminho)))
    except Exception as erro:                                      # noqa: BLE001
        log.warning("não deu para indexar a EFD-Contribuições",
                    extra={"arquivo": nome, "erro": str(erro)})
        resumo.ilegiveis += 1
        resumo.avisos.append(f"{nome}: {type(erro).__name__} ao indexar.")
        return arquivo_ilegivel(caminho, "contribuicoes", str(erro)[:300])

    for registro, quantos in indice.contagens.items():
        contagens.append((nome, registro, quantos))

    resumo.arquivos += 1
    resumo.contribuicoes += 1
    resumo.bytes += indice.bytes_totais
    resumo.linhas += indice.linhas
    andamento.arquivos += 1
    andamento.bytes += indice.bytes_totais
    andamento.registros += len(indice.contagens)
    anotar_identificacao(resumo.estabelecimentos, resumo.competencias,
                         indice.cabecalho.cnpj, indice.cabecalho.inicio)
    return {
        "nome": nome, "caminho": caminho, "tipo": "contribuicoes",
        "cnpj": indice.cabecalho.cnpj, "empresa": indice.cabecalho.nome,
        "inicio": indice.cabecalho.inicio, "fim": indice.cabecalho.fim,
        "bytes": indice.bytes_totais, "linhas": indice.linhas,
        "registros": len(indice.contagens),
        "itens": indice.quantos("C170"),
        "consolidacoes": indice.quantos("C180") + indice.quantos("C190"),
    }


def _uma_ecd(caminho: str, contagens: list, resumo: Resumo,
             andamento: Andamento) -> dict:
    """Indexa a ECD: o plano de contas e quantos lançamentos e partidas há."""
    nome = os.path.basename(caminho)
    try:
        indice = indexar_ecd(caminho)
    except (EcdInvalida, OSError) as erro:
        log.warning("não deu para quebrar a ECD", extra={"arquivo": nome, "erro": str(erro)})
        resumo.ilegiveis += 1
        resumo.avisos.append(f"{nome}: {erro}")
        return arquivo_ilegivel(caminho, "ecd", str(erro)[:300])

    # a ECD não tem contagem por registro como a EFD; o que ela tem de contável
    # são os dois blocos que importam, e é isso que vai para a mesma tabela
    contagens.append((nome, "I200", indice.lancamentos))
    contagens.append((nome, "I250", indice.partidas))

    resumo.arquivos += 1
    resumo.ecd += 1
    resumo.linhas += indice.partidas + indice.lancamentos
    andamento.arquivos += 1
    andamento.registros += 2
    anotar_identificacao(resumo.estabelecimentos, resumo.competencias,
                         indice.cnpj, indice.inicio)
    return {
        "nome": nome, "caminho": caminho, "tipo": "ecd", "cnpj": indice.cnpj,
        "empresa": indice.nome, "inicio": indice.inicio, "fim": indice.fim,
        "bytes": os.path.getsize(caminho) if os.path.isfile(caminho) else 0,
        "linhas": indice.partidas + indice.lancamentos,
        "contas": len(indice.contas), "lancamentos": indice.lancamentos,
        "partidas": indice.partidas,
    }


def _gravar_arquivos(linhas: list[dict], destino: str) -> None:
    pq.write_table(pa.Table.from_pylist(
        [{c: l.get(c, _padrao_de(c)) for c in ESQUEMA_ARQUIVOS.names} for l in linhas],
        schema=ESQUEMA_ARQUIVOS), destino)


def _padrao_de(coluna: str):
    tipo = ESQUEMA_ARQUIVOS.field(coluna).type
    return 0 if pa.types.is_integer(tipo) else ""


def _gravar_contagens(contagens: list[tuple[str, str, int]], destino: str) -> None:
    pq.write_table(pa.Table.from_pydict(
        {"arquivo": [c[0] for c in contagens], "registro": [c[1] for c in contagens],
         "quantidade": [c[2] for c in contagens]}, schema=ESQUEMA_CONTAGENS), destino)



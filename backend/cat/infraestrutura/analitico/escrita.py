"""O que toda leitura de SPED do trabalho compartilha.

Existe porque **quebrar** e **apurar** deixaram de ser a mesma coisa em
23/09/2026, e as duas precisam das mesmas três peças: gravar parquet em lotes,
parar quando pedem, e anotar de quem e de quando é o arquivo.

Ficar em módulo próprio é o que impede o de sempre — uma delas importar o
privado da outra, e as duas voltarem a ser uma só pela porta dos fundos.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import pyarrow as pa
import pyarrow.parquet as pq

# quantas linhas o escritor segura antes de despejar em disco
LINHAS_POR_LOTE = 50_000


class LeituraCancelada(Exception):
    """A rodada foi cancelada; nada do que ficou pela metade vale."""


def parar_se_pedirem(deve_parar: Callable[[], bool] | None) -> None:
    if deve_parar is not None and deve_parar():
        raise LeituraCancelada()


class Escritor:
    """Grava parquet em lotes, e só cria o arquivo quando há esquema.

    O esquema vem de fora (`colunas`), para que um trabalho sem nenhuma linha
    ainda produza um parquet legível em vez de arquivo nenhum — a etapa
    seguinte não deveria precisar saber a diferença.
    """

    def __init__(self, caminho: str, colunas: list[str]) -> None:
        self.esquema = pa.schema([(c, pa.string()) for c in colunas])
        self.escritor = pq.ParquetWriter(caminho, self.esquema)
        self.lote: dict[str, list] = {c: [] for c in colunas}
        self.gravadas = 0

    def escrever(self, linha: dict) -> None:
        for coluna in self.lote:
            self.lote[coluna].append(str(linha.get(coluna, "")))
        self.gravadas += 1
        if len(self.lote[next(iter(self.lote))]) >= LINHAS_POR_LOTE:
            self._despejar()

    def _despejar(self) -> None:
        if not self.lote[next(iter(self.lote))]:
            return
        self.escritor.write_table(pa.Table.from_pydict(self.lote, schema=self.esquema))
        self.lote = {c: [] for c in self.lote}

    def fechar(self) -> None:
        self._despejar()
        self.escritor.close()


def pasta_do_indice(caminho: str) -> str:
    """Uma pasta por arquivo, com nome que não colide nem some em disco."""
    from cat.infraestrutura.sped.indice import impressao_de  # noqa: PLC0415

    bruto = impressao_de(caminho)
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in bruto)[:120]


def anotar_identificacao(estabelecimentos: list[str], competencias: list[str],
                         cnpj: str, inicio: str) -> None:
    """De quem e de quando é o arquivo, sem repetir o que já foi anotado."""
    if cnpj and cnpj not in estabelecimentos:
        estabelecimentos.append(cnpj)
    # a competência é o mês: 2021-06-01 vira 2021-06
    if inicio and (mes := inicio[:7]) not in competencias:
        competencias.append(mes)


def arquivo_ilegivel(caminho: str, tipo: str, erro: str) -> dict:
    """A linha que descreve um arquivo que não deu para ler.

    Ele continua aparecendo na lista, com o motivo. Sumir da lista seria a
    pessoa procurar por que o total não fecha.
    """
    return {"nome": os.path.basename(caminho), "caminho": caminho, "tipo": tipo,
            "erro": erro}

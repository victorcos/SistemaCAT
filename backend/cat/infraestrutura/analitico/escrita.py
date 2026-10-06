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

from cat.log import obter_log

log = obter_log(__name__)

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
        """A linha entra inteira ou não entra.

        Montar os valores antes de encostar no lote parece o mesmo que apendar
        coluna a coluna, e não é. Se algo levantar no meio do caminho — e em
        05/10/2026 levantou na 13ª de 17 colunas, depois de seis horas e meia
        de leitura —, as colunas anteriores ficam com um valor a mais que as
        seguintes. O lote nunca mais fecha, e aí vem o pior: o `finally` que
        chama `fechar` troca a exceção de verdade por um

            ArrowInvalid: Column 13 named participante
                          expected length 49365 but got length 49364

        que manda quem lê procurar defeito no parquet — que não tem nenhum.
        """
        valores = [str(linha.get(coluna, "")) for coluna in self.lote]
        for coluna, valor in zip(self.lote, valores, strict=True):
            self.lote[coluna].append(valor)
        self.gravadas += 1
        if len(self.lote[next(iter(self.lote))]) >= LINHAS_POR_LOTE:
            self._despejar()

    def _emparelhar(self) -> int:
        """Corta o lote no tamanho da coluna mais curta, e diz que cortou.

        Com `escrever` sendo tudo ou nada, isto não deveria acontecer nunca.
        Está aqui porque **aconteceu**, e porque o estrago não foi a linha
        perdida: foi o `fechar` dentro de um `finally` ter levantado por cima da
        exceção que explicava a rodada inteira. Preferir a linha incompleta a
        destruir o diagnóstico é a escolha certa, e não é escolha difícil — a
        linha incompleta seria lixo de qualquer jeito.
        """
        tamanhos = {c: len(v) for c, v in self.lote.items()}
        menor = min(tamanhos.values())
        if min(tamanhos.values()) == max(tamanhos.values()):
            return menor
        log.error(
            "lote desemparelhado: alguma linha ficou pela metade. A rodada já "
            "estava caindo por outro motivo — é esse outro que interessa",
            extra={"tamanhos": {c: n for c, n in tamanhos.items() if n != menor},
                   "cortado_em": menor})
        for coluna, valores in self.lote.items():
            del valores[menor:]
        return menor

    def _despejar(self) -> None:
        if not self._emparelhar():
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

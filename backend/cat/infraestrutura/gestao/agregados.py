"""Os agregados da EFD-Contribuições, gravados em disco.

Ler os SPED de um cliente grande custa uma hora — foi o que a Gestão de 65
arquivos levou na base da CEMA. Até aqui esse trabalho era jogado fora ao fim
da rodada: a tese seguinte que precisasse dos mesmos números começaria do zero.

O que fica em disco é o resumo por chave — tributo, registro, operação, CST,
CFOP, natureza e alíquota, com as somas da competência. São dezenas de milhares
de linhas para um SPED de 1 GB: a leitura volta em segundos.

**Não é cache de arquivo, é produto da etapa.** Fica na pasta da execução, ao
lado dos outros parquets, e envelhece com ela: quem quiser os agregados de
outra base roda a etapa naquela base. Assim não há chave de invalidação para
errar — o parquet de uma execução é, por definição, o que aquela execução leu.

**O que não vem junto:** o bloco M, os ajustes e o 0110. Aquilo é a apuração
que o cliente declarou, e quem a usa é o montador dos quadros, que trabalha com
o `ApuracaoEFD` inteiro, na memória da própria rodada. Aqui ficam só os
documentos — que é o que as teses leem.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pyarrow.parquet as pq

from cat.infraestrutura.analitico.escrita import Escritor
from cat.infraestrutura.gestao.modelos import ApuracaoEFD
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_DOS_AGREGADOS = "agregados_efd.parquet"
# as contagens moram à parte de propósito: o registro que a leitura NÃO cobre
# não tem linha de documento nenhuma — e é justamente ele que precisa ser
# contado, para a tese avisar que ficou receita de fora
ARQUIVO_DAS_CONTAGENS = "contagens_efd.parquet"

COLUNAS = [
    "cnpj", "periodo", "arquivo",
    "tributo", "registro", "operacao", "cst", "cfop", "natureza", "aliquota",
    "vl_item", "vl_bc", "vl_trib", "quant", "linhas",
]

COLUNAS_DAS_CONTAGENS = ["cnpj", "periodo", "arquivo", "registro", "quantidade"]


@dataclass
class AgregadoDeArquivo:
    """O que uma tese precisa de um arquivo: quem, quando, e as somas.

    Tem a forma do `ApuracaoEFD` nos campos que as teses leem — de propósito:
    a mesma função serve o agregado recém-lido e o que voltou do disco.
    """

    cnpj: str = ""
    periodo: str = ""
    arquivo: str = ""
    documentos: dict = field(default_factory=dict)
    contagens: dict[str, int] = field(default_factory=dict)


def caminho(destino: str) -> str:
    return os.path.join(destino, ARQUIVO_DOS_AGREGADOS)


def caminho_das_contagens(destino: str) -> str:
    return os.path.join(destino, ARQUIVO_DAS_CONTAGENS)


def gravar(apuracoes: list[ApuracaoEFD], destino: str) -> int:
    """Escreve os agregados de todos os arquivos. Devolve quantas linhas gravou."""
    os.makedirs(destino, exist_ok=True)
    escritor = Escritor(caminho(destino), COLUNAS)
    contador = Escritor(caminho_das_contagens(destino), COLUNAS_DAS_CONTAGENS)
    try:
        for ap in apuracoes:
            nome = os.path.basename(ap.arquivo)
            for chave, somas in ap.documentos.items():
                tributo, registro, operacao, cst, cfop, natureza, aliquota = chave
                escritor.escrever({
                    "cnpj": ap.cnpj, "periodo": ap.periodo, "arquivo": nome,
                    "tributo": tributo, "registro": registro, "operacao": operacao,
                    "cst": cst, "cfop": cfop, "natureza": natureza, "aliquota": aliquota,
                    "vl_item": somas[0], "vl_bc": somas[1], "vl_trib": somas[2],
                    "quant": somas[3], "linhas": somas[4],
                })
            for registro, quantas in ap.contagens.items():
                contador.escrever({
                    "cnpj": ap.cnpj, "periodo": ap.periodo, "arquivo": nome,
                    "registro": registro, "quantidade": quantas,
                })
    finally:
        escritor.fechar()
        contador.fechar()

    log.info("agregados da efd gravados", extra={
        "arquivos": len(apuracoes), "linhas": escritor.gravadas,
        "contagens": contador.gravadas, "destino": os.path.basename(destino),
    })
    return escritor.gravadas


def ler(destino: str) -> list[AgregadoDeArquivo]:
    """Os agregados que a etapa deixou, um por arquivo lido.

    Volta vazio quando o parquet não existe — quem chama decide se isso é
    motivo para ler os SPED de novo ou para recusar a rodada. Silêncio aqui
    seria pior: uma tese calculada sobre zero linha dá zero, e zero não parece
    erro nenhum.
    """
    arquivo = caminho(destino)
    if not os.path.isfile(arquivo):
        return []

    por_arquivo: dict[tuple[str, str, str], AgregadoDeArquivo] = {}
    for lote in pq.ParquetFile(arquivo).iter_batches():
        for r in lote.to_pylist():
            chave_arquivo = (r["cnpj"], r["periodo"], r["arquivo"])
            alvo = por_arquivo.get(chave_arquivo)
            if alvo is None:
                alvo = por_arquivo[chave_arquivo] = AgregadoDeArquivo(
                    cnpj=r["cnpj"], periodo=r["periodo"], arquivo=r["arquivo"])
            chave = (r["tributo"], r["registro"], r["operacao"], r["cst"],
                     r["cfop"], r["natureza"], r["aliquota"])
            alvo.documentos[chave] = [
                int(r["vl_item"]), int(r["vl_bc"]), int(r["vl_trib"]),
                int(r["quant"]), int(r["linhas"]),
            ]

    _ler_contagens(destino, por_arquivo)
    agregados = list(por_arquivo.values())
    log.info("agregados da efd lidos do disco", extra={
        "arquivos": len(agregados), "destino": os.path.basename(destino),
    })
    return agregados


def _ler_contagens(destino: str, por_arquivo: dict) -> None:
    """As contagens de cada registro, inclusive as dos que não viram documento."""
    arquivo = caminho_das_contagens(destino)
    if not os.path.isfile(arquivo):
        return
    for lote in pq.ParquetFile(arquivo).iter_batches():
        for r in lote.to_pylist():
            chave = (r["cnpj"], r["periodo"], r["arquivo"])
            alvo = por_arquivo.get(chave)
            if alvo is None:
                # arquivo que só tem registros fora da leitura: sem nenhuma
                # linha de documento, ele existiria só aqui — e some se a
                # tese não souber dele
                alvo = por_arquivo[chave] = AgregadoDeArquivo(
                    cnpj=r["cnpj"], periodo=r["periodo"], arquivo=r["arquivo"])
            alvo.contagens[r["registro"]] = int(r["quantidade"])

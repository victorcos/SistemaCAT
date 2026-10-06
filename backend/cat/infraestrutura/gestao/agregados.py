"""Os agregados da EFD-Contribuições, gravados em disco.

Ler os SPED de um cliente grande custa uma hora — foi o que a Gestão de 65
arquivos levou na base da empresa 16. Até aqui esse trabalho era jogado fora ao fim
da rodada: a tese seguinte que precisasse dos mesmos números começaria do zero.

O que fica em disco é o resumo por chave — tributo, registro, operação, CST,
CFOP, natureza e alíquota, com as somas da competência. São dezenas de milhares
de linhas para um SPED de 1 GB: a leitura volta em segundos.

**Não é cache de arquivo, é produto da etapa.** Fica na pasta da execução, ao
lado dos outros parquets, e envelhece com ela: quem quiser os agregados de
outra base roda a etapa naquela base. Assim não há chave de invalidação para
errar — o parquet de uma execução é, por definição, o que aquela execução leu.

**O bloco M vem junto desde 06/10/2026**, e a razão é uma conta errada. As
teses leem os documentos e recalculam a contribuição grupo a grupo; o que o
cliente de fato declarou — os ajustes do M220/M620 e a contribuição a recolher
do M200/M600 — ficava só na memória da rodada da Gestão. Resultado: a exclusão
somava a contribuição **bruta** dos grupos, sem os ajustes redutores, e não
tinha como saber quanto do débito virou DARF e quanto foi quitado com crédito.

Numa base real isso apareceu como um "excluído da base" **maior que a própria
contribuição escriturada**, e como um crédito apresentado inteiro quando boa
parte dele só aumenta saldo credor. Nenhuma das duas coisas é calculável sem o
bloco M, e ele custa centenas de linhas por arquivo — nada, ao lado das dezenas
de milhares dos documentos.

**O que ainda não vem:** o 0110, que é regime e não valor.

## Três arquivos, e por que não um

Os documentos são somas por chave; os registros de apuração são **linhas cruas**
de comprimento variável; os ajustes são uma soma por `(registro, IND_AJ,
COD_AJ)`. Formatos diferentes, e um parquet só obrigaria a coluna mais larga a
existir vazia em todas as linhas das outras duas. Cada um no seu, e `ler()`
tolera a ausência de qualquer um — agregado gravado antes desta mudança volta
sem bloco M em vez de quebrar.
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
# o bloco M como o arquivo o escreveu: uma linha por registro de apuração
ARQUIVO_DA_APURACAO = "apuracao_efd.parquet"
# os ajustes já somados por (registro, IND_AJ, COD_AJ), como no `ApuracaoEFD`
ARQUIVO_DOS_AJUSTES = "ajustes_efd.parquet"

COLUNAS = [
    "cnpj", "periodo", "arquivo",
    "tributo", "registro", "operacao", "cst", "cfop", "natureza", "aliquota",
    "vl_item", "vl_bc", "vl_trib", "quant", "linhas",
]

COLUNAS_DAS_CONTAGENS = ["cnpj", "periodo", "arquivo", "registro", "quantidade"]

# `campos` é a linha do SPED com os campos juntos por "|". Pode, porque "|" é o
# separador do leiaute: campo nenhum o contém, por construção — foi ele que
# separou os campos na leitura. A ida e a volta é exata, e guardar a linha crua
# evita uma coluna por campo num registro cujo leiaute mudou em 2019 (ver
# `leiaute._M210_NOVO`)
COLUNAS_DA_APURACAO = ["cnpj", "periodo", "arquivo", "registro", "ordem", "campos"]

COLUNAS_DOS_AJUSTES = ["cnpj", "periodo", "arquivo", "registro", "ind_aj",
                       "cod_aj", "valor"]

SEPARADOR = "|"


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
    # os dois abaixo têm o nome e a forma dos campos homônimos do `ApuracaoEFD`,
    # para que quem lê o agregado do disco não precise saber de onde ele veio
    registros: dict[str, list[list[str]]] = field(default_factory=dict)
    ajustes: dict[tuple[str, str, str], int] = field(default_factory=dict)


def caminho(destino: str) -> str:
    return os.path.join(destino, ARQUIVO_DOS_AGREGADOS)


def caminho_das_contagens(destino: str) -> str:
    return os.path.join(destino, ARQUIVO_DAS_CONTAGENS)


def caminho_da_apuracao(destino: str) -> str:
    return os.path.join(destino, ARQUIVO_DA_APURACAO)


def caminho_dos_ajustes(destino: str) -> str:
    return os.path.join(destino, ARQUIVO_DOS_AJUSTES)


def gravar(apuracoes: list[ApuracaoEFD], destino: str) -> int:
    """Escreve os agregados de todos os arquivos. Devolve quantas linhas gravou."""
    os.makedirs(destino, exist_ok=True)
    escritor = Escritor(caminho(destino), COLUNAS)
    contador = Escritor(caminho_das_contagens(destino), COLUNAS_DAS_CONTAGENS)
    apurador = Escritor(caminho_da_apuracao(destino), COLUNAS_DA_APURACAO)
    ajustador = Escritor(caminho_dos_ajustes(destino), COLUNAS_DOS_AJUSTES)
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
            # `ordem` guarda a posição dentro do registro: o M210 do PIS vem
            # uma vez por código de contribuição, e a ordem é o que permite
            # devolvê-los na mesma sequência do arquivo
            for registro, linhas in ap.registros.items():
                for ordem, campos in enumerate(linhas):
                    apurador.escrever({
                        "cnpj": ap.cnpj, "periodo": ap.periodo, "arquivo": nome,
                        "registro": registro, "ordem": ordem,
                        "campos": SEPARADOR.join(campos),
                    })
            for (registro, ind_aj, cod_aj), valor in ap.ajustes.items():
                ajustador.escrever({
                    "cnpj": ap.cnpj, "periodo": ap.periodo, "arquivo": nome,
                    "registro": registro, "ind_aj": ind_aj, "cod_aj": cod_aj,
                    "valor": valor,
                })
    finally:
        escritor.fechar()
        contador.fechar()
        apurador.fechar()
        ajustador.fechar()

    log.info("agregados da efd gravados", extra={
        "arquivos": len(apuracoes), "linhas": escritor.gravadas,
        "contagens": contador.gravadas, "apuracao": apurador.gravadas,
        "ajustes": ajustador.gravadas, "destino": os.path.basename(destino),
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
    repetidas = 0
    for lote in pq.ParquetFile(arquivo).iter_batches():
        for r in lote.to_pylist():
            chave_arquivo = (r["cnpj"], r["periodo"], r["arquivo"])
            alvo = por_arquivo.get(chave_arquivo)
            if alvo is None:
                alvo = por_arquivo[chave_arquivo] = AgregadoDeArquivo(
                    cnpj=r["cnpj"], periodo=r["periodo"], arquivo=r["arquivo"])
            chave = (r["tributo"], r["registro"], r["operacao"], r["cst"],
                     r["cfop"], r["natureza"], r["aliquota"])
            if chave in alvo.documentos:
                # dois arquivos com o mesmo nome, CNPJ e competência: o parquet
                # os guardou separados e aqui um cobriria o outro. Ficar com um
                # é o certo — o mesmo arquivo entregue duas vezes conta uma —,
                # mas fazê-lo em silêncio esconderia uma base montada errada
                repetidas += 1
                continue
            alvo.documentos[chave] = [
                int(r["vl_item"]), int(r["vl_bc"]), int(r["vl_trib"]),
                int(r["quant"]), int(r["linhas"]),
            ]

    _ler_contagens(destino, por_arquivo)
    _ler_apuracao(destino, por_arquivo)
    _ler_ajustes(destino, por_arquivo)
    agregados = list(por_arquivo.values())
    if repetidas:
        log.warning("agregado com chave repetida: o mesmo arquivo entrou duas vezes", extra={
            "linhas_repetidas": repetidas, "destino": os.path.basename(destino),
        })
    log.info("agregados da efd lidos do disco", extra={
        "arquivos": len(agregados), "repetidas": repetidas,
        "destino": os.path.basename(destino),
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


def _alvo_de(r: dict, por_arquivo: dict) -> AgregadoDeArquivo:
    """O agregado do arquivo da linha, criado se ainda não existir.

    Criar aqui importa: um SPED pode ter bloco M e nenhum documento que a
    leitura cubra — e some da lista se só os documentos o criarem.
    """
    chave = (r["cnpj"], r["periodo"], r["arquivo"])
    alvo = por_arquivo.get(chave)
    if alvo is None:
        alvo = por_arquivo[chave] = AgregadoDeArquivo(
            cnpj=r["cnpj"], periodo=r["periodo"], arquivo=r["arquivo"])
    return alvo


def _ler_apuracao(destino: str, por_arquivo: dict) -> None:
    """O bloco M como o arquivo o escreveu, na ordem em que apareceu.

    Ausente quer dizer agregado gravado antes de 06/10/2026: volta sem bloco M,
    que é o que as teses viam até então. Melhor isso do que recusar a rodada
    por causa de um arquivo que nem existia quando ela gravou.
    """
    arquivo = caminho_da_apuracao(destino)
    if not os.path.isfile(arquivo):
        return
    # (arquivo, registro) -> [(ordem, campos)]. Junta antes de ordenar porque a
    # ordem é a do leiaute e não a da varredura — e dois lotes do parquet podem
    # partir o mesmo registro ao meio
    coletado: dict[tuple[tuple[str, str, str], str],
                   list[tuple[int, list[str]]]] = {}
    for lote in pq.ParquetFile(arquivo).iter_batches():
        for r in lote.to_pylist():
            _alvo_de(r, por_arquivo)          # garante que o arquivo existe na lista
            de_quem = (r["cnpj"], r["periodo"], r["arquivo"])
            campos = r["campos"].split(SEPARADOR) if r["campos"] else []
            coletado.setdefault((de_quem, r["registro"]), []).append(
                (int(r["ordem"]), campos))

    for (de_quem, registro), linhas in coletado.items():
        linhas.sort(key=lambda x: x[0])
        por_arquivo[de_quem].registros[registro] = [campos for _, campos in linhas]


def _ler_ajustes(destino: str, por_arquivo: dict) -> None:
    """Os ajustes do M110/M220/M510/M620, já somados por código."""
    arquivo = caminho_dos_ajustes(destino)
    if not os.path.isfile(arquivo):
        return
    for lote in pq.ParquetFile(arquivo).iter_batches():
        for r in lote.to_pylist():
            alvo = _alvo_de(r, por_arquivo)
            alvo.ajustes[(r["registro"], r["ind_aj"], r["cod_aj"])] = int(r["valor"])

"""Apuração de PIS/COFINS: o par que se confronta.

De um lado a **Consulta de Entradas (037)**, tirada da EFD-Contribuições: o que
a escrituração fiscal registrou como entrada. Do outro o **razão contábil**,
tirado da ECD: o que a contabilidade lançou. Onde os dois discordam é onde está
o trabalho.

## Por que não sai da quebra

Até 23/09/2026 isto vinha junto com a quebra de SPED, porque portei as duas no
mesmo dia. São coisas diferentes: a quebra **abre** os arquivos — diz que
registros cada um tem e onde cada um começa; esta **confronta** o fiscal com o
contábil. Quem quer olhar um C170 não quer esperar a 037 de um ano inteiro, e
quem quer a 037 não precisa do índice de todos os blocos.

**O custo de separar é reler os arquivos.** Uma passada a mais sobre a
EFD-Contribuições e outra sobre a ECD, porque nenhuma das duas guarda estado
para a outra. É o preço de as funcionalidades serem independentes, e foi uma
escolha consciente: amarrá-las para economizar leitura era o que as tinha
fundido numa coisa só.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field

from cat.infraestrutura.analitico.escrita import (
    Escritor,
    LeituraCancelada,
    anotar_identificacao,
    parar_se_pedirem,
)
from cat.infraestrutura.sped.ecd import EcdInvalida, indexar_ecd, razao
from cat.infraestrutura.sped.entradas import colunas_da_entrada, entradas
from cat.infraestrutura.sped.leitor import codificacao_de
from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, ler_cabecalho
from cat.infraestrutura.sped.saidas import Contagem, colunas_da_saida, saidas
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_DAS_ENTRADAS = "entradas.parquet"
ARQUIVO_DAS_SAIDAS = "saidas.parquet"
ARQUIVO_DO_RAZAO = "razao.parquet"

COLUNAS_DO_RAZAO = [
    "cnpj", "conta", "descricao", "conta_referencial", "competencia", "data", "numero",
    "valor_do_lancamento", "centro_de_custo", "valor", "debito_ou_credito", "historico",
    "codigo_do_historico", "participante", "tipo", "saldo", "arquivo",
]

# o nome antigo, para quem ainda o importa
ApuracaoCancelada = LeituraCancelada


@dataclass
class Andamento:
    arquivos: int = 0
    entradas: int = 0
    saidas: int = 0
    razao: int = 0


@dataclass
class Resumo:
    """O que o confronto produziu, para a tela e para o histórico."""

    arquivos: int = 0
    contribuicoes: int = 0
    ecd: int = 0
    ilegiveis: int = 0
    entradas: int = 0
    saidas: int = 0
    linhas_do_razao: int = 0
    # quantas entradas vieram de cada ramo de documento (C100/C170, C500/C501…)
    por_ramo: dict[str, int] = field(default_factory=dict)
    # e o mesmo do lado das saídas (C100/C170, C100/C175, A100/A170, F100)
    por_ramo_das_saidas: dict[str, int] = field(default_factory=dict)
    # registros de saída que a 047 ainda não sabe montar, e quantos apareceram.
    # Ver `sped/saidas.py`: a ausência tem de ser dita, não descoberta somando
    nao_cobertos: dict[str, int] = field(default_factory=dict)
    estabelecimentos: list[str] = field(default_factory=list)
    competencias: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def serializar(r: Resumo) -> dict:
    return {
        "versao": 1, "arquivos": r.arquivos, "contribuicoes": r.contribuicoes,
        "ecd": r.ecd, "ilegiveis": r.ilegiveis, "entradas": r.entradas,
        "saidas": r.saidas, "linhas_do_razao": r.linhas_do_razao,
        "por_ramo": dict(sorted(r.por_ramo.items())),
        "por_ramo_das_saidas": dict(sorted(r.por_ramo_das_saidas.items())),
        "nao_cobertos": dict(sorted(r.nao_cobertos.items())),
        "estabelecimentos": sorted(r.estabelecimentos),
        "competencias": sorted(r.competencias), "avisos": r.avisos,
    }


def confrontar(contribuicoes: list[str], ecds: list[str], destino: str,
               avisar: Callable[[Andamento], None] | None = None,
               deve_parar: Callable[[], bool] | None = None) -> Resumo:
    """Escreve a 037, a 047 e o razão contábil. Devolve o resumo.

    As duas fontes são independentes: um trabalho sem ECD ainda tem as duas
    consultas, e um sem EFD-Contribuições ainda tem o razão. Cada ausência vira
    aviso, porque descobri-la ao abrir a planilha é tarde.

    **A EFD-Contribuições é lida duas vezes**, uma para cada consulta. As duas
    passadas montam contextos diferentes — a 037 carrega o 0500 e os oito ramos
    de entrada, a 047 o cadastro por estabelecimento e os quatro de saída —, e
    fundi-las economizaria uma leitura ao custo de um módulo que ninguém mais
    entende. Ler de novo é barato; desentender o join é caro.
    """
    os.makedirs(destino, exist_ok=True)
    resumo = Resumo()
    andamento = Andamento()

    das_entradas = Escritor(os.path.join(destino, ARQUIVO_DAS_ENTRADAS), colunas_da_entrada())
    das_saidas = Escritor(os.path.join(destino, ARQUIVO_DAS_SAIDAS), colunas_da_saida())
    do_razao = Escritor(os.path.join(destino, ARQUIVO_DO_RAZAO), COLUNAS_DO_RAZAO)
    try:
        for caminho in contribuicoes:
            parar_se_pedirem(deve_parar)
            _entradas_de(caminho, das_entradas, resumo, andamento)
            parar_se_pedirem(deve_parar)
            _saidas_de(caminho, das_saidas, resumo, andamento)
            if avisar:
                avisar(andamento)
        for caminho in ecds:
            parar_se_pedirem(deve_parar)
            _razao_de(caminho, do_razao, resumo, andamento)
            if avisar:
                avisar(andamento)
    finally:
        das_entradas.fechar()
        das_saidas.fechar()
        do_razao.fechar()

    resumo.entradas = das_entradas.gravadas
    resumo.saidas = das_saidas.gravadas
    resumo.linhas_do_razao = do_razao.gravadas
    log.info("apuração de pis/cofins concluída", extra=serializar(resumo))
    return resumo


def _entradas_de(caminho: str, das_entradas: Escritor, resumo: Resumo,
                 andamento: Andamento) -> None:
    """A 037 de uma EFD-Contribuições.

    Uma passada sequencial, sem índice: o join da entrada precisa de tudo — as
    tabelas do bloco 0, o estabelecimento, o documento e o item —, e ler em
    ordem custa menos que pular pelo arquivo, ainda mais em disco de rede.
    """
    nome = os.path.basename(caminho)
    # de quem e de quando é o arquivo sai das próprias linhas, mas anotar a cada
    # uma custaria uma varredura de lista por linha — e são milhões. O par visto
    # entra num conjunto, e só o que é novo vai para o resumo
    vistos: set[tuple[str, str]] = set()
    try:
        codificacao = codificacao_de(caminho)

        # **a competência é do arquivo, não da linha de entrada.** Anotá-la só
        # ao ver uma entrada faz o arquivo sem entrada nenhuma desaparecer da
        # contagem — e aí a tela diz "4 competências" de uma base que cobre 44.
        # Aconteceu com uma locadora de veículos, cuja EFD-Contribuições só tem
        # nota de serviço: zero C100, 137 A100. O 037 em zero estava certo; o
        # número de competências é que mentia, e mentir sobre o alcance da base é
        # pior que mostrar zero, porque põe em dúvida o que está correto.
        #
        # Vale para este arquivo e não para o das saídas de propósito: as duas
        # passadas leem o mesmo arquivo, e contar nas duas dobraria o resto.
        with open(caminho, "rb") as f:
            primeira = f.readline().decode(codificacao, errors="replace")
        try:
            cabecalho = ler_cabecalho(primeira)
            # `.valor` e não `str()`: o `str` do Cnpj sai com máscara, e as
            # linhas de entrada trazem os catorze dígitos crus — misturar os
            # dois punha o mesmo estabelecimento duas vezes na lista
            anotar_identificacao(resumo.estabelecimentos, resumo.competencias,
                                 cabecalho.cnpj.valor if cabecalho.cnpj else "",
                                 cabecalho.inicio.isoformat())
        except ArquivoNaoReconhecido:
            pass  # o 0000 ilegível já vira aviso adiante, na leitura

        for linha in entradas(caminho, codificacao):
            das_entradas.escrever(linha.como_dicionario())
            resumo.por_ramo[linha.registros] = resumo.por_ramo.get(linha.registros, 0) + 1
            if (par := (linha.cnpj, linha.periodo)) not in vistos:
                vistos.add(par)
                anotar_identificacao(resumo.estabelecimentos, resumo.competencias,
                                     linha.cnpj, _iso(linha.periodo))
    except (OSError, ValueError) as erro:
        log.warning("não deu para tirar a 037 da EFD-Contribuições",
                    extra={"arquivo": nome, "erro": str(erro)})
        resumo.ilegiveis += 1
        resumo.avisos.append(f"{nome}: {type(erro).__name__} ao ler as entradas.")
        return

    resumo.arquivos += 1
    resumo.contribuicoes += 1
    andamento.arquivos += 1
    andamento.entradas = das_entradas.gravadas


def _saidas_de(caminho: str, das_saidas: Escritor, resumo: Resumo,
               andamento: Andamento) -> None:
    """A 047 de uma EFD-Contribuições.

    Não conta arquivo nem estabelecimento: quem fez isso foi `_entradas_de`,
    sobre este mesmo arquivo, e contar de novo dobraria o número no diário. O
    que sai daqui é só o que é da 047 — as linhas, os ramos e o que ela ainda
    não cobre.
    """
    nome = os.path.basename(caminho)
    contagem = Contagem()
    try:
        codificacao = codificacao_de(caminho)
        for linha in saidas(caminho, codificacao, contagem):
            das_saidas.escrever(linha.como_dicionario())
            resumo.por_ramo_das_saidas[linha.registros] = (
                resumo.por_ramo_das_saidas.get(linha.registros, 0) + 1)
    except (OSError, ValueError) as erro:
        log.warning("não deu para tirar a 047 da EFD-Contribuições",
                    extra={"arquivo": nome, "erro": str(erro)})
        resumo.avisos.append(f"{nome}: {type(erro).__name__} ao ler as saídas.")
        return

    for registro, quantos in (contagem.nao_cobertos or {}).items():
        resumo.nao_cobertos[registro] = resumo.nao_cobertos.get(registro, 0) + quantos
    andamento.saidas = das_saidas.gravadas


def _razao_de(caminho: str, do_razao: Escritor, resumo: Resumo,
              andamento: Andamento) -> None:
    """O razão de todas as contas analíticas de uma ECD."""
    nome = os.path.basename(caminho)
    try:
        indice = indexar_ecd(caminho)
    except (EcdInvalida, OSError) as erro:
        log.warning("não deu para ler a ECD", extra={"arquivo": nome, "erro": str(erro)})
        resumo.ilegiveis += 1
        resumo.avisos.append(f"{nome}: {erro}")
        return

    for linha in razao(caminho, indice):
        do_razao.escrever({
            "cnpj": linha.cnpj, "conta": linha.conta, "descricao": linha.descricao,
            "conta_referencial": linha.conta_referencial, "competencia": linha.competencia,
            "data": linha.data, "numero": linha.numero,
            "valor_do_lancamento": f"{linha.valor_do_lancamento:.2f}",
            "centro_de_custo": linha.centro_de_custo, "valor": f"{linha.valor:.2f}",
            "debito_ou_credito": linha.debito_ou_credito, "historico": linha.historico,
            "codigo_do_historico": linha.codigo_do_historico,
            "participante": linha.participante, "tipo": linha.tipo,
            "saldo": f"{linha.saldo:.2f}", "arquivo": linha.arquivo,
        })

    resumo.arquivos += 1
    resumo.ecd += 1
    andamento.arquivos += 1
    andamento.razao = do_razao.gravadas
    anotar_identificacao(resumo.estabelecimentos, resumo.competencias,
                         indice.cnpj, indice.inicio)


def _iso(periodo: str) -> str:
    """A 037 traz o período em dd/mm/aaaa; a identificação anota em aaaa-mm."""
    partes = (periodo or "").split("/")
    return f"{partes[2]}-{partes[1]}-01" if len(partes) == 3 else ""

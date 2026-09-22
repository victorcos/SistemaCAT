"""De uma lista de arquivos aos relatórios de gestão.

É a camada que decide **quais** arquivos entram, não como se lê cada um. Duas
coisas acontecem aqui, e as duas mudam número no relatório:

1. **Uma apuração por competência.** Original e retificadora costumam estar na
   mesma pasta, e a retificadora *substitui* a original por inteiro. Ler as
   duas dobraria o mês e, pior, misturaria valores de antes e depois da
   retificação. A retificadora vence; havendo empate, o arquivo mais novo;
2. **O preterido nunca some calado.** Cada exclusão vira aviso com os dois
   nomes, para que quem confere saiba qual arquivo produziu o número.

Portado do projeto Quebra de SPED em 22/09/2026. O paralelismo por processos
que o original tinha ficou de fora: lá a leitura acontecia dentro de uma página
Streamlit, que precisava de threads para não travar; aqui a etapa já roda fora
da requisição, na fila, e uma passada sequencial é mais simples de acompanhar e
de cancelar.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable

from cat.infraestrutura.gestao.agregador import agregar_efd
from cat.infraestrutura.gestao.modelos import ApuracaoEFD, Relatorio
from cat.infraestrutura.gestao.quadros import montar_relatorio_piscofins
from cat.log import obter_log

log = obter_log(__name__)

TRIBUTOS = ("PIS", "COFINS")


class GestaoCancelada(RuntimeError):
    """A rodada foi interrompida a pedido, entre um arquivo e outro."""


def ler(caminhos: Iterable[str],
        avisar: Callable[[ApuracaoEFD, int, int], None] | None = None,
        deve_parar: Callable[[], bool] | None = None) -> tuple[list[ApuracaoEFD], list[str]]:
    """Agrega cada EFD-Contribuições. Devolve as apurações e o que deu errado.

    Arquivo ilegível não derruba a rodada: vira aviso e a competência dele
    simplesmente falta — o que é visível no relatório, ao contrário de um
    número errado.
    """
    caminhos = list(caminhos)
    apuracoes: list[ApuracaoEFD] = []
    avisos: list[str] = []
    inicio = time.monotonic()

    for i, caminho in enumerate(caminhos, 1):
        if deve_parar is not None and deve_parar():
            raise GestaoCancelada("leitura da gestão cancelada a pedido")
        nome = os.path.basename(caminho)
        try:
            apuracao = agregar_efd(caminho)
        except (OSError, ValueError) as erro:
            log.warning("não deu para ler a efd na gestão",
                        extra={"arquivo": nome, "erro": str(erro)})
            avisos.append(f"{nome}: não deu para ler — {erro}.")
            continue
        if not apuracao.periodo:
            avisos.append(f"{nome}: o registro 0000 não trouxe período; o arquivo ficou de fora.")
            continue
        apuracoes.append(apuracao)
        if avisar is not None:
            avisar(apuracao, i, len(caminhos))

    log.info("gestão leu os arquivos", extra={
        "arquivos": len(caminhos), "apuracoes": len(apuracoes),
        "recusados": len(avisos), "segundos": round(time.monotonic() - inicio, 1),
    })
    return sorted(apuracoes, key=lambda a: (a.cnpj, a.periodo)), avisos


def selecionar_por_competencia(
    apuracoes: list[ApuracaoEFD],
) -> tuple[list[ApuracaoEFD], list[str]]:
    """Uma apuração por competência: retificadora vence; depois, a mais nova."""
    melhores: dict[str, ApuracaoEFD] = {}
    avisos: list[str] = []

    def prioridade(ap: ApuracaoEFD) -> tuple[int, float]:
        try:
            quando = os.path.getmtime(ap.arquivo)
        except OSError:
            quando = 0.0
        return (1 if ap.tipo_escrit == "1" else 0, quando)

    for apuracao in apuracoes:
        atual = melhores.get(apuracao.periodo)
        if atual is None:
            melhores[apuracao.periodo] = apuracao
            continue
        vencedor, perdedor = ((apuracao, atual) if prioridade(apuracao) > prioridade(atual)
                              else (atual, apuracao))
        melhores[apuracao.periodo] = vencedor
        avisos.append(
            f"{apuracao.periodo}: dois arquivos para a mesma competência; usado "
            f"{os.path.basename(vencedor.arquivo)}, ignorado "
            f"{os.path.basename(perdedor.arquivo)}."
        )
        log.info("competência com mais de um arquivo na gestão", extra={
            "periodo": apuracao.periodo,
            "usado": os.path.basename(vencedor.arquivo),
            "ignorado": os.path.basename(perdedor.arquivo),
            "por_retificadora": vencedor.tipo_escrit == "1",
        })
    return [melhores[p] for p in sorted(melhores)], avisos


def montar(apuracoes: list[ApuracaoEFD],
           avisos_da_leitura: Iterable[str] = ()) -> list[Relatorio]:
    """Os relatórios de PIS e de COFINS, com os avisos na frente.

    Os dois saem da mesma leitura: o bloco M é espelhado, e ler o arquivo duas
    vezes para produzir dois relatórios seria pagar o dobro pelo mesmo byte.
    """
    if not apuracoes:
        return []
    selecionadas, avisos_da_selecao = selecionar_por_competencia(apuracoes)
    antes = list(avisos_da_leitura) + avisos_da_selecao
    relatorios = []
    for tributo in TRIBUTOS:
        relatorio = montar_relatorio_piscofins(selecionadas, tributo)
        relatorio.avisos = antes + relatorio.avisos
        relatorios.append(relatorio)
    log.info("gestão montada", extra={
        "competencias": len(selecionadas), "relatorios": len(relatorios),
        "quadros": sum(len(r.quadros) for r in relatorios),
        "avisos": sum(len(r.avisos) for r in relatorios),
    })
    return relatorios

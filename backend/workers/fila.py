"""A fila de execuções: a tabela `execucao`, lida por um trabalhador.

Substitui `infraestrutura/tarefas.py`, que guardava a fila num `ThreadPoolExecutor`
dentro do processo da API. Dois defeitos disso:

* **a fila morria com o processo.** Com o `--reload` do desenvolvimento, salvar
  um arquivo Python no meio de uma conferência de 44 minutos matava a rodada em
  silêncio, e a linha ficava "rodando" para sempre — a tela mostrando uma barra
  que nunca mais andaria;
* **só quem criou a execução podia rodá-la.** Com a API em C# criando a
  execução pelo canal interno, quem roda precisa achar o trabalho no banco, não
  numa fila em memória.

Agora a execução nasce "na_fila" no banco, e o trabalhador pega a mais antiga.
Uma de cada vez, de propósito, como antes: duas extrações simultâneas disputam a
mesma rede e o mesmo disco e terminam as duas mais devagar. No Postgres a
reivindicação usa `FOR UPDATE SKIP LOCKED`, e dois trabalhadores nunca pegam a
mesma linha.

**Ao subir, o que estava "rodando" vira falha com motivo.** Só um trabalhador
roda por banco, então uma linha "rodando" quando ele sobe é uma rodada que o
reinício interrompeu. Melhor dizer isso na tela do que deixar a barra parada.

**Cada rodada num processo próprio.** A etapa 4 da empresa 19 lê 20 GB de relatório
em Python, e o que o Python solta ele não devolve ao sistema: o motor chegou a
12 GB e a apuração caiu por falta de memória duas vezes (#55 e #56, 16/09/2026),
na fase que vem depois da leitura. Num processo filho, a memória volta inteira
quando a rodada acaba, e o filho que morre por falta dela não leva o motor
junto: a execução vira falha com o motivo. `CAT_RODADAS_EM_PROCESSO=false` volta
a rodar dentro do motor, que é o que os testes usam.
"""

from __future__ import annotations

import multiprocessing
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select

from cat.aplicacao.casos_de_uso import (
    apurar_contribuicoes,
    apurar_credito_outorgado,
    apurar_combustivel,
    apurar_exclusoes,
    apurar_periodo,
    apurar_piscofins,
    apurar_suportado,
    conferir_documentos,
    extrair_movimentos,
    gerar_arquivo_digital,
    montar_entrega,
    montar_razao,
    pre_validar_arquivos,
    quebrar_sped,
    quebrar_xml,
)
from cat.aplicacao.casos_de_uso.historico_do_projeto import registrar_de_etapa
from cat.config import obter_config
from cat.dominio.projeto.historico import TipoDeEvento
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.modelos import ExecucaoDB
from cat.log import obter_log

log = obter_log(__name__)

# quanto o trabalhador espera antes de olhar a fila de novo, quando está vazia
SEGUNDOS_ENTRE_OLHADAS = 2.0

EXECUTORES = {
    conferir_documentos.ETAPA: conferir_documentos.executar,
    extrair_movimentos.ETAPA: extrair_movimentos.executar,
    apurar_suportado.ETAPA: apurar_suportado.executar,
    montar_razao.ETAPA: montar_razao.executar,
    apurar_periodo.ETAPA: apurar_periodo.executar,
    gerar_arquivo_digital.ETAPA: gerar_arquivo_digital.executar,
    pre_validar_arquivos.ETAPA: pre_validar_arquivos.executar,
    montar_entrega.ETAPA: montar_entrega.executar,
    quebrar_sped.ETAPA: quebrar_sped.executar,
    quebrar_xml.ETAPA: quebrar_xml.executar,
    apurar_contribuicoes.ETAPA: apurar_contribuicoes.executar,
    apurar_piscofins.ETAPA: apurar_piscofins.executar,
    apurar_credito_outorgado.ETAPA: apurar_credito_outorgado.executar,
    apurar_exclusoes.ETAPA: apurar_exclusoes.executar,
    apurar_combustivel.ETAPA: apurar_combustivel.executar,
}

MOTIVO_INTERRUPCAO = "Interrompida: o motor reiniciou durante a rodada. Rode de novo."
MOTIVO_PROCESSO = ("O processo da rodada terminou sem concluir (código {codigo}). Costuma ser falta de "
                   "memória na máquina; veja o log do motor e rode de novo.")
SEGUNDOS_ENTRE_CONFERENCIAS = 5.0

_parar = threading.Event()
_linha: threading.Thread | None = None


def reivindicar() -> tuple[int, str] | None:
    """Pega a execução mais antiga na fila, marcando-a antes de soltar a trava."""
    with Sessao() as sessao:
        consulta = (select(ExecucaoDB)
                    .where(ExecucaoDB.situacao == "na_fila")
                    .order_by(ExecucaoDB.id)
                    .limit(1))
        if sessao.bind.dialect.name == "postgresql":
            consulta = consulta.with_for_update(skip_locked=True)
        execucao = sessao.scalar(consulta)
        if execucao is None:
            return None
        execucao.situacao = "rodando"
        execucao.passo = "Começando"
        sessao.commit()
        return execucao.id, execucao.etapa


def processar_uma() -> int | None:
    """Roda a próxima execução da fila até o fim. Devolve o id, ou None se vazia."""
    pega = reivindicar()
    if pega is None:
        return None
    execucao_id, etapa = pega
    executar = EXECUTORES.get(etapa)
    if executar is None:
        _falhar(execucao_id, f"Etapa desconhecida para o motor: {etapa}.")
        return execucao_id
    log.info("execução retirada da fila", extra={"execucao_id": execucao_id, "etapa": etapa})
    if obter_config().rodadas_em_processo and _processos_viaveis():
        rodar_em_processo(execucao_id, etapa)
        return execucao_id
    # o executor grava a própria falha; isto é a rede de segurança para o que escapar dele
    try:
        executar(execucao_id)
    except Exception:                                   # noqa: BLE001
        log.exception("execução terminou em exceção não tratada", extra={"execucao_id": execucao_id})
        _falhar(execucao_id, "Falha não tratada no motor. Veja o log.")
    return execucao_id


def _processos_viaveis() -> bool:
    from cat.infraestrutura.analitico.arquivo_digital import _processos_viaveis as viaveis  # noqa: PLC0415
    return viaveis()


def _rodar_etapa(etapa: str, execucao_id: int) -> None:
    """O que o processo filho faz: log como o do motor, e a etapa."""
    from cat.log import configurar  # noqa: PLC0415
    configurar(obter_config().log_nivel)
    EXECUTORES[etapa](execucao_id)


def rodar_em_processo(execucao_id: int, etapa: str,
                      alvo: Callable[[str, int], None] = _rodar_etapa) -> int | None:
    """Roda a etapa num processo filho e espera. Devolve o código de saída.

    O executor grava sozinho a conclusão ou a falha. O que ele não consegue
    gravar — o processo morto pelo sistema — fica a cargo daqui.
    """
    filho = multiprocessing.get_context("spawn").Process(
        target=alvo, args=(etapa, execucao_id), name=f"cat-{etapa}-{execucao_id}", daemon=False)
    try:
        filho.start()
    except OSError as erro:
        log.exception("não deu para abrir o processo da rodada; roda dentro do motor",
                      extra={"execucao_id": execucao_id, "erro": str(erro)})
        alvo(etapa, execucao_id)
        return 0
    log.info("rodada em processo próprio", extra={"execucao_id": execucao_id, "etapa": etapa, "pid": filho.pid})
    while filho.is_alive():
        filho.join(SEGUNDOS_ENTRE_CONFERENCIAS)
        if _parar.is_set() and filho.is_alive():
            # o motor está saindo: a linha "rodando" vira falha quando ele voltar
            log.warning("motor saindo com rodada em curso; o processo dela é encerrado",
                        extra={"execucao_id": execucao_id, "pid": filho.pid})
            filho.terminate()
            filho.join(SEGUNDOS_ENTRE_CONFERENCIAS)
            return filho.exitcode
    if filho.exitcode != 0:
        log.error("processo da rodada terminou sem concluir",
                  extra={"execucao_id": execucao_id, "etapa": etapa, "codigo": filho.exitcode})
        _falhar(execucao_id, MOTIVO_PROCESSO.format(codigo=filho.exitcode))
    else:
        # saiu bem e não gravou fim: a rede de segurança de sempre
        _falhar(execucao_id, "A rodada terminou sem gravar o resultado. Veja o log do motor.",
                so_se_em_curso=True)
    return filho.exitcode


def processar_pendentes() -> list[int]:
    """Esvazia a fila, em ordem. É o que os testes usam para não depender de tempo."""
    feitas: list[int] = []
    while (execucao_id := processar_uma()) is not None:
        feitas.append(execucao_id)
    return feitas


def recuperar_interrompidas() -> int:
    with Sessao() as sessao:
        orfas = list(sessao.scalars(select(ExecucaoDB).where(
            ExecucaoDB.situacao.in_(("rodando", "cancelando")))))
        for execucao in orfas:
            # quem pediu para cancelar já não queria o resultado: o reinício
            # só completou o pedido, e chamar isso de falha confundiria a tela
            if execucao.situacao == "cancelando":
                execucao.situacao = "cancelada"
                execucao.passo = "Cancelada"
            else:
                execucao.situacao = "falhou"
                execucao.erro = MOTIVO_INTERRUPCAO
                execucao.passo = "Interrompida"
            execucao.terminada_em = datetime.now(timezone.utc)
        sessao.commit()
        for execucao in orfas:
            registrar_de_etapa(sessao, execucao.projeto_id, TipoDeEvento.ETAPA_FALHOU, execucao.etapa,
                               "Rodada interrompida pelo reinício do motor",
                               dados={"execucao_id": execucao.id}, autor_id=execucao.criada_por)
    if orfas:
        log.warning("execuções interrompidas por reinício marcadas como falha",
                    extra={"execucoes": [e.id for e in orfas]})
    return len(orfas)


def _falhar(execucao_id: int, motivo: str, so_se_em_curso: bool = False) -> None:
    with Sessao() as sessao:
        execucao = sessao.get(ExecucaoDB, execucao_id)
        if execucao is None or execucao.situacao in ("concluida", "falhou", "cancelada"):
            return
        if so_se_em_curso and execucao.situacao not in ("rodando", "cancelando"):
            return
        if execucao.situacao == "cancelando":
            execucao.situacao = "cancelada"
            execucao.passo = "Cancelada"
            execucao.terminada_em = datetime.now(timezone.utc)
            sessao.commit()
            log.warning("rodada cancelada terminou fora do ponto seguro", extra={"execucao_id": execucao_id})
            return
        execucao.situacao = "falhou"
        execucao.erro = motivo
        execucao.passo = "Falhou"
        execucao.terminada_em = datetime.now(timezone.utc)
        sessao.commit()


def _laco() -> None:
    log.info("trabalhador da fila no ar")
    while not _parar.is_set():
        try:
            if processar_uma() is None:
                _parar.wait(SEGUNDOS_ENTRE_OLHADAS)
        except Exception:                               # noqa: BLE001
            # banco fora do ar por um instante não pode matar o trabalhador
            log.exception("trabalhador da fila falhou ao olhar a fila; tenta de novo")
            _parar.wait(SEGUNDOS_ENTRE_OLHADAS * 5)
    log.info("trabalhador da fila parado")


def rodar_ate_parar() -> None:
    """O laço da fila **neste** processo, até alguém chamar `parar()`.

    É o que `workers/rodar.py` usa. Fora do motor, a fila não é derrubada pelo
    `--reload` do desenvolvimento — e uma apuração de uma hora deixa de morrer
    porque alguém salvou um arquivo.
    """
    recuperar_interrompidas()
    _parar.clear()
    _laco()


def iniciar_em_segundo_plano() -> None:
    global _linha
    if _linha is not None and _linha.is_alive():
        return
    recuperar_interrompidas()
    _parar.clear()
    _linha = threading.Thread(target=_laco, name="cat-fila", daemon=True)
    _linha.start()


def parar() -> None:
    _parar.set()

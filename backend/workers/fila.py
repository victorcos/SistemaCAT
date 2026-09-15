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
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from sqlalchemy import select

from cat.aplicacao.casos_de_uso import apurar_suportado, conferir_documentos, extrair_movimentos
from cat.aplicacao.casos_de_uso.historico_do_projeto import registrar_de_etapa
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
}

MOTIVO_INTERRUPCAO = "Interrompida: o motor reiniciou durante a rodada. Rode de novo."

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
    # o executor grava a própria falha; isto é a rede de segurança para o que escapar dele
    try:
        executar(execucao_id)
    except Exception:                                   # noqa: BLE001
        log.exception("execução terminou em exceção não tratada", extra={"execucao_id": execucao_id})
        _falhar(execucao_id, "Falha não tratada no motor. Veja o log.")
    return execucao_id


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


def _falhar(execucao_id: int, motivo: str) -> None:
    with Sessao() as sessao:
        execucao = sessao.get(ExecucaoDB, execucao_id)
        if execucao is None or execucao.situacao in ("concluida", "falhou", "cancelada"):
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

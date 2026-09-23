"""A Gestão Fiscal em disco: os quadros de PIS, COFINS, IRPJ e CSLL.

Lê a EFD-Contribuições e a ECF do lote e escreve **um** parquet com tudo:
`quadros.parquet`, no formato longo — uma linha por (tributo, quadro, linha,
competência).

## Por que longo e não largo

O relatório do MA é largo: uma coluna por mês. É assim que se lê, e é assim que
a planilha sai. Mas guardar largo em parquet significaria um esquema que muda a
cada trabalho — doze colunas num, sessenta noutro —, e qualquer consulta teria
de descobrir os nomes das colunas antes de somar. No formato longo o esquema é
sempre o mesmo, e quem precisa do largo pivota na saída, que é onde o largo faz
falta: na planilha e na tela.

## O que uma linha carrega

Além do valor, três coisas que o número sozinho não diz:

* **`unidade`** — quase tudo é dinheiro em centavos, mas o percentual de rateio
  de créditos não é. Formatar os dois igual faria 8.500 virar R$ 85,00 num campo
  que quer dizer 85%;
* **`externo`** — a linha existe no relatório do MA mas vem de fonte que o
  sistema não lê (DCTF, e-CAC). Fica **vazia**, não zerada: zero é uma afirmação,
  e não temos como fazê-la;
* **`titulo`** — linha de cabeçalho de subquadro, sem valor. Some da soma e
  aparece em negrito.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.parquet as pq

from cat.infraestrutura.gestao.modelos import Relatorio
from cat.infraestrutura.gestao.montagem import (
    GestaoCancelada,
    ler,
    ler_ecfs,
    montar,
    montar_irpj_csll,
)
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_DOS_QUADROS = "quadros.parquet"

# os rótulos que o relatório marca como percentual, e não como dinheiro
_PERCENTUAL = "percentual"
_DINHEIRO = "dinheiro"

ESQUEMA = pa.schema([
    ("tributo", pa.string()),
    ("quadro", pa.string()),
    ("quadro_titulo", pa.string()),
    # a ordem em que a linha aparece dentro do quadro: o relatório é uma
    # sequência de contas, e ordenar por rótulo embaralharia a aritmética
    ("ordem", pa.int32()),
    ("rotulo", pa.string()),
    ("nivel", pa.int32()),
    ("titulo", pa.bool_()),
    ("externo", pa.bool_()),
    ("unidade", pa.string()),
    ("competencia", pa.string()),
    # centavos. Nulo quando a linha é de fonte externa: vazio diz "não sei",
    # zero diria "é zero", e são coisas diferentes
    ("valor", pa.int64()),
])


@dataclass
class Andamento:
    arquivos: int = 0
    linhas: int = 0


@dataclass
class Resumo:
    arquivos: int = 0
    contribuicoes: int = 0
    ecf: int = 0
    ilegiveis: int = 0
    quadros: int = 0
    linhas: int = 0
    tributos: list[str] = field(default_factory=list)
    competencias: list[str] = field(default_factory=list)
    cnpj: str = ""
    razao_social: str = ""
    avisos: list[str] = field(default_factory=list)


def serializar(r: Resumo) -> dict:
    return {
        "arquivos": r.arquivos, "contribuicoes": r.contribuicoes, "ecf": r.ecf,
        "ilegiveis": r.ilegiveis, "quadros": r.quadros, "linhas": r.linhas,
        "tributos": r.tributos, "competencias": r.competencias,
        "cnpj": r.cnpj, "razao_social": r.razao_social, "avisos": r.avisos,
    }


def apurar(contribuicoes: list[str], ecfs: list[str], destino: str,
           avisar: Callable[[Andamento], None] | None = None,
           deve_parar: Callable[[], bool] | None = None) -> Resumo:
    """Lê as fontes, monta os quadros e grava o parquet. Devolve o resumo.

    A EFD-Contribuições dá PIS e COFINS; a ECF dá IRPJ e CSLL. Qualquer uma das
    duas pode faltar — o que houver fonte para montar é montado, e a ausência
    vira aviso em vez de erro. Um trabalho que só tem ECF ainda tem IRPJ/CSLL
    para mostrar.
    """
    inicio = time.time()
    resumo = Resumo()
    andamento = Andamento()
    relatorios: list[Relatorio] = []

    def andou(_apuracao, i: int, total: int) -> None:
        andamento.arquivos = i
        if avisar is not None:
            avisar(andamento)

    if contribuicoes:
        apuracoes, avisos = ler(contribuicoes, avisar=andou, deve_parar=deve_parar)
        resumo.contribuicoes = len(apuracoes)
        resumo.ilegiveis += len(avisos)
        resumo.avisos.extend(avisos)
        relatorios.extend(montar(apuracoes, avisos))

    if ecfs:
        if deve_parar is not None and deve_parar():
            raise GestaoCancelada("apuração das contribuições cancelada a pedido")
        apuracoes_ecf, avisos_ecf = ler_ecfs(ecfs, deve_parar=deve_parar)
        resumo.ecf = len(apuracoes_ecf)
        resumo.ilegiveis += len(avisos_ecf)
        resumo.avisos.extend(avisos_ecf)
        andamento.arquivos += len(apuracoes_ecf)
        relatorios.extend(montar_irpj_csll(apuracoes_ecf, avisos_ecf))
        if avisar is not None:
            avisar(andamento)

    resumo.arquivos = andamento.arquivos
    _gravar(relatorios, os.path.join(destino, ARQUIVO_DOS_QUADROS), resumo, andamento, avisar)

    if not relatorios:
        resumo.avisos.append(
            "Nenhuma fonte legível: sem EFD-Contribuições não há PIS/COFINS, e sem ECF não "
            "há IRPJ/CSLL.")

    log.info("gestão apurada", extra={
        "contribuicoes": resumo.contribuicoes, "ecf": resumo.ecf,
        "relatorios": len(relatorios), "quadros": resumo.quadros, "linhas": resumo.linhas,
        "competencias": len(resumo.competencias), "segundos": round(time.time() - inicio, 1),
    })
    return resumo


def _gravar(relatorios: list[Relatorio], caminho: str, resumo: Resumo,
            andamento: Andamento, avisar: Callable[[Andamento], None] | None) -> None:
    """Uma linha por (tributo, quadro, linha, competência).

    O parquet nasce mesmo sem relatório nenhum: etapa que termina sem arquivo é
    etapa que a próxima não sabe distinguir de etapa que não rodou.
    """
    colunas: dict[str, list] = {nome: [] for nome in ESQUEMA.names}
    competencias: set[str] = set()
    tributos: list[str] = []
    quadros = 0

    for relatorio in relatorios:
        tributos.append(relatorio.tributo)
        competencias.update(relatorio.periodos)
        if not resumo.cnpj:
            resumo.cnpj, resumo.razao_social = relatorio.cnpj, relatorio.razao_social
        resumo.avisos.extend(a for a in relatorio.avisos if a not in resumo.avisos)
        for quadro in relatorio.quadros:
            quadros += 1
            for ordem, linha in enumerate(quadro.linhas):
                unidade = (_PERCENTUAL if linha.rotulo.strip() in relatorio.unidade_percentual
                           else _DINHEIRO)
                for competencia in relatorio.periodos:
                    colunas["tributo"].append(relatorio.tributo)
                    colunas["quadro"].append(quadro.numero)
                    colunas["quadro_titulo"].append(quadro.titulo)
                    colunas["ordem"].append(ordem)
                    colunas["rotulo"].append(linha.rotulo)
                    colunas["nivel"].append(linha.nivel)
                    colunas["titulo"].append(linha.titulo)
                    colunas["externo"].append(linha.externo)
                    colunas["unidade"].append(unidade)
                    colunas["competencia"].append(competencia)
                    colunas["valor"].append(linha.valores.get(competencia))
                andamento.linhas += 1
        if avisar is not None:
            avisar(andamento)

    pq.write_table(pa.Table.from_pydict(colunas, schema=ESQUEMA), caminho)
    resumo.quadros = quadros
    resumo.linhas = andamento.linhas
    resumo.tributos = tributos
    resumo.competencias = sorted(competencias)

"""A Consulta de Saídas (047) na tela: recortar primeiro, olhar depois.

A apuração de PIS/COFINS já deixou `saidas.parquet` em disco, com todas as
saídas de todas as EFD-Contribuições do lote. Numa rede de supermercado isso é
**7,8 milhões de linhas em cinco anos** — o Excel não abre, a resposta HTTP não
carrega, e ninguém lê. A tela precisa recortar antes de mostrar, e este módulo
é o que a atende.

## Dois passos, como no razão contábil

1. **`filtros()`** — o que há para escolher: os estabelecimentos, as
   competências, os ramos de documento, os CFOP e os CST, cada um com quantas
   linhas tem. É por aqui que a pessoa monta o recorte sabendo o tamanho do que
   vai pedir, em vez de descobrir depois que pediu tudo;
2. **`linhas()`** — as linhas do recorte, paginadas, com os totais **do recorte
   inteiro** e não da página. Total que muda ao virar a página não serve para
   conferir nada.

## Por que existe um resumo materializado

`filtros()` responde a primeira coisa que a tela mostra. Levantar os valores
distintos varrendo 7,8 milhões de linhas a cada abertura seria segundos de tela
branca — e a tela branca é o que faz alguém achar que não há dado e ir embora.

O resumo tem uma linha por combinação de estabelecimento, competência, ramo,
CFOP e CST: nas bases reais são alguns milhares, não milhões. É a mesma
agregação de sempre, feita uma vez em vez de a cada clique. Some o arquivo, ele
se refaz; muda o `saidas.parquet`, ele se refaz sozinho pela data.

Escreve em nome provisório e renomeia no fim, porque duas telas abrindo ao
mesmo tempo leriam um parquet pela metade — e aqui isso não daria erro: daria
competência faltando na lista, que é pior.

## Tudo é texto no parquet

O escritor grava toda coluna como string, de propósito: esquema igual desde a
primeira linha. Então valor volta como `"1234,56"` — com **vírgula**, que é
como a 047 sai —, e somar exige trocar a vírgula por ponto antes do `CAST`. É
barato, o DuckDB faz na varredura, e é honesto: o arquivo guarda o que o
relatório mostra.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from decimal import Decimal

from cat.infraestrutura.analitico.confronto import _escapar
from cat.infraestrutura.analitico.piscofins import ARQUIVO_DAS_SAIDAS
from cat.infraestrutura.analitico.suportado import _leitura
from cat.log import obter_log

log = obter_log(__name__)

POR_PAGINA_PADRAO = 100
POR_PAGINA_MAXIMO = 500

ARQUIVO_DO_RESUMO = "saidas_por_recorte.parquet"
# o parquet do recorte, para o download. A marca é a impressão do filtro
ARQUIVO_RECORTADO = "saidas_recorte{marca}.parquet"

# o dinheiro no parquet é texto no padrão brasileiro: "1234,56"
def _decimal(coluna: str) -> str:
    return f"CAST(nullif(replace({coluna}, ',', '.'), '') AS DECIMAL(24,2))"


_VALOR = _decimal("valor_do_item")
_PIS = _decimal("pis")
_COFINS = _decimal("cofins")

# as colunas em que a busca livre procura. São as que alguém tem na mão quando
# vem conferir: a chave que o cliente mandou, o número da nota, o código ou o
# nome do produto, o nome de quem comprou
_BUSCAVEIS = ("chave", "numero_do_documento", "codigo_do_item",
              "descricao_do_item", "nome_do_participante")


class SaidasNaoGeradas(FileNotFoundError):
    """Pediram a 047 de uma execução que não tem o parquet em disco."""


@dataclass(frozen=True)
class Recorte:
    """O que a tela escolheu. Tudo vazio significa a 047 inteira."""

    cnpjs: tuple[str, ...] = ()
    competencias: tuple[str, ...] = ()
    ramos: tuple[str, ...] = ()
    cfops: tuple[str, ...] = ()
    cst_pis: tuple[str, ...] = ()
    busca: str = ""

    @property
    def inteiro(self) -> bool:
        return not any((self.cnpjs, self.competencias, self.ramos, self.cfops,
                        self.cst_pis, self.busca.strip()))

    @property
    def quantos_filtros(self) -> int:
        return sum(1 for v in (self.cnpjs, self.competencias, self.ramos, self.cfops,
                               self.cst_pis, self.busca.strip()) if v)


RECORTE_INTEIRO = Recorte()


def impressao_do_recorte(recorte: Recorte) -> str:
    """A marca do recorte no nome do arquivo.

    Sem ela, baixar o recorte de uma competência e depois o de outra serviria
    o primeiro arquivo para o segundo — com o nome certo e o conteúdo errado.
    É o mesmo cuidado de `casos_de_uso/planilhas.py::sufixo_do_recorte`, e pelo
    mesmo motivo.
    """
    if recorte.inteiro:
        return ""
    partes = "|".join([
        ",".join(sorted(recorte.cnpjs)), ",".join(sorted(recorte.competencias)),
        ",".join(sorted(recorte.ramos)), ",".join(sorted(recorte.cfops)),
        ",".join(sorted(recorte.cst_pis)), recorte.busca.strip().lower(),
    ])
    return "-" + hashlib.sha1(partes.encode("utf-8")).hexdigest()[:12]


def _arquivo(destino: str) -> str:
    caminho = os.path.join(destino, ARQUIVO_DAS_SAIDAS)
    if not os.path.isfile(caminho):
        raise SaidasNaoGeradas(
            f"A Consulta de Saídas não está em disco nesta execução ({ARQUIVO_DAS_SAIDAS}). "
            "Rode a apuração de PIS/COFINS de novo, com pelo menos uma EFD-Contribuições "
            "no lote.")
    return caminho


def _pagina(pagina: int, por_pagina: int) -> tuple[int, int]:
    return max(1, int(pagina)), max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))


def _texto(v) -> str:
    """Decimal vira texto com duas casas: é o que atravessa o JSON sem arredondar."""
    return format(Decimal(v or 0).quantize(Decimal("0.01")), "f")


def _em(coluna: str, valores: tuple[str, ...]) -> tuple[str, list[object]]:
    marcas = ", ".join("?" for _ in valores)
    return f"{coluna} IN ({marcas})", list(valores)


def _onde(recorte: Recorte) -> tuple[str, list[object]]:
    """O WHERE do recorte, com os parâmetros. Sem recorte, `1 = 1`."""
    filtros: list[str] = []
    parametros: list[object] = []
    for coluna, valores in (("cnpj", recorte.cnpjs), ("periodo", recorte.competencias),
                            ("registros", recorte.ramos), ("cfop", recorte.cfops),
                            ("cst_pis", recorte.cst_pis)):
        if valores:
            clausula, ps = _em(coluna, valores)
            filtros.append(clausula)
            parametros += ps
    if (busca := recorte.busca.strip()):
        ou = " OR ".join(f"{c} ILIKE ?" for c in _BUSCAVEIS)
        filtros.append(f"({ou})")
        parametros += [f"%{busca}%"] * len(_BUSCAVEIS)
    return (" AND ".join(filtros) or "1 = 1"), parametros


# ---------------------------------------------------------------------------
# o resumo materializado, que é quem responde o painel de filtros
# ---------------------------------------------------------------------------
def _resumo(destino: str) -> str:
    """Uma linha por combinação de recorte, escrita na primeira leitura."""
    origem = _arquivo(destino)
    caminho = os.path.join(destino, ARQUIVO_DO_RESUMO)
    if os.path.isfile(caminho) and os.path.getmtime(caminho) >= os.path.getmtime(origem):
        return caminho

    parcial = f"{caminho}.{os.getpid()}.parcial"
    comeco = time.monotonic()
    con = _leitura(destino)
    try:
        con.execute(f"""
            COPY (
                SELECT cnpj, periodo, registros, cfop, cst_pis,
                       any_value(natureza)          AS natureza,
                       any_value(descricao_do_cfop) AS descricao_do_cfop,
                       count(*)                     AS linhas,
                       sum({_VALOR})                AS valor,
                       sum({_PIS})                  AS pis,
                       sum({_COFINS})               AS cofins
                FROM read_parquet('{_escapar(origem)}')
                GROUP BY cnpj, periodo, registros, cfop, cst_pis
            ) TO '{_escapar(parcial)}' (FORMAT PARQUET)
        """)
    except BaseException:
        if os.path.isfile(parcial):
            os.remove(parcial)
        raise
    finally:
        con.close()
    os.replace(parcial, caminho)

    log.info("resumo da 047 materializado", extra={
        "execucao_pasta": os.path.basename(destino),
        "segundos": round(time.monotonic() - comeco, 1),
    })
    return caminho


def _distintos(con, caminho: str, coluna: str, onde: str, parametros: list[object],
               extra: str = "") -> list[dict]:
    """Os valores daquela coluna que sobrevivem ao recorte, com o tamanho de cada um.

    **O recorte não se aplica à própria coluna que está sendo listada.** Quem
    marcou o CFOP 5102 ainda precisa ver os outros CFOP para poder marcá-los
    também — se a lista encolhesse para o que já está marcado, o filtro viraria
    uma armadilha de mão única.
    """
    selecionado = f", any_value({extra}) AS rotulo" if extra else ""
    cursor = con.execute(f"""
        SELECT {coluna} AS valor, sum(linhas) AS linhas{selecionado}
        FROM read_parquet('{_escapar(caminho)}')
        WHERE {onde}
        GROUP BY {coluna} ORDER BY {coluna}
    """, parametros)
    return [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]


def filtros(destino: str, recorte: Recorte = RECORTE_INTEIRO) -> dict:
    """O que há para escolher, com quantas linhas cada escolha tem.

    Cada lista é contada **sem o próprio filtro** — ver `_distintos`. Assim a
    pessoa vê o que ganharia ao marcar mais uma coisa, e não só o que já marcou.
    """
    caminho = _resumo(destino)
    # **a busca livre não entra aqui.** O resumo é agregado por CNPJ,
    # competência, ramo, CFOP e CST: não tem chave, nem número de documento,
    # nem descrição de item — as colunas em que a busca procura. Mandá-la para
    # cá não dá resposta errada, dá erro de coluna inexistente. Quem conta a
    # busca é `linhas()`, que lê o parquet inteiro; a resposta diz isso em
    # `busca_conta_no_resumo` para a tela poder dizê-lo também
    sem_busca = Recorte(**{**_campos(recorte), "busca": ""})
    con = _leitura(destino)
    try:
        def sem(campo: str) -> tuple[str, list[object]]:
            limpo = Recorte(**{k: v for k, v in _campos(sem_busca).items() if k != campo})
            return _onde(limpo)

        listas = {}
        for campo, coluna, rotulo in (("cnpjs", "cnpj", ""),
                                      ("competencias", "periodo", ""),
                                      ("ramos", "registros", ""),
                                      ("cfops", "cfop", "descricao_do_cfop"),
                                      ("cst_pis", "cst_pis", "")):
            onde, parametros = sem(campo)
            listas[campo] = _distintos(con, caminho, coluna, onde, parametros, rotulo)

        onde, parametros = _onde(sem_busca)
        total, valor, pis, cofins = con.execute(f"""
            SELECT coalesce(sum(linhas), 0), coalesce(sum(valor), 0),
                   coalesce(sum(pis), 0), coalesce(sum(cofins), 0)
            FROM read_parquet('{_escapar(caminho)}') WHERE {onde}
        """, parametros).fetchone()
        inteiro = con.execute(f"""
            SELECT coalesce(sum(linhas), 0) FROM read_parquet('{_escapar(caminho)}')
        """).fetchone()[0]
    finally:
        con.close()

    return {
        **listas,
        "linhas_no_recorte": total,
        "linhas_no_total": inteiro,
        # a busca livre não está no resumo: ela varre as linhas, e o número
        # acima é o do recorte sem ela. A tela diz isso em vez de mentir
        "busca_conta_no_resumo": not recorte.busca.strip(),
        "totais": {"valor": _texto(valor), "pis": _texto(pis), "cofins": _texto(cofins)},
    }


def _campos(recorte: Recorte) -> dict:
    return {"cnpjs": recorte.cnpjs, "competencias": recorte.competencias,
            "ramos": recorte.ramos, "cfops": recorte.cfops,
            "cst_pis": recorte.cst_pis, "busca": recorte.busca}


# ---------------------------------------------------------------------------
# as linhas
# ---------------------------------------------------------------------------
def linhas(destino: str, recorte: Recorte = RECORTE_INTEIRO, pagina: int = 1,
           por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """As linhas do recorte, paginadas, com os totais do recorte inteiro.

    A ordem é a do arquivo — competência, estabelecimento, documento, item —,
    que é a ordem em que a escrituração aconteceu. Ordenar por valor daria uma
    tela mais vistosa e uma conferência impossível: quem confere segue a nota.
    """
    pagina, por_pagina = _pagina(pagina, por_pagina)
    caminho = _arquivo(destino)
    onde, parametros = _onde(recorte)
    base = (f"(SELECT * FROM read_parquet('{_escapar(caminho)}') WHERE {onde})")

    con = _leitura(destino)
    try:
        total, valor, pis, cofins = con.execute(f"""
            SELECT count(*), coalesce(sum({_VALOR}), 0),
                   coalesce(sum({_PIS}), 0), coalesce(sum({_COFINS}), 0)
            FROM {base}
        """, parametros).fetchone()
        cursor = con.execute(f"""
            SELECT * FROM {base}
            ORDER BY periodo, cnpj, numero_do_documento, numero_do_item
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, parametros)
        nomes = [c[0] for c in cursor.description]
        pagina_de_linhas = [dict(zip(nomes, r)) for r in cursor.fetchall()]
    finally:
        con.close()

    log.info("linhas da 047 lidas", extra={
        "execucao_pasta": os.path.basename(destino), "total": total, "pagina": pagina,
        "filtros": recorte.quantos_filtros,
    })
    return {
        "pagina": pagina, "por_pagina": por_pagina, "total": total,
        "linhas": pagina_de_linhas, "recortado": not recorte.inteiro,
        "totais": {"valor": _texto(valor), "pis": _texto(pis), "cofins": _texto(cofins)},
    }


def parquet_do_recorte(destino: str, recorte: Recorte) -> str:
    """O parquet só com o que passa no recorte, para o download sair recortado.

    Sem recorte, devolve o próprio `saidas.parquet` — copiar 7,8 milhões de
    linhas para depois gravar as mesmas 7,8 milhões seria trabalho dobrado.

    Com recorte, grava um parquet próprio e o reaproveita: quem baixa em xlsx e
    depois em csv o mesmo recorte não deve esperar a varredura duas vezes.
    """
    origem = _arquivo(destino)
    if recorte.inteiro:
        return origem
    marca = impressao_do_recorte(recorte)
    caminho = os.path.join(destino, ARQUIVO_RECORTADO.format(marca=marca))
    if os.path.isfile(caminho) and os.path.getmtime(caminho) >= os.path.getmtime(origem):
        return caminho

    onde, parametros = _onde(recorte)
    parcial = f"{caminho}.{os.getpid()}.parcial"
    con = _leitura(destino)
    try:
        con.execute(f"""
            COPY (SELECT * FROM read_parquet('{_escapar(origem)}') WHERE {onde})
            TO '{_escapar(parcial)}' (FORMAT PARQUET)
        """, parametros)
    except BaseException:
        if os.path.isfile(parcial):
            os.remove(parcial)
        raise
    finally:
        con.close()
    os.replace(parcial, caminho)
    log.info("recorte da 047 materializado", extra={
        "execucao_pasta": os.path.basename(destino), "filtros": recorte.quantos_filtros,
    })
    return caminho

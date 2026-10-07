"""Ler o razão da ECD na tela: escolher a conta, depois ver os lançamentos.

A apuração de PIS/COFINS já deixou `razao.parquet` em disco, com **todas** as partidas
de **todas** as contas analíticas de **todas** as ECD do lote. Numa empresa de
verdade isso é milhão de linhas: não cabe numa resposta, e não cabe na cabeça de
ninguém. A tela precisa de dois passos, e este módulo é o que os atende:

1. **`contas()`** — o seletor. Uma linha por conta, com quanto ela movimentou e
   quanto sobrou. É por aqui que a pessoa acha a conta que procura, buscando
   pelo código, pelo nome ou pela conta referencial;
2. **`lancamentos()`** — o razão em si, da conta escolhida, em ordem de data,
   paginado.

Nada é recalculado aqui. O saldo corrente de cada linha veio de
`sped/ecd.py::razao`, que sabe a ordem certa (a do tempo, não a do arquivo — o
SPED não obriga os lançamentos a virem em ordem de data). Este módulo agrega e
recorta; a aritmética contábil já aconteceu.

## Tudo é texto no parquet

O escritor da quebra grava toda coluna como string, de propósito: esquema igual
desde a primeira linha, sem depender do que apareceu no primeiro arquivo. Então
valor e saldo voltam como `"1234.56"` e é preciso `CAST` para somar. É barato —
o DuckDB faz isso na varredura — e é honesto: o arquivo guarda o que o SPED
escreveu, e a conversão acontece à vista, aqui.
"""

from __future__ import annotations

import os
import time
from decimal import Decimal

from cat.infraestrutura.analitico.confronto import _escapar
from cat.infraestrutura.analitico.piscofins import (
    ARQUIVO_DO_RAZAO,
    fonte_do_razao,
)
from cat.infraestrutura.analitico.suportado import _leitura
from cat.log import obter_log

log = obter_log(__name__)

# o galho das contas que a ECD não mapeou a referencial nenhuma
SEM_REFERENCIAL = "sem-referencial"

POR_PAGINA_PADRAO = 100
POR_PAGINA_MAXIMO = 500

# o que a pessoa pode pedir para ver só: o recorte é sobre o saldo da conta
RECORTES = {
    "devedoras": "saldo > 0",
    "credoras": "saldo < 0",
    "zeradas": "saldo = 0",
    "com_movimento": "lancamentos > 0",
}

# o dinheiro no parquet é texto; DECIMAL(24,2) é o que soma sem perder centavo
_VALOR = "CAST(valor AS DECIMAL(24,2))"
_DEBITO = f"CASE WHEN debito_ou_credito = 'D' THEN {_VALOR} ELSE 0 END"
_CREDITO = f"CASE WHEN debito_ou_credito = 'C' THEN {_VALOR} ELSE 0 END"


class RazaoNaoGerado(FileNotFoundError):
    """Pediram o razão de uma execução que não tem o parquet em disco."""


def _arquivo(destino: str) -> str:
    # uma forma ou a outra: arquivo único nas rodadas até 07/10/2026, pasta de
    # partes nas de agora, porque as ECD passaram a ser lidas em paralelo
    caminho = fonte_do_razao(destino)
    if caminho is None:
        raise RazaoNaoGerado(
            f"O razão contábil não está em disco nesta execução ({ARQUIVO_DO_RAZAO}). "
            "Rode a apuração de PIS/COFINS de novo, com pelo menos uma ECD no lote.")
    return caminho


def _pagina(pagina: int, por_pagina: int) -> tuple[int, int]:
    return max(1, int(pagina)), max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))


def _texto(v) -> str:
    """Decimal vira texto com duas casas: é o que atravessa o JSON sem arredondar."""
    return format(Decimal(v or 0).quantize(Decimal("0.01")), "f")


ARQUIVO_DO_RESUMO = "razao_por_conta.parquet"


def _resumo(destino: str) -> str:
    """O resumo por conta, escrito na primeira leitura e reaproveitado depois.

    O seletor agregava o razão inteiro a cada página — e "inteiro", numa base
    de rede, é dezessete milhões de partidas. Eram 27 segundos por página numa
    tela que é a **primeira** coisa que se vê: quem abria achava que não havia
    conta nenhuma e ia embora.

    O resumo tem uma linha por conta — dez mil, não milhões — e responde em
    milissegundos. Não é cache de consulta: é a mesma agregação de sempre,
    feita uma vez em vez de a cada clique. Some o arquivo, ele se refaz.

    Escreve em nome provisório e renomeia no fim, porque duas telas abrindo ao
    mesmo tempo leriam um parquet pela metade — que não é erro que apareça:
    seria conta faltando na lista.
    """
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
                SELECT cnpj, conta,
                       any_value(descricao)             AS descricao,
                       any_value(conta_referencial)     AS conta_referencial,
                       count(*)                         AS lancamentos,
                       sum({_DEBITO})                   AS debitos,
                       sum({_CREDITO})                  AS creditos,
                       sum({_DEBITO}) - sum({_CREDITO}) AS saldo,
                       min(data)                        AS de,
                       max(data)                        AS ate,
                       count(DISTINCT arquivo)          AS arquivos
                FROM read_parquet('{_escapar(origem)}')
                GROUP BY cnpj, conta
            ) TO '{_escapar(parcial)}' (FORMAT PARQUET)
        """)
    except BaseException:
        if os.path.isfile(parcial):
            os.remove(parcial)
        raise
    finally:
        con.close()
    os.replace(parcial, caminho)

    log.info("resumo do razão por conta materializado", extra={
        "execucao_pasta": os.path.basename(destino),
        "segundos": round(time.monotonic() - comeco, 1),
    })
    return caminho


def estabelecimentos(destino: str) -> list[dict]:
    """Os CNPJ que aparecem no razão, com quantas contas cada um tem.

    Existe para a tela poder filtrar antes de listar: uma empresa com trinta
    filiais tem o mesmo plano de contas trinta vezes, e sem o filtro o seletor
    vira uma lista de repetições.
    """
    caminho = _resumo(destino)
    con = _leitura(destino)
    try:
        cursor = con.execute(f"""
            SELECT cnpj,
                   count(*)          AS contas,
                   sum(lancamentos)  AS lancamentos,
                   min(de)           AS de,
                   max(ate)          AS ate
            FROM read_parquet('{_escapar(caminho)}')
            GROUP BY cnpj ORDER BY cnpj
        """)
        return [{"cnpj": c, "contas": n, "lancamentos": l, "de": de, "ate": ate}
                for c, n, l, de, ate in cursor.fetchall()]
    finally:
        con.close()


def contas(destino: str, busca: str | None = None, cnpj: str | None = None,
           so: str | None = None, pagina: int = 1,
           por_pagina: int = POR_PAGINA_PADRAO, pai: str | None = None,
           arvore: bool = False) -> dict:
    """O seletor de conta: os galhos do plano referencial e as contas deles.

    Dez mil contas numa lista chapada são cem páginas, e ninguém acha nada
    virando cem páginas. Então a lista é uma **árvore**: os galhos são a conta
    referencial da Receita — que a própria ECD declara, conta por conta, no
    I051 — e as folhas são as contas do cliente.

    `pai` diz de qual galho se querem os filhos. Sem ele, vêm as raízes: numa
    rede de supermercado de verdade são três (1 Ativo, 2 Passivo, 3 Resultado),
    contra 10.282 contas. Descendo: 6, 13, 36, 88 — a árvore fecha a lista em
    três ou quatro cliques.

    **Os galhos não paginam**; as contas sim. É de propósito: galho nenhum
    passa de uma centena, e o que estoura é folha — 5.659 contas de fornecedor
    penduradas no mesmo galho, uma por fornecedor, porque é assim que o cliente
    abriu o plano dele. Aí a tela mostra as primeiras e vai buscando o resto.

    **A busca desmonta a árvore de propósito.** Quem digita "CRBS" quer a conta,
    não o caminho até ela: com busca, vêm as contas que casam, de qualquer
    galho, e `nos` volta vazio.

    Sem `arvore`, a lista sai chapada como sempre saiu — é o que o download e
    quem quer *todas* as contas precisam. A árvore é da tela, e a tela pede.
    """
    if so and so not in RECORTES:
        raise ValueError(f"Recorte desconhecido: {so}. Há {', '.join(sorted(RECORTES))}.")
    pagina, por_pagina = _pagina(pagina, por_pagina)
    caminho = _resumo(destino)
    procurando = bool(busca and busca.strip())
    pai = (pai or "").strip() or None
    # com busca, o galho não tem serventia: procura-se na árvore inteira
    ramificando = arvore and not procurando

    filtros, parametros = [], []
    if cnpj and cnpj.strip():
        filtros.append("cnpj = ?")
        parametros.append(cnpj.strip())
    if procurando:
        filtros.append("(conta ILIKE ? OR descricao ILIKE ? OR conta_referencial ILIKE ?)")
        parametros += [f"%{busca.strip()}%"] * 3
    if so:
        filtros.append(RECORTES[so])

    # sem busca, a lista é a de um galho: as contas que ficam aqui são as que
    # não descem mais — as que descem estão nos galhos filhos, não repetidas
    nivel = len(pai.split(".")) + 1 if pai else 1
    if ramificando:
        if pai == SEM_REFERENCIAL:
            filtros.append("conta_referencial = ''")
        elif pai:
            filtros.append("conta_referencial = ?")
            parametros.append(pai)
        else:
            filtros.append("1 = 0")  # na raiz não há conta solta: tudo está sob um galho

    onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""
    base = f"(SELECT * FROM read_parquet('{_escapar(caminho)}') {onde})"

    con = _leitura(destino)
    try:
        total = con.execute(f"SELECT count(*) FROM {base}", parametros).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY cnpj, conta
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, parametros)
        nomes = [c[0] for c in cursor.description]
        linhas = [_conta_jsonavel(dict(zip(nomes, r))) for r in cursor.fetchall()]
        nos = _galhos(con, caminho, pai, nivel, cnpj, so) if ramificando else []
    finally:
        con.close()

    log.info("contas do razão listadas", extra={
        "execucao_pasta": os.path.basename(destino), "total": total, "galhos": len(nos),
        "pagina": pagina, "busca": procurando, "cnpj": bool(cnpj), "recorte": so or "",
        "pai": pai or "", "arvore": arvore,
    })
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total,
            "linhas": linhas, "nos": nos, "pai": pai or ""}


def _galhos(con, caminho: str, pai: str | None, nivel: int,
            cnpj: str | None, so: str | None) -> list[dict]:
    """Os galhos filhos de `pai`, com o que está pendurado em cada um.

    O total de cada galho é de tudo que há **abaixo** dele, não só do primeiro
    nível: quem olha "1.01" quer saber quantas contas tem o circulante inteiro.
    """
    if pai == SEM_REFERENCIAL:
        return []

    filtros = ["conta_referencial <> ''",
               f"len(str_split(conta_referencial, '.')) > {nivel}"]
    parametros: list[object] = []
    if pai:
        filtros.append("conta_referencial LIKE ?")
        parametros.append(f"{pai}.%")
    if cnpj and cnpj.strip():
        filtros.append("cnpj = ?")
        parametros.append(cnpj.strip())
    if so:
        filtros.append(RECORTES[so])

    codigo = f"array_to_string(list_slice(str_split(conta_referencial, '.'), 1, {nivel}), '.')"
    cursor = con.execute(f"""
        SELECT {codigo}        AS codigo,
               count(*)        AS contas,
               sum(lancamentos) AS lancamentos,
               sum(debitos)    AS debitos,
               sum(creditos)   AS creditos,
               sum(saldo)      AS saldo
        FROM read_parquet('{_escapar(caminho)}')
        WHERE {' AND '.join(filtros)}
        GROUP BY 1 ORDER BY 1
    """, parametros)
    galhos = [
        {"codigo": c, "contas": n, "lancamentos": l,
         "debitos": _texto(d), "creditos": _texto(cr), "saldo": _texto(s)}
        for c, n, l, d, cr, s in cursor.fetchall()
    ]

    # as contas que a ECD não mapeou a referencial nenhuma ficariam invisíveis
    # na árvore — e conta invisível é conta que ninguém confere
    if pai is None:
        soltas = con.execute(f"""
            SELECT count(*), sum(lancamentos), sum(debitos), sum(creditos), sum(saldo)
            FROM read_parquet('{_escapar(caminho)}') WHERE conta_referencial = ''
        """).fetchone()
        if soltas and soltas[0]:
            n, l, d, cr, s = soltas
            galhos.append({"codigo": SEM_REFERENCIAL, "contas": n, "lancamentos": l,
                           "debitos": _texto(d), "creditos": _texto(cr), "saldo": _texto(s)})
    return galhos


def lancamentos(destino: str, cnpj: str, conta: str, busca: str | None = None,
                de: str | None = None, ate: str | None = None, pagina: int = 1,
                por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """Os lançamentos de uma conta, em ordem de data, com os totais da conta.

    Os totais vêm da conta **inteira**, não da página — quem confere com a EFD
    precisa do total da conta, e um total que muda ao virar a página não serve
    para conferir nada. Quando há recorte de data ou busca, os totais são os do
    recorte, e a resposta diz qual é para que a tela possa dizê-lo também.
    """
    pagina, por_pagina = _pagina(pagina, por_pagina)
    caminho = _arquivo(destino)

    filtros = ["cnpj = ?", "conta = ?"]
    parametros: list[object] = [cnpj, conta]
    if de:
        filtros.append("data >= ?")
        parametros.append(de)
    if ate:
        filtros.append("data <= ?")
        parametros.append(ate)
    if busca and busca.strip():
        filtros.append("(historico ILIKE ? OR numero ILIKE ? OR participante ILIKE ?)")
        parametros += [f"%{busca.strip()}%"] * 3
    base = (f"(SELECT * FROM read_parquet('{_escapar(caminho)}') "
            f"WHERE {' AND '.join(filtros)})")

    con = _leitura(destino)
    try:
        total, debitos, creditos = con.execute(f"""
            SELECT count(*), coalesce(sum({_DEBITO}), 0), coalesce(sum({_CREDITO}), 0)
            FROM {base}
        """, parametros).fetchone()
        # a ordem é a mesma que gerou o saldo corrente: data, depois o número do
        # lançamento. Ordenar por outra coisa faria a coluna de saldo mentir
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY data, numero
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, parametros)
        nomes = [c[0] for c in cursor.description]
        linhas = [dict(zip(nomes, r)) for r in cursor.fetchall()]
    finally:
        con.close()

    log.info("lançamentos do razão lidos", extra={
        "execucao_pasta": os.path.basename(destino), "cnpj": cnpj, "conta": conta,
        "total": total, "pagina": pagina, "recortado": bool(de or ate or busca),
    })
    return {
        "pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas,
        "cnpj": cnpj, "conta": conta,
        "descricao": linhas[0]["descricao"] if linhas else "",
        "conta_referencial": linhas[0]["conta_referencial"] if linhas else "",
        "recortado": bool(de or ate or (busca or "").strip()),
        "totais": {"debitos": _texto(debitos), "creditos": _texto(creditos),
                   "saldo": _texto(Decimal(debitos or 0) - Decimal(creditos or 0))},
    }


def _conta_jsonavel(linha: dict) -> dict:
    """Os três valores em dinheiro viram texto; o resto vai como veio."""
    for campo in ("debitos", "creditos", "saldo"):
        linha[campo] = _texto(linha.get(campo))
    return linha

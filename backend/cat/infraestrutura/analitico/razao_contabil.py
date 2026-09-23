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
from decimal import Decimal

from cat.infraestrutura.analitico.confronto import _escapar
from cat.infraestrutura.analitico.piscofins import ARQUIVO_DO_RAZAO
from cat.infraestrutura.analitico.suportado import _leitura
from cat.log import obter_log

log = obter_log(__name__)

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
    caminho = os.path.join(destino, ARQUIVO_DO_RAZAO)
    if not os.path.isfile(caminho):
        raise RazaoNaoGerado(
            f"O razão contábil não está em disco nesta execução ({ARQUIVO_DO_RAZAO}). "
            "Rode a quebra de SPED de novo, com pelo menos uma ECD no lote.")
    return caminho


def _pagina(pagina: int, por_pagina: int) -> tuple[int, int]:
    return max(1, int(pagina)), max(1, min(int(por_pagina), POR_PAGINA_MAXIMO))


def _texto(v) -> str:
    """Decimal vira texto com duas casas: é o que atravessa o JSON sem arredondar."""
    return format(Decimal(v or 0).quantize(Decimal("0.01")), "f")


def estabelecimentos(destino: str) -> list[dict]:
    """Os CNPJ que aparecem no razão, com quantas contas cada um tem.

    Existe para a tela poder filtrar antes de listar: uma empresa com trinta
    filiais tem o mesmo plano de contas trinta vezes, e sem o filtro o seletor
    vira uma lista de repetições.
    """
    caminho = _arquivo(destino)
    con = _leitura(destino)
    try:
        cursor = con.execute(f"""
            SELECT cnpj,
                   count(DISTINCT conta) AS contas,
                   count(*)              AS lancamentos,
                   min(data)             AS de,
                   max(data)             AS ate
            FROM read_parquet('{_escapar(caminho)}')
            GROUP BY cnpj ORDER BY cnpj
        """)
        return [{"cnpj": c, "contas": n, "lancamentos": l, "de": de, "ate": ate}
                for c, n, l, de, ate in cursor.fetchall()]
    finally:
        con.close()


def contas(destino: str, busca: str | None = None, cnpj: str | None = None,
           so: str | None = None, pagina: int = 1,
           por_pagina: int = POR_PAGINA_PADRAO) -> dict:
    """O seletor de conta: uma linha por conta, com movimento e saldo.

    A ordem é pelo código da conta, que é a ordem do plano — é assim que o
    contador procura. Quem quiser a conta que mais movimentou tem a coluna para
    ordenar na tela; mudar a ordem padrão faria a lista deixar de parecer um
    plano de contas.
    """
    if so and so not in RECORTES:
        raise ValueError(f"Recorte desconhecido: {so}. Há {', '.join(sorted(RECORTES))}.")
    pagina, por_pagina = _pagina(pagina, por_pagina)
    caminho = _arquivo(destino)

    filtros, parametros = [], []
    if cnpj and cnpj.strip():
        filtros.append("cnpj = ?")
        parametros.append(cnpj.strip())
    if busca and busca.strip():
        filtros.append("(conta ILIKE ? OR descricao ILIKE ? OR conta_referencial ILIKE ?)")
        parametros += [f"%{busca.strip()}%"] * 3
    onde = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    agrupado = f"""
        SELECT cnpj, conta,
               any_value(descricao)          AS descricao,
               any_value(conta_referencial)  AS conta_referencial,
               count(*)                      AS lancamentos,
               sum({_DEBITO})                AS debitos,
               sum({_CREDITO})               AS creditos,
               sum({_DEBITO}) - sum({_CREDITO}) AS saldo,
               min(data)                     AS de,
               max(data)                     AS ate,
               count(DISTINCT arquivo)       AS arquivos
        FROM read_parquet('{_escapar(caminho)}') {onde}
        GROUP BY cnpj, conta
    """
    base = f"({agrupado})" if not so else f"(SELECT * FROM ({agrupado}) WHERE {RECORTES[so]})"

    con = _leitura(destino)
    try:
        total = con.execute(f"SELECT count(*) FROM {base}", parametros).fetchone()[0]
        cursor = con.execute(f"""
            SELECT * FROM {base} ORDER BY cnpj, conta
            LIMIT {por_pagina} OFFSET {(pagina - 1) * por_pagina}
        """, parametros)
        nomes = [c[0] for c in cursor.description]
        linhas = [_conta_jsonavel(dict(zip(nomes, r))) for r in cursor.fetchall()]
    finally:
        con.close()

    log.info("contas do razão listadas", extra={
        "execucao_pasta": os.path.basename(destino), "total": total,
        "pagina": pagina, "busca": bool(busca), "cnpj": bool(cnpj), "recorte": so or "",
    })
    return {"pagina": pagina, "por_pagina": por_pagina, "total": total, "linhas": linhas}


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

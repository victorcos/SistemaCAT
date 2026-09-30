"""Ler e gravar a tabela `aliquota_de_item`.

**Só o que foge da regra entra aqui.** Guardar as 7.276 alíquotas de um cliente
quando 6.720 delas são a alíquota padrão do estado seria trocar uma lei
auditável por uma tabela opaca — e é exatamente o que este projeto decidiu não
fazer (ver DECISOES de 30/09/2026). Quem grava filtra antes; quem lê recebe só
as exceções, e a regra responde pelo resto.

**Gravar substitui.** Diferente da Selic, aqui o valor **pode** mudar: alíquota
interna muda por lei, e produto muda de classificação. A última carga vale, e
`atualizada_em` diz quando foi.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.infraestrutura.repositorios.modelos import AliquotaDeItemDB
from cat.log import obter_log

log = obter_log(__name__)

# a chave, na ordem em que `tab_aliquota_icms.aplicavel` a monta
Chave = tuple[str, str, str, str]


def excecoes_de(sessao: Session, cnpjs: list[str]) -> dict[Chave, Decimal]:
    """As exceções dos estabelecimentos dados, prontas para o motor.

    Lista vazia devolve dicionário vazio sem ir ao banco: um trabalho sem
    estabelecimento conhecido não tem o que perguntar.
    """
    if not cnpjs:
        return {}
    linhas = sessao.scalars(
        select(AliquotaDeItemDB).where(AliquotaDeItemDB.cnpj.in_(cnpjs)))
    return {
        (linha.cnpj, linha.uf_origem, linha.uf_destino, linha.codigo_do_item):
            Decimal(linha.aliquota)
        for linha in linhas
    }


def gravar(sessao: Session, excecoes: dict[Chave, Decimal], fonte: str) -> int:
    """Substitui as exceções dadas. Devolve quantas ficaram gravadas."""
    if not excecoes:
        return 0

    existentes = {
        (linha.cnpj, linha.uf_origem, linha.uf_destino, linha.codigo_do_item): linha
        for linha in sessao.scalars(
            select(AliquotaDeItemDB).where(
                AliquotaDeItemDB.cnpj.in_({c for c, _, _, _ in excecoes})))
    }

    novas = mudadas = 0
    for chave, aliquota in sorted(excecoes.items()):
        linha = existentes.get(chave)
        if linha is None:
            cnpj, origem, destino, codigo = chave
            sessao.add(AliquotaDeItemDB(
                cnpj=cnpj, uf_origem=origem, uf_destino=destino,
                codigo_do_item=codigo, aliquota=aliquota, fonte=fonte))
            novas += 1
        elif Decimal(linha.aliquota) != aliquota:
            linha.aliquota = aliquota
            linha.fonte = fonte
            mudadas += 1

    sessao.commit()
    log.info("alíquotas de item gravadas", extra={
        "fonte": fonte, "recebidas": len(excecoes),
        "novas": novas, "mudadas": mudadas})
    return novas + mudadas

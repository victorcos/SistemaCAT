"""Ler e gravar a tabela `selic_mensal`.

**Grava só o que falta.** Mês que já está no banco não é sobrescrito, nem
quando a API o devolve de novo: taxa de mês fechado não muda, e deixar uma
consulta de hoje reescrever o número que corrigiu um pedido de ontem seria
mexer em dinheiro por conta própria.

Quando a API discorda do que está guardado, o repositório **avisa e mantém o
guardado**. Divergência aí é notícia — revisão do Banco Central, ou erro de
quem semeou —, e notícia se lê no log, não se aplica em silêncio.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.infraestrutura.repositorios.modelos import SelicMensalDB
from cat.log import obter_log

log = obter_log(__name__)


def ler(sessao: Session) -> dict[str, Decimal]:
    """A série inteira, "aaaa-mm" -> taxa do mês em por cento."""
    linhas = sessao.scalars(select(SelicMensalDB))
    return {linha.competencia: Decimal(linha.taxa) for linha in linhas}


def gravar(sessao: Session, taxas: dict[str, Decimal], fonte: str) -> int:
    """Grava o que ainda não existe. Devolve quantos meses entraram."""
    if not taxas:
        return 0

    ja_tem = {
        linha.competencia: Decimal(linha.taxa)
        for linha in sessao.scalars(
            select(SelicMensalDB).where(SelicMensalDB.competencia.in_(taxas)))
    }
    _avisar_das_divergencias(ja_tem, taxas, fonte)

    novos = [SelicMensalDB(competencia=mes, taxa=taxa, fonte=fonte)
             for mes, taxa in sorted(taxas.items()) if mes not in ja_tem]
    if not novos:
        return 0

    sessao.add_all(novos)
    sessao.commit()
    log.info("selic guardada", extra={
        "fonte": fonte, "meses": len(novos),
        "primeiro": novos[0].competencia, "ultimo": novos[-1].competencia})
    return len(novos)


def _avisar_das_divergencias(ja_tem: dict[str, Decimal], taxas: dict[str, Decimal],
                             fonte: str) -> None:
    """Mês guardado que voltou diferente vira aviso, nunca sobrescrita."""
    for mes, guardada in sorted(ja_tem.items()):
        if taxas[mes] != guardada:
            log.warning(
                "a Selic guardada difere da que %s devolveu; fica a guardada",
                fonte,
                extra={"competencia": mes, "guardada": str(guardada),
                       "recebida": str(taxas[mes]), "fonte": fonte,
                       "acao": "conferir antes de corrigir à mão"})

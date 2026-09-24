"""Até onde o crédito ainda pode ser pedido.

O prazo para repetir o indébito é de **cinco anos contados do pagamento** (LC
118/2005, art. 3º, e Tema 4 do STJ). Para PIS e COFINS o pagamento vence no
**dia 25 do mês seguinte** ao fato gerador (Lei 11.933/2009, art. 1º); é ele
que marca o início da contagem.

**O que fica prescrito não some: fica marcado.** Um relatório que apaga sozinho
as competências velhas esconde de quem assina a decisão mais importante do
trabalho — e a data de referência muda tudo: um pedido protocolado em janeiro
alcança um mês que um pedido de julho já perdeu. Por isso a data entra por
fora, e o resumo diz qual foi usada.

**Não decide sozinho o caso concreto.** Ação já ajuizada, pedido administrativo
anterior, tributo com exigibilidade suspensa — tudo isso desloca a contagem, e
nada disso está no SPED. O que o sistema faz é separar pela regra geral e
mostrar as duas somas; quem assina ajusta.
"""

from __future__ import annotations

from datetime import date

ANOS_DE_PRESCRICAO = 5
DIA_DO_VENCIMENTO = 25


def vencimento(competencia: str) -> date:
    """O dia em que a contribuição da competência venceu. "2021-03" -> 25/04/2021."""
    ano, mes = (int(p) for p in competencia.split("-")[:2])
    if mes == 12:
        ano, mes = ano + 1, 1
    else:
        mes += 1
    return date(ano, mes, DIA_DO_VENCIMENTO)


def limite(referencia: date) -> date:
    """O vencimento mais antigo que ainda alcança, para um pedido nesta data."""
    try:
        return referencia.replace(year=referencia.year - ANOS_DE_PRESCRICAO)
    except ValueError:
        # 29/02 num ano que não é bissexto cinco anos antes
        return referencia.replace(year=referencia.year - ANOS_DE_PRESCRICAO, day=28)


def prescrita(competencia: str, referencia: date) -> bool:
    """A competência está fora do prazo de cinco anos?

    O corte é o vencimento: a competência de 08/2021 venceu em 25/09/2021 e um
    pedido de 24/09/2026 ainda a alcança por um dia. É essa a conta que decide
    milhões num trabalho de cinco anos, e é por isso que ela não arredonda para
    o mês.
    """
    return vencimento(competencia) < limite(referencia)

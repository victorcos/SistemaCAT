"""Que Selic usar, e o que buscar para tê-la.

A regra é uma frase: **o banco é a memória, a API é só o que falta.**

1. banco vazio? Semeia com a tabela do repositório (`tab_selic.MENSAL`), que é
   o que o time já tinha conferido contra o gabarito do MA;
2. falta algum mês até o da restituição? Busca **só esses** no Banco Central e
   guarda;
3. a rede falhou? Segue com o que está guardado — e, se não cobrir, a etapa
   recusa dizendo o que falta, em vez de corrigir a menos.

## Por que não buscar sempre

Taxa de mês fechado não muda. Rebuscar a série inteira a cada rodada seria
pagar rede para receber o que já se sabe, e — pior — pôr um cálculo que vira
pedido de restituição na dependência de um serviço externo estar no ar. Depois
da primeira rodada de um mês, esta função não toca a rede.

## Um mês de sobreposição, de propósito

A busca começa um mês **antes** do primeiro que falta. Esse mês já está no
banco e não será sobrescrito — ele existe para que o repositório possa comparar
e avisar se o Banco Central publicou algo diferente do que corrigiu um pedido
nosso. Custa uma linha de JSON e é o único sinal que teríamos de uma revisão.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from cat.infraestrutura.selic import bcb, repositorio
from cat.infraestrutura.sped.tabelas import tab_selic
from cat.log import obter_log

log = obter_log(__name__)

# a fonte de quem semeou do código, para distinguir no banco de quem veio da API
FONTE_DO_REPOSITORIO = "repositorio"


class SelicIndisponivel(RuntimeError):
    """Nem o banco nem a API sabem a Selic dos meses pedidos."""


def serie(ate: str, sessao: Session | None = None,
          baixar=bcb.baixar) -> dict[str, Decimal]:
    """A série mensal que cobre uma restituição em `ate`.

    `baixar` entra por parâmetro para que o teste não precise de rede — e para
    que ligar ou desligar a busca seja uma decisão de quem chama, não um efeito
    escondido aqui dentro.
    """
    if sessao is not None:
        return _serie(ate, sessao, baixar)
    # sessão curta e própria: a Selic não é do projeto nem da rodada, e prendê-la
    # à transação da etapa faria um `rollback` de lá apagar o que já foi buscado
    from cat.infraestrutura.repositorios.banco import Sessao  # noqa: PLC0415

    with Sessao() as propria:
        return _serie(ate, propria, baixar)


def _serie(ate: str, sessao: Session, baixar) -> dict[str, Decimal]:
    guardada = repositorio.ler(sessao)
    if not guardada:
        # a primeira vez: o que já existe em código vai para o banco, de onde
        # ninguém mais o tira
        repositorio.gravar(sessao, dict(tab_selic.MENSAL), FONTE_DO_REPOSITORIO)
        guardada = repositorio.ler(sessao)
        log.info("selic semeada no banco a partir do repositório",
                 extra={"meses": len(guardada)})

    faltam = _faltando(guardada, ate)
    if not faltam:
        return guardada

    if _buscar(sessao, guardada, faltam, ate, baixar):
        return repositorio.ler(sessao)
    return guardada


def _buscar(sessao: Session, guardada: dict[str, Decimal], faltam: list[str],
            ate: str, baixar) -> bool:
    """Vai ao Banco Central pelos meses que faltam. `False` se não deu."""
    # um mês antes do primeiro que falta: é a sobreposição que denuncia revisão
    de = tab_selic.anterior(faltam[0]) if guardada else faltam[0]
    try:
        taxas = baixar(de, faltam[-1])
    except bcb.ConsultaAoBcbFalhou as erro:
        log.warning("selic não pôde ser atualizada; segue a do banco", extra={
            "motivo": str(erro), "faltam": faltam[:3],
            "ultimo_guardado": max(guardada) if guardada else "",
            "ate": ate})
        return False

    repositorio.gravar(sessao, taxas, bcb.FONTE)
    return True


def _faltando(guardada: dict[str, Decimal], ate: str) -> list[str]:
    """Os meses que a correção até `ate` exige e o banco não tem.

    A acumulada soma até o mês **anterior** ao da restituição; do começo, o mais
    antigo que a série guarda. Não se busca antes disso: competência mais velha
    que a série é assunto de quem semeia, não de quem corrige.
    """
    if not guardada:
        return []
    fim = tab_selic.anterior(ate)
    inicio = min(guardada)
    if fim < inicio:
        return []
    return [mes for mes in tab_selic.meses(inicio, fim) if mes not in guardada]


def acumulada(competencia: str, ate: str, mensal: dict[str, Decimal]) -> Decimal:
    """A acumulada de uma competência, sobre a série dada.

    Fina de propósito: a conta é uma só, e mora em `tab_selic`. Esta camada
    decide **qual série**, não como somar.
    """
    return tab_selic.acumulada(competencia, ate, mensal)


def alcanca(ate: str, mensal: dict[str, Decimal]) -> bool:
    """A série cobre uma restituição neste mês?"""
    return tab_selic.alcanca(ate, mensal)

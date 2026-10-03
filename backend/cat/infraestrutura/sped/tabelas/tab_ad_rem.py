"""A alíquota **ad rem** do ICMS monofásico de combustíveis, por competência.

Desde a LC 192/2022 o ICMS do combustível não é percentual: é um valor fixo por
litro ou por quilo, uniforme no país inteiro. O crédito de quem consome
combustível como insumo é `litros × ad rem × FCV` — e esta tabela é a metade do
meio.

## Por que ela é datada, e por que isso não é zelo excessivo

A cláusula sétima do Convênio ICMS 199/2022 foi alterada **cerca de vinte vezes
em três anos**: 10/23, 12/23, 19/23, 24/23, 64/23, 65/23, 74/23, 85/23, 112/23,
172/23, 186/23, 126/24, 149/24, 172/24, 12/25, 76/25, 113/25, 165/25, 39/26,
67/26. Um pedido de crédito cobre cinco anos e atravessa todas elas.

Uma tabela com um número por produto aplicaria a ad rem de hoje a uma compra de
2023 — e, como tudo aqui é multiplicação, o erro vai inteiro para o número final.

**E o mês da virada muda.** 2024 e 2025 começaram em **1º de fevereiro**; 2026
começou em **1º de janeiro**. Quem assumir "sempre fevereiro" erra janeiro de
2026 em 4,3% no diesel.

## O que está conferido, e o que não está

`AD_REM` guarda **só o que foi lido no texto do convênio no sítio do CONFAZ**.
`A_CONFERIR` guarda o que se suspeita — e o motor **recusa**, levantando
`AdRemDesconhecida`, até alguém abrir o convênio e mover a linha.

Duas das vigências conferidas têm uma segunda prova, independente da lei: a
escrituração da empresa G, que credita o monofásico por ajuste `SP020799`. O
crédito dela dividido pelos litros dá **exatamente** `0,9456` em 2024-01 e
`1,0635` em 2024-02, 2024-05 e 2024-06. Lei e livro do cliente concordando é o
padrão que esta casa exige — o mesmo de `tab_aliquota_icms`.

## O que esta tabela não é

Não é o FCV, que corrige o volume faturado a 20 °C e varia **por UF e por
produto** (SP: 0,9976 no diesel, 0,9967 na gasolina). Não é a alíquota da era do
ST, anterior à virada, que é percentual e estadual. E não é o valor efetivamente
cobrado pelo fornecedor: isso só o XML diz, no grupo N08a — ver
`docs/DOMINIO_COMBUSTIVEL.md`, §5.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# os produtos do regime monofásico, como o convênio os nomeia. São estes e
# **só** estes: lubrificante nunca entrou no monofásico, e etanol hidratado
# tampouco — ver `tab_combustivel`
DIESEL = "diesel"        # óleo diesel A/B e biodiesel B100, por litro
GASOLINA = "gasolina"    # gasolina C e etanol anidro, por litro
GLP = "glp"              # GLP e GLGN, inclusive o derivado de gás natural, por quilo

# a unidade em que a ad rem é cobrada. O GLP é o que pega quem não olha: ele é
# por **quilo**, e o SPED do cliente costuma declarar o botijão em unidades
LITRO = "litro"
QUILO = "quilo"

UNIDADE: dict[str, str] = {DIESEL: LITRO, GASOLINA: LITRO, GLP: QUILO}


@dataclass(frozen=True)
class Vigencia:
    """Uma ad rem, o mês em que passou a valer, e de onde ela saiu."""

    valor: Decimal
    desde: str        # "aaaa-mm"; vale desta competência em diante
    fundamento: str   # o convênio, e a prova de que foi lido


# **Só o que foi lido no texto do convênio.** Em ordem decrescente de vigência
# dentro de cada produto, que é a ordem em que se procura.
AD_REM: dict[str, tuple[Vigencia, ...]] = {
    DIESEL: (
        Vigencia(Decimal("1.17"), "2026-01",
                 "Convênio ICMS 113/2025, que altera a cláusula sétima do Conv. "
                 "199/2022; vigência de 1º/01/2026 — repare que o mês da virada "
                 "mudou de fevereiro para janeiro"),
        Vigencia(Decimal("1.12"), "2025-02",
                 "Convênio ICMS 126/2024, incisos I e II da cláusula sétima do "
                 "Conv. 199/2022; vigência de 1º/02/2025"),
        Vigencia(Decimal("1.0635"), "2024-02",
                 "Convênio ICMS 172/2023, incisos I e II da cláusula sétima do "
                 "Conv. 199/2022; vigência de 1º/02/2024. Conferido também na "
                 "escrituração da empresa G: o ajuste SP020799 dividido pelos "
                 "litros dá 1,0635 exato em 2024-02, 2024-05 e 2024-06"),
    ),
    GASOLINA: (
        Vigencia(Decimal("1.57"), "2026-01",
                 "Convênio ICMS 112/2025, que altera a cláusula sétima do Conv. "
                 "15/2023; vigência de 1º/01/2026"),
        Vigencia(Decimal("1.47"), "2025-02",
                 "Convênio ICMS 127/2024, cláusula sétima do Conv. 15/2023; "
                 "vigência de 1º/02/2025. Valor único para gasolina C e etanol "
                 "anidro"),
    ),
    GLP: (
        Vigencia(Decimal("1.47"), "2026-01",
                 "Convênio ICMS 113/2025, que altera a cláusula sétima do Conv. "
                 "199/2022; vigência de 1º/01/2026"),
        Vigencia(Decimal("1.39"), "2025-02",
                 "Convênio ICMS 126/2024, incisos I e II da cláusula sétima do "
                 "Conv. 199/2022; vigência de 1º/02/2025"),
        Vigencia(Decimal("1.4139"), "2024-02",
                 "Convênio ICMS 172/2023, incisos I e II da cláusula sétima do "
                 "Conv. 199/2022; vigência de 1º/02/2024"),
    ),
}

# O que se suspeita e ainda não se conferiu no texto do convênio. O motor
# **recusa** estas competências — ver `da_competencia`. Estão aqui para que quem
# for conferir saiba por onde começar, e não para serem usadas.
#
# O diesel de 0,9456 é o caso mais forte: aparece no exemplo da própria SEFAZ-SP
# (RC 28013/2023) e bate exato com a escrituração da empresa G em 2024-01. Mesmo
# assim fica aqui, porque ninguém leu a redação original da cláusula sétima — e
# a regra desta casa é que exemplo em resposta de consulta não é o ato legal.
A_CONFERIR: dict[tuple[str, str], tuple[Decimal, str]] = {
    (DIESEL, "2023-05"): (Decimal("0.9456"),
                          "redação original da cláusula sétima do Conv. ICMS "
                          "199/2022; exemplo da RC 28013/2023 e escrituração da "
                          "empresa G em 2024-01 batem, mas o texto não foi lido"),
    (GLP, "2023-05"): (Decimal("1.2571"),
                       "redação original do Conv. ICMS 199/2022, por quilo"),
    (GASOLINA, "2023-06"): (Decimal("1.22"),
                            "redação original da cláusula sétima do Conv. ICMS "
                            "15/2023; a gasolina entrou no monofásico um mês "
                            "depois do diesel"),
    (GASOLINA, "2024-02"): (Decimal("1.3721"),
                            "reajuste de fevereiro de 2024; falta localizar o "
                            "convênio que alterou o Conv. 15/2023"),
}


class AdRemDesconhecida(LookupError):
    """Pediram a ad rem de um produto, ou de um mês, que não se conferiu."""


def da_competencia(produto: str, competencia: str) -> Decimal:
    """A ad rem do produto na competência, em reais por litro ou por quilo.

    `competencia` em "aaaa-mm". Levanta `AdRemDesconhecida` quando o produto não
    está na tabela ou quando a competência é anterior à vigência mais antiga
    conferida — **inclusive quando há um palpite em `A_CONFERIR`**, e a mensagem
    diz qual é e o que falta para usá-lo.

    Recusar é deliberado. Esta tabela multiplica o número inteiro: um palpite
    aqui não vira erro de centavo, vira erro de dezena de por cento num pedido
    que alguém assina.
    """
    vigencias = AD_REM.get(produto)
    if vigencias is None:
        raise AdRemDesconhecida(
            f"{produto!r} não é produto do regime monofásico, ou não está em "
            f"`tab_ad_rem.AD_REM`. Os do regime são: "
            f"{', '.join(sorted(AD_REM))}.")

    for vigencia in vigencias:
        if competencia >= vigencia.desde:
            return vigencia.valor

    suspeita = _suspeita(produto, competencia)
    mais_antiga = vigencias[-1].desde
    raise AdRemDesconhecida(
        f"A ad rem de {produto} em {competencia} não está conferida: a vigência "
        f"mais antiga conhecida começa em {mais_antiga}."
        + (f" Suspeita-se de R$ {suspeita[0]} ({suspeita[1]}), e é preciso ler o "
           f"texto do convênio antes de usá-la." if suspeita else "")
        + " Conferir no sítio do CONFAZ e acrescentar a vigência em "
          "`tab_ad_rem.AD_REM`.")


def _suspeita(produto: str, competencia: str) -> tuple[Decimal, str] | None:
    """O palpite que cobriria esta competência, se houver. Nunca é devolvido ao
    cálculo — só entra na mensagem de quem vai conferir."""
    candidatas = [(desde, v) for (p, desde), v in A_CONFERIR.items()
                  if p == produto and competencia >= desde]
    return max(candidatas)[1] if candidatas else None


def unidade_de(produto: str) -> str:
    """Em que unidade a ad rem daquele produto é cobrada: litro ou quilo."""
    try:
        return UNIDADE[produto]
    except KeyError:
        raise AdRemDesconhecida(
            f"{produto!r} não tem unidade tributada conhecida.") from None

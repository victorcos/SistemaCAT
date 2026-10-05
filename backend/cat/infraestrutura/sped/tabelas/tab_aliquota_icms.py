"""A alíquota de ICMS aplicável a uma operação — a parte que é regra.

Serve ao **ICMS-ST presumido** do relatório 839: como a revenda de mercadoria
com ST já retido não destaca imposto nenhum, o ST que se exclui da base do
PIS/COFINS precisa ser reconstruído, e a alíquota é metade dessa reconstrução.

## O que é regra e o que é cadastro

**Regra, e mora aqui:**

* na operação **interestadual**, a alíquota é a da Resolução 22/1989 do Senado
  — 7% do Sul/Sudeste para o Norte, Nordeste, Centro-Oeste e Espírito Santo,
  12% no resto;
* na operação **interna**, a alíquota padrão do estado **na competência**.

**Cadastro, e mora no banco:** a alíquota interna de um *produto específico*,
quando ele foge do padrão — cesta básica, supérfluo, isento, importado. Isso é
classificação fiscal de mercadoria, muda de item para item, e **não está no
SPED**: o `ALIQ_ICMS` do registro 0200 é facultativo e veio vazio nos 8.061
cadastros do arquivo de referência. Por ser dado do cliente, fica na tabela
`aliquota_de_item` e nunca no repositório.

Medido no gabarito do 839 (463.212 linhas, 30/09/2026): a **regra sozinha
acerta 98,66%** das linhas, e as exceções são 556 pares de (estabelecimento,
UF, item).

## A alíquota tem data, e esquecer isso erra dinheiro calado

Uma tabela com um número por estado aplicaria a alíquota de hoje a uma operação
de 2021. Vários estados subiram a interna entre 2023 e 2025, e um pedido de
restituição cobre cinco anos — atravessa a mudança. Por isso cada estado guarda
**uma linha por vigência**, e `da_regra` recebe a competência.

Em Minas não mudou, o que é a razão de a conferência do 839 ter fechado 100%
sem esta coluna existir. Foi sorte, não acerto, e sorte não é método.

## O que está conferido, e o que não está

`INTERNA` guarda **só o que foi medido contra dado real**. Hoje é uma UF:

* **MG, 18%** — conferido na EFD ICMS/IPI da empresa 05, 201 arquivos de 2021 a
  2025: das saídas internas tributadas integralmente (CFOP 5xxx, CST 00), 18%
  responde por 56% a 59% das linhas em todos os anos, sem degrau em nenhum.

`A_CONFERIR` guarda o que se **suspeita**, e que o motor **recusa** até alguém
confirmar. Não é excesso de zelo: errar a interna em um ponto e meio sobre os
R$ 117 milhões de base de um cliente médio são R$ 160 mil de crédito pedido
indevidamente, e esse erro não aparece em lugar nenhum do relatório — vira só
um número maior.

**E a conferência não pode sair do relatório do escritório anterior.** Seria
circular: é exatamente a classificação que este módulo existe para não copiar.
A prova vem da escrituração do próprio cliente — `tools/aferir_aliquota_interna.py`
tira dela a alíquota que ele cobrou, ano a ano — mais o ato legal do estado, que
vai escrito na linha.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Resolução 22/1989 do Senado: 7% nas saídas do Sul/Sudeste para o Norte,
# Nordeste, Centro-Oeste e Espírito Santo; 12% nas demais interestaduais
SUL_SUDESTE = frozenset({"MG", "PR", "RJ", "RS", "SC", "SP"})
NORTE_NORDESTE_CENTRO_OESTE = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "PA", "PB", "PE", "PI", "RN", "RO", "RR", "SE", "TO",
})

SETE = Decimal(7)
DOZE = Decimal(12)


@dataclass(frozen=True)
class Vigencia:
    """Uma alíquota interna, o mês em que passou a valer e de onde ela saiu."""

    aliquota: Decimal
    desde: str        # "aaaa-mm"; vale desta competência em diante
    fundamento: str   # o ato legal, e a prova de que foi medida


# A alíquota interna padrão de cada estado, **só o que está conferido**. Em
# ordem decrescente de vigência dentro de cada UF, que é a ordem em que se
# procura. Acrescentar estado aqui exige as duas coisas do topo do módulo: o
# ato legal e a medição na escrituração de um cliente daquele estado.
INTERNA: dict[str, tuple[Vigencia, ...]] = {
    "MG": (
        Vigencia(Decimal(18), "2018-01",
                 "Lei 6.763/1975, art. 12, I, e; conferido na EFD ICMS/IPI da "
                 "empresa 05, 2021 a 2025, sem degrau"),
    ),
}

# O que se suspeita e ainda não se conferiu. O motor **recusa** estes estados —
# ver `da_regra`. Estão aqui para que quem for conferir saiba por onde começar,
# e não para serem usados: mover uma linha daqui para `INTERNA` é um ato
# deliberado, que exige o ato legal e a medição.
#
# São as alíquotas gerais que se acredita vigentes em 30/09/2026. Vários destes
# estados subiram a interna entre 2023 e 2025, então o número abaixo
# provavelmente **não** vale para a competência inteira de um pedido de cinco
# anos — e é justamente por isso que ninguém deve copiá-lo daqui.
A_CONFERIR: dict[str, Decimal] = {
    "AC": Decimal(19), "AL": Decimal(20), "AM": Decimal(20), "AP": Decimal(18),
    "BA": Decimal(20), "CE": Decimal(20), "DF": Decimal(20), "ES": Decimal(17),
    "GO": Decimal(19), "MA": Decimal(22), "MS": Decimal(17), "MT": Decimal(17),
    "PA": Decimal(19), "PB": Decimal(20), "PE": Decimal("20.5"),
    "PI": Decimal(21), "PR": Decimal("19.5"), "RJ": Decimal(20),
    "RN": Decimal(20), "RO": Decimal("19.5"), "RR": Decimal(20),
    "RS": Decimal(17), "SC": Decimal(17), "SE": Decimal(19), "SP": Decimal(18),
    "TO": Decimal(20),
}


class AliquotaDesconhecida(LookupError):
    """Pediram a alíquota interna de um estado, ou de um mês, que não se sabe."""


def interna(uf: str, competencia: str) -> Decimal:
    """A alíquota interna daquele estado naquela competência.

    `competencia` em "aaaa-mm". Levanta `AliquotaDesconhecida` quando o estado
    não está conferido, ou quando está e a competência é anterior à vigência
    mais antiga que se conhece.
    """
    uf = (uf or "").strip().upper()
    vigencias = INTERNA.get(uf)
    if not vigencias:
        suspeita = A_CONFERIR.get(uf)
        pista = (f" Há um valor a conferir de {suspeita}%, que **não** deve ser "
                 "usado sem confirmação." if suspeita is not None else "")
        raise AliquotaDesconhecida(
            f"A alíquota interna de {uf or '(sem UF)'} não está conferida.{pista} "
            "Rode `tools/aferir_aliquota_interna.py` sobre a EFD ICMS/IPI do "
            "cliente, confronte com a lei do estado e acrescente a linha em "
            "`tab_aliquota_icms.INTERNA`. Conferir pelo relatório do escritório "
            "anterior não vale: seria copiar a classificação que este módulo "
            "existe para não copiar.")

    for vigencia in sorted(vigencias, key=lambda v: v.desde, reverse=True):
        if competencia >= vigencia.desde:
            return vigencia.aliquota

    mais_antiga = min(v.desde for v in vigencias)
    raise AliquotaDesconhecida(
        f"A alíquota interna de {uf} só é conhecida a partir de "
        f"{mais_antiga[5:]}/{mais_antiga[:4]}, e a competência pedida é "
        f"{competencia[5:]}/{competencia[:4]}. Acrescente a vigência anterior "
        "em `tab_aliquota_icms.INTERNA`.")


def da_regra(origem: str, destino: str, competencia: str) -> Decimal:
    """A alíquota que a lei manda, sem olhar o produto.

    `origem` e `destino` são siglas de UF; `competencia` é "aaaa-mm".
    Interestadual segue a Resolução do Senado — que não muda desde 1989 e por
    isso não tem vigência aqui. Interna, a alíquota do estado naquele mês.
    """
    origem, destino = (origem or "").strip().upper(), (destino or "").strip().upper()
    if origem and destino and origem != destino:
        return (SETE if origem in SUL_SUDESTE
                and destino in NORTE_NORDESTE_CENTRO_OESTE else DOZE)
    return interna(destino or origem, competencia)


def aplicavel(origem: str, destino: str, competencia: str, cnpj: str,
              codigo_do_item: str,
              excecoes: dict[tuple[str, str, str, str], Decimal] | None = None,
              ) -> Decimal:
    """A alíquota do produto nesta operação: a exceção, se houver; senão a regra.

    `excecoes` vem do banco (`aliquota_de_item`), com a classificação fiscal dos
    produtos que fogem do padrão. Vazio significa "nenhum produto foge" — o que
    é a verdade em quase todo estabelecimento e em 98,66% das linhas medidas.

    A exceção é consultada **antes** da regra, e por isso um produto conhecido
    dispensa o estado estar conferido. É de propósito: quem cadastrou a exceção
    daquele item sabe mais sobre ele do que a alíquota geral do estado.
    """
    if excecoes:
        chave = (cnpj, (origem or "").upper(), (destino or "").upper(), codigo_do_item)
        if (achada := excecoes.get(chave)) is not None:
            return achada
    return da_regra(origem, destino, competencia)

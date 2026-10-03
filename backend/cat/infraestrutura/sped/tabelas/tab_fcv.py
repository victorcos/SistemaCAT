"""O Fator de Correção do Volume — o terceiro termo da conta do combustível.

O crédito de quem consome combustível como insumo é `litros × ad rem × FCV`.
Esta tabela é o FCV.

## O que ele corrige, e por que ele existe

Combustível líquido é **faturado a 20 °C**. No tanque, à temperatura ambiente do
estado, o mesmo combustível ocupa mais espaço — e quem mede em litros no posto
mede o volume dilatado, não o volume faturado. O FCV desfaz essa dilatação.

É por isso que ele **cai conforme a temperatura sobe**: Rio Grande do Sul, a
21,0 °C, corrige quase nada (0,9992 no diesel); Roraima, a 30,5 °C, corrige dez
vezes mais (0,9914). A tabela é física, não fiscal, e essa monotonia é a melhor
conferência que ela tem.

## Por UF **e** por produto

Dois eixos, e esquecer o segundo custa 0,09% em São Paulo — a gasolina dilata
mais que o diesel, porque é mais leve. Em 02/10/2026 descobriu-se o primeiro eixo
errado num papel de trabalho de projeto **encerrado**: ele aplicou o FCV de São
Paulo (0,9976) a um cliente do **Espírito Santo**, cujo fator é 0,9943 — 0,33% de
diferença, sistemática, em tudo que foi apurado.

## O GLP não tem FCV, e isso não é lacuna

Ele é tributado **por quilo**. Massa não dilata com a temperatura; volume dilata.
Não há o que corrigir, e a SEFAZ-SP diz o mesmo na RC 28013/2023. Por isso
`fator()` devolve 1 para o GLP — um fato, e não um valor desconhecido disfarçado
de neutro.

## O que está conferido, e o que não está

Lido no texto do **Ato COTEPE/ICMS 64/2019** no sítio do CONFAZ, vigente desde
1º/01/2020. As 27 unidades federadas estão aqui, com a temperatura média que as
explica.

**Uma incerteza registrada:** o FCV é, por definição, calculado **anualmente** —
da tabela de densidade da ANP, das temperaturas médias do INMET e da conversão da
Resolução CNP 06/70. Ainda assim, tanto a resposta de consulta da SEFAZ-SP (2023)
quanto um papel de trabalho de 2025 continuam citando o Ato de 2019. Ou ele não
foi atualizado, ou as atualizações não foram localizadas. Se aparecer Ato novo,
isto aqui vira uma segunda vigência — a estrutura já comporta.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cat.infraestrutura.sped.tabelas.tab_ad_rem import DIESEL, GASOLINA, GLP

# o FCV do Ato COTEPE 64/2019 passou a valer nesta competência
DESDE = "2020-01"

FUNDAMENTO = ("Ato COTEPE/ICMS 64/2019, cláusula nona do Convênio ICMS 110/2007; "
              "vigente desde 1º/01/2020")


@dataclass(frozen=True)
class Fatores:
    """Os fatores de uma UF, e a temperatura média que os explica."""

    temperatura: Decimal   # °C, média anual do INMET
    gasolina: Decimal
    diesel: Decimal


# As 27 unidades federadas, como o Ato COTEPE as publica. A temperatura fica
# junto de propósito: é ela que torna a tabela conferível por quem a lê — fator
# que não acompanha a temperatura do estado está errado.
POR_UF: dict[str, Fatores] = {
    "AC": Fatores(Decimal("27.5"), Decimal("0.9917"), Decimal("0.9939")),
    "AL": Fatores(Decimal("28.0"), Decimal("0.9912"), Decimal("0.9935")),
    "AM": Fatores(Decimal("30.0"), Decimal("0.9890"), Decimal("0.9918")),
    "AP": Fatores(Decimal("29.5"), Decimal("0.9895"), Decimal("0.9923")),
    "BA": Fatores(Decimal("27.5"), Decimal("0.9917"), Decimal("0.9939")),
    "CE": Fatores(Decimal("29.0"), Decimal("0.9901"), Decimal("0.9927")),
    "DF": Fatores(Decimal("24.0"), Decimal("0.9956"), Decimal("0.9967")),
    "ES": Fatores(Decimal("27.0"), Decimal("0.9923"), Decimal("0.9943")),
    "GO": Fatores(Decimal("26.5"), Decimal("0.9928"), Decimal("0.9947")),
    "MA": Fatores(Decimal("30.0"), Decimal("0.9890"), Decimal("0.9918")),
    "MG": Fatores(Decimal("24.0"), Decimal("0.9956"), Decimal("0.9967")),
    "MS": Fatores(Decimal("27.5"), Decimal("0.9917"), Decimal("0.9939")),
    "MT": Fatores(Decimal("28.5"), Decimal("0.9906"), Decimal("0.9931")),
    "PA": Fatores(Decimal("29.0"), Decimal("0.9901"), Decimal("0.9927")),
    "PB": Fatores(Decimal("28.0"), Decimal("0.9912"), Decimal("0.9935")),
    "PE": Fatores(Decimal("28.0"), Decimal("0.9912"), Decimal("0.9935")),
    "PI": Fatores(Decimal("30.0"), Decimal("0.9890"), Decimal("0.9918")),
    "PR": Fatores(Decimal("22.5"), Decimal("0.9973"), Decimal("0.9980")),
    "RJ": Fatores(Decimal("26.0"), Decimal("0.9934"), Decimal("0.9951")),
    "RN": Fatores(Decimal("29.5"), Decimal("0.9895"), Decimal("0.9923")),
    "RO": Fatores(Decimal("29.5"), Decimal("0.9895"), Decimal("0.9923")),
    "RR": Fatores(Decimal("30.5"), Decimal("0.9884"), Decimal("0.9914")),
    "RS": Fatores(Decimal("21.0"), Decimal("0.9989"), Decimal("0.9992")),
    "SC": Fatores(Decimal("23.5"), Decimal("0.9962"), Decimal("0.9971")),
    "SE": Fatores(Decimal("28.5"), Decimal("0.9906"), Decimal("0.9931")),
    "SP": Fatores(Decimal("23.0"), Decimal("0.9967"), Decimal("0.9976")),
    "TO": Fatores(Decimal("29.0"), Decimal("0.9901"), Decimal("0.9927")),
}

# o que o GLP leva: nada. Ver o topo do módulo
SEM_CORRECAO = Decimal(1)


class FcvDesconhecido(LookupError):
    """Pediram o FCV de uma UF, de um produto ou de um mês que não se sabe."""


def fator(uf: str, produto: str, competencia: str) -> Decimal:
    """O FCV daquela UF e produto na competência.

    `competencia` em "aaaa-mm". Devolve **1 para o GLP**, que é tributado por
    quilo e não tem volume a corrigir — isso é fato, não ausência de dado.

    Levanta `FcvDesconhecido` para UF que não existe, produto fora do regime, ou
    competência anterior à vigência do Ato.
    """
    if produto == GLP:
        return SEM_CORRECAO

    if competencia < DESDE:
        raise FcvDesconhecido(
            f"O FCV de {competencia} não se sabe: o {FUNDAMENTO} vale de {DESDE} "
            f"em diante, e o Ato anterior não foi levantado.")

    fatores = POR_UF.get((uf or "").strip().upper())
    if fatores is None:
        raise FcvDesconhecido(
            f"{uf!r} não é uma unidade federada conhecida. A tabela tem as 27 do "
            f"{FUNDAMENTO}.")

    if produto == DIESEL:
        return fatores.diesel
    if produto == GASOLINA:
        return fatores.gasolina
    raise FcvDesconhecido(
        f"{produto!r} não tem FCV publicado: o Ato traz gasolina A e óleo diesel. "
        f"O GLP é por quilo e não corrige volume.")

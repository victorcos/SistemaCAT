"""Que produto é cada NCM, e qual deles entra na tese do combustível.

É a tabela que o classificador consulta depois de decidir **que** a NCM manda.
Dado, não regra: a cascata (NCM decide; NCM ausente, a descrição decide) mora em
`sped/classificador_de_combustivel.py`.

## Por que a NCM manda aqui, e não a descrição

No crédito outorgado é o contrário — lá *"a descrição manda, a NCM confirma"*,
porque a NCM é declarada pelo emitente e erra. Aqui a NCM ganha por um motivo
medido:

```
OLEO MOTOR DIESEL SAE15     ← NCM 27101932: é LUBRIFICANTE, e a descrição diz DIESEL
```

A subposição é juridicamente precisa — `2710.19.21` é óleo diesel, `2710.19.3` é
óleo lubrificante — e é a descrição que mente. Na empresa G são **R$ 239.828 em
273 linhas** sob `27101932`, que um classificador baseado em "a descrição contém
DIESEL" lançaria como crédito.

## O que está medido

Varredura de 40 EFD ICMS/IPI da empresa G (02/2023 a 03/2026), sobre todas as
compras, filtrando as NCM das posições 2710, 2711, 2207, 3403, 3819 e 3820:

| NCM | linhas | valor | CST vistos | produto |
|---|---|---|---|---|
| `27101921` | 3.741 | R$ 13.343.756 | 61, 60, 90 | **diesel** |
| `27101259` | 483 | R$ 359.600 | 61, 60, 90 | **gasolina** |
| `27101932` | 273 | R$ 239.828 | 60, 500, 90 | lubrificante |
| `38190000` | 25 | R$ 1.614 | 500, 90, 60 | fora (fluido de freio) |
| `22071090` | 23 | R$ 3.466 | **60, 90** | etanol hidratado |
| `27101999` | 16 | R$ 3.192 | 90, 500, 00 | fora (desengripante) |
| `38200000` | 15 | R$ 3.950 | 90, 00, 40 | fora (arrefecimento) |
| `27111910` | 9 | R$ 5.872 | 90, 41 | **GLP** |
| `27102000` | 4 | R$ 629 | 60 | fora (limpa-bico) |
| `27101931` | 3 | R$ 1.605 | 90, 60 | lubrificante |
| `27101992` | 2 | R$ 1.406 | 900 | fora (óleo hidráulico) |
| `27101991` | 1 | R$ 30 | 500 | fora (vaselina) |
| `34031900` | 1 | R$ 40 | 60 | fora (WD-40) |

**Duas confirmações caíram de graça nessa medição.** O diesel aparece com CST
**61, 60 e 90** — as duas eras da tese mais o destacado. E o **etanol não tem
uma linha de CST 61**, só 60 e 90: bate com o art. 3º-B da Lei 7.000/2001, que
pôs no monofásico o etanol *anidro* e só ele.

## Os três conjuntos, e por que não são um

`DA_TESE` são os três do monofásico, que `tab_ad_rem` conhece. `A_CONFERIR` é o
etanol hidratado: ele existe nas compras, segue percentual até hoje, e **se dá
crédito ainda não se decidiu** — ver `DOMINIO_COMBUSTIVEL.md`, §11. `DE_OUTRA_TESE`
é o lubrificante: crédito de ST na aquisição por quem usa como insumo, pela
legislação estadual e não pelo Conv. 26/2023 — R$ ~1 milhão medido, e **não se
mistura no mesmo número**.

Um conjunto só obrigaria quem soma a saber de cabeça qual produto pertence a
qual pedido. Três conjuntos põem isso na tabela.

## A hierarquia de prefixo, e onde ela para

`POR_NCM` tem o que foi medido. `POR_PREFIXO` cobre a vizinhança não medida —
`2710.19.3` é a subposição dos lubrificantes, então `27101933` também é
lubrificante mesmo sem ter aparecido. **O prefixo nunca promove à tese:** ele só
classifica em `lubrificante` e `fora`, porque errar para dentro da tese é pedir
crédito, e errar para fora é deixar linha para o revisor ver.
"""

from __future__ import annotations

# Os nomes dos produtos vêm de onde cada um já morava, e **não se redefinem
# aqui**: dois lugares com o mesmo nome divergem calado. Os três do monofásico
# são do `tab_ad_rem`, que é quem sabe multiplicá-los; o hidratado e o
# lubrificante são do `tab_aliquota_combustivel`, que é quem sabe a alíquota
# percentual deles.
from cat.infraestrutura.sped.tabelas.tab_ad_rem import (  # noqa: F401
    DIESEL,
    GASOLINA,
    GLP,
)
from cat.infraestrutura.sped.tabelas.tab_aliquota_combustivel import (  # noqa: F401
    ETANOL_HIDRATADO,
    LUBRIFICANTE,
)

# Este é novo, e nasce aqui porque é aqui que ele faz falta: o anidro não tem
# NCM próprio nas compras: chega **dentro** da gasolina C.
ETANOL_ANIDRO = "etanol_anidro"

# nem combustível nem lubrificante: fluido de freio, arrefecimento, vaselina,
# desengripante, limpa-bico. Rótulo próprio em vez de vazio, porque "não
# classificado" e "classificado como fora" são estados diferentes
FORA = "fora"

# Os três do regime monofásico — os que `tab_ad_rem` sabe multiplicar.
DA_TESE = frozenset({DIESEL, GASOLINA, GLP})

# Existe nas compras, segue percentual, e se dá crédito não se decidiu.
A_CONFERIR = frozenset({ETANOL_HIDRATADO})

# Crédito de ST na aquisição por quem usa como insumo, pela legislação estadual.
# Tese separada: não se mistura no mesmo número.
DE_OUTRA_TESE = frozenset({LUBRIFICANTE})

# **Só o que foi medido em arquivo real.** A contagem e o valor de cada um estão
# na tabela do topo do módulo.
POR_NCM: dict[str, str] = {
    "27101921": DIESEL,            # óleo diesel B — 3.741 linhas
    "27101259": GASOLINA,          # gasolina C — 483 linhas
    "27111910": GLP,               # GLP — 9 linhas
    "22071090": ETANOL_HIDRATADO,  # etanol comum — 23 linhas, nenhuma de CST 61
    "27101931": LUBRIFICANTE,      # óleo de motor 2T — 3 linhas
    "27101932": LUBRIFICANTE,      # óleo de motor — 273 linhas, R$ 239.828
    "27101991": FORA,              # vaselina
    "27101992": FORA,              # óleo hidráulico
    "27101999": FORA,              # desengripante
    "27102000": FORA,              # limpa-bico
    "34031900": FORA,              # WD-40
    "38190000": FORA,              # fluido de freio
    "38200000": FORA,              # fluido de arrefecimento
}

# A vizinhança não medida, por subposição. **Nunca promove à tese** — ver o topo.
# Em ordem decrescente de especificidade, que é a ordem em que se procura.
POR_PREFIXO: tuple[tuple[str, str], ...] = (
    ("2710193", LUBRIFICANTE),  # óleos lubrificantes
    ("2710199", FORA),          # outros óleos da posição
    ("3403", FORA),             # preparações lubrificantes
    ("3819", FORA),             # fluidos para freio
    ("3820", FORA),             # anticongelantes
)

# O etanol anidro não tem NCM próprio nas compras medidas: ele chega **dentro**
# da gasolina C, e é por isso que o Conv. 15/2023 lhes dá a mesma ad rem. Fica
# nomeado aqui porque a apuração precisa do nome, não porque se classifique por
# NCM.
SEM_NCM_PROPRIO = frozenset({ETANOL_ANIDRO})


# As posições da NCM em que combustível, lubrificante e congêneres podem estar.
# Fora delas a resposta é categórica: parafuso é capítulo 73, pneu é 40, e
# nenhum dos dois é combustível em nenhuma circunstância.
#
# Serve para **não encher a fila de revisão**: sem isto, as 10.066 linhas de
# compra comum da empresa G caíam em "não sei, revisar" — e fila de revisão com
# dez mil parafusos não é fila.
POSICOES_DE_INTERESSE = ("2710", "2711", "2207", "3403", "3819", "3820")


def fora_das_posicoes(ncm: str) -> bool:
    """Se a NCM é de posição que não pode ser combustível nem lubrificante.

    Exige NCM de oito dígitos: NCM curta ou torta é **desconhecida**, não
    descartada, porque a descrição ainda pode salvá-la — foi assim que as 86
    linhas de `DIESEL S10` sem NCM entraram.
    """
    limpo = (ncm or "").strip()
    return (len(limpo) == 8 and limpo.isdigit()
            and not limpo.startswith(POSICOES_DE_INTERESSE))


def produto_de(ncm: str) -> str:
    """O produto daquela NCM, ou vazio quando a tabela não sabe.

    Vazio, e não `FORA`: "a tabela não conhece esta NCM" e "esta NCM está fora
    da tese" são fatos diferentes, e tratá-los igual faria o classificador parar
    de consultar a descrição justamente onde ela é a única fonte — nas 86
    descrições de NCM vazio da empresa G, que incluem `DIESEL S10` em 86 linhas.
    """
    limpo = (ncm or "").strip()
    if not limpo:
        return ""
    if (exato := POR_NCM.get(limpo)) is not None:
        return exato
    for prefixo, produto in POR_PREFIXO:
        if limpo.startswith(prefixo):
            return produto
    return ""


def entra_na_tese(produto: str) -> bool:
    """Se o produto gera o crédito que este módulo apura.

    `False` para o lubrificante **e** para o etanol hidratado: o primeiro é
    outra tese, o segundo é dúvida aberta. Os dois aparecem no relatório, fora
    do total — mesmo tratamento da competência prescrita.
    """
    return produto in DA_TESE

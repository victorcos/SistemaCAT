"""Redução de base de cálculo que vem da entrada e alcança o ICMS efetivo da
saída a consumidor final (enquadramento 1). Puro, sem I/O.

## Por que existe

O valor de confronto do enquadramento 1 é o ICMS efetivo da saída: o imposto
que a operação teria se fosse tributada. Quando a mercadoria goza de redução de
base de cálculo, esse imposto **não** é o valor cheio vezes a alíquota interna —
é a alíquota sobre a base já reduzida. Ignorar isso infla o complemento, porque
o efetivo fica maior do que o imposto que a operação de fato comportaria.

Quem diz que há redução é a **entrada**: o fornecedor emite com CST 20 (redução
de base) ou 70 (redução de base com ST) e informa a base que usou.

## O que a Advertising mostrou (agosto/2022 a junho/2024)

Um único fornecedor, 139 notas, 210 itens, 100% consistentes:

| NCM | Alíquota | `pRedBC` declarado | Base que ele usou | Carga |
|---|---|---|---|---|
| 3305.90.00, 3304.99.90 | 25% | 48,00 | 48% do valor | 12% |
| 3401.20.10, 3307.20.10, 3307.20.90 | 18% | 66,67 | 66,67% do valor | 12% |
| 3006.70.00 (CST 10) | 18% | — | sem redução | 18% |

O `pRedBC` está **preenchido ao contrário**: o fornecedor põe ali o percentual
da base que sobra, não o da redução. Lido ao pé da letra daria 13% no grupo de
25% e 6% no de 18% — dois números diferentes para o mesmo benefício, e nenhum
deles bate com o `vICMS` da própria nota. Foi o que a RVZ fez no trabalho de
referência.

Por isso este módulo **não lê `pRedBC`**: calcula a redução pela base que a
nota de fato usou, `1 - vBC / (vProd - vDesc)`, que reproduz o `vICMS` da nota
ao centavo e dá a mesma carga de 12% nos dois grupos (decisão do Victor,
17/09/2026).

## O que a entrada decide, e o que a lei decide

A entrada diz **se a mercadoria tem o benefício**; quanto ele vale é a lei que
diz. O artigo 34 do Anexo II do RICMS/SP reduz a base de modo que a carga
resulte em **12%** — e é essa a redução que a saída aplica, não a que o
fornecedor mediu (decisão do Victor, 18/09/2026).

A diferença é pequena e teimosa: na nota 51462 o fornecedor usou base de
48,84% do valor e recolheu 12,21%, não 12,00%; em outras usou 48% e recolheu
12,00%. Levar essa variação para a nossa saída seria herdar o arredondamento
do sistema dele. Com a carga fixa, a redução vira `1 - 12 / alíquota`: 52% no
que é tributado a 25%, 33,33% no que é tributado a 18%.

**Fica pendente** a janela do Decreto 65.255/2020, que elevou essa carga a
13,3% de 15/01/2021 a 14/01/2023 — o fornecedor da Advertising faturou a 12%
mesmo dentro dela, e o sistema não trata o redutor por período.

## Onde se aplica

Só no **enquadramento 1**, por decisão do Victor. O 3 (isenção ou não
incidência) segue com a alíquota cheia, e o 2 e o 4 confrontam com o ICMS
próprio da entrada, onde a redução já vem embutida no `vICMS` que a nota traz.
"""

from __future__ import annotations

from decimal import Decimal

# CST em que o fornecedor declara base reduzida: 20 é redução pura, 70 é
# redução com retenção por substituição.
CST_COM_REDUCAO = frozenset({"20", "70"})

_CEM = Decimal(100)
_Q4 = Decimal("0.0001")

# a carga que o benefício do artigo 34 do Anexo II do RICMS/SP deixa na
# operação interna. Não é a alíquota: é o que sobra depois da redução da base
CARGA_DO_BENEFICIO = Decimal("12")


def reducao_da_entrada(cst: str | None, base: Decimal | None, valor: Decimal | None,
                       desconto: Decimal | None = None) -> Decimal | None:
    """Percentual de redução (0 a 100) que a entrada aplicou, ou None.

    Calculado pela base que a nota usou, não pelo `pRedBC` declarado — ver o
    cabeçalho do módulo. Devolve None quando o CST não admite redução, quando
    falta base ou valor, e quando a conta cai fora de 0 a 100 (base maior que o
    valor, valor zerado, item de bonificação): nesses casos a saída fica com a
    alíquota cheia, em vez de herdar um número que não se sustenta.
    """
    if (cst or "")[-2:] not in CST_COM_REDUCAO:
        return None
    if base is None or valor is None:
        return None
    cheio = Decimal(valor) - Decimal(desconto or 0)
    if cheio <= 0 or Decimal(base) <= 0:
        return None
    reduzida = (Decimal(1) - Decimal(base) / cheio) * _CEM
    if reduzida <= 0 or reduzida >= _CEM:
        return None
    return reduzida.quantize(_Q4)


def reducao_da_carga(aliquota: Decimal, carga: Decimal = CARGA_DO_BENEFICIO) -> Decimal | None:
    """A redução de base que faz a alíquota resultar na carga do benefício.

    25% com carga de 12% dá 52% de redução; 18%, 33,33%. Devolve None quando a
    alíquota não passa da carga — aí não há o que reduzir, e inventar uma
    redução negativa seria majorar imposto por conta própria.
    """
    if aliquota <= carga:
        return None
    return ((Decimal(1) - Decimal(carga) / Decimal(aliquota)) * _CEM).quantize(_Q4)


def base_reduzida(valor: Decimal, reducao: Decimal | None) -> Decimal:
    """O valor da saída depois da redução herdada da entrada."""
    if not reducao:
        return Decimal(valor)
    return Decimal(valor) * (_CEM - Decimal(reducao)) / _CEM


def icms_efetivo(valor: Decimal, aliquota: Decimal, reducao: Decimal | None = None) -> Decimal:
    """Alíquota interna sobre a base já reduzida — o valor de confronto do
    enquadramento 1."""
    return base_reduzida(valor, reducao) * Decimal(aliquota) / _CEM

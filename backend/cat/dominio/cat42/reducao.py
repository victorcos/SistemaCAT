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


def base_reduzida(valor: Decimal, reducao: Decimal | None) -> Decimal:
    """O valor da saída depois da redução herdada da entrada."""
    if not reducao:
        return Decimal(valor)
    return Decimal(valor) * (_CEM - Decimal(reducao)) / _CEM


def icms_efetivo(valor: Decimal, aliquota: Decimal, reducao: Decimal | None = None) -> Decimal:
    """Alíquota interna sobre a base já reduzida — o valor de confronto do
    enquadramento 1."""
    return base_reduzida(valor, reducao) * Decimal(aliquota) / _CEM

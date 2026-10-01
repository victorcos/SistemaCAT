"""A tese das próprias contribuições fora da base, **item a item** — o 680.

A quarta tese da família a ganhar detalhe por item, e a única que tem **duas
frentes**:

* **o consolidado** (`exclusoes/piscofins_na_propria_base.py`, rodado por
  `exclusoes.apurar`) soma por grupo e arredonda uma vez por grupo, com a
  alíquota efetiva daquele grupo. É o número que se pede;
* **este**, nas 35 colunas do relatório 680 do MA, uma linha por item. É o
  detalhe que acompanha o pedido e permite conferir linha a linha contra o
  relatório do escritório anterior.

A soma dos dois difere, e **é de propósito**: 0,06% na DMINAS, cerca de R$ 1,6
mil em R$ 2,7 milhões. Ver a decisão de 24/09/2026 e o topo de
`sped/exclusao_piscofins_na_base.py`.

## Por que este não entra no parquet agregado das exclusões

As outras três teses por item são as **únicas** frentes das suas teses, e por
isso entram em `exclusoes.parquet` ao lado da tese da receita. Esta não: a tese
da receita **já está lá**, consolidada. Gravar as duas no mesmo arquivo daria a
quem o somasse um total com a tese 1 contada duas vezes — e quem soma um parquet
de teses não tem como saber que duas delas são a mesma.

O detalhe vive no seu próprio parquet, que é o que a planilha do 680 lê.

## A mecânica

É a de `exclusoes_por_item.py`, compartilhada com o 903, o 839 e o 933. O que é
desta tese mora no motor; aqui só se diz **qual** motor e **em que arquivo**.

O grupo desta tese não fixa o registro: as linhas saem de quatro ramos —
`C100/C170`, `C100/C175`, `A100/A170` e `F100` —, e é a linha que diz de qual.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from cat.infraestrutura.analitico.exclusoes_por_item import (
    Andamento,
    Motor,
    Resumo,
    serializar,
)
from cat.infraestrutura.analitico.exclusoes_por_item import apurar as _apurar
from cat.infraestrutura.sped.exclusao_piscofins_na_base import (
    colunas_da_exclusao_piscofins,
    exclusoes_do_piscofins,
)

ARQUIVO_DA_EXCLUSAO_PISCOFINS = "exclusao_piscofins_na_base.parquet"

# o nome da frente por item. **Não é o mesmo** da tese consolidada
# (`exclusoes.TESE_PISCOFINS_NA_BASE`) de propósito: são duas frentes do mesmo
# pedido, com arredondamentos diferentes, e confundi-las soma a tese duas vezes
TESE_PISCOFINS_POR_ITEM = "piscofins_na_propria_base_por_item"

__all__ = ["ARQUIVO_DA_EXCLUSAO_PISCOFINS", "TESE_PISCOFINS_POR_ITEM", "apurar",
           "serializar"]


def apurar(contribuicoes: list[str], destino: str, ate: str = "",
           avisar: Callable[[Andamento], None] | None = None,
           deve_parar: Callable[[], bool] | None = None,
           referencia: date | None = None,
           mensal: dict[str, Decimal] | None = None) -> Resumo:
    """Escreve o 680 em parquet e devolve o resumo.

    `mensal` é a série da Selic, que vem do banco pela camada de cima: as quatro
    teses corrigem pelo mesmo número ou não corrigem nenhuma.
    """
    motor = Motor(
        nome="piscofins_por_item", tese=TESE_PISCOFINS_POR_ITEM,
        arquivo=ARQUIVO_DA_EXCLUSAO_PISCOFINS,
        colunas=colunas_da_exclusao_piscofins,
        ler=lambda caminho, codificacao, mes: exclusoes_do_piscofins(
            caminho, codificacao, mes, mensal=mensal),
    )
    return _apurar(motor, contribuicoes, destino, ate, avisar, deve_parar, referencia)

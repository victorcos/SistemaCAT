"""A contingência das notas não escrituradas: a multa do art. 527 do RICMS/SP.

Nota não escriturada não entra na ficha (decisão do Victor, 16/09/2026). Mas
ela não some: o fisco que pegar a nota fora da EFD cobra multa, e o cliente
precisa saber quanto, para decidir se retifica antes. A RVZ calculou isso na
Advertising, e é o que se reproduz aqui, com uma diferença:

* **sem SELIC.** A CAT 42 não se atualiza pela SELIC (orientação dos colegas do
  Victor). A multa é sobre o valor do documento, como está.

A infração é a do art. 215 do RICMS/SP (Decreto 45.490/00). As multas:

* **entrada** — art. 527, V, "a": 10% do valor da operação constante no
  documento, item a item (o valor do produto no XML);
* **saída** — art. 527, I, "b": 75% do valor do imposto, quando o documento foi
  emitido e não escriturado. O imposto é o ICMS destacado no XML: a RVZ aplicou
  18% sobre o valor, mas o XML vence, e saída de mercadoria com ST já retida
  não tem imposto próprio a pagar.

A operação é a do estabelecimento, não a de quem emitiu: nota emitida por ele
com `tpNF` 1 é saída e com `tpNF` 0 é entrada; nota recebida é o contrário.
"""

from __future__ import annotations

from decimal import Decimal

PERCENTUAL_ENTRADA = Decimal("10")
PERCENTUAL_SAIDA = Decimal("75")

FUNDAMENTO_ENTRADA = "RICMS/SP art. 527, V, a: 10% do valor da operação"
FUNDAMENTO_SAIDA = "RICMS/SP art. 527, I, b: 75% do ICMS"

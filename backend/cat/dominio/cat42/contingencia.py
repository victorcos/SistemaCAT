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
  emitido e não escriturado.

**A base é a do XML** (decisão do Victor, 17/09/2026): o valor do item na
entrada, o ICMS destacado na saída. Quando o XML não traz a base — a saída de
CST 60 sem ICMS destacado, a entrada de valor zero —, vale a **nota mais
próxima** do mesmo produto no mesmo estabelecimento e operação, anterior ou
posterior, que traga — devolução não serve, porque carrega o valor da operação
de origem: dela se tira o valor por unidade, que multiplica a quantidade da
nota apurada. No empate de datas, a anterior. Sem nota nenhuma do
produto com a base, o item fica com base zero e é contado. A RVZ, em vez disso,
aplicou 18% sobre o valor das saídas.

A operação é a do estabelecimento, não a de quem emitiu: nota emitida por ele
com `tpNF` 1 é saída e com `tpNF` 0 é entrada; nota recebida é o contrário.
"""

from __future__ import annotations

from decimal import Decimal

PERCENTUAL_ENTRADA = Decimal("10")
PERCENTUAL_SAIDA = Decimal("75")

FUNDAMENTO_ENTRADA = "RICMS/SP art. 527, V, a: 10% do valor da operação"
FUNDAMENTO_SAIDA = "RICMS/SP art. 527, I, b: 75% do ICMS"

# de onde veio a base da multa de cada item
BASE_DO_XML = "xml"
BASE_DA_NOTA_ANTERIOR = "nota anterior"
BASE_DA_NOTA_POSTERIOR = "nota posterior"
SEM_REFERENCIA = "sem referência"

"""A alíquota de ICMS por produto, guardada por estabelecimento.

A metade **cadastro** da alíquota que o ICMS-ST presumido usa — a metade
**regra** é lei e mora em `sped/tabelas/tab_aliquota_icms.py`.

Fica no banco, e não no repositório, porque código de item é do ERP do cliente:
versioná-lo seria publicar a carteira de produtos de quem nos contratou. E fica
por estabelecimento, e não por empresa, porque a mesma mercadoria pode ter
tratamento diferente em filiais de estados diferentes.
"""

from cat.infraestrutura.aliquotas.repositorio import excecoes_de, gravar

__all__ = ["excecoes_de", "gravar"]

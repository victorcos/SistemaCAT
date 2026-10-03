"""Tabelas auxiliares do SPED: CFOP, natureza do crédito, município, tipo de item.

São dado, não regra — por isso vivem separadas do código que as consulta. Vieram
do projeto Quebra de SPED (22/09/2026) e trazem, entrada a entrada, a marca do que
foi confirmado contra arquivo de cliente e do que ainda é o texto do Guia Prático.

As **empresas A, B e C** são as três cujos relatórios de referência serviram
de gabarito no projeto de origem.

As notas de procedência falam em **empresa A**, **empresa D**, **empresa F** e
assim por diante. Nenhum nome de cliente é versionado — nem aqui, nem em lugar
nenhum do repositório —, e nem o CNPJ: os dois identificam o cliente igual, e
anonimizar só um não anonimiza nada. O registro que decodifica as tags vive em
`docs/REGISTRO_EMPRESAS.local.md`, que está no `.gitignore`.

As letras **E**, **I** e **O** não são usadas: "empresa e" se confunde com a
conjunção num `grep`, e **I** e **O** se confundem com 1 e 0.

O que dá peso à nota é quantas linhas foram conferidas, de que competência e
contra qual relatório — e isso está escrito.
"""

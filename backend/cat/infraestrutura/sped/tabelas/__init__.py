"""Tabelas auxiliares do SPED: CFOP, natureza do crédito, município, tipo de item.

São dado, não regra — por isso vivem separadas do código que as consulta. Vieram
do projeto Quebra de SPED (22/09/2026) e trazem, entrada a entrada, a marca do que
foi confirmado contra arquivo de cliente e do que ainda é o texto do Guia Prático.

As **empresas 01, 02 e 03** são as três cujos relatórios de referência serviram
de gabarito no projeto de origem.

As notas de procedência falam em **empresa 01**, **empresa 04**, **empresa 05** e
assim por diante. Nenhum nome de cliente é versionado — nem aqui, nem em lugar
nenhum do repositório —, e nem o CNPJ: os dois identificam o cliente igual, e
anonimizar só um não anonimiza nada. O registro que decodifica as tags vive em
`docs/REGISTRO_EMPRESAS.local.md`, que está no `.gitignore`.

**Eram letras até 05/10/2026, e número é melhor por duas razões.** A sequência
de letras tinha de pular **E**, **I** e **O** — "empresa e" se confundia com a
conjunção num `grep`, e I e O com 1 e 0 — e, com 21 das 23 aproveitáveis já em
uso, o próximo cliente não teria etiqueta. Número não pula nada e não acaba.

A numeração segue a ordem em que as etiquetas foram atribuídas, que era a de
frequência no repositório. Não é ordenação de nada: é identidade, e trocá-la
depois faria quem já leu a doc reaprender tudo por nada.

O que dá peso à nota é quantas linhas foram conferidas, de que competência e
contra qual relatório — e isso está escrito.
"""

"""Gestão Fiscal no padrão do Sistema MA, para PIS/Pasep e COFINS.

Monta, a partir da EFD-Contribuições, os **36 quadros** que o MA exporta na
"Gestão": receita por CST, contribuição apurada, natureza dos créditos,
ajustes, controle de saldos — cada quadro uma lista de linhas, cada linha um
valor por competência.

## O caminho

```
EFD-Contribuições ──► agregador ──► ApuracaoEFD ──► quadros ──► Relatorio
     (1 GB)          uma passada     (poucos MB)      regras     36 quadros
```

O `ApuracaoEFD` é o resumo de **um** arquivo: registros de apuração inteiros,
ajustes somados por código e os itens dos blocos A/C/D/F agregados por chave.
Cabe em memória mesmo quando o arquivo não cabe — e é ele, não o arquivo, que
os quadros consomem. Trocar a regra de um quadro não obriga a reler 1 GB.

## Tudo em centavos inteiros

Somar float de milhões de linhas acumula erro, e o MA arredonda o crédito
recalculado **por grupo**: um erro de 1e-9 no lugar errado vira um centavo de
diferença no relatório. Valores em centavos, alíquotas em décimos-milésimos de
ponto percentual. Ver `numeros.py`.

## Procedência

Portado do projeto Quebra de SPED em 22/09/2026. As regras aqui **não foram
deduzidas do Guia Prático** — foram confrontadas com o export real da Gestão do
MA em 59 competências, e o que bateu centavo a centavo está marcado
`# VALIDADO` ou `# CONFIRMADO` linha a linha. Onde eu discordaria, escrevi
comentário em vez de mudar a regra: sem o arquivo de referência eu não teria
como revalidar.

As notas de procedência falam em **empresa A, B e C**. O nome delas não é
versionado; o que dá peso à nota é quantas competências foram conferidas.
"""

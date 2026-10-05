"""Gestão Fiscal no padrão do Sistema MA: PIS/COFINS da EFD, IRPJ/CSLL da ECF.

Monta os mesmos relatórios que o MA exporta na "Gestão" — cada um uma lista de
quadros, cada quadro uma lista de linhas, cada linha um valor por competência.

Duas fontes, quatro relatórios:

* **EFD-Contribuições** → PIS/Pasep e COFINS, nos **36 quadros**: receita por
  CST, contribuição apurada, natureza dos créditos, ajustes, controle de saldos;
* **ECF** → IRPJ e CSLL do Lucro Real: Parte A do e-Lalur e do e-Lacs, cálculo
  do imposto e saldo das contas da Parte B.

## O caminho

```
EFD-Contribuições ──► agregador ──► ApuracaoEFD ──► quadros ──► Relatorio
     (1 GB)          uma passada     (poucos MB)      regras     36 quadros

ECF  ──► ecf.py ──► ApuracaoECF ──► quadros_irpj_csll ──► Relatorio
 (MB)   uma passada   por período        regras          IRPJ e CSLL
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

**Isso vale para PIS e COFINS.** IRPJ e CSLL não passaram por gabarito nenhum —
o arquivo de referência é de outra empresa e a comparação ficou pendente também
no projeto de origem. `tools/validar_gestao.py` já aceita os dois, e há uma
suspeita anotada esperando essa rodada (`quadros_irpj_csll.py::_compensacoes`).

As notas de procedência falam em **empresa 01, 02 e 03**. Nenhum nome de cliente
é versionado, e nem o CNPJ — ver `tabelas/__init__.py` e o registro em
`docs/REGISTRO_EMPRESAS.local.md`, fora do repositório. O que dá peso à nota é
quantas competências foram conferidas.
"""

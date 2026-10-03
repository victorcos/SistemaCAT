# DOMÍNIO — Crédito de ICMS sobre combustível

> Levantamento de 01 e 02/10/2026, antes de uma linha de código. O que está
> marcado como **medido** foi contado em arquivo de cliente; o resto é lei,
> jurisprudência ou dúvida registrada como dúvida.

---

## 1. A tese, e por que ela são duas

Quem **consome** combustível fora da cadeia de revenda — transportadora,
indústria, frota própria — pagou ICMS embutido no preço e tem direito a creditá-lo
quando o combustível é insumo da sua atividade. O que muda é **como** esse imposto
foi cobrado, e isso mudou no meio do período recuperável:

| | até | a partir de | base |
|---|---|---|---|
| Diesel B, B100, GLP, GLGN | 30/04/2023 | **01/05/2023** | Convênio ICMS 199/2022 |
| Gasolina C, etanol anidro | 31/05/2023 | **01/06/2023** | Convênio ICMS 15/2023 |

**A virada é por produto, não por data única.** Um motor com um único corte erra
o mês de maio/2023 na gasolina. A chave de regime é `(produto, competência)`.

### Regime ST — até a virada

```
crédito = C170_VL_ITEM × alíquota interna do produto na UF
```

**Medido** no papel de trabalho da empresa H (projeto encerrado, ES, 2021-2022,
2.650 linhas): GLP 17%, diesel 12%, gasolina 27% — e 25% em algumas linhas, que é
uma vigência anterior. Total de R$ 792.861,06 em 20 competências.

Note que a alíquota é **do produto**, não a interna geral do estado.

### Regime monofásico — depois da virada

```
crédito = litros × alíquota ad rem × FCV
```

Confirmado pela SEFAZ-SP em [RC 28013/2023] e [RC 28237/2023], com o exemplo do
próprio fisco: `R$ 0,9456 × 20 L × 0,9976 = R$ 18,87`.

---

## 2. Quem pode creditar

[Convênio ICMS 26/2023], publicado em 14/04/2023 e alterado pelo **Convênio ICMS
61/2023**, reconhece o direito ao crédito nas aquisições de **Gasolina C, Óleo
Diesel B, GLP e GLGN** usados como insumo.

**Veda a quatro grupos:** os contribuintes da cláusula terceira do Conv. 199/22
(refinaria, produtor, importador), os importadores de combustível, as
**distribuidoras** e os **TRR**. Quem está na cadeia não credita; quem consome,
credita.

**Mas quem concede é o estado.** O convênio é autorizativo. O ES internalizou no
**RICMS/ES art. 264-G**, que o Decreto 6.183-R/2025 moveu para o **art. 269-Q**.
Cada UF tem seu artigo e sua data — é tabela de base legal por estado, como os
códigos de enquadramento da CAT 42.

Em SP há duas vedações extras ([RC 28237/2023]):

* **prestação iniciada em outro estado não dá crédito em SP**;
* quem optou pelo **crédito outorgado** do art. 11 do Anexo III do RICMS/SP não
  credita o diesel. (Atenção: é o outorgado **do transporte**, não o mesmo do
  módulo `credito_outorgado.py`, que é lista de mercadorias.)

---

## 3. As duas tabelas, e as duas camadas de regra

São **dois relógios diferentes**, e misturá-los apodrece o módulo:

* a **classificação** muda quando entra cliente novo — alguém escreve
  `OD B S-10 ORIGINAL(BOMBA:27 BICO:27)`;
* a **tributação** muda quando sai convênio — ~20 alterações da ad rem em 3 anos.

Se a ad rem morar dentro do classificador, cada convênio obriga a mexer nele — e
o dia em que se mexe, a conferência de 100% que ele tinha morre.

### Camada 2: a tributação, datada

Molde: `tab_aliquota_icms`, com `Vigencia`, `INTERNA` (só o medido), `A_CONFERIR`
(o suspeito) e um `AliquotaDesconhecida` que **o motor recusa**.

```
(produto, uf, competência)  →  regime, fator, unidade tributada, base legal, fonte
```

* **regime ST**: fator = alíquota interna do produto na UF;
* **regime monofásico**: fator = ad rem × FCV(uf, produto, ano).

**A cadeia de vigências da ad rem**, pela fonte do papel de trabalho (melhor que
notícia): Conv. 199/2022 em 01/05/2023 → **Conv. 172/2023** de 01/02/2024 a
31/01/2025 → **Conv. 126/2024 e 127/2024** a partir de 02/2025. A cláusula sétima
foi alterada por 10/23, 12/23, 19/23, 24/23, 64/23, 65/23, 74/23, 85/23, 112/23,
172/23, 186/23, 126/24, 149/24, 172/24, 12/25, 76/25, 113/25, 165/25, 39/26,
67/26. **É cadastro vivo, não constante.**

**O FCV varia por UF _e por produto_**: em SP, 0,9976 para diesel e **0,9967 para
gasolina** (Ato COTEPE 64/2019). Publicado anualmente, da densidade da ANP com a
temperatura média do INMET e a conversão da Resolução CNP 06/70.

A `base legal` entra **na linha da planilha**: o gabarito da empresa H tem uma aba
"BASE LEGAL" porque o cliente pergunta "por que esse número?".


### A alíquota do ST: `tab_aliquota_combustivel`

Feita em 03/10/2026, lendo o **texto consolidado da Lei 7.000/2001** do Espírito
Santo — 175 páginas, com o histórico de redações de cada inciso. O consolidado é
o que importa: um resumo não distingue inciso vigente de inciso que nunca valeu.

| Produto | ES | Fundamento | Até |
|---|---|---|---|
| Óleo diesel / B-100 | **12%** | art. 20, II, "k" (Lei 8.098/05; Lei 9.937/12) | 04/2023 |
| Gasolina | **27%** | art. 20, VI, "a" (Lei 8.237/05, de 1º/01/2006) | 05/2023 |
| Álcool de todos os tipos | **27%** | art. 20, VI, "b" (de 29/03/2006) | segue |
| GLP | **não conferido** | não é nomeado em nenhum inciso do art. 20 | 04/2023 |

**A tabela acaba onde a `tab_ad_rem` começa**, e por produto, não por data: o
art. 3º-B da mesma lei pôs diesel e GLP no monofásico em **1º/05/2023** e
gasolina e etanol anidro em **1º/06/2023**. Pedir percentual de uma competência
do monofásico levanta `ForaDoRegimePercentual`, que é erro **separado** de
`AliquotaDeCombustivelDesconhecida`: não é dado que falta, é pergunta errada.
Quem trata os dois como a mesma coisa completa com a interna do estado uma conta
que devia ser `litros × ad rem × FCV`.

**Nenhum dos três combustíveis segue a interna geral do ES, que é 17%.** Usar a
geral na gasolina credita 37% menos do que a lei manda. É a razão de esta tabela
existir separada de `tab_aliquota_icms`: lá o eixo é a UF, aqui são UF **e**
produto, e o produto manda mais.

**Os 30% da gasolina não existem, e o engano está registrado.** Uma busca na
internet devolve 30% para a gasolina do ES, e o número está de fato na lei: a
Lei 8.098, de 27/09/2005, incluiu o inciso VI com 30%. Ele **nunca produziu
efeitos** — a Lei 8.237, de 28/12/2005, deu nova redação ao mesmo inciso antes da
entrada em vigor. O valor ficou em `REFUTADO`, com o motivo, para que a próxima
pessoa que o encontrar reconheça o que encontrou. Sobre R$ 10 milhões de base são
R$ 300 mil pedidos com fundamento num inciso que nunca valeu.

**A revogação do diesel que não produziu efeitos.** A Lei 11.768/2022 revogou a
alínea dos 12% em 30/12/2022, e o monofásico só chegou em 05/2023. Tomada ao pé
da letra, a revogação jogaria o diesel na interna de 17% por quatro meses — 42%
de crédito a mais. Mas o **art. 179-I, § único** diz que ela *não produz
efeitos*, invocando o art. 32-A, § 1º, III, da LC 87/96. Os 12% valeram sem
interrupção. Há teste parametrizado nos cinco meses da janela.

### Por que o livro do cliente não confere esta tabela

Em `tab_aliquota_icms` a regra é *ato legal mais medição na escrituração*. **Aqui
a segunda metade não existe, e a razão é a própria tese:** na era do ST o
consumidor recebe CST 60, que não destaca imposto nenhum. Foi essa ausência que
criou a tese; ela também impede que o livro dele sirva de prova.

A prova independente vem do **XML**, não do SPED: `vICMSSTRet ÷ vBCSTRet`, que o
leitor em `dominio/notafiscal/xml.py` já lê (`valor_st_retido`, `bc_st_retido`).
Quando houver XML de compra de combustível de cliente do ES na era do ST, essa
divisão confirma ou derruba os 12% e os 27%.

Até lá o peso vem da lei mais uma concordância independente: o papel de trabalho
da empresa H apurou gasolina a 27% e diesel a 12%. Ele **errou** o FCV, e por isso
não serve de gabarito sozinho — mas acertar a alíquota pelo mesmo número que a
lei, tendo errado outra coisa, é concordância e não cópia.

### São Paulo, que é onde está o volume

Lido no **RICMS/SP (Decreto 45.490/2000), arts. 52 a 56-C**, no sítio da SEFAZ-SP.
Importa mais que o ES por um motivo simples: os quatro clientes com CST 61 são de
São Paulo. O ES tem o gabarito; SP tem o dinheiro.

| Produto | SP | Fundamento | Observação |
|---|---|---|---|
| Óleo diesel | **12%** | art. 54, VI | até 14/01/2021 e de 15/01/2023 |
| Óleo diesel | **13,3%** | art. 54, § 7º | de 15/01/2021 a 14/01/2023 |
| Gasolina / EAC | **25%** | art. 55, XXVI | a era inteira, sem complemento |
| Etanol hidratado | **não conferido** | art. 54, VI + Informativos SFP | |
| GLP | **não conferido** | não é nomeado nos arts. 54 nem 55 | |

**O complemento de alíquota da Lei 17.293/2020 é o achado.** O art. 22 daquela lei
somou **1,3 ponto** às operações do art. 54, e o § 7º diz, com estas palavras,
*"passando as operações internas indicadas no caput a ter uma carga tributária de
13,3%"*. O diesel é o inciso VI e **não** está entre as exceções do parágrafo
(incisos I e XIX). Então dois anos de compras de diesel em SP foram a 13,3%, não
a 12% — e quem apurar a 12% perde **10% do crédito** daquele período.

Veio pelo Decreto 65.253, de 15/10/2020, com a redação do Decreto 65.470, de
14/01/2021, e foi **revogado** pelo Decreto 67.524, de 27/02/2023, com efeitos
retroativos a 15/01/2023.

**E daí nasceram os dois meses partidos.** O complemento começou no **dia 15** de
janeiro de 2021 e acabou no **dia 15** de janeiro de 2023. Nesses dois meses há
duas alíquotas, e a competência não decide qual vale. A tabela ganhou o campo
`dia` na `Vigencia` e um erro próprio, **`MesPartido`**, que recusa a competência
da virada e manda separar as entradas pela data do documento. Escolher um lado
calado erraria 1,3 ponto num mês inteiro de compras de diesel.

São agora **três recusas distintas**, e a distinção é o que protege:

| Erro | Significa | O que fazer |
|---|---|---|
| `ForaDoRegimePercentual` | a era é ad rem | ir para `tab_ad_rem` e `tab_fcv` |
| `MesPartido` | duas alíquotas no mês | separar pela data do documento |
| `AliquotaDeCombustivelDesconhecida` | não se leu | ler o ato e preencher `INTERNA` |

**A gasolina de SP não leva complemento nem adicional.** O complemento é dos
arts. 53-A (7%) e 54 (12%), e o art. 55 não tem parágrafo equivalente — conferido
no texto. E o adicional de 2% do **art. 56-C** tem só dois incisos: bebidas
alcoólicas da posição 2203 e fumo do capítulo 24. Combustível não está lá, e o
adicional só vale em operação destinada a consumidor final.

Isso derruba uma segunda leitura secundária: somar os 2% aos 25% dá **27%**, que
é o que uma leitura resumida do RICMS/SP devolve. Entrou em `REFUTADO` junto com
os 30% do ES. **Os dois enganos são na gasolina, os dois vêm de fonte secundária,
e os dois erram para cima** — e há teste que afirma essa propriedade, não só os
dois casos.

**O que ficou em aberto em SP.** O etanol hidratado divide o inciso VI com o
diesel, mas o RICMS traz **dois Informativos SFP só para ele** — um "aplicável de
15/07/2022 a 30/06/2023" e outro "aplicável a partir de 1º/07/2023". Isso indica
regime próprio nessas janelas, e enquanto ninguém ler os dois (DOE 18/07/2022 e
DOE 30/06/2023) o motor recusa EHC em SP. O GLP, como no ES, não é nomeado: cai
na geral do art. 52, I por resíduo, e antes de usar há que procurar redução de
base no Anexo II do RICMS/SP, que é por onde SP costuma tratar o botijão.


---

## 4. Os arquivos: EFD ICMS/IPI, por (CNPJ, competência)

**A fonte é a EFD ICMS/IPI.** É lá que estão o `C170` com CST 60/61/90, `QTD` e
`UNID`; o `0200` com NCM e descrição; o `0150` do fornecedor; e — decisivo — o
**`E111`**, que é como se descobre o crédito que o cliente **já tomou**. Sem o
E111 não há auditoria, só estimativa. Contribuições, ECD e ECF não entram.

**A de-duplicação é por `(CNPJ, competência)`, não por competência.** Medido:

```
Empresa G      411 EFD ICMS/IPI   4 estabelecimentos   62 competências
  por competência só:        até 10 arquivos (9 em 34 competências)
  por (CNPJ, competência):   1 em 48 · 2 em 93 · 4 em 58 · 7 em 1

Empresa F      201 EFD ICMS/IPI   4 estabelecimentos   58 competências
  por (CNPJ, competência):   1 em 144 · 2 em 57
```

> **Armadilha do código existente — corrigida em 03/10/2026 (v0.137.0).** O
> `selecionar_por_competencia` chaveava **só por competência**, e na empresa G
> isso guardaria 62 arquivos de 411, perdendo três estabelecimentos inteiros.
> Não quebrava nada porque seus dois usuários leem **EFD-Contribuições**, que a
> matriz entrega consolidada; a ICMS/IPI é por estabelecimento, e o combustível
> é o primeiro a usá-la.
>
> A chave agora é `(CNPJ, competência)` e a função chama-se
> `selecionar_por_cnpj_e_competencia`. **O que fazia o defeito ser invisível era
> o aviso:** ele dizia "dois arquivos para a mesma competência; usado X,
> ignorado Y", o que parece correto a quem lê. Duas filiais agora não geram
> aviso nenhum, porque não são conflito.

Dentro de cada par ainda há retificadora. A regra existente resolve: retificadora
vence, depois a mais nova.

**Lê-se tudo e marca-se o vencido**, em vez de filtrar os cinco anos na entrada —
competência que venceu precisa aparecer, como já se faz com a prescrita.

---

## 5. As duas fases: estimar pela EFD, conferir pelo XML

**Fase 1 — estimativa, pela EFD.** `litros × ad rem × FCV`, com a ad rem da nossa
tabela.

**O limite honesto, que precisa estar escrito no número que vai ao cliente:** a
estimativa **assume que o fornecedor cobrou o que a lei manda**. A EFD não traz o
que foi efetivamente cobrado — o `VL_ICMS` vai **zero** no CST 61 por
determinação da Nota Orientativa 01/2023, e o `ALIQ_ICMS` vem truncado em duas
casas (`0,95` contra `0,9456`) e **zerado em 3.918 das 6.678 linhas** medidas.

**Fase 2 — a verdade, pelo XML.** O grupo N08a traz `vICMSMonoRet`: o valor que o
vendedor declarou ter sido cobrado antes. Estado do leitor da casa
(`dominio/notafiscal/xml.py`):

| período | o que o XML dá | estado |
|---|---|---|
| até 04-05/2023 (ST) | `vICMSSTRet`, `vICMSSubstituto`, `vICMSEfet` | **o leitor já tem os campos** |
| de 05-06/2023 (monofásico) | `vICMSMonoRet`, `adRemICMSRet`, `qBCMonoRet` | falta o grupo `ICMS61` |

Cada linha carrega a **fonte do valor**: `efd` (estimado) ou `xml` (conferido) —
mesmo padrão do `fonte` da `aliquota_de_item`. Com isso as duas fases convivem no
mesmo relatório e a diferença fica explicável linha a linha, em vez de o número
mudar entre uma apresentação e outra.

---

## 6. O produto não é achar crédito: é auditar o crédito tomado

**Medido na empresa G**, e foi a descoberta que reverteu o módulo:

```
E111  SP020799   111 lançamentos   32 competências   "CRÉDITO DE DIESEL MONOFASICO"
```

**O cliente já aplica a tese.** Não há crédito virgem de monofásico ali. Então a
pergunta deixa de ser "quanto há a recuperar" e passa a ser "**o que ele creditou
está certo?**" — com dois lados:

**Ele não aplica o FCV.** Nos meses em que a conta fecha exata, o R$/litro é a ad
rem cheia: `0,9456` em 2024-01, `1,0635` em 2024-02, 2024-05 e 2024-06. Credita
0,24% a mais, sistematicamente. (E isso **valida a nossa tabela de ad rem contra a
escrituração do cliente** — o método exigido para a alíquota interna.)

**A maioria dos meses está curta**, e aí está a oportunidade:

| competência | R$/litro creditado | ad rem da lei | |
|---|---|---|---|
| 2025-09 | 0,2787 | ~1,12 | **−75%** |
| 2026-01 | 0,6060 | ~1,17 | **−48%** |
| 2025-07 | 0,6687 | ~1,12 | −40% |
| 2023-12 | 0,7908 | 0,9456 | −16% |

**E alguns acima**, que são risco e não ativo: 2024-03 a `1,2507` contra `1,0635`
— 18% a mais.

Por isso o relatório tem três colunas por competência, com sinal:

```
devido (litros × ad rem × FCV)  −  creditado (SP020799 + destacado)  =  diferença
```

Positiva é oportunidade; negativa é exposição. Somar as duas num total só
esconderia o que o cliente precisa saber.

**A era do ST segue virgem:** não há `SP020799` antes de 2023-08, e as linhas CST
060 de 2022-01 a 2023-04 não têm destacado.

> **Os números absolutos deste levantamento estão ~3× inflados** porque o censo
> somou todos os arquivos por competência, retificadoras incluídas. As **razões**
> (R$/litro) sobrevivem, porque numerador e denominador inflam junto. É a razão de
> a de-duplicação vir antes de qualquer soma.

---

## 7. O classificador: NCM manda, descrição confirma

Medido na empresa G: **324 descrições distintas**, 16 NCM, e o registro **0206
(código ANP) não aparece em nenhum dos 95 arquivos** — a chave exata não existe
na prática.

| NCM | o que é | linhas | valor | entra? |
|---|---|---|---|---|
| `27101921` | óleo diesel B | 13.870 | R$ 54.020.060 | **sim** |
| `27101259` | gasolina | 2.136 | R$ 3.358.267 | **sim** |
| `27111910` | GLP | 189 | R$ 115.817 | **sim** |
| `22071090`/`22072011` | etanol | 108 | R$ 18.524 | **a conferir** |
| *(NCM vazio)* | gasolina aditivada, diesel S-500 | 6 | R$ 8.009 | **sim** |
| `27101932` e outros 9 | lubrificante, graxa, solvente, querosene | 1.346 | R$ ~1 mi | **não** |

**A regra se inverte em relação ao crédito outorgado.** Lá, *"a descrição manda, a
NCM confirma"*, porque a NCM é declarada pelo emitente e erra. Aqui é o contrário:

```
OLEO MOTOR DIESEL SAE15     ← NCM 27101932: é LUBRIFICANTE, e a descrição diz DIESEL
```

São R$ 965.161,05 que um classificador baseado em "a descrição contém DIESEL"
lançaria como crédito de combustível. A subposição da NCM é juridicamente precisa
(2710.19.21 diesel contra 2710.19.3 lubrificantes); é a descrição que mente.

**Mas a NCM sozinha também falha**, e há prova no mesmo cliente: 6 linhas com
**NCM vazio**, CST 061, CFOP 1653, `GASOLINA ADITIVADA` e `DIESEL S-500`.
Combustível de verdade, sem NCM. Ali só a descrição salva.

### A cascata

```
1. código ANP (0206)         chave exata — nunca apareceu em cliente nenhum ainda
2. NCM presente              DECIDE. Lubrificante sai aqui, mesmo dizendo "diesel"
3. NCM ausente               a descrição decide
4. NCM e descrição discordam fila humana, nunca palpite
```

**Forma, não de-para.** O de-para resolve emparelhar o mesmo produto escriturado
com códigos diferentes; aqui é **rotular** num conjunto fechado de ~7 produtos. A
mecânica que serve é a do reenquadrador — hierarquia de prefixo de NCM, exceção com
escopo, escala de confiança —, cuja extração para uso comum já está decidida
(DECISOES de 09/09/2026) e **ainda não foi feita**: reaproveitar aqui significa
**portar**, não `import`.

Do de-para levam-se duas peças: a **cascata determinística antes do modelo** (com
a regra registrada de que *"sem par" não é fila de IA*) e o conceito de **fator**
da regra de kit.

### A saída é tupla, não rótulo

```
(produto, unidade tributada, fator de conversão, confiança, por quê)
```

Porque dizer "é GLP" não serve: a ad rem do GLP é **por quilo**, o SPED declara
`UN`, e o fator está no texto — `20 KGS GLP ONU 1075 2.1` e `P20 - GLP 20 KGS`,
dois formatos. Unidades medidas no mesmo cliente: `L`, `LT`, `LTS`, `LITRO`, `LI`,
`UN`, `UND`, `PC`, `BD`, `KG`, `GA`, `900M`, `..5L`.

### Por que este classificador pode ser **provado**

324 descrições colapsam para ~uma dúzia depois de normalizar — tirar pontos de
preenchimento, `(BOMBA:x BICO:y)`, marca (`ORIGINAL` é Ipiranga), e colapsar
`S10`/`S 10`/`S-10`. Num universo de 7 produtos, dá para **revisar 100% uma vez** e
a confiança passar a ser **taxa de acerto medida por tipo de regra**, não número
estimado. Nem o reenquadrador (milhares de NCM) nem o de-para (24.730 itens)
puderam fazer isso.

**Não indexe por `COD_ITEM`:** o padrão `(BOMBA:27 BICO:27)` mostra que o posto
gera um código por bico de bomba — foi por isso que deu 135 descrições num NCM só.
A chave é **descrição normalizada + NCM**.

---

## 8. O percentual de confiança são dois, e um deles recusa

**Confiança da classificação** — inferência sobre texto livre. **Nunca recusa**:
emite tudo, ranqueado, com o motivo. O revisor decide.

**Cobertura da regra** — fato sobre a tabela, não probabilidade. A ad rem de maio
de 2024 não é um palpite com 87% de confiança: está num convênio. Imprimir
percentual nela inventa incerteza onde não há e ensina o revisor a desconfiar da
parte que é certa. A gradação é outra: vigência conferida **e** a UF internalizou
o crédito (alta); vigência conferida sem norma da UF localizada (média);
**sem vigência cobrindo a competência → recusa**, com o motivo, e a linha aparece
no relatório fora do total — mesmo tratamento da competência prescrita.

> **O humano decide o que o produto é; a tabela decide quanto ele vale.** Nunca o
> contrário: ninguém deve ser perguntado "qual era a ad rem em maio de 2024?".

---

## 9. Sem SELIC, e o prazo é outro

**Crédito escritural não se corrige**, por falta de previsão legal. A [Súmula 411
do STJ] estabelece a regra pelo avesso: a correção é devida *quando há oposição ao
aproveitamento decorrente de resistência ilegítima do Fisco*. Sem oposição, não há
correção. O STF entende inadmissível a correção de crédito escritural extemporâneo
de ICMS.

Confirmado também pelo gabarito: **o papel de trabalho da empresa H não tem coluna
de correção nenhuma** — `AD REM / ALÍQ`, `CRÉDITO`, `CLASSIFICAÇÃO` e depois SPED
cru. Valor nominal.

A razão de fundo: **não é a mesma natureza das quatro teses de PIS/COFINS**. Lá há
indébito — pagou-se a mais e se pede de volta, com SELIC. Aqui houve **crédito que
o cliente deixou de tomar**, e o remédio é lançá-lo extemporaneamente, a valor
nominal.

**O perigo silencioso.** O art. 23, parágrafo único, da LC 87/96: o direito de
**utilizar** o crédito extingue-se em cinco anos contados da **emissão do
documento**. É prazo para lançar, não para pedir — a linha não muda de valor, ela
**desaparece**, e some sem avisar. Daí três colunas que as teses de PIS/COFINS não
têm:

```
data de emissão do documento
prazo final para aproveitar  (emissão + 5 anos)
competência em que se pode lançar  (a atual, não a original)
```

E o relatório conta quantas linhas **já venceram** — aparece, não soma.

**A exceção, para não surpreender depois:** se o estado glosar, a resistência
ilegítima afasta a natureza escritural e a correção passa a ser devida — mas aí é
via judicial, outro produto, outro número. Por isso cada linha grava a **via**:
escritural (nominal) ou judicial (com correção). Hoje todas saem escriturais.

---

## 10. O que o repo já dá, e o que falta

**De graça:** `dominio/sped/cabecalho.py` já distingue EFD ICMS/IPI de
Contribuições (`TipoSped`) e já mapeia que a ICMS/IPI alimenta o módulo `icms`;
`analitico/exclusoes_por_item.py` dá a casca da rodada (ler em ordem, parquet,
andamento, cancelamento, apagar parquet pela metade); `credito_outorgado.py` tem a
classificação por descrição e NCM; `tab_aliquota_icms` é o molde da tabela com
vigência; `planilhas/conferencia.py` e o pacote para a entrega.

**Já feito desde o levantamento:** as três tabelas de tributação — ad rem
(`tab_ad_rem`), FCV (`tab_fcv`) e alíquota percentual da era do ST
(`tab_aliquota_combustivel`, ES e SP) — e o **leiaute da EFD ICMS/IPI**
(`sped/registros_icms.py`), módulo irmão do `registros.py` porque o `0000` e o
`0200` colidem entre os dois arquivos. 16 registros medidos em 40 EFD reais,
com `tools/medir_leiaute_icms.py` para reconferir em cliente novo.

O **leitor das compras** também está feito (`sped/combustivel.py`, v0.138.0):
uma linha por item de entrada, com documento e cadastro juntos, mais
`itens_do_cadastro` com o `0200` e o `0205` para o classificador. Ele não sabe o
que é combustível — entrega tudo, e quem filtra é quem classifica.

**Dois achados do leitor que mudam o cálculo.** O campo `CST_ICMS` carrega
**origem+CST ou CSOSN**, com cinco códigos ambíguos resolvidos por medição e
marcados como tal; e o **`VL_ICMS` do C170 é esparso** (o CST `000` tem 610
linhas e 24 com valor), então ICMS destacado confiável vem do `C190`, que é
obrigatório.

A **rodada** está feita (`analitico/combustivel.py`, v0.139.0): escolhe um
arquivo por `(CNPJ, competência)` chamando a regra da Gestão em vez de copiá-la,
grava o parquet das compras, conta por `(CNPJ, competência, CST, unidade)` e
apaga parquet pela metade quando alguém cancela. Ela **não** aplica prescrição —
a do ICMS conta cinco anos da emissão, regra diferente da do PIS/COFINS — e em
vez disso devolve a primeira e a última emissão encontradas.

O **classificador** está feito (v0.140.0), em dois módulos: `tab_combustivel`
(que NCM é que produto, medido) e `classificador_de_combustivel` (a cascata).
Medido nas 15.107 compras da empresa G: **10.323 linhas saem por posição de NCM
sem revisão**, 4.233 da tese decididas por NCM medida com confiança alta, e a
**fila de revisão fica em 1,7%**. As 132 descrições do diesel colapsam para 18
formas canônicas.

E o **`0220`** foi medido (20 milhões de linhas da empresa Z, duas larguras) e
entrou no leiaute — é a fonte certa do fator de conversão, com o texto da
descrição como recurso de quem não o tem.

A **apuração** está feita (`sped/credito_de_combustivel.py`, v0.141.0):
`quantidade × ad rem × FCV` no monofásico, `base × alíquota` na era do ST, e o
que a tabela não cobre **vira recusa com o motivo**, não zero. A era do ST sai
marcada `estimativa` porque **a base não está no arquivo** — medido: zero base
de ST em 5.234 linhas de CST 60/61.

Rodada a cadeia inteira em 25 competências da empresa G: devido R$ 1.567.603,81
contra R$ 1.328.691,14 creditados, **R$ 238.912,67 a menos**. E três meses batem
ao centavo com `litros × ad rem`, confirmando a ad rem e revelando que o cliente
não aplica o FCV.

A **rodada já apura** (v0.143.0): classifica e calcula cada linha, grava as três
camadas no parquet e soma em três chaves — compras, crédito e recusas por
motivo. E tem a porta que evita creditar duas vezes: **compra com ICMS destacado
não ganha a ad rem em cima**, porque o documento já deu aquele crédito.

**Falta:** o caso de uso da etapa e a rota (para o botão aparecer); a tela; a
auditoria do `E111` dentro do sistema; a prescrição do ICMS; a tabela de UF que
internalizaram o Conv. 26/2023; a ad rem de 05/2023 a 01/2024; e medir `0206` e
`C171`.

**Atenção ao reúso que não serve:** o `Total.somar` do `exclusoes_por_item` lê
`linha.pis`, `linha.cofins`, `linha.diferenca_do_pis`, `linha.selic_sobre_o_pis`.
É moldado em PIS/COFINS **e** em SELIC — os dois vícios que este módulo não tem.
Reaproveita-se a casca; o `Total`/`Resumo`/`somar` precisa de um irmão de ICMS.

**O formato de saída já está definido pelo gabarito:** a extração padrão
`C100 + C170 + 0200 + 0150` mais três colunas — `AD REM / ALÍQ`, `CRÉDITO`,
`CLASSIFICAÇÃO`. A coluna B é de duplo propósito, e é ela que materializa os dois
regimes num relatório só.

---

## 11. O que ainda é dúvida, e continua dúvida

**Quatro coisas no papel de trabalho da empresa H** que não vou tratar como verdade:

1. o arquivo se chama "2021 e 2022" e os dados são percentuais, mas **o texto da
   metodologia descreve o monofásico** (2023+). Texto e dado não combinam;
2. ~~o cliente é do **ES** e o papel cita o **FCV de SP**~~ — **confirmado erro**
   em 02/10/2026: 0,9976 contra 0,9943, 0,33% sistemáticos (ver `tab_fcv`);
3. a reconstrução do ST usa `VL_ITEM × alíquota`, o que **ignora que a base do ST
   era o PMPF**. É simplificação aceita ou é a metodologia?
4. o texto conclui **R$ 559.997,23** "para os dois meses de amostragem" e a
   planilha soma **R$ 792.861,06** em 20 competências. Dois números no mesmo
   documento.

**Mais três:**

5. **Etanol hidratado — resolvido em 03/10/2026, pelo art. 3º-B da lei do ES.**
   O artigo lista os produtos do monofásico e nomeia o **etanol anidro
   combustível (EAC)**, e só ele. O **hidratado ficou fora**: segue no regime
   plurifásico até hoje, e no ES a alíquota é **27%** (art. 20, VI, "b", "álcool
   de todos os tipos, inclusive o álcool carburante"). Logo ele **não** tem ad
   rem, e pedir uma é erro de categoria. O que **continua** dúvida é se o ES o
   mantém sob ST — a alíquota se sabe, o regime não;
6. **Lubrificante** (R$ ~1 milhão): tese **separada e possivelmente válida** —
   crédito de ST na aquisição por quem usa como insumo, pela legislação estadual,
   não pelo Conv. 26/2023. Saber que existe; não misturar no mesmo número.
   Confirmado que **nunca entrou no monofásico**, então a alíquota percentual
   vale até hoje; a do ES está em `A_CONFERIR` pelo mesmo motivo do GLP;
7. ~~**"Já credita" é regra ou exceção?**~~ — **resolvido em 03/10/2026: é
   regra.** Varredura do `E111` nos clientes com CST 61:

   | Cliente | Litros CST 61 | Credita? | Fundamento que o próprio ajuste cita |
   |---|---|---|---|
   | empresa Z | 7.231.083 | **sim**, 72 ajustes | LC 192/2022 e cláusula 7ª do Conv. 199/2022 |
   | empresa G | 3.772.408 | **sim**, 111 linhas, R$ 5,08 mi em 32 competências | *(ajuste sem texto de fundamento)* |
   | empresa K | 2.235.536 | **não** | — |
   | empresa Y | 445.861 | **sim**, 13 ajustes | Conv. 26/2023 e 61/2023, "e a proporcionalidade das operações tributadas" |

   **O achado não é o placar, são os fundamentos.** As três que creditam citam
   bases legais **diferentes**: uma a cláusula da ad rem (que diz *quanto* é o
   imposto), outra os convênios do **direito ao crédito** (que dizem *quem*
   pode tomar). Não há prática assentada, e isso é argumento a favor do módulo:
   o fundamento entra na linha da planilha justamente porque o cliente pergunta
   "por que esse número?".

   **E a empresa Y rateia.** O texto dela diz "a proporcionalidade das operações
   tributadas" — ela credita só a parcela correspondente às saídas tributadas,
   o que as outras duas aparentemente não fazem. É uma **terceira** variável de
   divergência, ao lado do FCV que a empresa G não aplica e dos meses curtos.
   Se o rateio é devido ou é conservadorismo do contador é questão aberta, e
   decide se a empresa Y tem crédito **a mais** para pedir.

   **Uma advertência de método.** A primeira varredura devolveu zero `E111` para
   a empresa G — justamente a que se sabia creditar R$ 5 mi. O motivo era banal:
   o script assumia uma subpasta que aquele cliente não usa. Os números acima da
   empresa Y e da empresa Z vêm de **duas rodadas independentes** que
   concordaram; o da empresa G vem de contagem direta de `SP020799`. Varredura
   que devolve zero para um caso conhecido não prova nada sobre os outros zeros.

**Resolvido no levantamento:** o **CST 090** era a maior dúvida, e não é "não sei o
que é" — é **ICMS destacado a 12%** em 4.383 de 4.995 linhas, **já creditado pelo
documento**: representa 70,3% de todos os créditos do E110 naqueles meses, chegando
a 97% em 2022-09. Fica fora da tese.

---

## 12. Onde isso mora na esteira

O combustível é a **seção 4** de uma revisão fiscal maior, descrita pela própria
casa em `Z:\ICMS - PROJETOS\00 - Prompt para IA`. As outras seções — insumos,
energia, CIAP, fretes, bloco E, créditos extemporâneos — compartilham a leitura do
mesmo arquivo. Vale desenhar o motor sabendo disso, ainda que se construa só o
combustível.

Gabaritos disponíveis: `14 - Encerrado/empresa H` (projeto encerrado, era do ST) e
`03 - Em Execução/01 - empresa G` (atravessa os dois regimes, com
`WP - GRUPO ETTORI_072021 a 052026.xlsb` e uma pasta `Relatorios MA`).

[RC 28013/2023]: https://legislacao.fazenda.sp.gov.br/Paginas/RC28013_2023.aspx
[RC 28237/2023]: https://www.ibet.com.br/resposta-a-consulta-tributaria-28237-2023-de-31-de-julho-de-2023-ementa-icms-regime-de-tributacao-monofasica-para-operacoes-com-combustiveis-utilizacao-de-oleo-diesel-como-insu/
[Convênio ICMS 26/2023]: https://www.confaz.fazenda.gov.br/legislacao/convenios/2023/CV026_23
[Súmula 411 do STJ]: https://www.stj.jus.br/docs_internet/revista/eletronica/stj-revista-sumulas-2014_39_capSumula411.pdf

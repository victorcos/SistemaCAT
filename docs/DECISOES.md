# DECISÕES — CRM Fiscal

> Registro datado das escolhas e do porquê. Decisão sem motivo escrito vira
> discussão de novo daqui a seis meses.

---

## 2026-10-05 — A tela do combustível, e a demanda acendeu

`pages/Combustivel.tsx` é a última peça: até agora a etapa aparecia no hub com
"ainda não construída", porque `Implementada: false` era de propósito — acender
a chave sem ter tela faria o card convidar a clicar para lugar nenhum. Com a
tela no ar, a chave virou.

**O registro de uma etapa tem cinco pontos, e não três.** Os três do servidor
(`PREPARADORES`, `EXECUTORES`, `ETAPAS_CANCELAVEIS`) já têm teste que os cobra.
Os do front não tinham nome escrito em lugar nenhum, e são dois: a rota em
`constants/routes.ts` com a tela em `routers/index.tsx`, e o rótulo do botão em
`DESTINOS` de `pages/Projeto.tsx` — sem o segundo o card acende e não leva a
nada. Mais a chave `Implementada` no `Etapas.cs`, que é o que o servidor
responde. Ficam registrados aqui porque descobri cada um por falta.

**O número grande sozinho é resposta incompleta, e a tela recusa dá-la.** Três
coisas saem junto com o total, porque sem elas alguém soma errado:

* **quanto do total é estimativa** — na era da substituição tributária a base é
  o valor do item, porque o arquivo do destinatário não traz a do ST (medido:
  zero em 5.234 linhas de CST 60/61). Sai em aviso próprio, com o valor, e
  **não** somado por dentro do número grande;
* **o que ficou fora, e por quê** — cada motivo com a contagem e uma frase de
  exemplo. Competência sem ad rem conferida não vira zero: vira linha com
  explicação, porque a providência é diferente em cada caso (uns se resolvem
  cadastrando tabela, outros são crédito que o documento já deu);
* **o intervalo de emissão** — é ele que diz se prescrição é assunto. A tela
  mostra e não corta nada por prazo: cortar sozinha esconderia a decisão.

**Motivo que o front não sabe traduzir aparece pela chave.** O motor ganha
código curto de recusa novo toda vez que uma tabela nova entra, e a tradução
mora no front. A tentação é filtrar o desconhecido para não mostrar
`ad_rem_nao_conferida` cru na tela — e é justamente o erro: a linha sumiria, o
total não fecharia, e ninguém saberia por quê. Dois testes cobram isso, um na
marcação e um na função.

**O formatador de data não passa por `Date`.** `new Date("2024-01-01")` é
meia-noite **UTC**: em Brasília imprime `31/12/2023`. Data de emissão de
documento não tem fuso — é o dia escrito no arquivo —, então `format.dia()`
parte a string em vez de montar um `Date`. A mutação fiel confirmou que o bug é
real nesta máquina: trocar a implementação faz dois testes caírem com
`31/12/2023`.

**A fila não recarrega, e foi ela que segurou a demanda.** O motor sobe com
`--reload` e pega `.py` salvo; a fila (`workers.rodar`) **não**, de propósito —
com ela dentro do motor, uma apuração de uma hora morria a cada arquivo salvo
(23/09/2026). O efeito colateral: a fila de 03/10 não conhecia a etapa
`combustivel`, e o clique deixaria a execução parada para sempre. O sintoma é o
que o docstring do `/saude` já prescrevia: versão do motor diferente do arquivo
`VERSAO`. Estava em 0.144.0 contra 0.145.0. **Toda etapa nova exige reiniciar a
fila**, e isso não é opcional nem detectável pela tela.

**E reiniciar levou cinco tentativas, por duas armadilhas.** Valem escritas,
porque cada uma produz um reinício que parece ter funcionado e não funcionou:

* `Get-NetTCPConnection -LocalPort 8020 -State Listen` respondeu **um**
  listening enquanto `netstat -ano` mostrava **dois**. O docstring do `/saude`
  já mandava usar o `netstat` — eu usei o cmdlet, li "porta livre" e fui
  procurar cache na API em C#, que não tem cache nenhum;
* o órfão que segurava o socket é um filho de `multiprocessing`, e a linha de
  comando dele **não contém `uvicorn`**. Meu laço de kill filtrava por
  `uvicorn|workers.rodar`, dizia "morto" para o pai e deixava o filho vivo
  atendendo com o código de dois minutos antes. A conta fechou quando vi um
  processo nascido às 10:43 respondendo a uma requisição às 10:58, com o
  `VERSAO` escrito às 10:52: só um processo mais velho que o arquivo explica
  isso.

A fila e o motor pegam um `VERSAO` novo reiniciando. A API em C# **não**: o
`dotnet watch` reconstrói quando um arquivo muda de **conteúdo**, não reage a
`touch` de data e não relança o app quando o processo morre por fora.

---

## 2026-10-05 — A etapa do combustível existe, e a rota responde

`casos_de_uso/apurar_combustivel.py` é a casca: prepara a execução, chama a
rodada, escreve o diário que a tela lê e registra no histórico. A regra não está
nela — está no leitor, no classificador e na apuração, e isso é o ponto.

**Uma recusa que nomeia o arquivo.** Sem EFD ICMS/IPI no lote a etapa não roda, e
a mensagem diz **qual** arquivo falta e por que a EFD-Contribuições não serve:
ela não traz o CST do ICMS nem a unidade do item. "Importe a base" não ajuda
quem importou a base errada achando que servia.

**Dois avisos que levam a providências opostas.** Quando nada é apurado, o
resumo distingue "a empresa não comprou combustível" de "comprou, mas tudo veio
com ICMS destacado" — no primeiro caso não há tese, no segundo o crédito já foi
tomado pelo caminho normal. Um "zero" sem explicação leva à providência errada.

### Eram dois registros. Eram três.

Eu tinha mapeado dois: `PREPARADORES`, do canal interno, e `EXECUTORES`, da
fila. Escrevi um teste que percorre os dois mapas e cobra os dois lados de
**toda** etapa — não só da nova —, porque esquecer um deles não quebra teste
nenhum: quebra no clique, com o canal dizendo "etapa desconhecida" ou a execução
ficando na fila para sempre.

E aí um teste que **já existia** pegou o terceiro: `ETAPAS_CANCELAVEIS`, em
`rodada.py`. Ele varre os casos de uso procurando quem constrói um `Freio` e
cobra que a lista os contenha — *"etapa que sabe parar e a tela recusa
cancelar"*. A minha sabia parar e não estava na lista.

Vale registrar que o teste que me pegou é do mesmo tipo do que eu acabara de
escrever: ambos derivam a verdade do código e cobram a lista, em vez de repetir
a lista. É o formato que sobrevive a quem chega depois.

### A rota, conferida no ar

`Execucoes.Combustivel` e uma linha de `Etapa(...)` em `ExecucoesRotas.cs` — o
lado C# é fatorado o bastante para isso ser uma linha. Conferido contra a API em
execução: as quatro rotas respondem **401** (pede sessão) e um caminho
inexistente responde **404**. O controle importa: sem ele, "401" não provaria
que a rota existe.

### O botão ainda não acende, de propósito

`Implementada` segue `false`. Acendê-la agora faria a etapa aparecer como
pendente sem ter para onde ir — a tela é a próxima peça, e é ela que vira a
chave.

1.869 testes Python, 392 C#.

---

## 2026-10-05 — As etiquetas de empresa viraram número

Pedido do Victor: *"é bem mais eficiente a leitura"*. `empresa A` virou
`empresa 01`, `empresa D` virou `empresa 04`, e assim por diante — 463 trocas em
122 arquivos.

**As letras tinham dois defeitos, e os dois eram do mesmo tipo.** A sequência
precisava **pular E, I e O**: "empresa e" se confundia com a conjunção num
`grep` (deu 34 falsos positivos quando tentei usá-la) e I e O se confundem com 1
e 0. E, com 21 das 23 letras aproveitáveis em uso, o cliente seguinte **não
teria etiqueta** — teria de virar `empresa AA` ou recomeçar com número. Número
não esbarra em nenhum dos dois.

**E elas nunca foram alfabéticas**, embora parecessem. A ordem era a de
frequência no repositório no dia da anonimização: a empresa com 95 ocorrências
ficou com D, a de 51 com F, a de 15 com G. A numeração **preserva essa mesma
ordem** — não porque ela signifique algo, mas porque trocá-la faria quem já leu
a documentação reaprender todas as etiquetas em troca de nada.

### Três casos que a troca automática pegaria errado

**`EMPRESA A` que não é etiqueta.** Em `test_credito_outorgado.py` ela é razão
social fictícia dentro de um XML de teste — `<xNome>EMPRESA A</xNome>`.
Convertê-la faria parecer que a etiqueta 01 está ali. Ficou como está, protegida
por selo durante a troca.

**Lista de letras.** "empresa A, B e C" tem uma etiqueta e duas letras soltas: a
expressão pegava a primeira e deixava "empresa 01, B e C". E a versão plural —
"as **empresas** A, B e C" — nem a primeira pegava. Os dois casos apareceram
numa varredura por `, [A-Z] e [A-Z]`, e foram corrigidos à mão.

**`blocos A, C, D e F`** em `gestao/leiaute.py` são blocos do SPED, não empresas.
A mesma varredura os mostrou, e eles ficaram.

### O que ficou como história

A entrada de 03/10 que explicava por que as letras pulavam E, I e O continua
lá, com nota de superada. E o relato do `EMPRESA_T` — o identificador que
quebrou a compilação na anonimização — menciona o nome novo entre parênteses:
apagar o antigo tornaria o relato incompreensível.

Suítes: 1.861 Python, 392 C#, 42 do front, `tsc` limpo.

---

## 2026-10-03 — A rodada apura, e a porta que evita creditar duas vezes

`analitico/combustivel.py` deixou de gravar só as compras: cada linha passa pelo
classificador e pela apuração, e o parquet sai com as três camadas — o que o
arquivo trouxe, o que o classificador decidiu, o que a tabela calculou.

**Três somas, três perguntas, três chaves.** `grupos` responde "o que entrou",
por CST e unidade como o arquivo os escreveu; `creditos` responde "quanto vale",
por produto e regime, com a parte estimada à parte; `recusas` responde "o que era
da tese e não entrou", por motivo. Misturá-las somaria litro declarado com litro
convertido — e um balde de recusas que recebesse tudo o que não gera crédito
receberia a loja inteira, parafuso incluído.

**O motivo virou código curto.** As frases de recusa trazem a competência e a
alíquota dentro, então agrupar por elas daria um grupo por linha. Agora cada
recusa tem um código (`ad_rem_nao_conferida`, `mes_partido`, …) e a rodada guarda
**uma** frase de exemplo por código: a tela diz "ad rem não conferida (9 linhas)"
e abre o porquê inteiro de uma. Há teste que percorre os caminhos de recusa e
exige que nenhum saia sem código.

### A porta que faltava, e como ela apareceu

Escrevi um teste chamando um parafuso de parafuso — e dei a ele o NCM do diesel.
Ele gerou crédito. Isso estava **certo**: quem decide o produto é a NCM. Mas
revelou o que faltava: **a apuração ignorava o CST por completo**, então uma
compra com ICMS já destacado ganhava a ad rem em cima. Contagem dupla.

A doc já dizia que o CST 090 é ICMS destacado já creditado pelo documento e fica
fora da tese; o que faltava era o código fazer isso.

### E a primeira versão da porta estava errada

Ela exigia CST 61 na era do monofásico. Rodando contra o acervo real, o devido
caiu de R$ 1,57 milhão para R$ 1,04 milhão e **meses inteiros sumiram** — meses
em que o cliente creditou.

Fui ver o que eram as 1.026 linhas recusadas, R$ 3 milhões: diesel e gasolina
comprados em posto — `Rodoposto Bandeirantes`, `Auto Posto Viaduto` —, 914 e 112
linhas, concentradas em 2025, **todas sem uma gota de ICMS destacado**. Compra de
combustível de verdade, escriturada pelo fornecedor com 60 em vez de 61.

**O regime é da lei, não do rótulo que o posto digitou.** Em 2025 o diesel é
monofásico tenha o fornecedor escrito 60 ou 61, e nos dois casos o imposto foi
cobrado lá atrás. O que separa essas linhas das de CST 90 é o **destaque**: CST
60 tem **zero** linhas com ICMS destacado; CST 90 tem **792 de 1.080**.

A regra passou a ser: **destaque primeiro, rótulo depois**. Com destaque,
recusa por `icms_ja_destacado`. Sem destaque e com CST 61, 60 ou CSOSN 500,
apura. Sem destaque e com outro CST, recusa para olho humano — não se sabe por
qual via o produto foi tributado, e adivinhar ali é inventar crédito.

### Quanto a porta vale, medido

Com e sem ela, nas 25 competências: o devido vai de R$ 1.567.603,81 para
**R$ 1.566.349,35**. São **R$ 1.254,46** que seriam pedidos duas vezes.

Pouco neste cliente, e vale dizer por quê: ele compra quase tudo em posto, sem
destaque. Num cliente que compre de distribuidor com ICMS destacado a porta pesa
muito mais.

**E eu tinha estimado "uns R$ 290 mil"** — uma regra de três sobre a contagem de
linhas, dita como se fosse medição. O número certo é 230 vezes menor. Estimativa
apresentada como medida é o mesmo defeito das outras cinco deste dia, só que
disfarçado de ordem de grandeza.

### O resultado, com a porta no lugar

| | |
|---|---|
| devido | R$ 1.566.349,35 |
| creditado pelo cliente | R$ 1.328.691,14 |
| **diferença** | **−R$ 237.658,21** |

E os três meses que batem **ao centavo** com `litros × ad rem` continuam batendo:
2024-02 (−0,07), 2024-05 (+0,03), 2024-06 (−0,03). A porta não os tocou, que é
como se sabe que ela recusou o que devia.

---

## 2026-10-03 — O card do combustível no hub de ICMS, antes de a tela existir

Primeiro pedaço de frente, e ele é **uma edição de dado**: a trilha `CMB` entrou
em `TrilhasPorModulo["icms"]` e a etapa `combustivel` no catálogo de etapas, com
`Implementada: false`.

O card aparece no hub ao lado de `BASE`, `C42`, `OUT` e `XML`, com a etapa dizendo
**"Ainda não disponível"** e sem botão. Isso é desenho, não gambiarra — o próprio
`Projeto.tsx` diz: *"Chave sem entrada aqui aparece na barra e no cartão sem
botão, o que é o certo para uma funcionalidade ainda sem tela."* E o
`Implementada` existe exatamente para isso: o usuário vê o caminho inteiro e sabe
onde o trabalho está.

**O front não mudou**, fora a sigla. As trilhas vêm da API (`d.trilhas`), a
`sigla()` cai nas iniciais quando a chave é desconhecida, e o mapa de destinos
não ter a chave é o que tira o botão. Acrescentei `combustivel: "CMB"` só para o
quadradinho não sair "CDI".

**Uma etapa só, por enquanto.** A fila de revisão do classificador — o revisor
confirmando o que cada descrição é — será a segunda, quando existir; hoje o
classificador marca a linha e quem revisa olha a planilha.

### Um teste do domínio quebrou, e ele estava certo

`Projeto_novo_tem_tudo_pendente_e_nada_barrado` afirmava que **toda** etapa de um
projeto novo sai `Pendente` e `Acessivel`. Com uma etapa não implementada no
catálogo, isso deixou de valer: ela sai `NaoDisponivel`, e `Acessivel` é
literalmente `Situacao is not NaoDisponivel`.

Corrigi o teste para afirmar as **duas** metades — implementada sai pendente e
acessível; por vir sai não disponível e não acessível — com um `Assert.NotEmpty`
na primeira, para que a regra não passe a valer por vacuidade se alguém marcar
tudo como não implementado.

**O progresso não inflou**, e isso já estava resolvido antes de mim: `Progresso`
filtra por `Implementada && Conta`, então a etapa por vir não entra no
denominador. Sem isso, todo projeto de ICMS passaria a mostrar 7 de 8 para
sempre.

---

## 2026-10-03 — A apuração, e a tabela que eu publiquei errada hoje mesmo

Última peça da conta: `sped/credito_de_combustivel.py` recebe uma compra e uma
classificação e devolve quanto ela vale. Não lê arquivo, não classifica, não
infere nada — todo número sai de `tab_ad_rem`, `tab_fcv` ou
`tab_aliquota_combustivel`.

> O humano decide o que o produto é; **a tabela decide quanto ele vale.**

### A era do ST não se calcula, e isso é a tese

Medido antes de escrever: **5.234 linhas de C170 com CST 60 ou 61 e zero com
base ou valor de ST**; 3.867 linhas de C190 das mesmas CST, todas com `VL_OPR` e
**nenhuma** com `VL_BC_ICMS_ST`. Não é defeito do arquivo — o imposto foi retido
na origem e o destinatário não o vê. Foi essa ausência que criou o direito ao
crédito e é ela que impede de medi-lo no SPED.

Então a era do ST sai como **estimativa rotulada**, com a base no valor do item,
e `estimativa=True` **na linha** e não em nota de rodapé: quem somar um total com
estimativa dentro tem de saber pela própria linha. A base verdadeira era o PMPF,
e a diferença não se sabe sem a tabela dele — nem o sinal. A conferência é o XML
(`vICMSSTRet ÷ vBCSTRet`), como decidido em 02/10/2026.

### O que não cobre não vira zero

Zero soma; recusa aparece. Competência sem vigência cadastrada, tratada como
zero, sai do relatório como "não havia crédito naquele mês" — e ninguém procura
o que não viu. As exceções das três tabelas são capturadas e **viram texto na
linha**, que é a única forma de o motivo chegar ao relatório.

**O maior buraco de cobertura aparece assim**, e é grande: o monofásico do diesel
começou em 05/2023 e a vigência mais antiga **conferida** é de 02/2024. As nove
competências do meio recusam, com a suspeita de 0,9456 na mensagem. A empresa 06
tomou crédito em todas elas — auditá-las exige abrir a redação original da
cláusula sétima do Conv. 199/2022.

**A cobertura nunca chega a "alta" hoje**, e o `porque` diz por quê: falta a
tabela de UF que internalizaram o Conv. 26/2023. O convênio dá o direito; quem
concede é o estado. Chamar de alta sem a norma seria inventar certeza.

### O resultado, com a cadeia inteira rodando

25 competências da matriz da empresa 06, leitor → classificador → apuração:

| | |
|---|---|
| devido (com FCV) | **R$ 1.567.603,81** |
| `litros × ad rem` (sem FCV) | R$ 1.571.403,79 |
| creditado pelo cliente | R$ 1.328.691,14 |
| **diferença** | **−R$ 238.912,67** |

E três meses batem **ao centavo** com `litros × ad rem`: 2024-02 (−0,07),
2024-05 (+0,03) e 2024-06 (−0,03). Sete centavos em R$ 69 mil confirmam a ad rem
de 1,0635 por via independente do convênio, e mostram que o cliente **não aplica
o FCV**.

Os meses que destoam são o produto: 2025-09 creditou R$ 13.089,81 contra
R$ 54.279,39 devidos; 2025-01, R$ 32.486,17 contra R$ 71.500,64. Vários a cerca
de metade.

### A tabela que eu publiquei errada hoje, e como

No commit da rodada (v0.139.0) publiquei um cruzamento que concluía "sete dos
nove meses saem curtos", com 2025-02 dando razão absurda de 59,79 por litro. **O
cruzamento somava gasolina junto com diesel** nos litros do denominador, e
comparava o total com um `E111` que é só de diesel.

Com os produtos separados pelo classificador, nada daquilo se sustenta: a razão
é 1,0635 nos meses em que o cliente credita certo, e a diferença dos outros é de
valor, não de proporção. A tabela de v0.139.0 está **superada por esta**.

Pior: foi essa medição errada que me fez **remover do `tab_ad_rem` uma afirmação
correta** — a de que o livro do cliente corrobora a ad rem. Ela voltou, agora com
os números medidos pelo motor inteiro.

**A lição é sobre método, não sobre combustível.** Medição errada derruba
afirmação certa com a mesma facilidade com que sustenta afirmação errada. Em um
dia: um teste vazio com dados inventados, uma mutação que quebrava o código em
vez de reproduzir comportamento, uma varredura que devolveu zero por caminho
assumido, um `heredoc` que comeu a expressão regular, e agora um cruzamento que
misturou dois produtos. Cinco vezes — e as cinco só apareceram porque alguma
outra medição as contradisse.

35 testes na apuração, quatro guardas conferidas por mutação (recusa virar zero,
tirar o FCV da conta, não marcar estimativa, FCV fixo de SP — as quatro falham).

---

## 2026-10-03 — O classificador, e o corte que esvaziou a fila de revisão

Quinta peça do motor, em dois módulos: `tabelas/tab_combustivel.py` é o dado
(que NCM é que produto) e `sped/classificador_de_combustivel.py` é a regra (a
cascata). O `tab_ad_rem` já referenciava um `tab_combustivel` que não existia;
agora existe.

**A NCM manda, e a inversão vale R$ 239.828.** No crédito outorgado é a
descrição que manda e a NCM confirma, porque a NCM é declarada pelo emitente e
erra. Aqui é o contrário, e a prova está em 273 linhas: `OLEO MOTOR DIESEL
SAE15` tem NCM `27101932`, que é lubrificante. Quem deixa a descrição decidir
lança isso como crédito de combustível.

**Mas a NCM sozinha falha, no mesmo cliente:** 86 linhas de `DIESEL S10` com NCM
vazio, mais `GASOLINA COMUM` (24) e `DIESEL S-500` (10). Ali só a descrição
salva — e a mesma lista tem `LANTERNA` e `FAROL`, então a descrição tem de saber
dizer não.

### O corte por posição de NCM, que eu não tinha previsto

A primeira versão deixava **10.066 das 15.107 linhas** em "não sei, revisar" —
os parafusos, pneus e correias da empresa, cujo NCM a tabela não conhece. Fila
de revisão com dez mil parafusos não é fila.

A saída é fato sobre a nomenclatura, não inferência: parafuso é capítulo 73, e
nenhuma NCM fora das posições 2710, 2711, 2207, 3403, 3819 e 3820 pode ser
combustível ou lubrificante. Com o corte, o quadro das 15.107 compras fica:

| | linhas | confiança |
|---|---|---|
| fora, por posição de NCM | 10.323 | alta, sem revisão |
| diesel, gasolina e GLP por NCM medida | 4.233 | alta, sem revisão |
| lubrificante por NCM | 276 | alta, sem revisão |
| diesel e gasolina **sem NCM**, pela descrição | 136 | média, revisar |
| não sei | 98 | baixa, revisar |

**A fila de revisão é 1,7% das linhas.** E a NCM curta ou torta continua
*desconhecida* em vez de descartada — descartar por NCM malformada mataria as 86
linhas sem NCM.

### Duas normalizações, porque servem a coisas opostas

`normalizar` tira o bico de bomba (`(BOMBA:27 BICO:27)`), os pontos de
preenchimento e colapsa `S-10`/`S 10`/`BS10`. Mantém marca e variante, porque o
revisor decide lendo o texto e tirar palavra é tirar evidência.

`forma_canonica` tira também marca e qualificador de grau, e é a **chave de
agrupamento**. Medido: as **132 descrições de `27101921` colapsam para 18
formas**; as 26 da gasolina, para 9; as 6 do etanol, para 3. O lubrificante quase
não colapsa (102 para 99) — e está certo, lubrificante varia de verdade.

Agrupar quer menos informação; revisar quer mais. Uma função só teria de escolher
um dos dois e serviria mal ao outro.

**A chave não é o `COD_ITEM`:** o posto gera um código por bico de bomba.

### O fator nunca é 1 por omissão

O GLP é tributado por quilo e o SPED declara `UN`. O `0220` é a fonte certa —
medido em 20 milhões de linhas da empresa 22, com duas larguras, agora na tabela
de leiaute. Sem ele, o fator vem do texto: `P20 - GLP 20 KGS` e `20 KGS GLP ONU
1075 2.1`, dois formatos do mesmo cliente. Sem nenhum dos dois, `fator=None` e
`revisar=True` — assumir "um botijão é um quilo" erraria vinte vezes.

E o fator do texto só vale se a unidade **casar com a tributada**: `20LT` não
serve para quem é tributado por quilo, porque inventar densidade aqui seria
calcular no lugar errado.

### A confiança não recusa, e por isso o módulo não tem exceção

Regra da §8: a confiança da classificação é inferência sobre texto livre e emite
tudo ranqueado, com o motivo; quem recusa é a cobertura da regra, que é fato
sobre tabela e mora no `tab_ad_rem`. Exceção aqui faria a linha **desaparecer**
do relatório em vez de chegar ao revisor. Toda classificação traz o `porque`:
sem ele o revisor não tem o que julgar.

### A mutação que passou, e o teste que ela consertou

Quatro guardas foram testadas por mutação. Três falharam como devia; a quarta
**passou** — inverter a ordem dentro de `produto_pela_descricao`, pondo o teste
de diesel antes do de lubrificante, não quebrou teste nenhum.

O motivo: eu guardava a ordem com `OLEO MOTOR - 20 LITROS`, que **não contém a
palavra DIESEL**. O teste afirmava guardar uma ordem que não exercitava. Agora
são três descrições com as duas palavras e sem NCM — `OLEO MOTOR DIESEL SAE15`,
`LUB MOTOR DIESEL 15W40`, `OLEO DIESEL HIDRAULICO` — e a mutação cai.

É a quarta verificação minha hoje que passava sem provar nada. As anteriores
estão registradas acima; o padrão não muda: **a verificação tem de poder
falhar.**

---

## 2026-10-03 — A rodada do combustível, e a corroboração que ela derrubou

Quarta peça do motor: `analitico/combustivel.py` escolhe os arquivos do lote,
chama o leitor em ordem, grava o parquet e devolve o resumo. A mecânica vem de
`exclusoes_por_item.py` — `Escritor`, `parar_se_pedirem` e o `try/finally` que
apaga parquet interrompido. **A soma não vem:** o `Total` de lá lê `linha.pis`,
`linha.cofins` e `linha.selic_sobre_o_pis`, e esta tese não tem nenhum dos três.

**A regra da retificadora é chamada, não copiada.** `escolher` monta um
`ApuracaoEFD` com os cinco campos que `selecionar_por_cnpj_e_competencia` usa e
delega. O `tipo_escrit` vem do `COD_FIN` da ICMS/IPI, que tem outro nome e a
mesma convenção — conferido em 40 arquivos, 17 com `0` e 23 com `1`.

**A unidade entra na chave do grupo.** Somar `L`, `LT` e `LTS` numa coluna só
daria número sem grandeza. Separadas, a soma é conferível e o tamanho do
problema fica visível para quem vai normalizá-lo — e a primeira rodada mostrou
até `l` minúsculo.

**Não aplica prescrição, e diz por quê.** O ICMS prescreve em cinco anos da
**emissão** (LC 87/96, art. 23), regra diferente da do PIS/COFINS que
`dominio/piscofins/prescricao.py` implementa. Em vez de inventar a regra no
lugar errado, o resumo traz a **primeira e a última emissão** encontradas: quem
roda vê o intervalo e sabe se o assunto existe.

### O primeiro resultado real, e ele corrige o que eu escrevi hoje

> **Esta tabela está SUPERADA.** O cruzamento abaixo somava gasolina junto com
> diesel nos litros e comparava com um `E111` que é só de diesel. Ver a entrada
> da apuração, mais acima nesta mesma data, para os números com os produtos
> separados pelo classificador.

Cruzando os litros de CST 61 que o leitor acha com o `E111` `SP020799` do mesmo
arquivo, em nove competências da matriz da empresa 06:

| comp | litros CST 61 | creditado | devido | diferença |
|---|---|---|---|---|
| 2024-02 | 66.555,39 | 69.134,45 | 70.611,79 | −1.477,34 |
| 2024-03 | 70.134,66 | 85.516,82 | 74.409,20 | **+11.107,62** |
| 2024-04 | 60.396,36 | 59.234,73 | 64.077,38 | −4.842,65 |
| 2024-05 | 85.080,88 | 88.182,47 | 90.266,35 | −2.083,88 |
| 2024-06 | 72.540,30 | 75.140,90 | 76.961,45 | −1.820,55 |
| 2024-07 | 68.877,94 | 67.660,47 | 73.075,89 | −5.415,42 |
| 2025-02 | 1.051,67 | 62.874,28 | 1.175,04 | **+61.699,24** |
| 2025-06 | 70.645,79 | 77.473,59 | 78.933,39 | −1.459,80 |
| 2026-01 | 36.462,19 | 21.141,68 | 42.558,38 | −21.416,70 |

**Sete dos nove meses saem curtos**, o que confirma o que o levantamento já
dizia. Dois saem acima, e o de 2025-02 é absurdo: 1.051 litros contra R$ 62.874
de crédito, razão de 59,79 por litro. Absurdo não é resultado — é sinal de que
o crédito daquele mês cobre combustível comprado em outro estabelecimento, ou é
correção retroativa. **A auditoria aponta; não conclui.**

Ressalva que precisa ficar escrita: estes números são de **um** estabelecimento
(a pasta da matriz). Em 2024-02 conferi que os outros três não têm CST 61; nos
demais meses, não conferi. Serve de demonstração da cadeia, não de laudo.

### A corroboração que eu afirmei e que isto derrubou

Até hoje o `tab_ad_rem` dizia que a escrituração daquele cliente era uma segunda
prova da ad rem — "o crédito dela dividido pelos litros dá **exatamente**
1,0635". A razão medida varia de **0,58 a 59,79**: 1,0388 em 2024-02, 1,2193 em
2024-03, 0,9808 em 2024-04. **O livro do cliente não confirma a ad rem; ele é o
objeto da auditoria.** A base daqueles números é só uma, e basta: o texto do
convênio.

**E o teste que sustentava a afirmação era vazio.** Ele comparava
`creditado × FCV` com `litros × ad_rem × FCV`, com o par (litros, creditado)
escrito à mão na parametrização — qualquer par cuja razão fosse a ad rem
passaria. E o par estava errado: dizia R$ 207.403,35 em 2024-02, e o `E111` real
traz R$ 69.134,45. Três vezes mais.

É a terceira vez hoje que um teste ou medição meu passa por certo sem prová-lo
nada (as outras: a mutação que quebrava o código em vez de reproduzir o
comportamento antigo, e a varredura de `E111` que devolveu zero por caminho
assumido). O padrão é o mesmo — **a verificação tem de poder falhar**, e a única
forma de saber é fazê-la falhar de propósito.

O que sobrou no lugar é aritmética, não medição: o desvio de quem pula o FCV é
0,24% e **não depende do volume**, com teste que o afirma em três ordens de
grandeza.

25 testes na rodada, inclusive o cancelamento que apaga o parquet pela metade e
o par ambíguo que sai marcado no parquet.

---

## 2026-10-03 — O leitor das compras, e o campo que carrega dois domínios

Terceira peça do motor: `sped/combustivel.py` entrega uma linha por item de
**entrada** da EFD ICMS/IPI, com o documento e o cadastro do item já juntos. É
a matéria-prima que a apuração multiplica.

**O módulo não sabe o que é combustível.** Ele entrega todas as compras; o
classificador decide o que é diesel e a apuração decide quanto vale. Três
relógios diferentes — classificação muda com cliente novo, tributação muda com
convênio novo, extração não muda — e por isso três módulos.

**Duas coisas são mais simples aqui que na EFD-Contribuições.** A ICMS/IPI traz
o CNPJ no `0000` e não tem `0140` nem `C010`, então o cadastro é uma tabela por
arquivo e não a `CadastroPorEstabelecimento` que a 037 precisa. E dos nove ramos
de documento de entrada sobra um: `C100 > C170`.

### O erro que eu cometi, e que o teste de fumaça pegou

Escrevi a lista de CST de ICMS na versão clássica — 00, 10, 20, 30, 40, 41, 50,
51, 60, 70, 90 — e com ela **o `061` não era reconhecido como nada**. O
monofásico criou quatro CST que aquela lista não tem (`02`, `15`, `53` e `61`),
e o `61` **é a tese inteira**: é ele que marca a compra de combustível de quem
consome.

O defeito não apareceria em teste de unidade escrito depois do código, porque eu
teria escrito o teste com a mesma lista errada. Apareceu porque rodei a função
contra a lista de códigos que a medição havia devolvido do arquivo real, e o
`061` voltou vazio. Há um teste nomeado `TestOCstQueEuErrei` para que não volte.

### O campo `CST_ICMS` tem dois domínios dentro

Para fornecedor de regime normal são três dígitos de **origem + CST**; para o do
Simples Nacional é o **CSOSN**, que é outro domínio no mesmo campo. Cinco
códigos cabem nos dois — `102`, `202`, `300`, `400` e `500` — e as duas leituras
dizem o oposto sobre haver imposto: `500` como origem 5 + CST 00 é tributada
integralmente; como CSOSN 500 é ST cobrado anteriormente.

**Resolvido por medição.** Das 3.245 linhas com `500` nos 40 arquivos, **uma só**
traz ICMS destacado; tributada integralmente traria em quase todas. O `400` tem
179 e nenhuma. O CSOSN vence — **e o resultado sai marcado `ambiguo`**, porque a
estatística é de um cliente e a apuração pode querer recusar em vez de confiar
nela. A lista de ambíguos é **calculada**, não digitada: acrescentar um CST novo
recalcula a ambiguidade em vez de deixar a lista velha em silêncio.

O `900` não é ambíguo, e não por estatística: a origem vai de 0 a 8, então
origem 9 não existe.

### Uma premissa do cálculo que caiu

**O `VL_ICMS` do C170 é esparso.** O CST `000` — tributada integralmente — tem
610 linhas de entrada e **só 24 com valor de ICMS**: o campo é facultativo por
perfil e este cliente quase não o preenche. Quem for reconstruir ICMS destacado
tem de ir ao **`C190`**, que é obrigatório e soma por CST/CFOP/alíquota. O
leitor entrega o campo como veio, e `None` quando veio vazio.

**Vazio não é zero** — a lição do 680 vale igual. Alíquota ausente e alíquota
zero não erram o total, erram a pergunta "este fornecedor destacou imposto?",
que é a que decide se a linha entra na tese.

### A prova de ponta a ponta

Rodado em quatro EFD de 2024 da empresa 06: 1.279 itens de entrada, **334 de CST
61**, com **236.070 litros** escritos em **três unidades diferentes pelo mesmo
cliente** — `L` (183.086,72), `LT` (41.685,15) e `LTS` (11.298,55). Extrapolado
para as 62 competências, bate com os 3,77 milhões de litros já medidos.

Normalizar essas unidades é trabalho do classificador, com o `0190` e o `0220`.
O leitor entrega a unidade como o arquivo a escreveu — inventar `L` para `LTS`
dentro da extração esconderia o problema de quem tem de resolvê-lo.

### Documento cancelado

21 dos 7.210 documentos vieram com `COD_SIT` `02`. Pouco o bastante para passar
despercebido num total, e o suficiente para um pedido conter nota cancelada. Os
itens deles não saem, e o que ficou de fora vai contado no log, por motivo.

60 testes, com as quatro guardas conferidas por mutação: tirar o `61` da lista,
fazer vazio virar zero, ignorar o cancelamento e aceitar saída — as quatro
falham. Nenhuma linha de cliente entrou como fixture: as EFD dos testes são
montadas **pelo nome do campo** a partir de `registros_icms.CAMPOS`, o que faz o
teste conferir também que o leitor e a tabela de leiaute concordam.

---

## 2026-10-03 — O CNPJ entrou na chave da seleção, e a função trocou de nome

Segundo pré-requisito do motor de combustível, e o que estava marcado como
bloqueante: `selecionar_por_competencia` guardava **uma** apuração por
competência, chamando de duplicata o que era outra filial. Agora a chave é
`(CNPJ, competência)`, e o nome é `selecionar_por_cnpj_e_competencia` — o antigo
descrevia o que a função fazia, e passaria a mentir.

**Era latente, não inofensivo.** Os dois usuários da função leem
EFD-Contribuições, que a matriz entrega consolidada: um CNPJ por competência, e
aí as duas chaves dão no mesmo. A EFD ICMS/IPI vem **por estabelecimento**, e o
combustível é o primeiro a lê-la. Medido na empresa 06: 411 arquivos em 62
competências, com até 10 na mesma competência — a chave curta deixaria 62.

**O que fazia o defeito ser invisível era o aviso.** Ele dizia "dois arquivos
para a mesma competência; usado X, ignorado Y", o que parece correto a quem lê:
dois arquivos, um escolhido. Só que não eram duplicatas, eram filiais. Agora o
texto diz "do mesmo estabelecimento", e duas filiais **não geram aviso nenhum**,
porque não são conflito.

**Entrou um log, e não um aviso, para a contagem de arquivos.** Quando a seleção
mantém mais de um estabelecimento, o número de arquivos escolhidos deixa de ser
o número de competências. Quem conferir o total precisa saber por quê, mas isso
não é problema a reportar na tela — é log.

**Mexeu em código compartilhado com as exclusões, validadas em 100%.** O
resguardo é a forma do teste: três casos novos de múltiplos estabelecimentos, e
a prova de que eles pegam o defeito antigo. Revertida a chave para só a
competência, **exatamente os três novos falham e os antigos continuam
passando** — isto é, a correção captura o defeito e não altera o comportamento
de cliente com um estabelecimento só, que é o caso das exclusões.

**Uma mutação minha que não valia.** A primeira tentativa de reverter trocou a
chave por uma string, e aí a linha que conta estabelecimentos tentou
desempacotá-la e o código **quebrou** — cinco testes falharam, inclusive dois
que nada tinham com isso. Teste que falha porque o código explodiu não prova que
ele detecta comportamento errado. Refeita a mutação de forma fiel (chave
`("", competência)`), o resultado foi o que interessa: só os três novos caem.

---

## 2026-10-03 — O leiaute da EFD ICMS/IPI, medido em vez de lido

Primeira peça do motor de combustível: sem leitor não há litro para multiplicar.
O `registros.py` da casa é de **EFD-Contribuições**, e os dois arquivos
**colidem** em dois registros — o `0000` e o `0200` existem nos dois com
leiautes diferentes. Uma tabela só teria de escolher um, lendo o outro com os
nomes errados e calada. Por isso `registros_icms.py` é módulo irmão, não uma
extensão.

**Nenhuma linha saiu do Guia Prático.** As 16 entradas foram contadas em 40 EFD
ICMS/IPI reais da empresa 06 (02/2023 a 03/2026), e a contagem vai escrita em
cada registro — é ela que torna a tabela conferível por quem desconfiar. O
motivo de não ler o Guia tem precedente nesta casa: no `0140` da Contribuições
ele trazia um `IND_SIT_INI_PER` que o arquivo não tem, e o campo empurrado não
quebrava nada, porque o vizinho também era texto.

A medição confirmou dos dois lados o que só estava anotado: o `0200` da ICMS/IPI
tem mesmo 13 campos, com o `CEST` que o da Contribuições não tem.

**`tools/medir_leiaute_icms.py` é a outra metade.** Ele conta os campos de cada
registro numa pasta de cliente e compara com a tabela, reportando divergência,
registro não medido e confirmado. Rodado na empresa 06: 16 registros, zero
divergência. **Rodado na empresa 22, achou o `0220`** — o registro que converte
fardo, caixa e tambor em litro, e que a tese depende — **com dois tamanhos no
mesmo acervo**, 3 campos em 38.577 linhas e 4 em 18.302. É a variante por versão
de PVA que o `CAMPOS_ANTIGOS` do módulo irmão existe para tratar, e foi a
ferramenta que a encontrou, não a leitura.

**Três registros ficaram de fora de propósito:** `0206` (código ANP), `0220` e
`C171`. Nomeá-los com leiaute tirado do Guia e nunca exercitado seria pior que
faltar — quem visse o nome assumiria conferência. `posicao_do_campo` levanta
`RegistroNaoMedido` com o motivo escrito, que é erro **diferente** de "campo
desconhecido": um é engano de digitação, o outro é trabalho a fazer.

**Uma premissa que eu quase inverti, e a medição salvou.** O `C110` traz
observação em texto livre, e nela aparece a base do ST que o CST 60 não destaca:
`"BC-ICMS-ST GASOLINA: R$ 2.350,34 VALOR-ICMS-ST: R$ 423,06"`. Pareceu
substituir a dependência do XML. Medido: **33 de 6.905 linhas**, em pelo menos
três formatos de três fornecedores diferentes. Meio por cento, sem formato
garantido e sem obrigação de existir — serve de conferência, não de fonte. A
fonte do ST retido continua sendo o XML.

**E um erro meu de método, que vale registrar.** A primeira medição do `C110`
devolveu zero ocorrências, e eu quase concluí que o texto não existia. A causa
era `heredoc` sem aspas: o shell comeu o `\$` da expressão regular e `R\$` virou
`R$`, um ancoramento de fim de linha que nunca casa. Medição que devolve zero
pede desconfiança antes de virar conclusão — é a segunda vez hoje (a primeira
foi a varredura de `E111` que devolveu zero para quem se sabia creditar).

**O que o teste afirma, e o que ele não afirma.** Afirma a **contagem** de cada
registro contra o que se mediu; não afirma que os nomes estão na ordem certa,
que só o arquivo diz. É a guarda que importa: um nome a mais no meio empurra
todos os seguintes uma casa, e o valor na coluna errada continua parecendo certo
— alíquota e valor do ICMS são os dois número com duas casas. Há também um teste
que lê a mesma linha com a tabela errada e exige que ela **levante**, em vez de
devolver outra coisa.

Nenhuma linha de cliente entrou como fixture: as amostras dos testes são
sintéticas, com a mesma forma e a mesma contagem das reais.

---

## 2026-10-03 — A raiz do CNPJ de cliente também saiu, e os dois dígitos da chave

Segunda metade da anonimização. Os nomes saíram no commit anterior; o CNPJ
identifica igual, e ficar só com metade não anonimiza nada.

**Dez raízes trocadas por fictícias** (`440000NN`), preservando o número da
filial para que os casos de múltiplos estabelecimentos continuem fazendo
sentido. Cinco delas se confirmaram reais cruzando com as pastas de cliente do
`Z:`, que trazem o CNPJ no nome — isso é verificável, diferente de palpite.

**A primeira tentativa estava errada de quatro jeitos, e cada um ensinou algo.**

1. **Trocar o CNPJ de 14 dígitos não bastava.** A mesma raiz aparece solta
   (`raiz="43112531"`), como base de 12 (`"509483710013" +
   digitos_verificadores(...)`), truncada em 13 (teste de tamanho errado),
   dentro de chave de 44, dentro de uma string de 33 e dentro de um **float**
   (`3.5220743112531e43` — uma chave que o Excel converteu para número, e que o
   teste usa justamente para provar que chave-como-número não é lida). A troca
   passou a ser da **raiz**, em qualquer contexto, com os DV refeitos depois.
2. **A raiz pontuada não casa com a corrida.** `11.517.841/0034-55` tem pontos
   no meio de `11517841`. O valor esperado do teste mudava e a entrada não —
   5 testes quebraram só por isso.
3. **A chave tem dois dígitos verificadores, não um.** Eu refiz o DV da chave
   (posição 43) e esqueci o do **CNPJ que ela carrega** (posições 6 a 19).
   Resultado: o CNPJ solto virou `...000237` e o de dentro da chave ficou
   `...000278`. O confronto por chave parou de casar e 12 testes caíram —
   inclusive um que conta documentos escriturados, que passou a ver 3 onde havia
   4. **O DV da chave é validado em `pre_validacao.py:205`**, então não era
   opcional.
4. **Um DV literal que nenhum script adivinha.** `assert c.dv == "78"` — os
   dois dígitos escritos à mão, sem o CNPJ ao lado. Corrigido na unha.

**O que tinha de continuar errado continuou.** `50948371000179` é o CNPJ de
dígito verificador errado de `test_recusa_digito_errado`. Trocar a raiz e
recalcular o DV o tornaria **válido**, e o teste perderia o sentido calado. O
script o protege com um selo antes da troca e devolve, no lugar, um DV
deliberadamente errado para a raiz nova.

**Dois números que parecem CNPJ e não são.** `07891024183007` e `07891653...`
começam com 789 — é prefixo de **EAN brasileiro**, e o campo se chama
`codigo_barras`. Ficaram. Confundir os dois teria estragado fixtures de produto
sem necessidade.

**Conferência, e não só "os testes passam":** 24 CNPJ de raiz fictícia e 12
chaves de 44 varridos do repo e validados pelo `Cnpj` do próprio domínio e pelo
módulo 11 da chave; o CNPJ que devia seguir inválido conferido à parte. 1430
unitários, 154 de integração, 171 do domínio C# e 42 do front.

**O que não rodou:** `Cat.Api.Testes`. O build não acontece com a API de pé —
o `dotnet watch` segura as DLL — e redirecionar a saída quebra o grafo de
dependências. As mudanças ali são quatro literais de CNPJ, iguais nos dois lados
de cada asserção, com a chave reconstruída e validada. Fica para rodar quando a
API estiver parada.

---

## 2026-10-03 — Nenhum nome de cliente no repositório, e nem CNPJ

**A regra já estava escrita, e o repositório a contrariava.** O
`tabelas/__init__.py` dizia desde setembro que *"o nome delas não é versionado,
aqui nem em lugar nenhum do repositório"* — e ao mesmo tempo 389 ocorrências de
nome de cliente estavam versionadas, inclusive em código que eu mesmo escrevi
hoje (`tab_ad_rem.py` nomeava a empresa 06 quatro vezes).

**O escopo cresceu no meio, e por um motivo que vale escrever.** A pergunta era
sobre nomes. Mas os mockups de tela em `frontend/claude/design/screens` traziam
**razão social, CNPJ, inscrição estadual e caminho de pasta do cliente**, juntos,
numa só linha. Anonimizar o nome e deixar o CNPJ ao lado não anonimiza nada: os
dois identificam o cliente igual. Então entraram os dois, e o registro passou a
dizer isso explicitamente.

**O registro vive fora do repositório.** `docs/REGISTRO_EMPRESAS.local.md`, com
`*.local.md` no `.gitignore`. Fica onde as pessoas procuram e não é enviado. É o
único lugar onde as duas colunas aparecem juntas.

**As letras pulam E, I e O.** "empresa e" se confunde com a conjunção num
`grep` — e eu ia usar E até perceber que a varredura devolvia 34 falsos
positivos por causa dela. **I** e **O** se confundem com 1 e 0.

> **Superado em 05/10/2026:** as etiquetas viraram **número**. Pular letra e
> ficar sem letra eram sintomas do mesmo defeito — ver a entrada daquela data.

**Três armadilhas que a substituição automática criou, e que só apareceram
porque foram procuradas:**

1. **nome de cliente como identificador de código.** `test_cnpj.py` tinha
   `BOA = "44000003000109"`, e a troca cega produziu `empresa 17 = "..."` —
   `SyntaxError`. Passou a haver uma regra separada, só para arquivos de código,
   que gera `EMPRESA_T` (hoje `EMPRESA_17`, depois da troca para número).
   Peguei com `py_compile` em todos os `.py`, não com o
   pytest: arquivo que não compila nem chega a ser coletado;
2. **concordância de gênero.** "o Amigão" virou "o empresa 19", "do Superpão"
   virou "do empresa 08" — 89 casos. "Amigão" é masculino, "empresa" não;
3. **nome quebrado em duas linhas.** "da Casa\nAvenida" virou "da Casa\nempresa
   X", porque a expressão não cruza o fim de linha.

**Uma coisa ficou deliberadamente feia:** `empresa 18` e `empresa 20` têm nomes
parecidos e CNPJ diferente, e não se confirmou se são a mesma empresa. Ficaram
com tags separadas. Juntar o que não se sabe igual é pior que ter duas tags.

**O que isto não alcança, e não deve ser feito sozinho.** As **mensagens de
commit antigas** continuam com os nomes. Reescrevê-las exige reescrever o
histórico de um repositório já enviado — destrutivo, e quebra o clone de quem já
baixou. Fica registrado como pendência de decisão de quem tem alçada.

**O que fica no repositório é o que dá peso à nota:** quantas linhas foram
conferidas, de que competência, contra qual relatório. Isso se confere sem saber
de quem é — e era o argumento da regra desde o começo.

---

## 2026-10-03 — São Paulo: o complemento de 1,3 ponto, e os dois meses partidos

**Por que SP depois do ES no mesmo dia.** O ES entrou primeiro porque tinha
gabarito para confrontar. Mas o ES **não tem cliente com combustível** — os
quatro com CST 61 são todos de São Paulo (7,2 / 3,8 / 2,2 / 0,4 milhões de
litros). O ES provou o método; SP é onde ele rende.

**O achado é o complemento de alíquota da Lei 17.293/2020.** O art. 22 somou
1,3 ponto às operações do art. 54 do RICMS/SP, e o § 7º diz com estas palavras
*"passando [...] a ter uma carga tributária de 13,3%"*. O diesel é o inciso VI e
não está entre as exceções do parágrafo. **Dois anos de compras de diesel em SP
foram a 13,3%, não a 12%** — de 15/01/2021 a 14/01/2023, pelo Decreto 65.253/2020
com a redação do 65.470/2021, revogado pelo Decreto 67.524/2023 com efeitos
retroativos a 15/01/2023. Quem apurar a 12% perde 10% do crédito do período.

**Os dois meses partidos, e o campo que eles obrigaram a criar.** O complemento
começou e terminou **no dia 15**. Em 01/2021 e 01/2023 há duas alíquotas, e a
competência não decide qual vale. A `Vigencia` ganhou um campo `dia` e a tabela
um erro próprio, `MesPartido`, que **recusa a competência da virada** e manda
separar as entradas pela data do documento.

Era tentador resolver começando a vigência no mês seguinte — foi o que eu tinha
feito com o álcool do ES, cuja alínea valeu de 29/03/2006. Só que isso devolve
calado a alíquota *anterior* para o mês da virada. No ES passou despercebido
porque não havia vigência anterior e a consulta recusava por outro motivo; em SP
devolveria 12% para janeiro de 2021 inteiro. Corrigi o ES também: ele agora
declara `desde="2006-03", dia=29`, que é a regra de verdade, e há teste que
percorre a tabela inteira exigindo que toda vigência com `dia != 1` recuse o
próprio mês.

**São três recusas, e a distinção é o que protege.** `ForaDoRegimePercentual`
(a era é ad rem, vá para `tab_ad_rem`), `MesPartido` (duas alíquotas, separe pela
data) e `AliquotaDeCombustivelDesconhecida` (ninguém leu, preencha `INTERNA`).
Nenhuma é subclasse da outra, e há teste que afirma isso: se `MesPartido`
herdasse de `AliquotaDeCombustivelDesconhecida`, um `except` do motor engoliria o
mês partido e completaria com qualquer coisa.

**A segunda armadilha na gasolina, e o que ela ensina sobre fonte secundária.**
Pedi a leitura do RICMS/SP a uma busca antes de abrir o texto, e ela devolveu
gasolina a **27%**: os 25% do art. 55, XXVI somados ao adicional de 2% do art.
56-C. O art. 56-C tem **dois incisos** — bebidas alcoólicas da posição 2203 e
fumo do capítulo 24 —, e o adicional só vale em operação destinada a consumidor
final. Combustível não está lá. A mesma busca também afirmou que o complemento
de 1,3% seguia vigente, quando o Decreto 67.524/2023 o revogou.

É o segundo engano de gasolina em um dia, depois dos 30% do ES. **Os dois vêm de
fonte secundária e os dois erram para cima.** Virou teste de propriedade sobre
`REFUTADO`, não dois casos anotados: todo valor refutado que tenha par conferido
tem de ser maior que ele.

**Fica em aberto em SP:** o etanol hidratado, que divide o inciso VI com o diesel
mas tem dois Informativos SFP próprios (janelas de 15/07/2022 a 30/06/2023 e de
1º/07/2023 em diante) — indício de regime próprio; e o GLP, que não é nomeado em
nenhum dos dois artigos e cai na geral por resíduo, faltando descartar redução de
base no Anexo II. Os dois recusam.

**O que SP viabiliza e o ES não.** A conferência pelo XML (`vICMSSTRet ÷
vBCSTRet`, campos que `dominio/notafiscal/xml.py` já lê) só é possível onde há
cliente com compra de combustível na era do ST. Em SP há. O alvo mais
interessante é o 13,3%, justamente porque é o número que ninguém espera achar.

---

## 2026-10-03 — A alíquota do combustível na era do ST, e o inciso que nunca valeu

**O que faltava.** O módulo de combustível já sabia calcular o monofásico
(`tab_ad_rem` × `tab_fcv`), mas um pedido cobre cinco anos e a maior parte dele é
**anterior a maio de 2023**, quando o ICMS do combustível ainda era percentual e
estadual. Sem a alíquota daquela era, o módulo só enxergava o pedaço novo.

**Começamos pelo Espírito Santo** porque é o estado em que havia com o que
confrontar — um papel de trabalho de projeto encerrado. A fonte, porém, foi a
lei: o **texto consolidado da Lei 7.000/2001**, 175 páginas, extraído com `pypdf`
instalado numa pasta de rascunho e **não** no venv do projeto.

**Diesel 12%, gasolina 27%, álcool 27%.** Nenhum dos três é a interna geral do
estado, que é 17% — usar a geral na gasolina credita 37% menos do que a lei manda.
É por isso que a tabela nova é separada de `tab_aliquota_icms`: lá o eixo é a UF,
aqui são UF **e** produto, e o produto manda mais.

**Os 30% que circulam não existem.** Uma busca na internet devolve 30% para a
gasolina do ES, e o número está de fato na lei: a Lei 8.098, de 27/09/2005,
incluiu o inciso VI com exatamente isso. Ele **nunca produziu efeitos** — a Lei
8.237, de 28/12/2005, deu nova redação ao mesmo inciso antes da entrada em vigor,
e o consolidado marca a versão anterior como *"sem efeitos"*. Quem lê resumo em
vez do consolidado pega os 30%: sobre R$ 10 milhões de base são R$ 300 mil
pedidos com fundamento num inciso que nunca valeu.

Por isso entrou um terceiro registro na tabela, ao lado de `INTERNA` e
`A_CONFERIR`: **`REFUTADO`**, para valor que já se provou errado, com o motivo
escrito. Suspeita e engano identificado não são a mesma coisa, e guardar só o
primeiro condena a casa a reabrir a discussão. Há teste que falha se alguém
promover um valor refutado para `INTERNA`.

**A revogação que não produziu efeitos.** A Lei 11.768/2022 revogou a alínea dos
12% do diesel em 30/12/2022, e o monofásico só chegou em 05/2023. Ao pé da letra
haveria quatro meses a 17% — 42% de crédito a mais. Mas o **art. 179-I, § único**
diz que a revogação *não produz efeitos*, invocando o art. 32-A, § 1º, III, da
LC 87/96. Os 12% valeram sem interrupção, e há teste parametrizado nos cinco
meses da janela.

**Duas eras, dois erros diferentes.** A tabela **acaba** onde a `tab_ad_rem`
começa, e por produto: o art. 3º-B da mesma lei pôs diesel e GLP no monofásico em
1º/05/2023 e gasolina e etanol anidro em 1º/06/2023 — **um mês de diferença**, que
erra maio de 2023 inteiro na gasolina para quem usa uma data só. Pedir percentual
de competência do monofásico levanta `ForaDoRegimePercentual`, erro **separado**
de `AliquotaDeCombustivelDesconhecida`. A distinção é o que protege: "não sei" e
"aqui não há percentual" tratados como a mesma coisa levam alguém a completar com
a interna do estado uma conta que devia ser `litros × ad rem × FCV`. Esse erro
vale para qualquer UF, inclusive as não conferidas, porque a virada é nacional.

**O etanol hidratado ficou resolvido de lambuja.** O art. 3º-B nomeia o etanol
**anidro** (EAC) e só ele; o hidratado nunca entrou no monofásico e segue
percentual até hoje, a 27% no ES. Não tem ad rem, e pedir uma é erro de
categoria.

**O GLP ficou de fora, e de propósito.** Ele não é nomeado em nenhum inciso do
art. 20, o que à primeira vista o joga na geral de 17%. Só que o inciso II, "m"
põe a **12%** as mercadorias dos **Anexos VII e VIII do Regulamento**, e esses
anexos estão no Decreto 1.090-R, não na lei — o sítio da SEFAZ-ES não respondeu.
São cinco pontos sobre toda a base de GLP, e é exatamente a divergência das
fontes secundárias: o papel de trabalho diz 17%, a busca diz 12%, nenhum dos dois
leu o anexo. Ficou em `A_CONFERIR` com o caminho escrito, e **o motor recusa**.

**O que esta tabela não pode ter, e por quê.** A regra da casa em
`tab_aliquota_icms` é *ato legal mais medição na escrituração do cliente*. Aqui a
segunda metade **não existe**, e a razão é a própria tese: na era do ST o
consumidor recebe CST 60, que não destaca imposto nenhum. Foi essa ausência que
criou a tese de recuperação; ela também impede que o livro dele sirva de prova.
A prova independente virá do XML — `vICMSSTRet ÷ vBCSTRet`, campos que o leitor
em `dominio/notafiscal/xml.py` já lê. Está escrito no módulo para que ninguém
confunda a procedência destas linhas com a da linha de Minas.

---

## 2026-10-02 — O tíquete travava apagar o trabalho, e o teste que escrevi nasceu vazio

**O defeito.** Apagar um trabalho devolvia "Erro interno" com código de suporte,
numa tela em que a pessoa já tinha confirmado com a própria senha. O log disse o
que era em uma linha:

```
23503: update or delete on table "execucao" violates foreign key constraint
       "tiquete_de_download_execucao_id_fkey"
```

A tabela de tíquetes nasceu horas antes, com chave estrangeira **sem cascata**.
Um tíquete vive dois minutos e passou a impedir apagar o trabalho inteiro: o
primeiro download de uma execução a travava para sempre.

**A correção** é `ON DELETE CASCADE` nas duas chaves — `execucao` e `usuario`.
Tíquete não é dado de negócio; é autorização descartável, e nada deve esperar por
ele. Migração `d1a5c38e7b94`.

**O que o relato mostrou de bom:** o código de suporte na tela levou do sintoma à
linha do banco em uma consulta ao log. É para isso que ele existe.

### O teste que eu escrevi passou sem exercitar nada

Primeira versão: inserir um tíquete, apagar o trabalho, conferir que sobrou zero.
Passou — **inclusive com o defeito recriado**, o que provava que ele não media
nada. Duas descobertas ao investigar o próprio teste:

* desfazer a migração no banco **principal** não afeta o de teste;
* o `BancoDeTeste` **derruba e recria** o banco a cada rodada e migra para
  `head`, então não há como simular o defeito ali.

E o mais importante: se o `INSERT` do tíquete falhasse por qualquer motivo —
execução que não existe, coluna renomeada —, "zero tíquetes no fim" seria verdade
trivial e o teste passaria para sempre sem tocar no assunto.

**A correção do teste é uma asserção a mais, antes do ato:** o tíquete tem de
existir. Com ela, o teste prova que o `INSERT` aconteceu e que o `DELETE`
atravessou a chave estrangeira. Se a cascata sair da cadeia de migrações, o banco
de teste nasce sem ela e o teste quebra.

**Teste que passa pelo motivo errado é pior que teste nenhum**, porque compra
confiança sem entregar nada.

---

## 2026-10-02 — O certificado cobre a sub-rede, para o IP poder mudar

**A escolha é do Victor, e é a certa pelo motivo dele.** Usar o nome da máquina
(`https://VBMS-0151:8010`) resolveria a troca de IP de graça — mas depende do DNS
interno da empresa, e isso depende da equipe de infra. Recusado: "é muito
trabalhoso, e problemático". Um endereço que exige abrir ticket não é um endereço
que a equipe usa.

Então vale o IP. E o IP tem o problema que apareceu na mesma tarde: **mudou duas
vezes em quinze minutos** — cabo para Wi-Fi e de volta —, e o certificado ficou
obsoleto nas duas.

**A saída, inteiramente local: cobrir o /24 no `subjectAltName`.**
`192.168.88.1` a `.254`, 260 entradas. Qualquer endereço que o DHCP entregue já
está no certificado, e não há o que refazer quando ele troca.

**Não é frouxidão.** O certificado continua autoassinado e a chave privada
continua só na máquina: cobrir um endereço não permite a ninguém se passar por
ele. O que a sub-rede compra é o navegador parar de reclamar de **nome** quando o
IP muda — a reclamação de autoridade continua, e é a que se aceita uma vez.

Os adaptadores virtuais do Hyper-V entram só com o próprio endereço, sem
expansão: ninguém acessa o sistema por eles, e expandir dois /24 a mais só
engordaria o certificado.

**O limite, dito claro:** sub-rede diferente exige regerar. Se a empresa mudar a
faixa, `npm run certificado -- --refazer`.

### E o proxy do Vite passou a seguir o esquema da API

Ligar o modo de rede quebrou o desenvolvimento: o proxy apontava para
`http://localhost:8010` fixo, a API virou HTTPS, e `localhost:5173` passou a
carregar a página e dar 500 em toda chamada — página que abre e não funciona, que
é pior que página que não abre.

Agora o `vite.config.ts` lê o `backend/.env` — o mesmo arquivo que a API lê — e
segue o esquema dela, com `secure: false` porque o certificado é autoassinado e
validar aqui recusaria a própria máquina. **Uma fonte de verdade:** ligar o modo
num lugar não pode exigir lembrar de um segundo.

---

## 2026-10-02 — Nunca foi o IP: era o firewall, e a rede estava como pública

**O relato.** "Não está rodando no IP local em outra máquina" — e, logo depois,
que **com cabo também não funcionava**. Essa segunda frase é que fechou o
diagnóstico: se o endereço antigo também não abria, o IP não era a causa.

**O que o Windows tinha:**

```
firewall            ligado nos tres perfis
rede Wi-Fi          NetworkCategory = Public    <- o mais restritivo
regra de entrada    para 5173 ou 8010: NENHUMA
```

A porta escutava em `0.0.0.0` e ninguém de fora chegava nela. Em rede
classificada como pública o Windows recusa praticamente todo tráfego não
solicitado, e sem regra de entrada nenhum `netstat` saudável ajuda.

**O que me enganou, e vale como método.** Meu primeiro teste foi `curl` da
própria máquina para o próprio IP da rede, e deu **HTTP 200**. Isso não prova
nada: tráfego que nasce e morre no mesmo host não atravessa o firewall. Testar
alcance de rede exige outra máquina — ou, na falta dela, olhar as regras em vez
do socket.

### A correção, e por que ela abre uma porta em vez de duas

`scripts/liberar-na-rede.ps1` faz as duas coisas que exigem administrador:
reclassifica a rede da empresa como `Private` e abre **a porta da API**, com
perfil `Private,Domain` — a regra não vale em rede pública, e levar o notebook
para um café não abre a porta lá.

Uma porta porque, desde a v0.127.0, a API serve o front e a própria API. Antes
seriam duas: a 5173 do Vite e a 8010.

### Dois presentes do caminho pela API

**O endereço sobrevive à troca de IP.** O certificado cobre o hostname
(`VBMS-0151`), e em Wi-Fi o IP muda a cada DHCP. `https://VBMS-0151:8010`
continua valendo.

E isso **só funciona pela API**: `http://VBMS-0151:5173` devolve **403**. É o
`allowedHosts` do Vite, que recusa acesso por nome desde a 6.0.9 como proteção
contra rebind de DNS. Pelo Vite seria preciso `CAT_HOSTS=VBMS-0151`; pela API,
nada.

### As três linhas ficaram comentadas no `.env`, de propósito

`CAT_PASTA_DO_FRONT` e o par TLS estão escritos no `backend/.env`, **comentados**.
Com elas ativas, qualquer reinício do `dotnet watch` — inclusive o que uma
alteração de código de outra sessão dispara — subiria a API em HTTPS e derrubaria
o proxy do Vite para quem estivesse usando o endereço antigo. Quem liga o modo
escolhe a hora.

---

## 2026-10-02 — A API passa a servir o front, em HTTPS e na mesma origem

**A causa de fundo, finalmente atacada.** Os funcionários usavam um **servidor de
desenvolvimento** pela rede. Daí vinham o `allowedHosts`, o proxy do Node no
caminho dos bytes, e principalmente a falta de contexto seguro — que foi o que
derrubou o download do 037 e custou a investigação da manhã.

**A decisão.** `CAT_PASTA_DO_FRONT` aponta para `frontend/dist` e a API o serve;
`CAT_TLS_CERTIFICADO` e `CAT_TLS_CHAVE` põem o Kestrel em HTTPS. Os três são
**opt-in**: sem eles a API sobe em HTTP e não serve front, que é o que o
desenvolvimento quer — Vite rodando e API servindo uma cópia velha por cima
seria o pior dos dois mundos. Receita completa na ARQUITETURA §14.

**Uma porta, um esquema.** Dois esquemas na mesma porta não existem, e inventar
uma segunda porta para manter o endereço antigo vivo seria duas verdades sobre
onde o sistema está. Quem liga o TLS avisa o pessoal que o endereço passa a
`https`. O esquema entra no log de subida, ao lado da porta: servidor antigo que
sobrevive a um reinício só se denuncia pelo que diz ao subir.

### Dois defeitos achados ao verificar, e nenhum dos dois apareceria sozinho

**O PEM não serve ao Kestrel direto no Windows.** `CreateFromPemFile` carrega a
chave num provedor que o SChannel não usa, e o handshake falha com um erro que
não menciona nem PEM nem chave. Exportar para PKCS#12 e reimportar devolve o
mesmo certificado num formato que o sistema sabe usar — e é por isso que
`Tls.Carregar` dá esse passeio aparentemente supérfluo.

**Duas configurações do mesmo arquivo, divergindo.** `MapFallbackToFile` tem
`StaticFileOptions` próprias. Com o `OnPrepareResponse` só no `UseStaticFiles`, o
mesmo `index.html` saía com `no-cache` pedido como `/index.html` e **sem
cabeçalho nenhum** pedido como `/` ou `/projetos/1` — que são justamente os
caminhos por onde as pessoas entram. Era exatamente o caso que o cabeçalho existe
para cobrir. Agora é uma configuração só, usada nos dois lugares, e o teste
cobre os quatro caminhos.

### Verificado de ponta a ponta, não por leitura

Instância temporária na 8099, servindo o `dist` de verdade em HTTPS: raiz e rotas
do SPA devolvem o `index.html` com `no-cache`; `assets/` com resumo no nome vêm
`immutable` por um ano; `/api/saude` responde JSON; **`/api/nao-existe` devolve
JSON 404 e não o `index.html`** — o desvio do SPA não engoliu a API; e HTTP na
porta do TLS é recusado.

`FrontTestes` guarda os seis comportamentos, inclusive os dois que não são
caminho feliz: pasta não configurada (a API não serve front) e pasta configurada
que não existe (avisa no log e **não** morre na subida — quem esqueceu o
`npm run build` tem de ver a API no ar, não um processo caído).

200 testes na API, todos passando. O `Banco_sem_esquema...`, que havia falhado por
timeout do Postgres ao derrubar um banco, voltou a passar: era transitório, como
eu suspeitava e não tinha provado.

---

## 2026-10-02 — Quem baixa é o navegador, não a aba

**O problema que o HTTPS não resolve.** Com contexto seguro o seletor de pasta
volta e o `pipeTo` grava em fluxo — mas só no Chromium. Firefox e Safari não têm
a API nem em https, e continuam no caminho antigo: `fetch` e `await r.blob()`,
com o arquivo **inteiro na memória da aba**. Num 037 de 2,93 milhões de linhas
isso não passa, e a API já servia do disco em fluxo: todo o desperdício era do
navegador.

**A decisão: baixar por navegação.** `<a download href>` num endereço da mesma
origem faz o **navegador** baixar — o gerenciador dele grava direto no disco,
mostra progresso, não tem teto de tamanho e funciona em qualquer navegador, com
ou sem contexto seguro. A aba não toca nos bytes.

Navegação não manda cabeçalho `Authorization`, e é essa lacuna que o **tíquete**
fecha: `POST .../planilhas/{qual}/tiquete` devolve um segredo de vida curta, e o
`GET` o aceita no lugar do cabeçalho.

### Quatro escolhas que valem estar escritas

**No banco, não em memória.** Haverá mais de uma instância da API; tíquete
emitido numa tem de ser resgatável na outra. Tabela `tiquete_de_download`,
migração `c4e07a91d5b2`.

**Vida curta em vez de uso único.** Dois minutos, amarrado a um usuário e a um
arquivo. Uso único seria mais apertado no papel e hostil na prática: o
gerenciador de download do navegador **repete a requisição** — queda de rede,
redirecionamento, às vezes um `HEAD` antes do `GET` —, e recusar a repetição
transforma um soluço de rede em "o link morreu". Quem protege é o prazo;
`usado_em` é auditoria. E porque não há trava, não há corrida entre instâncias.

**O tíquete manda, não a URL.** O `GET` serve o que o tíquete descreve —
`qual`, `formato` e recorte. Sem isso, um tíquete de um CSV pequeno pediria o
xlsx inteiro trocando o parâmetro na barra de endereço.

**Emitir não gera a planilha.** É a propriedade que faz tudo valer: gerar na
emissão devolveria os dezesseis minutos para dentro da aba, com o botão travado.
O `POST` confere o que é barato — a execução existe, é do escopo de quem pede, é
da etapa certa — e o resto acontece no `GET`, com a espera no gerenciador de
download e a pessoa livre para trabalhar.

### O que se perde, dito claro

**Erro de disco aparece depois.** Escopo e identificador errados viram aviso na
tela, antes da espera — melhor que hoje, em que chegam depois de o arquivo
inteiro ser montado. Mas "os arquivos não estão mais em disco" e "esta versão
não tem esta lista" passam a aparecer como download que falhou no navegador, e
não como aviso. É o preço de a espera sair da aba, e é um preço bom.

**Cancelar vale até a autorização.** Depois dela o download é do navegador, e é
lá que se cancela. O botão para de girar na hora, enquanto o servidor ainda monta
o arquivo — quem acompanha é a barra de downloads.

### Onde o desvio é reconhecido

`baixarArquivo` decide pela **forma da rota**:
`/api/<segmento>/<id>/planilhas/<qual>` é o desenho que `ExecucoesRotas.Etapa`
registra para toda etapa, e é lá que vive o tíquete. A extração da quebra e a
planilha da 047 têm rota própria, com corpo, e seguem pelo caminho antigo.
Reconhecer a forma num lugar é o que fez as **vinte e duas** chamadas de
download ganharem isso sem que nenhuma precisasse mudar — e é o que os testes de
`conferencia.teste.ts` guardam, porque errar o desvio manda um `POST` para uma
rota que não existe.

---

## 2026-10-02 — HTTPS no dev server, porque contexto seguro não é firula

**O problema, em uma frase:** os funcionários usam o dev server pela rede, e
`http://<ip>:5173` não é contexto seguro — então a `File System Access API` não
existe, o download cai no caminho antigo, e o caminho antigo põe o arquivo
**inteiro na memória da aba** antes de gravar. Num 037 de 2,93 milhões de linhas
isso não passa.

O servidor já faz a parte dele certo: o C# serve do disco em fluxo. Todo o
desperdício está no navegador, e só o contexto seguro permite contorná-lo com
`pipeTo`.

**A decisão: certificado autoassinado, opt-in pela existência do arquivo.**
`npm run certificado` gera o par em `frontend/certificado/`, com
`subjectAltName` cobrindo `localhost`, `127.0.0.1` e **todos os IPv4 da
máquina** — sem o SAN do endereço que a pessoa digita, o navegador não oferece
nem o "prosseguir". O `vite.config.ts` o encontra sozinho.

**Opt-in por arquivo, e não por variável de ambiente**, pelos dois lados: quem
não gerou continua em HTTP sem configurar nada, e quem gerou não precisa lembrar
de ligar. Variável de ambiente seria uma terceira coisa para alguém esquecer.

**A chave privada não é versionada** — o `.gitignore` da raiz já excluía `*.pem`
e `*.key`, e cada máquina gera a sua. Conferido com `git check-ignore`.

### O que isso não resolve, dito claro

Autoassinado dá **aviso do navegador na primeira visita**. Quem prosseguir ganha
contexto seguro de verdade (`isSecureContext === true`), que é tudo o que o
download precisa — mas é um aviso, e aviso de certificado é exatamente o que se
ensina a ninguém ignorar. Para não ter aviso: instalar a autoridade em cada
máquina (`mkcert -install`) ou servir o build atrás da API com certificado
próprio.

E **só cobre quem usa Chromium**. Firefox e Safari não têm a API nem em contexto
seguro, e continuam no caminho da memória. Por isso esta decisão é a ponte, não
o destino: o conserto que serve a todo navegador é o **download por navegação**,
em que o gerenciador do navegador baixa em fluxo e a aba não toca nos bytes.

### Migração

As marcações dos funcionários mudam de `http://` para `https://` — depois do
reinício o dev server atende **só** TLS naquela porta, e um GET em HTTP falha.
Vale avisar antes de reiniciar.

---

## 2026-10-02 — O outro ramo do seletor também saía calado

**O relato.** O 037 do MIX VALI pedido de outra máquina: "está carregando há um
tempo, não sei se travou" e, logo depois, **"ele nem gerou a opção de selecionar
o caminho para salvar"**.

**Não havia defeito no download.** A segunda frase é o diagnóstico inteiro: o
seletor abre **antes** do fetch, de propósito, porque a ativação do gesto do
clique não sobrevive a uma ida à rede. Se ele não apareceu, a requisição nem
saiu — e o que aconteceu depois foi o caminho antigo, que é o pior possível para
esse arquivo.

**A causa.** O `vite.config.ts` abre o dev server para a rede por padrão
(`host: CAT_HOST ?? true`, e o comentário diz "de outra maquina"). Quem acessa
`http://<ip>:5173` está fora de **contexto seguro**, e a `File System Access
API` simplesmente não existe ali. O código saía por `if (typeof seletor !==
"function") return null` — correto, e **sem uma linha no console**.

A correção de 01/10 havia posto o `console.warn` só no `catch`, que cobre o
seletor que existe e falha. O ramo em que ele **não existe** — o mais comum dos
dois — continuou mudo por nove dias.

**O que mudou.** `motivoSemSeletor()` responde por que não há seletor, e separa
os dois motivos **porque as soluções são diferentes**: contexto inseguro se
resolve abrindo por `localhost` ou https; navegador sem suporte (Firefox,
Safari) não se resolve. Vai ao console e, principalmente, **à tela** — o
analista não abre o console, e `BaixarPlanilha` está em quinze telas.

O aviso diz as três coisas que importam: onde o arquivo vai cair, por quê, e que
nesse caminho ele **passa inteiro pela memória** — então em lista grande vale o
CSV ao lado. O DOM só muda quando há o que dizer: o componente vive em
contêineres de linha e de coluna, e envolver sempre mudaria o layout de quinze
telas para avisar de um caso excepcional.

### O que a medição mostrou sobre a espera

Medido no MIX VALI: **644 arquivos e 15,8 GB na pasta, mas só 59 arquivos e 7,53
GB são EFD Contribuições** — o que o 037 lê. O resto é 567 EFD ICMS/IPI, 6 ECD,
5 ECF e 7 cabeçalhos irreconhecíveis.

```
leitura dos 7,53 GB         93 s     (81 MB/s)
itens de entrada            2.933.762 linhas
xlsx                        ~16 min, em 4 abas
csv                         27 s
```

**A leitura nunca foi o gargalo.** O xlsx é, e 2,93 milhões de linhas não cabem
numa aba de Excel de todo jeito. É a mesma conclusão de 01/10 no 680, agora numa
etapa diferente: acima de um milhão de linhas, o formato do MA é CSV porque o
Excel não é opção.

---

## 2026-10-01 — O formato dentro do pacote é o do arquivo de referência

**O que se mediu, no 680 da empresa 05 — 3.568.362 linhas, 35 colunas:**

```
csv      33 s     862 MB
xlsx  1.181 s     512 MB   em quatro abas
```

Vinte minutos é mais do que qualquer download espera, e um xlsx de meio giga não
abre no Excel nem quando chega. **O 680 vai em CSV no pacote**, e os outros três
em xlsx — 839 com 463.212 linhas, 903 com 138.358, 933 com 33.

**Não é contorno: é o formato do próprio MA.** O arquivo de referência do 680
veio em **CSV de 1,17 GB**; os do 839 e do 933 vieram em xlsx. A razão é a mesma
dos dois lados — o 680 é o detalhe geral da receita e não cabe num milhão de
linhas. Quem escolhe o formato do relatório é o tamanho dele, e o MA já tinha
escolhido.

O pacote inteiro: **249,5 MB em 312 s**. O CSV comprime de 862 para 121 MB; o
xlsx do 839 não comprime (107 → 105), porque xlsx já é um zip. O proxy da API
roda com `Timeout.InfiniteTimeSpan`, então cinco minutos passa — e a tela agora
**diz que leva alguns minutos**, ao lado do botão. Botão que demora cinco minutos
sem avisar é o mesmo "botão bugado" de hoje de manhã, com outra causa: quem não
sabe que vai demorar clica de novo.

### A rodada inteira, conferida de ponta a ponta

Cinco leituras dos 57 SPED em **497 s**. As duas frentes da tese 1:

```
                 consolidado        por item (680)
base          228.466.346,24      228.466.346,24     igual ao centavo
excluido       21.114.397,76       21.114.397,76     igual ao centavo
total           2.379.774,25        2.381.054,95     0,0538%
```

**A base e a exclusão batem ao centavo, e só o total difere.** É exatamente o que
tinha de acontecer: as duas partem da mesma receita — se divergissem aqui, uma
das duas estaria filtrando errado e nenhuma serviria para conferir a outra — e se
separam só no arredondamento, que é a escolha de 24/09/2026. O teste da etapa
passou a cobrar essa igualdade de base.

---

## 2026-10-01 — O 680 fecha em 100%, e quatro regras só o dado contou

**O relatório.** 680 — Metodologia 01 — Todos Registros — Por Documento e Itens:
as próprias contribuições fora da própria base, **item a item**, 35 colunas,
3.568.362 linhas no arquivo de referência da empresa 05. Fecha **100,0000%**, sem
linha a mais nem a menos, nas 57 competências.

**Quatro frentes agora, e duas delas são da mesma tese.** O consolidado soma por
grupo e arredonda uma vez por grupo — é o número que se pede; o 680 é o detalhe
que acompanha o pedido. A diferença de 0,06% entre os dois é a decisão de
24/09/2026, e está escrita nos dois módulos. Por isso o detalhe **não entra** no
`exclusoes.parquet`: a tese dele já está lá, consolidada, e gravar as duas no
mesmo arquivo daria a quem o somasse a tese 1 contada duas vezes.

### As quatro regras que a conferência arrancou

**1. A ausência é do ramo, não do campo.** O C170 traz ICMS, desconto e rateio
nas 602.510 linhas, **mesmo zerados**; o C175 traz só o desconto, nas 2.965.485;
o A170 e o F100 não trazem nenhum dos três — nem o A170, que tem `VL_DESC` no
leiaute e vem preenchido. Escrever zero no lugar do vazio divergia em 71.837
linhas de uma competência só. A primeira tentativa foi olhar se o campo de
origem estava vazio: certo por acidente em três ramos, errado no quarto.

**2. O rateio obriga a guardar o documento.** Frete, seguro e outras despesas
repartidos pelo valor do item sobre a soma de **todos** os itens da nota — o
frete foi pago pela nota inteira. São **10 linhas não-zero em 3,5 milhões**, e é
a diferença entre reproduzir o relatório e quase reproduzi-lo. O módulo dizia,
escrito por mim, que ali "não há buffer de documento"; o dado disse o contrário.

**3. Tributada basta; paga não.** Uma linha de **R$ 0,06** com CST 01 e alíquota
cheia recolhe R$ 0,00 nas duas contribuições por arredondamento, e o MA a traz.
Era a única das 81.193 linhas de 05/2021 que o filtro "PIS ou COFINS pago"
deixava de fora. A alíquota entra na pergunta **ao lado** do valor e não no lugar
dele: o monofásico de pauta tem valor sem alíquota percentual.

**4. O F100 sai somado por dia — uma linha, não várias.** Único ramo que o MA
consolida, e a razão está no leiaute: o F100 não tem número de documento, nem
modelo, nem item. Duas linhas suas com o mesmo CNPJ, CST, data e alíquota são
indistinguíveis no relatório. Medido: em cada grupo (CNPJ, competência, CST), o
número de linhas do gabarito é exatamente o número de datas distintas do grupo.
Somar reduziu 841 linhas nossas às 334 dele, ao centavo.

### O erro mais caro foi o que parecia inofensivo

**Registro sem CFOP entrava como faturamento por suposição.** O F100 e o A170
não têm CFOP, e eu os tratava como receita pelo simples fato de não haver o que
perguntar. Entravam **aquisições**: F100 de compra e serviço contratado, com CST
50 — CST de crédito, que só existe na entrada. R$ 193.939,37 de base num mês,
R$ 81,3 mil em outro, em linhas idênticas a todas as outras do relatório.

O sentido vem do `IND_OPER`: 1 no F100 é geração de receita (0 é aquisição, 2
outros documentos); 1 no A100 é serviço prestado (0 é contratado). O erro oposto
— perguntar o CFOP a quem não tem — é maior, e derruba R$ 10,28 milhões de base
(01/10/2026). Nenhum dos dois é palpite: os dois foram medidos contra o gabarito.

**O que fica em aberto, dito em voz alta.** O agregador da Gestão trata o F100
`IND_OPER = 2` como saída (`gestao/agregador.py`), e o 680 só aceita o 1. **Na
empresa 05 não existe nenhum F100 com `IND_OPER = 2`** — 281 de aquisição e 558 de
receita —, então as duas frentes concordam nesta base e não há como medir qual
está certa. Fica anotado para a primeira base que tiver: é divergência latente
entre o número que se pede e o detalhe que o acompanha.

### O conferidor passou a ler o gabarito em lotes

`tools/validar_680.py` materializava a tabela inteira — 3.568.362 × 35 = 125
milhões de strings Python de uma vez — e passou a estourar com `MemoryError`
antes de conferir coisa nenhuma. O arquivo não cresceu; a memória livre
encolheu. Agora lê por lote de 65.536, e o filtro de competência corre no lote
antes de virar objeto. Ganhou também: imprime **campo a campo** as linhas órfãs
das duas pontas. Linha sem par é mais grave do que mil colunas divergentes —
diz que não lemos o documento, e não que erramos a conta dele. Foi assim que as
quatro regras apareceram.

---

## 2026-10-01 — Um download que não baixava e não dizia nada

**O que o Victor viu:** os dois botões da tese das contribuições — a planilha e
o CSV — "bugados". Clicar não fazia nada.

**O que a investigação provou, antes de qualquer palpite.** A rota existe e
responde: chamada sem token devolve 401, e o middleware registra. O motor gera
os oito arquivos da tela — as quatro teses em xlsx e csv — sem erro. E o log da
API, no período inteiro, **não tem uma única requisição de planilha**. Nenhum
arquivo apareceu em Downloads, na Área de Trabalho ou na pasta de trabalho.

O clique morria no navegador, antes da rede.

**Onde.** `baixarArquivo` abre o seletor de "salvar como" **antes** do fetch, e
tem de ser assim: o navegador só mostra o seletor enquanto a ativação do gesto
do clique vale, e ela não sobrevive a uma ida à rede. O seletor era o único
ponto antes da requisição — e tinha um caminho que não deixava rastro.

**O defeito.** `showSaveFilePicker` avisa das duas coisas do mesmo jeito:
`AbortError` tanto para "o usuário desistiu" quanto para "não consegui abrir".
O código tratava os dois como desistência e seguia em silêncio — que é a
resposta certa para quem desistiu e a pior possível para quem clicou e não viu
nada acontecer. Sem download, sem arquivo, sem erro na tela.

**A correção: medir o tempo.** Ninguém abre uma janela do sistema, lê o nome do
arquivo e desiste em menos de 150 ms. Abortou depressa demais para alguém ter
lido? O seletor não apareceu, e vale o caminho antigo — entrega na pasta de
downloads e sempre funciona. Demorou o bastante? Foi decisão de quem clicou, e
silêncio é a resposta.

**Errar a favor do download é de propósito.** Baixar para a pasta errada é um
aborrecimento; não baixar nada é um defeito. E fica um `console.warn` dizendo
que o seletor não abriu, para a próxima investigação começar com a resposta em
vez de meia hora de eliminação.

**A lição de método.** O que resolveu não foi ler o código — li o caminho
inteiro, do botão ao fetch, e ele estava certo. Foi **provar onde o clique não
chegava**: rota chamada por fora, log conferido, disco varrido. Defeito de
front com sintoma "não faz nada" se acha por eliminação de caminhos, não por
leitura.

### A segunda rodada, e o defeito de verdade

A primeira correção não bastou, e o relato seguinte deu a informação que
faltava: **o seletor abre, a pessoa escolhe, e ele volta a pedir o diretório.**
Dessa vez o log mostrou uma requisição com **status 200 em 80 ms** — a planilha
veio do servidor — e o disco continuou sem arquivo nenhum.

Ou seja: o problema não era chegar ao servidor. Era o que acontecia **depois**
dele, e ali todo caminho de falha era silencioso:

* `pipeTo` abortado avisa com `AbortError`, igualzinho a um cancelamento;
* `DownloadCancelado` é engolido de propósito pelo `executar` — quem cancelou
  sabe que cancelou;
* e `descartar` apaga o arquivo que o seletor já tinha criado.

Três acertos isolados que, somados, produzem o pior resultado possível: 200 no
servidor, nada no disco, nada na tela.

**E havia uma armadilha que fecha o laço.** O botão que baixava **virava
"Cancelar"** enquanto baixava, no mesmo lugar. Quem clicava de novo achando que
travou abortava o próprio download e apagava o arquivo; o clique seguinte abria
o seletor outra vez. O laço que o usuário descreveu era isso.

**O que mudou.** O Cancelar saiu de cima do botão e foi para o lado — clicar
duas vezes no mesmo lugar voltou a ser inofensivo, que é o que se espera de um
botão de baixar. E a gravação que falha **sem ninguém ter cancelado** agora diz
isso na tela, em vez de sumir: só é cancelamento quando o sinal foi abortado de
verdade.

**A regra que fica:** erro que o servidor não viu é erro que só o usuário vê.
Caminho de cliente que termina em silêncio precisa provar que houve
desistência — e, na dúvida, falar.

---

## 2026-10-01 — O 680 existia, e a tese 1 tinha duas lacunas de dinheiro

**A pergunta do Victor:** "não encontrou nada de PIS/COFINS da própria base?"

Eu havia respondido, no dia anterior, que **o MA não produz esse relatório** —
conclusão tirada da ausência do arquivo na pasta do cliente. Ele produz: é o
**680 — Metodologia 01 — Todos Registros — Por Documento e Itens**, 1,17 GB,
3.568.362 linhas. Conclusão tirada de ausência é palpite com cara de fato, e
esta base já havia ensinado isso duas vezes.

**A metodologia é a nossa, e o próprio nome diz que há outras.** O MA numera:
"Metodologia 01". Medido nas 3.568.362 linhas, a base do PIS e a da COFINS
depois da exclusão são **iguais em 100%** — é a leitura escolhida em
24/09/2026, a base de cada uma perdendo as duas. A leitura conservadora seria
outra metodologia, com outro número.

### A primeira lacuna: não corrigíamos pela Selic

O 680 trazia R$ 755.828,97 de Selic que o nosso relatório não mostrava. Pior: eu
havia **escrito no código** que "esta tese não corrige por Selic", ao
acrescentar as colunas de correção ao parquet agregado. Tratei como
característica o que era lacuna — e a frase no código fazia a lacuna parecer
decidida.

A correção é aplicada **uma vez por grupo**, que é onde esta tese arredonda
desde 24/09. Corrigir a soma da competência daria outro centavo, e os dois
arredondamentos têm de morar no mesmo lugar.

### A segunda: "só no débito" não quer dizer "só a saída"

O filtro era `operacao == SAIDA`, e errava nos **dois** sentidos:

* deixava entrar **remessa, bonificação e baixa de estoque** (CFOP 5924, 5927,
  5901, 6901, 5910) — são saída e não são receita: R$ 215.706,22 de base a mais;
* deixava de fora a **devolução de venda** (1411, 1202, 2411) — é entrada, mas é
  estorno de receita tributada, não aquisição: R$ 723.198,32 de base a menos.

A decisão de 24/09 dizia "o crédito das **aquisições** fica como está", e o
código lia isso como "toda entrada fica de fora". Devolução de venda não é
aquisição.

**A devolução entra com o CST que tiver.** Ela se escritura com CST de crédito —
50, 73, 98 e 99 nas 8.822 linhas do 680 —, e exigir CST de receita era o que a
derrubava mesmo depois de corrigir o filtro de CFOP.

### E o registro que não tem CFOP

A primeira versão do filtro por CFOP derrubou o **A170 e o F100**: eles não têm
CFOP no leiaute, e a classificação devolvia vazio. Eram R$ 10,28 milhões de
base — um erro maior que os dois que a mudança vinha consertar.

O MA deixa a solução à vista: na coluna "CFOP" dessas linhas ele escreve **"S"**
— o sentido da operação, não um CFOP — e classifica como faturamento. Então a
regra é: **o CFOP responde quando há CFOP; o sentido, quando não há.**

### O resultado

Base e exclusão passaram a bater **ao centavo** com o 680:

| | nosso | 680 |
|---|---|---|
| base escriturada | 228.466.346,24 | 228.466.346,24 |
| excluído da base | 21.114.397,76 | 21.114.397,76 |
| total | 2.708.188,08 | 2.709.812,46 |

Os R$ 1.624,38 que sobram (0,06%) são a divergência **escolhida** em 24/09: o MA
arredonda linha a linha nas 3,5 milhões de linhas; nós arredondamos uma vez por
grupo, nos 433, com a alíquota efetiva de cada um. Aparece nas colunas: o nosso
PIS é R$ 36,8 mil menor e a COFINS R$ 168,6 mil maior, e os dois se compensam.

### A classificação de receita mudou de casa

`classificacao_do_cfop` morava dentro de `sped/exclusao_do_icms.py`, de onde
nasceu. Agora serve às **quatro** teses, e foi para
`sped/tabelas/tab_cfop_receita.py`: tese nenhuma deve importar regra fiscal do
módulo de outra, e regra que serve a quatro não é de uma.

---

## 2026-10-01 — Sessenta testes de exclusão, e nenhum rodava a etapa

**O defeito.** `exclusao_do_icms_st` e `exclusao_do_iss` não reexportavam
`serializar` de `exclusoes_por_item`. `exclusoes.apurar` chama `serializar` nos
três módulos de tese, e a apuração morria com `AttributeError` — **na tela do
usuário, no meio da rodada.**

**Por que passou.** Havia 60 testes de exclusão e nenhum chamava
`exclusoes.apurar`. Cada tese era conferida sozinha, e bem: os três motores
batem 100% contra os gabaritos do MA, 601.603 linhas. Os validadores também
chamam o motor direto. **A costura — a função que roda as quatro teses, junta os
resumos e grava o parquet agregado — nunca era exercitada por ninguém.**

A conferência que eu apresentei como completa tinha esse buraco, e ele não era
pequeno: era justamente o caminho que a tela dispara. Motor conferido contra
gabarito não é o mesmo que etapa que roda.

**A forma do erro também explica como ele nasceu.** Quem escreve o terceiro
módulo copia o segundo, e o segundo foi escrito copiando o primeiro — menos o
que o primeiro não precisava declarar, porque era o único. A superfície do
módulo é exatamente o tipo de coisa que a cópia perde e que nenhum teste de
cálculo olha.

**Duas portas fechadas, e são portas diferentes.**

`test_analitico_superficie_das_exclusoes.py` cobra que os três módulos exponham
o que a etapa chama — `apurar`, `serializar`, `Andamento`, `Resumo` —, que o
`serializar` seja o mesmo nos três, e que cada tese tenha nome e arquivo
próprios. É barato e pega a quarta tese que nascer por cópia.

`test_analitico_exclusoes_na_etapa.py` roda `exclusoes.apurar` inteira sobre um
SPED minúsculo com as três teses dentro, e confere o que fica em disco: os
quatro parquets, a coluna `tese` separando as quatro no agregado, as colunas da
correção, e as quatro fases chegando ao `avisar` — barra que não recebe uma fase
é barra travada. Com a versão publicada, ele reproduz o `AttributeError`.

A superfície pega o sintoma; a etapa pega a sala. Um argumento com nome errado,
um resumo que não serializa ou o agregado sem uma tese passariam pela primeira e
caem na segunda.

**A regra que fica.** Tese conferida contra gabarito prova o **cálculo**. A
etapa que a entrega precisa do seu próprio teste, e ele tem de ser o caminho que
a tela dispara — não o motor por baixo dela. Vale varrer as outras etapas atrás
do mesmo buraco.

---

## 2026-09-30 — Importar ganha card próprio, e frente de uma etapa vai direto

**O pedido do Victor:** subir arquivo pela Quebra de SPED não faz sentido; abrir
um card para importar arquivos facilita a viabilidade dos processos.

**O que estava errado.** `importar` era a **primeira etapa de cada trilha**. A
intenção era boa — a base é a mesma para todas as frentes, quem importou para a
CAT 42 já importou para o crédito outorgado — mas o efeito na tela era o oposto:
para mandar a base de um cliente era preciso **entrar numa frente de trabalho**
e achar o card de importar dentro dela. Quem só tinha arquivo para subir
atravessava a Quebra de SPED, que não tem nada com isso.

O erro não era de código: era de classificação. Importar não é etapa de nenhuma
frente — é o que vem antes de todas.

**O que passou a valer.** `importar` é o **primeiro card de todo módulo**, com
uma etapa só, e nenhuma outra trilha a lista. Três testes cobram isso: que ela é
a primeira de cada módulo, que nenhuma outra a repete, e que módulo sem frente
de apuração construída ainda tem como importar.

**Dois ganhos que não estavam no pedido.**

O IRPJ/CSLL não tinha frente nenhuma construída, e a tela dizia só "nenhuma
frente construída ainda" — **sem caminho nenhum para subir arquivo**, que é
exatamente o que aquele módulo faz hoje. Agora tem o card.

E a contagem de cada frente passou a ser sobre o trabalho dela. Antes a CAT 42
dizia "1 de 8" com a base importada e mais nada feito; o "1" era o importar, que
não é etapa da CAT 42.

**Frente de uma etapa só vai direto para a tela dela.** Sem isso o card novo não
resolveria nada: project → card → painel com um card → tela seriam os mesmos
três cliques de antes. Abrir uma página para mostrar um card e nada mais é um
clique cobrado sem nada em troca.

A regra é geral, e não um caso especial do importar — tirar `importar` de dentro
das trilhas deixou quase todas com uma etapa, e todas se beneficiam. A CAT 42,
que tem sete, continua abrindo o painel.

**Um defeito que a mudança acordou.** O DTO da trilha calculava "construída"
com `Chave != "importar"`, para que nenhuma frente parecesse construída só por
ter a base. Com `importar` virando trilha própria, essa exclusão passou a apagar
justamente o card novo — ele ficaria cinza, dizendo "ainda não construída", e
sem destino. A exclusão saiu: qualquer etapa própria da frente serve, porque
agora `importar` só aparece na frente em que ela é a etapa.

**A dependência não se perdeu.** Ela nunca morou na lista de etapas da trilha:
continua cobrada por quem pode cobrá-la — o servidor, que recusa a etapa sem
lote e devolve a frase que explica o que falta — e a faixa de leiautes, no topo
das duas telas, continua dizendo quantos arquivos de cada tipo o trabalho tem. O
roteiro do módulo também segue começando por `importar`, porque ele nunca saiu
de lá: é derivado das trilhas com a base posta na frente.

---

## 2026-09-30 — A alíquota interna tem data, e a prova dela não pode vir do MA

**O apontamento do Victor:** conferir a alíquota interna pela métrica do MA não
serve. Está certo, e por duas razões que se somam.

**A primeira é circularidade.** O relatório do MA traz a alíquota que **ele**
atribuiu a cada produto. Conferir a nossa contra a dele é copiar a classificação
alheia com aparência de medição — exatamente o que a decisão do 839, hoje mais
cedo, existiu para evitar quando separou a regra (lei, no código) do cadastro
(cliente, no banco). Usar o MA como prova desfaria a separação pela porta dos
fundos.

**A segunda apareceu ao procurar a primeira, e é pior.** A tabela que eu tinha
escrito guardava **um número por estado, sem data**. Um pedido de restituição
cobre cinco anos, e vários estados subiram a alíquota interna entre 2023 e 2025:
a tabela aplicaria a alíquota de hoje a uma operação de 2021, calada. Em Minas
não mudou — e é só por isso que a conferência do 839 fechou 100% sem esta coluna
existir. Foi sorte, e sorte não é método.

### O que passou a valer

**A alíquota tem vigência.** Cada estado guarda uma linha por período, com o ato
legal escrito, e `da_regra` recebe a competência. Acrescentar vigência é um ato
comum; esquecê-la deixou de ser possível.

**Só entra na tabela o que foi medido.** `INTERNA` tem hoje **uma** UF: MG a
18%, conferida na EFD ICMS/IPI da empresa 05 — 201 arquivos, 2021 a 2025, em que as
saídas internas tributadas integralmente mostram 18% em 56% a 59% das linhas
todos os anos, sem degrau. As outras 26 saíram para `A_CONFERIR`, que o motor
**recusa**, com um recado que diz como conferir e avisa que o relatório do
escritório anterior não serve de prova.

Recusar bloqueia o 839 fora de Minas até alguém gastar meia hora com a lei. É
deliberado: errar a interna em um ponto e meio sobre os R$ 117 milhões de base
de um cliente médio são R$ 160 mil de crédito pedido indevidamente, e esse erro
não aparece em lugar nenhum do relatório — vira só um número maior. Ninguém
confere um número que veio grande a favor do cliente.

**A exceção do produto vence a regra, e dispensa o estado estar conferido.**
Quem cadastrou a exceção daquele item sabe dele mais do que a alíquota geral do
estado. Isso também dá um caminho a quem tem o cadastro do cliente e não tem a
lei na mão.

### A prova que serve

`tools/aferir_aliquota_interna.py` lê a EFD ICMS/IPI do próprio cliente e mostra,
ano a ano, a alíquota que ele cobrou nas saídas internas tributadas
integralmente — e aponta o **degrau**, quando a dominante muda de um ano para o
outro, que é o que diz quantas vigências a tabela precisa ter.

**É evidência, não decisão**, e o comando diz isso ao terminar: a moda das
vendas de um cliente não é a lei. Um cliente cujo catálogo fosse todo de cesta
básica mostraria 12% como dominante. Quem escreve a linha confronta este número
com a legislação estadual e assume o que assinou — e a linha guarda o ato legal
ao lado da alíquota, para que a assinatura tenha onde se apoiar.

---

## 2026-09-30 — O 933: o ISS, e a descoberta de que cada relatório tem a sua conta

A exclusão do ISS da base do PIS/COFINS fecha **100% contra o gabarito do MA**:
33 linhas, 32 colunas. Com ela, os três motores da família de exclusões estão
medidos — 903 (ICMS), 839 (ICMS-ST) e 933 (ISS).

**É o menor e o mais instrutivo.** Das 33 notas de serviço da empresa 05, **uma**
tem ISS preenchido: R$ 5.586,51, que rendem R$ 646,71 corrigidos. O campo
`VL_ISS` do registro A100 é facultativo, e quando vem vazio o valor não se
perde — ele está na NFS-e, que este motor ainda não lê. Até lá a linha sai com a
coluna do ISS **em branco**, e o resumo conta quantas são: é o número que diz
quanto da tese está esperando o XML.

**Uma linha só parecia pouco para conferir, e não era.** É ela que exerce a
conta inteira — rateio, base STF, diferença, Selic e total —, e foi ela que
revelou o achado abaixo. As outras 32 exercem o caminho oposto, o de não haver o
que excluir, que é o que acontece na maioria das notas de serviço.

### Cada relatório do MA tem a sua aritmética, e não dá para supor

Foi a terceira vez neste dia que dois relatórios do mesmo sistema discordaram
numa regra que parecia universal. Vale listar as três, porque juntas formam uma
lição de método:

1. **A diferença da contribuição.** O 903 calcula `PIS − PIS STF`; o 933 calcula
   `diferença da base × alíquota`. Na única nota com ISS, a primeira dá 92,17 e
   a segunda 92,18 — e o gabarito escreve 92,18. No 903, a subtração está medida
   em 138.358 linhas. As duas estão certas, cada uma no seu relatório.
2. **O completamento do cadastro pela matriz.** A 047 completa; o 839 não. Ver a
   decisão do 839, hoje.
3. **A base recalculada.** A do 903 subtrai o imposto; a do 933 não — ela é só
   `valor − desconto`.

A conclusão prática: **regra medida num relatório não se transporta para outro
sem medir de novo.** Cada motor tem o seu conferidor, cada conferidor tem o seu
gabarito, e nenhum deles empresta conclusão do vizinho.

### Duas outras coisas que o gabarito ensinou

**Vazio não é zero.** O MA preserva a ausência: `VL_DESC` em branco sai em
branco na planilha, `VL_DESC` igual a "0,00" sai zero. Para quem confere são
coisas diferentes — "não informou" e "informou zero" —, e tratá-las como a mesma
divergia em todas as linhas sem desconto.

**"Percentual Rateio" é fração.** Vale `1`, não `100`. Como todos os documentos
do arquivo têm um item só, o rateio entre vários itens não tem uma linha sequer
para conferir: a divisão está no código pela conta, não pela medida, e isso está
dito no módulo.

---

## 2026-09-30 — O 839: o ICMS-ST que não está escrito em lugar nenhum

A exclusão do ICMS-ST da base do PIS/COFINS — a tese do contribuinte
**substituído** — fecha **100% contra o gabarito do MA**: 463.212 linhas, 46
colunas. Vale R$ 2.668.059,20 para a empresa 05.

**A pergunta que a medição respondeu antes de haver código.** A cadeia pedida
cobre só a EFD-Contribuições, e ali o ICMS-ST simplesmente não existe: a revenda
com ST já retido tem CST 60, que por definição não destaca imposto. Medido nos
57 arquivos e também na EFD ICMS/IPI do mesmo cliente — **zero** linhas com ST
destacado, nem na entrada, nem na saída, nem no analítico C190.

Então o MA **presume**, e nós reproduzimos:

```
base presumida = valor do item − desconto + rateio de frete/seguro/despesas
ICMS-ST        = base presumida × alíquota  (ao centavo)
base STF       = base do PIS/COFINS − ICMS-ST
```

As três fecham em 100% das linhas. **Não há a guarda do "já excluiu" do 903**,
e não faria sentido: o que nunca foi escriturado não pode ter sido excluído.

**Isto é arbitramento, e está dito onde precisa estar.** O 903 devolve o que o
arquivo tem; o 839 devolve uma reconstrução. A fórmula está no topo do módulo
para que o pedido seja defendido por ela, e não por um número que saiu de uma
caixa preta.

**A alíquota: o que é lei ficou escrito como lei.** Podia-se copiar as 7.276
alíquotas do relatório do MA e fechar 100% sem pensar. Não se fez. A regra —
alíquota interna do estado, ou a Resolução 22/1989 do Senado na interestadual —
mora em `tab_aliquota_icms` e **acerta sozinha 98,66%** das linhas. O que sobra
são 556 pares de (estabelecimento, UF, item): cesta básica a 12%, supérfluo a
25%, isento a 0%, importado a 4%. Isso é classificação fiscal de mercadoria, é
cadastro do cliente, e por isso vai para o banco — nunca para o repositório.

A tentativa de derivar essa classificação do próprio SPED foi feita e falhou, o
que também está medido: o `ALIQ_ICMS` do registro 0200 é facultativo e veio
vazio nos 8.061 cadastros; o NCM não determina a alíquota (71 NCMs têm mais de
uma, atingindo 84% das linhas); e derivar das vendas tributadas do próprio
cliente cobre 30 de 595 itens.

**Os dois relatórios são disjuntos, e isso foi confirmado pelos dois lados.** Um
item entra no 903 (ICMS próprio) ou no 839 (ICMS-ST), nunca nos dois — quem
separa é a CST de ICMS: 00 é tributada integralmente e vai ao 903. As três
linhas que sobravam aqui tinham CST 00, e as três estão no gabarito do 903. Dos
601.570 itens dos dois relatórios, 8 aparecem em ambos: são CST 10 e 70, em que
há ICMS próprio **e** ST na mesma linha, e aí a dupla presença é correta.

**Nem todo relatório do MA completa o cadastro pela matriz.** A 047 completa — é
de lá que a regra foi medida, em 29/09. O 839 não. Nas três linhas de
setembro/2023 em que a filial cadastrou "SALAME ITALIANO PAMPLONA KG" sem código
de barra e a matriz tem o mesmo código como "DETERGENTE LIMPOL", o 839 escreve o
EAN em branco e a 047 escreveria o do detergente. Em vez de uma segunda classe
quase igual, `CadastroPorEstabelecimento.linha()` ganhou `completar=False`, e a
diferença entre os dois relatórios ficou escrita lá.

**O zero negativo.** `Decimal("-0.001")` arredondado ao centavo vira `-0.00`, que
sai na coluna como "-0"; o MA escreve "0". Eram 192 das 463.212 linhas, todas de
produto com alíquota zero, em que a diferença é só resíduo de arredondamento.
Menos um sinal não é menos dinheiro, mas é uma coluna que não bate.

**O que ainda falta**, e está no roteiro: a tabela `aliquota_de_item` no banco
com o seu carregador, a camada analítica, a planilha, o bloco próprio na tela e
os testes.

---

## 2026-09-30 — A Selic sai do código e vai para o banco, buscada só pelo que falta

**O pedido do Victor.** Atualizar a Selic pela API, "porém sempre salvar no
banco o que já existe", já que a de anos anteriores não muda.

**A observação que sustenta o desenho.** Taxa de mês fechado é publicada uma vez
e vale para sempre: a de março de 2021 hoje é a mesma de daqui a dez anos.
Então buscar a série inteira a cada rodada seria pagar rede para receber o que
já se sabe — e, pior, pôr um cálculo que vira pedido de restituição na
dependência de um serviço de terceiro estar no ar naquele minuto.

**A regra, em uma frase: o banco é a memória, a API é só o que falta.** Tabela
`selic_mensal`, uma linha por mês, sem empresa e sem projeto — a Selic é a mesma
para todo mundo. Na primeira vez o banco recebe a tabela que o time mantinha em
código (`tab_selic.MENSAL`, marcada com fonte `repositorio`); daí em diante a
rodada calcula quais meses faltam para corrigir até o mês da restituição e
busca **só esses** na série 4390 do SGS. Quando não falta nenhum — o caso normal
depois da primeira rodada do mês — não há chamada nenhuma.

**Mês guardado nunca é sobrescrito.** Nem quando a API o devolve diferente.
Deixar uma consulta de hoje reescrever o número que corrigiu um pedido de ontem
seria mexer em dinheiro por conta própria. Divergência vira **aviso no log**,
com o guardado e o recebido lado a lado, e alguém decide.

**Um mês de sobreposição, de propósito.** A busca começa um mês antes do
primeiro que falta. Esse mês já está no banco e não será sobrescrito — ele
existe só para que a divergência acima possa ser detectada. Custa uma linha de
JSON, e é o único sinal que teríamos de uma revisão do Banco Central.

**Rede fora não derruba rodada.** Falha na consulta vira aviso e a rodada segue
com o que está guardado. O que **não** muda é a recusa: se a série não cobre o
mês da restituição, a etapa não corrige a menos — diz o que falta e para. Foi
medido nos dois sentidos: apagando dois meses do banco, a rodada os rebusca e os
grava com fonte `bcb-sgs-4390`; pedindo correção até 12/2026, que o Banco
Central ainda não publicou, ela recusa.

**Sem dependência nova.** `urllib` da própria Python resolve um GET que devolve
JSON. Uma biblioteca a mais num motor que roda na máquina de quem trabalha custa
mais do que as vinte linhas que pouparia.

**O motor continua puro.** `sped/exclusao_do_icms.py` não conhece banco: recebe
a série pronta no parâmetro `mensal`. Quem decide **qual série** é a camada de
infraestrutura; quem sabe **somar** é `tab_selic`. Foi o que permitiu conferir a
mudança inteira contra o gabarito sem tocar em nenhum número — 138.358 linhas e
R$ 625.871,38, idênticos aos de antes.

---

## 2026-09-30 — Tema 69: sai da EFD-Contribuições sozinha, e a Selic estava errada em dois lugares

O relatório 903 — a exclusão do ICMS da base do PIS/COFINS, item a item — fecha
**100% contra o gabarito do MA**: 138.358 linhas, 40 colunas, conferidas uma a
uma. O total a recuperar bate ao centavo: R$ 625.871,38.

**A decisão de 22/09 foi revista, e o motivo é medição.** Aquela nota decidiu
cruzar sempre a EFD-Contribuições com a EFD ICMS/IPI, porque `VL_ICMS` no C170
da Contribuições não é de preenchimento obrigatório e um arquivo em branco seria
"o caso normal de metade dos clientes". Nos 57 arquivos da empresa 05 — cinco anos,
três estabelecimentos, 138.358 itens com ICMS destacado — **não há um caso**. E o
relatório do MA, que é o padrão que o cliente confere, sai do mesmo campo: se
ele cruzasse com a EFD ICMS/IPI, nossos números não bateriam com os dele, e
batem nos 40.

Então a tese se apura da EFD-Contribuições sozinha. O risco que sobrava —
cliente com o campo em branco — vira um sintoma visível, não um número errado:
sem ICMS destacado, o item simplesmente não entra no relatório, e a competência
aparece com zero. O risco de verdade, que a nota de 22/09 não via, é o oposto:
**excluir duas vezes**. Quem já apurou o Tema 69 tem a base do PIS/COFINS
escriturada já líquida de ICMS, e pedir de novo sobre ela seria pedir o que já
foi pedido. É contra isso que existe a base recalculada.

**Os quatro filtros, e o que cada um evita.** Entra o item que tem CFOP de venda
ou de devolução de venda (o Tema 69 é sobre receita), ICMS destacado maior que
zero (sem ele não há o que excluir), base de PIS/COFINS maior que zero, e
contribuição efetivamente paga. O item que não passa não some do arquivo — ele
nunca esteve no relatório; o que aparece com crédito **zero** é outro caso: a
nota cuja base já excluiu o ICMS. Essa fica, porque conferir que algo foi feito
certo também é trabalho, e some-la faria o relatório parecer menor do que o do
escritório anterior sem explicar por quê.

**O defeito que o CNPJ denunciou.** 61 linhas saíam com o CNPJ errado — o da
filial seguinte. O motor guarda a nota em buffer (o rateio do frete só se reparte
quando se conhecem todos os itens dela) e só fechava o documento no `C100`
seguinte. Quando a nota era a **última do bloco `C010`**, o fechamento
acontecia depois que o `C010` do próximo estabelecimento já tinha trocado o CNPJ.
O mesmo descuido estava latente no 037; a 047 já fechava — foi lá que a lição
apareceu primeiro, e não tinha sido levada às outras duas.

Vale reparar em como o defeito se mostrou: a contagem batia, os valores batiam,
99,96% das linhas eram idênticas. Só a conferência **coluna a coluna** das 61
linhas sem par disse qual campo era. Conferir por total teria dado igual.

**A tabela da Selic estava errada duas vezes, e nenhuma das duas aparecia.**

A primeira: a série foi derivada das diferenças entre competências consecutivas
do próprio gabarito, e cada diferença foi guardada sob a competência de origem.
Mas `acumulada(M) − acumulada(M+1)` é a Selic de **M+1**. A série inteira estava
deslocada um mês. Refeita da **série 4390 do SGS do Banco Central** — a mesma
que a Receita publica —, e conferida: bate nos 56 meses que o gabarito cobre.

A segunda: faltava a defasagem do pagamento. A regra corrige a partir do mês
seguinte ao do **pagamento**, e o PIS/COFINS de uma competência vence no dia 25
do mês seguinte a ela — logo a soma começa **dois** meses depois da competência.
Sem isso, todas as 57 competências vinham com uma parcela a mais de Selic.

Por que nenhuma das duas aparecia: a conferência do 903 rodava com
`--selic-do-gabarito`, que empresta a acumulada do próprio gabarito e **pula a
tabela inteira**. A tabela existia, era importada, e nunca era exercitada. Foi
só tirar a muleta para os dois erros caírem juntos. Fica a regra:
**conferência que contorna o código não confere o código** — e por isso
`tests/unidade/test_tab_selic.py` agora compara a tabela com a série do Banco
Central, mês a mês.

**A tese não usa o agregado da Gestão, e não tem como usar.** A outra tese desta
etapa parte de somas por competência, CST e CFOP, e volta em segundos. Esta se
apura no item: a base recalculada se reconstrói do valor, do desconto, do rateio
e do ICMS de cada item, e é assim que se sabe quais notas já excluíram o ICMS.
Agregado não tem item; tem soma de item. São 57 arquivos em 53 segundos — barato
perto de pedir restituição em duplicidade.

**O que prescreveu aparece e não soma.** Sete competências da empresa 05 estão fora
dos cinco anos: R$ 72.445,95, que o relatório mostra em vermelho e o total não
inclui. O relatório do MA soma as duas coisas num número só.

---

## 2026-09-30 — Cinco rodadas longas recusavam cancelamento, e a lista era a culpada

**O que o usuário viu.** "Esta etapa ainda não aceita cancelamento", com 71
arquivos na fila e uma apuração de PIS/COFINS no quinto deles.

**A causa.** O cancelamento tem duas metades: a rodada precisa conferir o freio,
e a etapa precisa estar em `ETAPAS_CANCELAVEIS`. As duas saíram de sincronia —
o sistema passou a **onze** etapas com freio e a lista continuou com as **seis**
originais. Recusavam cancelamento sabendo parar: quebra de SPED, apuração de
PIS/COFINS, exclusões, Gestão Fiscal e crédito outorgado.

**Por que passou despercebido.** É um defeito que não quebra nada: quem
acrescenta o freio a uma etapa nova e esquece a lista não vê teste falhar, nem
erro em log. Só o usuário descobre, e no pior momento — com a rodada longa em
curso, que é exatamente quando cancelar importa.

**A correção não foi completar a lista.** Foi escrever um teste que lê o
**código-fonte** dos casos de uso: toda etapa que constrói um `Freio` tem de
estar autorizada, e nenhuma sem freio pode estar. Autorizar quem não para seria
pior que o defeito original — a tela diria que vai parar uma rodada que vai até
o fim. As três que ainda não param — conferência, movimentos e quebra de XML —
ficam nomeadas no teste, para que dar freio a uma delas cobre a atualização.

## 2026-09-30 — O chip do CFOP sumia de rótulo, e era `any_value`

Um teste da tela da 047 falhava de vez em quando e passava sozinho. Não era
defeito de teste: o resumo montava o rótulo do CFOP com `any_value`, que o
DuckDB resolve sem garantia nenhuma. Quando as linhas de um mesmo CFOP
discordam — uma com descrição, outra sem —, o chip saía **sem rótulo, de forma
aleatória, de uma carga para a outra**. `max` sobre texto prefere o não vazio e
é determinístico.

Fica a lição para as outras agregações da casa: `any_value` só serve onde todas
as linhas do grupo são iguais por construção. Onde podem divergir, ele troca um
dado por outro sem avisar.

---

## 2026-09-30 — O gabarito do 037 derruba cinco deduções, e a 037 passa a bater inteira

**O que entrou.** O gabarito do 037 da empresa 05 — 458.792 linhas, 57
competências, em xlsx. Conferido linha a linha pelo `tools/validar_037.py`:
**458.792 de 458.792, zero divergência.**

A 037 existia desde a v0.74.0 e era tida por validada. Estava errada em sete
pontos, e nenhum deles mudaria um centavo de somatório — são colunas de
classificação, de texto e de crédito. É a segunda vez na semana que comparar
linha a linha acha o que comparar total esconderia.

### As cinco regras que eram dedução e viraram medida

**O CFOP vem por extenso.** Montando a 047 eu concluíra que a grafia abreviada
era a da 037; era da Gestão. As duas consultas do MA escrevem "Compra para
comercialização", e a nossa `tab_cfop` dizia "Compra p/comercial" — 8.020 das
8.040 linhas de uma competência. As 31 grafias de entrada foram geradas do
próprio gabarito, sem transcrição.

**A natureza do crédito não tem segunda tentativa.** Havia um recurso ao
`TIPO_ITEM = "00"` para o CFOP que a tabela não conhece. Nas 107 linhas em que o
gabarito deixa a natureza vazia, o CFOP é sempre um não mapeado — e em 84 delas
o tipo é "00", exatamente onde a regra escrevia "01 - Aquisição de bens para
revenda". Era natureza inventada, e o cliente a leria como lida. E a tabela
estava incompleta: entraram 1124→03 (serviços), 1113→01 e 2122→02.

**O MA encurta o texto da 4.3.7.** Onde a tabela oficial diz "Energia elétrica e
térmica, inclusive sob a forma de vapor", a 037 escreve "Energia elétrica e
térmica". Quatro dos dez textos. `tab_437` guarda as duas grafias, como
`tab_cfop` — a oficial é a da lei e a da tela; a do MA é a de quem compara
relatório com relatório.

**O ICMS só sai no ramo do C170.** O C500, o D100 e o D500 trazem `VL_ICMS` e
nós os escrevíamos. Não é "vazio porque é zero": no C170 o MA escreve `0` em
centenas de milhares de linhas. É por ramo.

**A conta contábil vem do registro da COFINS.** Nos 443 pares em que C501 e C505
apontam a mesma conta, tanto faz; nos **2** em que divergem, o MA segue o C505
nos dois. Um deles é conta de energia elétrica contra "mercadorias para
revenda" — erro visível a olho nu para quem seguir o registro do PIS.

### O D/C deixou de ser hipótese

Era "C quando o CST é 50 e há PIS", declarado no código como ~98% de aderência
com as discordâncias "concentradas em CFOP de devolução". **A concentração era
real e me enganou**: todo branco era devolução, mas nem toda devolução era
branco — das 17.460 devoluções, 7.881 têm "C". Inverti a regra e passei de 8
para 116 erros numa competência.

O que separa são três condições, e as três foram medidas contra as 458.792:

1. o **CST dá direito a crédito** — 50 a 56 e 60 a 66, não só o 50; há CST 53;
2. há **base de cálculo**, e não valor: alíquota zero sobre base positiva
   continua gerando crédito. Pelo valor do PIS erra 9; sem condição erra 42;
   pela base erra **zero**;
3. o **participante não é pessoa física** — identificado e sem CNPJ. São as 879
   linhas que me enganaram: é o consumidor, não a devolução, que tira o crédito.

As três fazem sentido tributário, o que é bom sinal de que valem noutro cliente.

### Duas ausências preenchidas

**A coluna `Código Serviço`**, que o MA tem e nós não tínhamos — vem do
`0200_COD_LST`. Nossa 037 fica com 53 colunas: as 52 do MA mais o **Município do
Participante**, que é acréscimo nosso da v0.76.0 e não tem par no gabarito.

**O ramo A100/A170**, nota de serviço tomada. O módulo declarava tê-lo deixado
de fora por não haver ocorrência; o gabarito tem 2 linhas, e foi com elas na mão
que o ramo entrou. A natureza do crédito dele é **lida** do `A170_NAT_BC_CRED` —
nota de serviço não tem CFOP de onde deduzir. Dos outros dois ausentes,
C395/C396 e F150, a empresa 05 não tem nenhuma ocorrência.

### O que o gabarito erra, e nós não

Duas divergências eram defeito **dele**, e o conferidor passa a reproduzi-las
para não acusar erro onde não há:

* **a codificação.** A EFD é cp1252, onde o byte 0x92 é o apóstrofo `’`. O MA
  decodifica como latin-1 e grava um caractere de controle no nome do
  participante: "STELLA D⟨controle⟩ORO". São 10 linhas;
* **o D105 inconsistente.** Em 2 fretes o D105 declara natureza diferente do
  D101 do mesmo documento, e o MA descarta o lado da COFINS inteiro — valores e
  conta. Aqui a escolha foi **replicar**, decidida em 30/09/2026: o efeito é
  deixar de mostrar R$ 586,68 de COFINS que o arquivo declara. A prova são dois
  casos contra 255, e isso está escrito na própria função.

---

## 2026-09-29 — A 047 ganha tela: recortar antes de olhar, e baixar o que se olhou

**O problema que o download não resolve.** A 047 do cliente de referência tem
7.784.121 linhas. O Excel para em 1.048.576 por aba, e mesmo que abrisse,
ninguém lê sete milhões de linhas — quem confere quer uma competência, um CFOP,
uma nota. O download continua valendo para quem leva o arquivo inteiro para
outro sistema; a tela existe para o outro gesto.

**Mesma forma do razão contábil**, e de propósito: recortar primeiro, olhar
depois, tudo paginado no servidor. Quem já usou uma sabe usar a outra.

**Os filtros dizem o tamanho de cada escolha.** Cada chip traz quantas linhas
aquele valor rende, e é isso que permite decidir antes de pedir: "este CFOP são
quatro milhões de linhas" muda o clique seguinte.

**Cada lista é contada sem o próprio filtro.** Marcar o CFOP 5102 encolhe a
lista de CST e a de competência — que é o que mostra o que aquele CFOP tem
dentro —, mas **não** encolhe a lista de CFOP. Se encolhesse, o filtro seria de
mão única: quem marcasse um CFOP nunca mais acharia outro para marcar junto.

**A busca livre não entra no resumo, e a tela diz isso.** O resumo é agregado
por estabelecimento, competência, ramo, CFOP e CST — não tem chave nem descrição
de item, que é onde a busca procura. Então os chips contam sem a busca e o total
do alto conta com ela; sem avisar, alguém somaria os chips e acharia que o
sistema erra. Quem conta a busca é a consulta das linhas, que lê o parquet.

**Os totais são do recorte inteiro, nunca da página.** Total que muda ao virar
a página não serve para conferir nada.

**O download sai do tamanho da tela**, com a marca do recorte no nome do
arquivo: sem ela o primeiro download ficaria em cache e o segundo filtro
devolveria a planilha errada, com o nome certo. É o mesmo cuidado que a extração
de registro já tinha, pelo mesmo motivo.

**Um resumo materializado responde os filtros.** Levantar os valores distintos
varrendo 7,8 milhões de linhas a cada abertura seria segundos de tela branca — e
tela branca é o que faz alguém achar que não há dado e ir embora. O resumo tem
alguns milhares de linhas e responde em 0,03 s; a primeira leitura o escreve, e
ele se refaz sozinho quando a apuração roda de novo.

---

## 2026-09-29 — A 047 sai da EFD-Contribuições, e o gabarito confirma linha a linha

**O que entrou.** A **Consulta de Saídas (047)** do Sistema MA, gerada só a
partir da EFD-Contribuições, como a 037 já era. Quatro ramos: `C100/C170` (nota
fiscal item a item), `C100/C175` (o analítico da NFC-e), `A100/A170` (nota de
serviço) e `F100` (demais documentos). Sai na mesma etapa da 037, na mesma tela,
num botão ao lado — é a mesma leitura do mesmo arquivo.

**Conferida contra o gabarito inteiro**, e não por amostra: 7.784.121 linhas, 57
competências, as 53 colunas comparadas texto contra texto, pelo
`tools/validar_047.py`. Comparar total teria escondido tudo o que está abaixo —
e as três primeiras rodadas, que erravam em 483, 27 e 3 linhas, não teriam
mudado um centavo de nenhum somatório.

**Resultado: 7.784.121 de 7.784.121, sem uma divergência.**

**Uma única ressalva na comparação, e é do gabarito.** O CSV do MA não consegue
transportar ponto-e-vírgula — é o separador dele —, e troca-o por ponto: o item
que o SPED chama de "MARG DELICIA 1KG C/SAL C/CREME DE LEITE ;" aparece lá
terminado em ponto. São 2 linhas em 7.784.121, o valor certo é o nosso, e o
conferidor desfaz a troca para não acusar defeito onde não há.

**A última divergência a cair foi um par de UF pela metade.** Um participante
cadastrado no 0150 sem município: sem ele não há de onde tirar a UF, e nós
escrevíamos "MG/". O MA escreve a coluna vazia — uma ponta só não é par de
origem e destino. Uma linha em 7.784.121, e a única maneira de achá-la era
comparar linha a linha.

**A UF troca de lado.** Na 037 a coluna "UF Origem/Destino" é
participante/estabelecimento; na 047 é estabelecimento/participante. Numa saída
a origem somos nós. Um 6411 de Minas para São Paulo sai "MG/SP".

**A natureza da operação é outra coisa que a natureza do crédito.** A 037 traz
a Tabela 4.3.7 ("01 - Aquisição de bens para revenda"); a 047 traz uma palavra —
Venda, Transferência, Devolução de compra, Remessa, Lançamento de valor, Outras
saídas/prestações —, tirada do CFOP, e escreve "Faturamento" numa coluna própria
quando a natureza é Venda. Nas 7.784.121 linhas, 7.687.522 são Venda e todas têm
Faturamento; nenhuma das demais tem. A tabela está em
`tab_cfop_natureza_operacao` com os 21 CFOP do gabarito, porque uma regra que
lesse a descrição erraria o **5209** — "Devol de mercadoria recebida em
transferência", que o MA classifica como Transferência, e não como Devolução.

**O MA escreve o CFOP de dois jeitos.** Abreviado na Gestão e na 037 ("Devol
compra p/comercial"), quase por extenso no 047 ("Devol de compra para
comercialização"). Não dá para ter uma grafia só: mudar a que já existe quebraria
a comparação da Gestão, que `tools/validar_gestao.py` confere coluna a coluna.
Convivem as duas em `tab_cfop`, cada uma com a sua procedência.

**A nota cancelada rende uma linha, e a NFC-e cancelada não rende nenhuma.**
Documento com `COD_SIT` 02 a 05 é escriturado sem filho — o leiaute manda
preencher só até a chave —, e o MA emite a linha assim mesmo: são 3.360 no
gabarito. Mas o modelo 65 cancelado não aparece: 106 documentos numa competência,
nenhuma linha. O MA trata o C100/C175 como consulta à parte, e a linha do
documento sozinho só existe na do C100/C170.

**O que não está aqui, e por quê.** A cadeia do 047 tem mais ramos — C180/C185,
C380/C385, C400/C405/C485, C490/C495, C600/C605, C860/C880, as saídas do bloco D,
F500 a F560 e o I100. O cliente de referência não tem uma ocorrência sequer de
nenhum deles, e sem arquivo real não há como saber que rótulo o MA dá ao ramo nem
o que põe em cada coluna. É a mesma escolha da 037, pelo mesmo motivo. Para que a
ausência não seja silenciosa, a passada **conta** esses registros e a tela diz
quantos apareceram — descobrir isso somando a planilha seria tarde.

---

## 2026-09-29 — O 0200 e o 0150 são do estabelecimento, não do arquivo

**O defeito.** Na EFD-Contribuições o **0140 abre um bloco de cadastro próprio**
— 0150, 0190, 0200, 0400, 0500 — e um segundo 0140 recomeça tudo. A 037, a 047 e
a extração tratavam essas tabelas como uma só por arquivo, com o último a
aparecer sobrescrevendo o primeiro.

**Não é teórico.** No arquivo de outubro/2025 da empresa de referência, **134
códigos de item existem nos dois estabelecimentos com produtos que não têm nada
a ver um com o outro**: o código 10918 é "SABAO LIQ YPE 12X1L" na matriz e "PAO
DE FORMA ILUSTRE 400G" na filial. A nota da matriz saía com a mercadoria da
filial — descrição, NCM e código de barra trocados —, em 1.953 das 117.158 linhas
daquela competência. **Sem nenhum sinal de que errou**: a coluna vem preenchida,
com um produto que existe.

**Como apareceu.** Montando a 047 contra o gabarito do MA. Foi a única razão de
o defeito ter sido visto: nada no arquivo denuncia, e nenhum total muda — o
valor, a quantidade e o imposto estão certos, só a mercadoria é outra.

**A correção mora num módulo só**, `sped/cadastro.py`, e vale para as duas
consultas: a regra é sutil, e escrita duas vezes ela ia divergir. Duas ressalvas,
as duas tiradas do gabarito:

* código que o estabelecimento corrente não tem ainda vale procurar nos outros,
  mas **só se existir num só** — havendo mais de um não há desempate, e cadastro
  errado com cara de certo é pior que coluna vazia;
* campo vazio no cadastro certo o MA completa com o do **cadastro da matriz** —
  o estabelecimento cujo CNPJ é o do 0000. É o código de barra (ou o NCM) de
  outro produto e eu discordaria, mas está marcado no código como replicação, e
  não como convicção.

**"A matriz" e "quem cadastrou primeiro" não são a mesma coisa**, e a diferença
custou 317 linhas erradas numa competência até eu medi-la. O item 911047 está
em duas filiais e em nenhuma matriz: o gabarito deixa o NCM **em branco** nas 85
linhas da segunda filial. Já o 911159 está na matriz — como "BISC. RENATA
20X360G MAIZENA" — e na filial como "SALGADO" sem NCM: aí o gabarito escreve o
NCM da matriz nas 10 linhas da filial. Só a regra da matriz acerta os dois.

**Ainda não corrigidos**, e com o mesmo defeito: `sped/extracao.py`,
`sped/consolidado.py` e `analitico/registros_do_sped.py` — a extração de
registros e o consolidado. Não entraram aqui porque cada um tem a sua própria
forma de montar o join e os seus próprios testes; entram na sequência, e até lá
a coluna de descrição do item daqueles caminhos pode trazer o produto do outro
estabelecimento num cliente com matriz e filial.

---

## 2026-09-25 — `nItem` também vem como elemento, e sem ele o item do XML não casa com o C170

**O defeito.** As 121 notas que a Dom Atacarejo entregou em 25/09/2026 vinham
com `<det><nItem>1</nItem>` em vez de `<det nItem="1">` — o número do item como
elemento, não como atributo. O leiaute da NF-e diz atributo, e é assim que a
SEFAZ autoriza a nota; XML que passou por ferramenta de terceiro (portal de
consulta, conversor do cliente) chega reserializado. O leitor só olhava o
atributo, e as 916 linhas saíram com **item 0**.

**Por que isso é grave e não aparece.** A posição do item é o que casa o item do
XML com a linha do C170 da EFD: o par (chave, item) é o único identificador que
as duas fontes têm em comum. Com zero em toda linha, o cruzamento simplesmente
não existe — e nada denuncia a perda, porque o resto do item vem completo e a
coluna de zeros parece dado. Na consolidação de movimentos do ICMS é o mesmo
estrago, mais discreto: `itens_pareados_com_xml` cai sem explicação.

**Não se inventa pela ordem do arquivo.** Quando o número não vem de jeito
nenhum, fica zero: falta declarada. A ordem dos `<det>` no arquivo não é promessa
da numeração da nota, e um número inventado casaria com a linha errada do C170 —
pior que não casar.

---

## 2026-09-24 — O XML entra no PIS/COFINS, e o que é de outra empresa sai à vista

**O que estava quebrado.** A trilha de quebra de XML foi criada nos dois
módulos, mas a tabela que diz quem lê o quê continuou mandando XML só para o
ICMS. Resultado na tela: pasta com 7.186 XML, "PIS/COFINS LÊ 0", o aviso de que
nada ali alimenta o trabalho e o botão de importar desligado. A trilha existia e
não tinha como receber arquivo. Agora `xml_nfe` e `xml_compactado` alimentam
`piscofins` também — e só eles: o evento de cancelamento é da conferência da CAT
42, e não tem o que fazer numa apuração de contribuição.

**O descarte por empresa passa a ser conferível.** A regra não mudou: arquivo em
que nem o emitente nem o destinatário é o CNPJ do trabalho fica de fora, sem
perguntar. Misturar cliente é o acidente mais caro que este sistema pode causar
— contamina a apuração de dois de uma vez —, e confirmação nenhuma justifica
correr esse risco. O que mudou é que o descarte deixou de ser um número perdido
no meio dos avisos: a conferência da pasta mostra quantos saíram, de que CNPJ,
quantos bytes, e abre a lista com o nome dos arquivos. **Descarte que ninguém vê
é boato** — e quem importa precisa conferir, antes de gravar, que o que saiu não
era seu.

**O zip era o buraco.** A importação identifica o XML solto e o separa por CNPJ;
o zip do portal entra fechado, e ninguém sabe o que há dentro dele até a etapa
abrir. Numa pasta de rede — que guarda o grupo inteiro — isso significa a nota
de outra empresa entrando na planilha por baixo. Agora quem lê XML recebe a raiz
do CNPJ do trabalho e descarta nota a nota, com contador por CNPJ no resumo e no
log. Vale para a quebra de XML e para a extração de movimentos do ICMS.

**Nota sem ponta legível fica.** Recusar o que não se sabe de quem é perderia
nota boa, e o que não tem CNPJ nenhum não contamina apuração de ninguém — que é
o risco que a regra existe para evitar. Pelo mesmo motivo a comparação é por
**raiz**: outra filial é a mesma empresa.

**O que fica de fora de propósito.** A conferência da CAT 42 (etapa 2) não
filtra por empresa: lá só se lê o começo e o fim do arquivo, e a única ponta
legível sem abrir a nota é o emitente — filtrar por ele jogaria fora toda nota
de compra, que é justamente o insumo da CAT 42.

---

## 2026-09-24 — O trabalho ganha um nível: um card por frente, e as etapas dentro dele

**O que mudou de fato.** O ICMS tinha oito etapas porque tinha uma obrigação só.
Com o crédito outorgado entrando, e com CAT 207 e quebra de XML no caminho
(decisão do Victor, 24/09/2026), a tela do trabalho passaria a empilhar doze,
quinze cards soltos, misturando obrigações que não têm nada a ver uma com a
outra. Agora o trabalho mostra **uma frente por card** — CAT 42, crédito
outorgado — e clicar no card abre as etapas daquela frente.

**Chama-se trilha no código, e frente na tela.** `frente` já é a coluna do
projeto (`Frentes`: cat42, depara, sped, notafiscal), que classifica o trabalho
inteiro — e um trabalho de frente "cat42" percorre hoje a CAT 42 **e** o crédito
outorgado. Dois nomes para conceitos diferentes valem mais que um nome para
dois; quem lê a tela nunca vê a palavra trilha, só o nome da frente.

**O roteiro passou a ser derivado das trilhas**, e não escrito à mão ao lado
delas. Duas listas para a mesma verdade divergiriam no primeiro dia em que
alguém mexesse numa, e o preço seria uma etapa existindo no roteiro e não
aparecendo em card nenhum. Um teste cobra exatamente isso.

**Toda trilha começa por `importar`, e o roteiro só o tem uma vez.** A base é a
mesma para todas — quem importou para a CAT 42 já importou para o crédito
outorgado. `importar` abre todo roteiro e `historico` fecha todos: os dois são
de qualquer trabalho, e não de uma frente.

**Frente sem nada construído não some: entra apagada.** E o card não diz "1 de
1 concluída" só porque a base foi importada — `Construida` olha as etapas
próprias da frente, ignorando o `importar` que todas têm. Card que desaparece
faz a pessoa procurar a frente que ela sabe que foi contratada.

**O card é o mesmo do hub de tributos**, com a cor do módulo em vez de uma cor
por frente: dentro do trabalho o assunto já é um só, e pintar cada frente de uma
cor inventaria uma distinção que não existe. Quem escolheu ICMS numa tela de
cards não deveria aprender uma segunda gramática para escolher a CAT 42 dentro
dele.

**O que fica em aberto:** de dentro de uma etapa (o razão, por exemplo), o
"Voltar ao trabalho" cai no nível das frentes, e não na frente de onde se veio.
É um clique a mais, e o conserto exige a etapa saber de que frente foi aberta.

---

## 2026-09-23 — O crédito outorgado entra no ICMS, vindo do Quebra de SPED

**De onde veio.** A funcionalidade existe e roda no projeto `Quebra de SPED`
(`src/credito_outorgado/`) sobre 120 mil XML por vez. Ela varre as notas de
saída e separa, item a item, o que é produto beneficiado pelo crédito outorgado
— o benefício é da **mercadoria**, e o trabalho do analista é dizer quais das
milhões de linhas vendidas são da lista que a lei estadual concede.

**A regra foi portada como está: a descrição manda, a NCM confirma.** Item entra
se a descrição contiver algum termo cadastrado; bater só a NCM **não basta**.
Não é descuido da origem, é o que a prática ensinou: a NCM é declarada pelo
emitente e erra (a mesma farinha vem 11010010 num fornecedor e 19019090 noutro),
enquanto a descrição é o produto que o dono do negócio reconhece. Quando as duas
batem, o item sai marcado `NCM+DESCRIÇÃO` — e é por esse rótulo que se separa o
que está redondo do que merece um olhar.

**Duas diferenças conscientes, ambas na comparação de NCM.** Lá, o código
cadastrado era procurado em qualquer posição (`"690"` achava `21069090`) e os
zeros à esquerda eram descartados dos dois lados. Aqui casa por **prefixo**, com
os zeros: NCM é hierárquica, vale da esquerda para a direita. Como a NCM sozinha
nunca decide elegibilidade, a mudança só pode mexer no **rótulo** de um item já
elegível pela descrição — nunca em quem entra. O **acento continua contando**
("PAO" não acha "PÃO"), como na origem: dobrar acento faria entrar aqui item que
lá fica de fora, e os dois resultados precisam poder ser comparados.

**O que a travessia ganhou de graça.** O leitor é o da casa
(`dominio/notafiscal/xml`), e não um parser próprio: entram CF-e SAT junto com a
NF-e, CT-e e evento de cancelamento reconhecidos e ignorados, nota denegada fora
da conta, XML declarado UTF-8 e gravado em Latin-1 relido em vez de perdido, e o
zip aberto sem extrair para o disco. E **uma cópia por chave** — a mesma nota vem
no zip do mês e no do trimestre (28.407 chaves repetidas na empresa 04), e
contar duas vezes inflaria justamente o número que interessa.

**O filtro é do trabalho, e fica no banco.** Na origem era um JSON global, um
só para todas as empresas. Aqui é uma linha por trabalho
(`credito_outorgado_filtro`): a lista muda com o estado, com o período e com o
que a empresa vende. **Sem nenhum termo a etapa se recusa a rodar**, em vez de
varrer 120 mil arquivos para entregar uma lista vazia; quem quer ver o universo
antes de escrever o primeiro termo liga `sem_filtro`, que é explícito e marca
cada linha com o rótulo `SEM FILTRO`.

**Cada rodada guarda o filtro que a produziu**, no resumo da execução. Não é
redundância com a tabela: lá fica o filtro de hoje, aqui o que produziu aquela
lista — e é este que responde, meses depois, por que ela tinha aquelas linhas.

**Três listas viraram duas, e nasceu uma terceira coisa.** A origem escrevia
elegíveis, descartados e "todos"; o "todos" era a soma dos dois, e saiu. O que
entrou no lugar é a leitura por **produto**: ninguém revisa um filtro lendo três
milhões de linhas de venda — lê-se a lista de produtos distintos que ele
capturou, e aí salta aos olhos o que não devia estar ali e o que ficou de fora.

**O PIS e o COFINS do item passaram a ser lidos do XML.** Não servem à CAT 42;
servem à triagem, onde o CST do produto confirma ou desmente o que a descrição
diz — cesta básica sai com CST 04 ou 06, e o que sai com 01 merece conferência.

---

## 2026-09-23 — O cartão de trabalho diz de que tributo é, e a cor do assunto passa a ter uma fonte só

**O que faltava.** Na lista de todos os trabalhos, o cartão dizia a empresa, o
CNPJ, a frente ("CAT 42 — Ressarcimento de ICMS-ST", "Quebra de SPED") e o
nome do projeto — e **não dizia de que tributo o trabalho é**. Dava para
deduzir pela frente, mas deduzir uma vez por cartão é exatamente o trabalho
que uma etiqueta poupa. Agora há uma, na cor do assunto.

**A etiqueta é do módulo, não do segmento.** Ela mostra `modulo_rotulo` —
"PIS/COFINS", "CBS", "ICMS", "IBS", "IRPJ/CSLL". O segmento diria "PIS/COFINS"
tanto para um trabalho de PIS/COFINS quanto para um de CBS, e na transição de
2027 a 2033 os dois convivem: é justamente aí que a distinção importa.

**Ela some na lista já recortada.** Em `/modulos/icms` o título da tela já diz
"Trabalhos de ICMS"; repetir a etiqueta em quarenta cartões idênticos não
informa nada, só acrescenta cor. A etiqueta responde "qual é o assunto deste?",
pergunta que só existe quando a lista mistura assuntos.

**A cor do assunto vira uma fonte só** (`constants/assuntos.ts`). A mesma
tabela já estava escrita em dois lugares — os cards do hub (`CardDeEscolha`) e
as pílulas de segmento na lista de usuários —, e esta etiqueta seria a
terceira. Três cópias da mesma verdade divergem no dia em que alguém mexer
numa, e "o azul é o ICMS" só vira reconhecimento se for sempre o mesmo azul.
O sucessor herda a cor de quem sucede: CBS laranja como PIS/COFINS, IBS azul
como ICMS.

**Uma mudança de comportamento no meio disso:** assunto que a tabela não
conhece agora cai em **cinza**, e não mais no laranja da casa. Cinza diz "não
sei o que é isto"; laranja diria que é PIS/COFINS, o que é pior do que não
dizer nada.

**A busca acompanha o que o cartão passou a mostrar.** Quem lê "PIS/COFINS"
ali espera digitar isso e achar os trabalhos do tributo — `modulo_rotulo`
entrou nos campos pesquisados.

---

## 2026-09-23 — Um caminho por funcionalidade: o card perde o "Abrir", o histórico sai da barra

**Duas repetições, a mesma regra.** Quem olha a tela do trabalho precisa
conseguir contar as funcionalidades e chegar ao número certo. Duas coisas
atrapalhavam isso.

**O "Abrir →" do card.** O card inteiro já é um `<Link>` — a chamada no rodapé
repetia o que o cartão inteiro é, e a etiqueta do topo ("Pendente",
"Concluída") já diz em que pé a coisa está. Saiu. O rodapé ficou **só no card
indisponível**, e ali o que vai nele não é chamada, é o motivo: "Ainda não
construída". É o único lugar do corpo do card onde essa razão aparece.

**O histórico aparecia três vezes**: botão no canto superior, aba na barra e
card na grade — os três levando ao mesmo lugar. Ficou **só o botão do canto**,
que está sempre ali, em qualquer módulo, inclusive quando o trabalho está
parado.

**Por que o botão, e não o card.** O histórico não é etapa do trabalho: ele
**nunca conclui**. Entre cards que dizem "Pendente" e "Concluída" ele mentiria
sobre si mesmo todo dia. O servidor já sabia disso — `DefinicaoEtapa.Conta:
false` o mantém fora do progresso desde que a aba nasceu —, e a tela agora
concorda com o servidor em vez de só herdar a lista dele.

**O que isso corrigiu de quebra.** A tela recontava o progresso no navegador
(`etapas.filter(implementada)`), o que era uma segunda verdade sobre a mesma
coisa — e ela **discordava**: contava o histórico no denominador. Agora o
número exibido é o do servidor (`Etapas.Progresso`, via `etapas_feitas` e
`etapas_totais`), que ignora o que não foi construído e o que não conclui.

Fica em aberto a repetição maior, que é escolha de desenho e não de código: a
barra (`BarraDeFuncionalidades`) e os cards (`PainelDoTrabalho`) ainda
navegam para os mesmos lugares, na mesma tela.

---

## 2026-09-24 — Cinco anos: o que prescreveu aparece, e não entra no crédito

**A regra.** O prazo para repetir o indébito é de cinco anos contados do
pagamento (LC 118/2005, art. 3º), e PIS/COFINS vence no dia 25 do mês seguinte
ao fato gerador (Lei 11.933/2009). A competência está fora quando o vencimento
dela é anterior a `data do pedido − 5 anos`.

**O corte é por dia, não por mês.** A competência de 08/2021 venceu em
25/09/2021: um pedido de 24/09/2026 ainda a alcança — por um dia. Arredondar
para o mês jogaria fora R$ 567 mil na base da empresa 16, e é o tipo de decisão que
ninguém quer descobrir depois.

**Mostrar em vermelho, não somar** — foi o pedido, e é o certo. Competência
prescrita aparece na tabela com a linha em vermelho e o valor riscado, some do
número grande, e o rodapé do destaque diz quanto e quantas: "R$ 3.309.472,34 em
7 competências fora dos cinco anos, contados de 24/09/2026 — não entram no
crédito". A planilha ganhou a coluna `Prescrita`, para quem confere fora da
tela.

**A data de referência entra por fora.** O padrão é hoje, que é o certo para
quem está montando o cálculo; mas ação já ajuizada, pedido administrativo
anterior ou exigibilidade suspensa deslocam a contagem, e nada disso está no
SPED. O sistema separa pela regra geral, diz qual data usou, e quem assina
ajusta.

**Na empresa 16:** o crédito passou de R$ 48.861.132,72 para **R$ 45.551.660,38**,
com R$ 3.309.472,34 em 2021-01 a 2021-07 marcados como prescritos.

---

## 2026-09-24 — O gabarito do MA achou o defeito: C181 e C185 eram dois grupos

**O número era 22% menor que o do MA, e a culpa era da chave do grupo.** O
registro entra na chave, e a consolidação de NF-e escreve **dois** registros
sobre a mesma receita: o C181 traz o PIS, o C185 traz a COFINS. Separados:

    C181 CST 01   base 68.066.165   PIS 1.123.487   COFINS         0
    C185 CST 01   base 68.066.165   PIS         0   COFINS 5.172.665

A base entrava duas vezes e — pior — cada grupo excluía só a própria
contribuição, que é exatamente a **tese conservadora** que não foi escolhida.
Por isso os meses de C175 (que traz os dois na mesma linha) batiam a 2% e os de
C180 erravam 29%: o defeito só aparecia onde a escrituração separa os tributos.

Agora os pares vão para a mesma família — `C180/C181/C185`, `C190/C191/C195`,
`C380/C381/C385`, `C400/C481/C485`, `C490/C491/C495`, `C600/C601/C605`,
`D100/D101/D105`, `D200/D201/D205`, `D500/D501/D505`, `D600/D601/D605` —, com o
nome que o MA usa, para os dois relatórios se compararem linha a linha.

**O efeito:** de R$ 38.211.172,71 para **R$ 48.861.132,72**, contra
R$ 49.229.265,54 do MA — de 22% de diferença para **0,75%**. Os grupos caíram
de 1.535 para 869, e a base de R$ 10,06 bi para R$ 5,82 bi (a duplicação).

**Do que sobrou, R$ 287 mil estão em três meses do próprio gabarito.** Em
2023-07, 2023-08 e 2023-09 a razão entre o que volta e a base passa do teto
teórico do método (0,8556% para 9,25%): com base de R$ 93,16 mi e contribuições
de R$ 8,70 mi, o máximo seria R$ 811,9 mil e o MA traz R$ 932,9 mil. As colunas
dele são coerentes entre si (zero linhas com `base STF ≠ base − PIS − COFINS`),
então é conta de dentro do MA que precisa de explicação — anotado para
perguntar a quem o gerou.

**O resto — cerca de R$ 81 mil em 60 competências, 0,17%** — é o recorte: o MA
inclui CST 49 e classifica por CFOP, e o sistema ainda recorta por CST.

**E o CSV ganhou cabeçalho sem ambiguidade.** Comparar os dois arquivos só foi
possível depois de descobrir que o meu tinha duas colunas "PIS" e duas
"COFINS" — no xlsx as faixas separam, no CSV não. O gerador agora põe o bloco
na frente quando o título se repete ("PIS - Valor"), e um teste percorre os
catálogos cobrando isso. **A Consulta de Entradas tinha sete pares assim** e
ninguém havia notado.

---

## 2026-09-24 — A tela que já sabe o tributo para de perguntar

O "Novo trabalho" abria com um seletor de **Tributo** listando os cinco — e
marcado em ICMS — numa tela chamada "Trabalhos de PIS/COFINS". Pior que
redundante: convidava ao erro. A frente vinha "CAT 42" junto, e o trabalho
nasceria de ICMS dentro da lista de PIS/COFINS, onde ninguém o encontraria
depois.

**Quando a tela define o tributo, ele deixa de ser pergunta**: vira um campo de
leitura, com o rótulo que vem do catálogo do servidor. O seletor continua
existindo para quando não há tela que o defina.

**A frente passa a nascer coerente.** `frente` é a coluna do banco — o TIPO de
trabalho — e não se deduz do tributo sozinha; é escolha de quem cadastra. O que
se pode fazer é nascer certa em vez de nascer "CAT 42" em toda tela: ICMS nasce
CAT 42, PIS/COFINS e IRPJ/CSLL nascem Quebra de SPED. Trocar continua a um
clique. O exemplo do nome também mudou junto — "Ressarcimento ST 2025" não é
exemplo de trabalho de PIS/COFINS.

**O teste é da ligação, não do modal.** O defeito não estava no modal, que
fazia o que lhe mandavam: estava na tela, que não lhe dizia onde ele tinha sido
aberto. Por isso os quatro casos montam a página inteira em `/modulos/piscofins`
e conferem o que chega ao `criarProjeto`.

**E o ambiente de teste ganhou o `<dialog>`**: o jsdom não implementa
`showModal()` nem `close()`. Sem eles, nenhuma tela com modal pode ser testada
— e o `open` que o remendo põe e tira é o que faz o conteúdo existir para as
queries por papel.

---

## 2026-09-24 — Barra de rolagem que não rolava nada

A tabela de usuários tinha `min-w-[1240px]` dentro de um `overflow-x-auto`:
sempre que o card ficava um pixel abaixo disso, o navegador mostrava a barra
horizontal — e ela aparecia **sem ter o que rolar**, que é o pior tipo de
barra: ocupa espaço, chama atenção e não leva a lugar nenhum.

O mínimo passou a ser **de cada coluna** (`minmax(190px,1.4fr)` e companhia), e
não da tabela inteira. A largura mínima da tabela vira a soma dos mínimos, a
proporção continua dividindo a sobra, e a barra aparece só quando não cabe de
verdade — em janela estreita.

**Uma armadilha do Tailwind no caminho:** a classe estava montada por
concatenação de três literais, e o Tailwind lê o **texto** do arquivo. Classe
que não existe inteira em lugar nenhum não vira CSS, e a grade sairia sem
colunas. Ficou em uma linha só, com o porquê ao lado — e conferido no CSS
gerado antes de publicar.

Outras telas usam o mesmo par `overflow-x-auto` + `min-w` com valores menores
(900 a 1120 px), onde a barra só aparece em janela realmente estreita. Ficam
como estão; se alguma aparecer à toa, a correção é esta.

---

## 2026-09-24 — O painel do combobox para na borda do modal

**O segundo defeito da mesma lista.** Em 23/09 o painel abria **atrás** do
diálogo, e foi resolvido montando-o dentro do `<dialog>` (top layer). Agora
abria **para fora**: num campo perto do rodapé, a lista descia além da borda do
card e ficava sobre o fundo escurecido da página. Visto no "Novo trabalho", no
seletor de tributo.

**A causa era a medida.** O espaço disponível vinha da janela, e a janela é
maior que o modal: havia 278 px até o rodapé da tela e só 30 px até o rodapé do
card. Quem está dentro de um diálogo tem o diálogo por mundo — é a borda dele
que decide se cabe embaixo, se cabe em cima e onde a lista para.

**O que o teste achou de brinde.** `offsetHeight ?? 280` só cai no padrão
quando o valor é nulo, e painel ainda sem layout devolve **zero** — com zero,
qualquer frestinha de 8 px parecia espaço bastante. Virou `|| 280`: altura zero
é painel não medido, não painel de zero pixel.

**Segunda volta, no mesmo dia: virar por pouco é pior que descer.** Com o
limite certo, a lista passou a virar para cima cedo demais — num campo com
235 px embaixo e 269 em cima, ela subia para ganhar 34 px e **cobria o título
do modal**. Para baixo virou o padrão: só vira quando o espaço de cima passa o
de baixo em mais de 60 px. Abaixo disso, desce e rola por dentro.

**E o ambiente de teste ganhou o que faltava:** `scrollIntoView`, que o jsdom
não implementa. Sem isso o efeito do teclado estoura e o teste falha por um
motivo que nada tem a ver com o que ele mede.

---

## 2026-09-24 — A quebra de XML, com a planilha que cada um escolhe

**O que entrou.** A etapa `quebra_xml` deixa de ser promessa: abre as notas do
lote item a item e entrega a planilha. Existe nos **dois módulos** — no ICMS,
porque a EFD não traz o item da saída própria (NF-e e NFC-e vão à escrituração
só com o analítico); no PIS/COFINS, porque o CST e a alíquota que o C170
consolidado esconde estão no XML.

**Não é leitor novo.** É o mesmo `itens_do_xml.py` que a extração de movimentos
usa desde a etapa 3: trata NF-e, NFC-e e CF-e SAT, recusa CT-e e evento de
cancelamento, escolhe a cópia autorizada entre as repetidas e lê zip sem
descompactar em disco. Aproveitar o que já tinha calo foi a escolha óbvia
diante de portar o extrator avulso — que, aliás, lia **só** `PISAliq` e perderia
todo CST que não fosse alíquota básica.

**O que faltava no parquet, e agora está lá:** PIS, COFINS, IPI e ISSQN por
item, e o nome de quem emitiu e de quem recebeu. O leitor já lia PIS e COFINS —
só não chegavam ao disco, porque a CAT 42 não usa. IPI e ISSQN o domínio passou
a ler.

**A particularidade pedida: escolher as colunas.** São 57 possíveis e quase
ninguém quer as 57 — quem confere ICMS não olha ISSQN; quem confere contribuição
não olha ST. A tela mostra os campos em oito blocos, com atalhos (`ICMS`,
`PIS/COFINS`, `Descontos`, `Tudo`) e liberdade campo a campo dentro deles.

Três decisões dentro dessa:

* **o catálogo vem do servidor.** A tela pede a lista do que a planilha sabe
  produzir, em vez de carregar uma cópia. Duas listas divergiriam na primeira
  coluna nova, e a tela ofereceria coluna que a planilha não entrega;
* **a ordem é a do catálogo**, nunca a da escolha: duas planilhas do mesmo
  trabalho se comparam lado a lado;
* **escolha estragada não derruba nada.** Campo que não existe mais — guardado
  no navegador de alguém — é ignorado; e se a escolha inteira for de campos
  inexistentes, sai o catálogo completo em vez de uma planilha vazia.

**Como a escolha viaja:** em `classificacoes`, o canal genérico de recorte das
planilhas, aqui recortando **coluna** em vez de linha. `modelos` continua
recortando linha (55, 65, 59). Nenhuma rota nova para isso.

**Corrigido no mesmo dia: o seletor segue o tributo do trabalho.** A primeira
versão abria marcada no atalho de **ICMS** em qualquer módulo, e mostrava
ICMS-ST, IPI e ISSQN com o mesmo peso numa tela de PIS/COFINS. Quem fosse
baixar levaria as colunas erradas sem perceber — o download não avisa.

Agora o padrão é o atalho do módulo, os blocos do outro tributo ficam atrás de
"mostrar os outros tributos" — **sem sumir**, porque cruzar a nota com o ICMS
destacado é trabalho legítimo — e o atalho do outro tributo sai da barra, onde
convidava ao clique errado. Cinco testes de tela guardam isso, incluindo o que
prova que a coluna do outro tributo, quando marcada à mão, vai no download.

**A aba "Resumo" do extrator não veio** — uma linha por nota com a conferência
entre o desconto declarado e a soma dos itens. Foi decisão de quem pediu: uma
aba só, de itens. Fica anotada, porque a conferência de desconto é útil e o
dado para montá-la já está no parquet.

---

## 2026-09-24 — A tela das Exclusões, e o arquivo que entrou duas vezes

**A tela.** Exclusões deixa de ser promessa na barra: roda, acompanha, mostra o
que volta e baixa a planilha. O número grande vem com a base ao lado — e, com o
mesmo destaque, **o que a conta recusou e por quê**. Número de tese que não diz
o que ficou de fora é número que ninguém assina.

A tabela por competência mostra o total de cada mês, que é a soma dos grupos
daquele mês **já arredondados**. Recalcular sobre a soma daria outro número, e
a primeira conferência que somasse a planilha à mão encontraria a diferença.

**O que a primeira rodada real descobriu.** Rodando a base inteira, três
execuções seguidas deram três números diferentes — R$ 38.711.369,34,
R$ 38.507.768,78 e R$ 38.221.053,53. A causa não era o cálculo: o lote tem
**dois arquivos com o mesmo nome** para 2021-03, os dois "Retificadora" com o
mesmo carimbo de hora, e tamanhos de 138 MB e 365 MB. A primeira rodada somou
os dois; as seguintes ficaram com um ou com o outro, conforme a ordem de
leitura.

**Três correções saíram daí:**

* a exclusão passou a escolher **um arquivo por competência**, com a mesma
  regra da Gestão (retificadora vence; depois, o mais novo). Sem isso, um lote
  com a original e a retificadora do mesmo mês somava as duas;
* a leitura do agregado **conta e avisa** quando a mesma chave aparece duas
  vezes, em vez de deixar uma cobrir a outra em silêncio;
* o aviso de competência repetida passou a **identificar o arquivo** — nome,
  tamanho e pasta. "Usado X, ignorado X" não ajuda ninguém a decidir se o
  certo foi escolhido, e é exatamente o que ele dizia quando os dois têm o
  mesmo nome.

**O agregado envenenado foi apagado.** O parquet da execução 119 guardava os
dois arquivos sob a mesma chave; qualquer rodada que partisse dele herdaria a
escolha arbitrária. Apagar e reler foi o certo: 14 minutos contra um número em
que não se pode confiar.

**O que fica para o cliente decidir:** qual dos dois arquivos de 2021-03 vale.
O sistema escolhe o mais novo e diz qual ignorou, mas 227 MB de diferença entre
dois arquivos que se dizem a mesma retificadora é pergunta para quem transmitiu.

---

## 2026-09-24 — Os agregados ficam em disco, e a segunda conta sai em segundos

**O gargalo.** Ler os 65 SPED da empresa 16 custa 1h18. Até aqui esse trabalho era
jogado fora ao fim da rodada da Gestão: a Exclusão, que precisa exatamente dos
mesmos números, começaria do zero — e a tese seguinte também, e a próxima.

**A mudança.** A Gestão grava `agregados_efd.parquet` na pasta da execução: o
resumo por chave (tributo, registro, operação, CST, CFOP, natureza, alíquota)
com as somas da competência. Dezenas de milhares de linhas para um SPED de 1 GB.
A Exclusão parte dele e sai em segundos.

**Não é cache, é produto da etapa.** Fica na pasta da execução e envelhece com
ela. Não há chave de invalidação para errar: o parquet de uma execução é, por
definição, o que aquela execução leu. Quem quiser agregado de outra base roda a
etapa naquela base — e a Exclusão sempre procura a Gestão **mais recente** que
tenha agregado, porque número velho que bate com nada é pior que número nenhum.

**As contagens moram num parquet próprio.** O registro que a leitura não cobre
— C601, D350 e companhia — não vira linha de documento nenhuma, e é justamente
ele que a tese precisa contar para avisar que ficou receita de fora. Guardá-lo
junto do documento o perderia; o teste guarda essa lição.

**Sem Gestão rodada, a Exclusão não recusa.** Lê os SPED ela mesma e grava o
agregado na própria pasta — a tese seguinte não paga de novo. O resumo diz de
onde veio ("agregados" ou "sped"), porque dez segundos e uma hora são a mesma
etapa com fontes diferentes, e quem acompanha merece saber qual foi.

**Consequência operacional da fila fora do motor:** o trabalhador não recarrega
sozinho. Etapa nova ou executor alterado só valem depois de reiniciar a janela
da fila. É o preço de a rodada de uma hora sobreviver a quem salva arquivo — e
o preço certo.

---

## 2026-09-24 — A primeira exclusão: PIS e COFINS da própria base

**A tese.** O preço de venda embute as duas contribuições, e receita não é
imposto. Excluindo-as, a base encolhe e o que foi pago a mais volta.

**A regra, escolhida por quem apura, não pelo código.** A base de cada uma
perde **as duas**. Numa venda de R$ 1.000,00 com PIS de R$ 16,50 e COFINS de
R$ 76,00, a base nova é R$ 907,50 para os dois — não R$ 983,50 para o PIS e
R$ 924,00 para a COFINS. Volta R$ 8,56. A leitura conservadora (cada um só da
própria base) daria R$ 6,05, e o gross-up pela alíquota daria o mesmo R$ 8,56
enquanto o arquivo estiver coerente. Ficou a primeira, e o teste guarda o
número: mudar aquilo é mudar a tese, não o código.

**Só no débito.** O crédito das aquisições fica como está. É o que o
escritório pede, e é o que dá o maior saldo — a visão líquida (com o efeito no
crédito) fica anotada para quando alguém quiser o piso do benefício.

**O agrupamento é o do MA, e isso não é detalhe.** Registro, CST e CFOP dentro
da competência; o arredondamento acontece uma vez por grupo, com a alíquota
**efetiva** (valor ÷ base) do próprio grupo. Duas razões: a alíquota efetiva é
imune a alíquota fora do padrão, a ajuste na linha e ao arredondamento do ERP
— e arredondar linha a linha, numa base de milhões de itens, move o total. O
teste mostra o efeito em três vendas de R$ 10,00: linha a linha não volta
nada; somadas, volta um centavo.

**O que a conta recusa, contando:**

* **alíquota em reais** (CST 03): a contribuição vem da quantidade, não da
  receita — excluir dinheiro de uma base em litros não quer dizer nada;
* **receita sem contribuição** e grupos zerados: não há o que excluir;
* **base menor que a contribuição do próprio grupo**: arquivo inconsistente.
  Recalcular ali devolveria base zero e "recuperaria" 100% do grupo — número
  que passa na soma e não sobrevive à fiscalização.

**O que ainda não é lido, e o resumo diz quando aparece:** C601/C605, D300,
D350, F200, F510, F560 e I100. A leitura da Gestão cobre o resto da receita —
A170, C170, C175, C181/C185, C381/C385, C481/C485, C491/C495, C870/C880,
D201/D205, D601/D605, F100, F500, F550 —, e é ela que alimenta a exclusão: uma
passada no arquivo serve às duas contas.

**Medido na base real** (empresa 16, dois meses de um estabelecimento): base de
R$ 123.602.140,38, excluídos R$ 10.446.337,02, e voltam R$ 932.622,22 —
R$ 160.268,51 de PIS e R$ 772.353,71 de COFINS. Nenhuma chave com contribuição
apurada ficou de fora; o que sobrou no contador foram aquisições (fora por
regra) e grupos zerados de CST 04 e 49.

**O próximo passo, e a razão dele.** Hoje a Gestão monta os agregados e os
descarta ao terminar, então a exclusão precisaria reler os arquivos — uma hora
nesta base. Gravar os agregados na pasta da execução (são poucos MB para um
SPED de 1 GB) faz a exclusão sair em segundos, e serve a toda tese que vier
depois: a do ICMS destacado já está declarada na barra esperando.

---

## 2026-09-24 — A fila sai de dentro do motor

**O estrago.** A Gestão Fiscal de 65 arquivos morreu no quarto, com
"Interrompida: o motor reiniciou durante a rodada". A mensagem estava certa: o
motor de desenvolvimento roda com `--reload`, a fila de execuções era uma
thread dentro dele, e salvar um `.py` derruba o processo — que, ao sair, ainda
encerra de propósito o processo filho da rodada. Com duas pessoas mexendo no
código ao mesmo tempo, isso acontece dezenas de vezes por dia: uma apuração de
uma hora **nunca** chegava ao fim. A de 23/09 morreu duas vezes assim (a
conferência de 95 mil documentos, em 220; a Gestão, em 4 de 65).

**O diagnóstico que faltava.** O projeto já tinha tratado metade do problema em
16/09: cada rodada passou a ter processo próprio, para que falta de memória não
derrubasse o motor. Mas quem **vigia** o filho continuava dentro do processo que
recarrega — e o vigia, ao ser encerrado, mata o filho junto.

**A mudança.** `workers/rodar.py`: a fila roda em processo próprio, fora do
motor. `python -m workers.rodar`, uma janela dedicada em `scripts/subir.ps1`, e
o motor sobe com `CAT_FILA_AUTOMATICA=false`. O motor recarrega à vontade — é o
que torna o desenvolvimento suportável — e não leva rodada nenhuma junto.

**Por que não é só configuração.** Dois trabalhadores no mesmo banco não
disputam execução (o `SKIP LOCKED` cuida disso), mas o que reinicia marca como
interrompida a rodada que o outro está tocando: `recuperar_interrompidas` não
tem como saber que a linha "rodando" é de outro processo vivo. Daí o motor
subir **sem** fila, e o trabalhador avisar no log quando percebe que o motor
também está configurado para rodá-la.

**Provado na base real.** Com a apuração em curso, salvei um `.py` de propósito:
o motor reiniciou (`/interno/saude` respondeu `ok` logo depois) e a rodada
seguiu de 2/65 para 4/65 sem piscar. Antes, esse mesmo gesto a matava.

**O que fica de dívida.** `recuperar_interrompidas` continua sendo heurística:
"linha rodando quando eu subo é rodada morta". Com a fila num processo só, a
heurística volta a valer. Para valer sempre, a execução precisaria registrar
quem a está tocando (máquina e processo), e aí a recuperação checaria se aquele
trabalhador ainda vive. Fica anotado para quando houver mais de um.

---

## 2026-09-23 — O front ganhou testes, por uma pergunta que o código não respondia

**A pergunta.** "Filtrar, marcar uma conta, trocar de filtro, marcar outra — a
primeira continua marcada?" O código dizia que sim: a seleção mora no seletor,
acima da lista, e trocar filtro só refaz a lista. Mas isso era **leitura de
código**, não resposta: bastaria alguém mover o estado para dentro da lista
numa refatoração para a resposta virar não, sem nada quebrar visivelmente. Quem
descobre é quem perde meia hora de marcação na frente do cliente.

**O que faltava era instrumento.** O front tinha `tsc -b` e mais nada — nenhum
teste de tela em nove meses de projeto. Agora tem vitest + Testing Library em
jsdom, `npm test`, e os arquivos seguem o nome do resto da casa
(`*.teste.tsx`, como `test_*.py` no motor).

**O primeiro arquivo cobre o que foi perguntado**, e o vizinho de cada caso:
busca, recorte por saldo, estabelecimento e navegação pela árvore não desmarcam;
o que se extrai é o que está marcado, **inclusive o que o filtro tirou da tela**;
Limpar desmarca; sem marcação não há o que extrair; e a mesma conta em dois
estabelecimentos marca nos dois, porque é uma conta só do plano.

**O que o teste encontrou.** O comportamento estava certo — nenhum defeito de
seleção. Mas escrever o teste expôs outro: os botões da árvore não tinham nome
acessível nenhum. O nome saía do conteúdo — código, contagem e três valores
grudados —, impronunciável em leitor de tela e impossível de alcançar por
papel. Ganharam `aria-label`.

**Quando escrever teste de tela.** Onde o estado atravessa interações — seleção
que sobrevive a filtro, rascunho que sobrevive a navegação, acumulado de
páginas. Renderização de lista e formatação de número continuam não valendo o
custo: o compilador e o olho pegam.

---

## 2026-09-23 — O seletor de contas vira árvore, pela referencial da ECD

**O problema.** 10.282 contas numa lista de 100 por página são 103 páginas.
Ninguém acha nada virando 103 páginas, e quem precisa marcar seis contas para
extrair desistia antes.

**Por que a conta referencial, e não o código do cliente.** O código do cliente
vem **sem separador** nesta base — `1103010001`, dez ou onze dígitos — e não há
como saber onde um nível termina sem o I050, que traz nível e conta superior. O
I050 está nos arquivos, e reler esta base custa 1h18 (foi o que a apuração
levou). A conta referencial, ao contrário, a própria ECD declara no I051 conta
por conta, já está no parquet e cobre 99,96% das contas desta base. Árvore feita
de dado declarado, não de palpite sobre o formato do código.

**O que ela fecha.** Da raiz até a conta: 3 galhos, depois 6, 13, 36, 88. Três
ou quatro cliques no lugar de 103 páginas. Cada galho mostra quantas contas e
quantas partidas há **abaixo** dele — quem olha "1.01" quer o circulante
inteiro, não o primeiro nível.

**Onde a árvore não resolve, a tela não finge que resolve.** O cliente abre uma
conta analítica por fornecedor: o galho `2.01.01.03.01` pendura 5.659 delas, e
nenhuma hierarquia quebra isso, porque elas são irmãs de verdade. Ali vale a
busca — e, para percorrer, **"mostrar mais"** em vez de trocar de página, que é
o que faz perder o lugar.

**A busca desmonta a árvore de propósito.** Quem digita "CRBS" quer a conta, não
o caminho até ela: com busca vêm as contas que casam, de qualquer galho.

**Conta sem referencial ganha galho próprio.** São quatro nesta base. Sem isso
elas sumiriam da árvore — e conta invisível é conta que ninguém confere.

**A lista chapada continua existindo.** `arvore` é opção, e o padrão é o de
sempre: quem quer todas as contas — o download, um script — não passa a
depender de navegar.

---

## 2026-09-23 — O cruzamento com a 037 é do analista, não do sistema

**A decisão.** A apuração de PIS/COFINS monta os dois lados — a Consulta de
Entradas (037), do fiscal, e o razão da ECD, do contábil — e **para aí**. Não
casa um com o outro.

Casar partida contábil com item de nota exige critério que muda de cliente para
cliente: um lança a nota inteira numa conta, outro rateia por centro de custo,
outro agrupa o mês num lançamento só. Um casamento automático acertaria em
alguns e **erraria calado** nos demais — e erro calado em conferência é pior
que conferência nenhuma, porque ninguém volta a olhar o que o sistema disse que
bate.

**O que o sistema entrega, então.** Na tela do razão: marcar as contas e
extrair. Marca-se por código de conta, a marcação atravessa busca e página, e
saem as partidas só das marcadas — em xlsx ou CSV. É essa planilha que se
compara com a 037, por fora, com o critério de quem conhece o cliente.

**Como o recorte chega ao servidor.** Pelo canal genérico de recorte das
planilhas (`classificacoes`), que já servia às situações do documento na
conferência e às fontes da cascata no suportado. Aqui são as contas, e a
planilha do razão passou a filtrar por `conta` em vez de ignorar o recorte.
Nenhuma rota nova, nada de novo no C#.

**O nome do arquivo em cache.** Cada recorte é um arquivo, senão o primeiro
download ficaria em cache e o filtro seguinte devolveria a planilha errada —
com o nome certo. Trinta contas no nome, porém, passam do que o Windows aceita
em caminho, e a gravação morreria depois de o servidor ter feito a planilha
inteira: acima de 60 caracteres o recorte vira resumo. Mesma seleção, mesmo
nome; ordem de marcação não conta.

**O seletor levava 27 segundos, e por isso parecia vazio.** Cada página
reagregava o razão inteiro — dezessete milhões de partidas numa base de rede —
e ainda fazia isso duas vezes, uma para contar e outra para paginar. A tela é a
primeira coisa que se vê: quem abria via cabeçalho, "1 / 1" e nenhuma linha, e
concluía que não havia conta nenhuma.

Agora o resumo por conta é **materializado na primeira leitura**
(`razao_por_conta.parquet`, uma linha por conta em vez de milhões) e reusado
depois. Medido na base real: 25,7 s na primeira abertura, 80 ms nas seguintes,
150 ms com busca. Não é cache de consulta — é a mesma agregação, feita uma vez;
some o arquivo e ele se refaz, e o mtime do razão manda nele. Escreve em nome
provisório e renomeia, porque duas telas abrindo juntas leriam um parquet pela
metade, e isso não dá erro: dá conta faltando na lista.

**De onde veio o formato.** Do Streamlit (`4_ECD_Razao_Contabil.py`), que é como
a casa faz isso hoje: escolhe-se no plano de contas e o razão sai consolidado
das escolhidas. As colunas já eram as mesmas — CNPJ, conta, competência, data,
número, valor, D/C, saldo acumulado, histórico, participante. O que faltava era
poder escolher.

---

## 2026-09-23 — O SQLite aceitava a consulta que o Postgres recusa

**O erro.** "Quebrar os SPED" respondia **"O motor do sistema não respondeu"**.
O motor estava de pé e a saúde dizia `ok`: o que não respondia era a etapa. A
consulta que lista o que abrir era

```sql
SELECT DISTINCT caminho ... ORDER BY competencia, caminho
```

e o Postgres recusa isso — `for SELECT DISTINCT, ORDER BY expressions must
appear in select list`. O `ProgrammingError` subia como 500 no canal interno, e
500 não é recusa com motivo: o C# o traduz para `MotorIndisponivel`, que na tela
vira "o motor não respondeu". A mensagem estava certa sobre o canal e calada
sobre a causa.

**Por que a suíte inteira passou.** Os testes rodam em SQLite, que aceita essa
consulta. Havia teste de integração iniciando as duas etapas, e ele passava. O
erro só existia no banco em que o sistema roda.

**A correção.** A consulta traz a competência no `SELECT` — com `DISTINCT`, tudo
que ordena precisa estar selecionado — e vive num lugar só,
`rodada.caminhos_do_lote`, usada pela quebra de SPED e pela apuração das
contribuições. As duas tinham a mesma consulta copiada, e portanto o mesmo erro:
a segunda etapa de PIS/COFINS morreria igual assim que alguém chegasse nela.
Repetição some no caminho (o mesmo arquivo pode vir em dois lotes) e vai para o
log com contador, como todo descarte.

**O teste que faltava.** `test_fontes_da_etapa.py` compila a consulta no dialeto
do **Postgres** e exige que todo `ORDER BY` esteja no `SELECT DISTINCT`. É a
única forma de pegar isso sem subir um Postgres na bateria: conferir o resultado
não adianta, porque no SQLite ele sai certo mesmo com a consulta errada.

**Regra que fica.** Consulta nova com `DISTINCT` ordena só por coluna que ela
seleciona. Quando o banco de teste e o de produção discordam, o teste tem de
olhar a consulta, não o resultado.

---

## 2026-09-23 — Arquivo útil é útil para um trabalho, não no absoluto

**O bloqueio.** Apontar uma pasta de EFD-Contribuições num trabalho de
PIS/COFINS trazia o botão de importar **desabilitado**, com "Nada aqui alimenta
a CAT 42, então não há o que importar". Não era aviso: era recusa. A base do
trabalho de PIS/COFINS não entrava no sistema — e a API respondia 422 mesmo se
alguém chamasse direto.

A causa é a mesma da entrada anterior, um passo adiante: `alimenta_a_cat` era
um sim/não do arquivo, quando a pergunta certa é *para qual trabalho*.

**A mudança.** `TipoDeArquivo` passa a declarar os módulos que leem cada
arquivo, nos dois domínios — `dominio/lote.py` e `TiposDeArquivo.cs` —, e o
teste de compatibilidade agora confere **também esse mapa**, além de rótulo,
grupo e a CAT. Divergir os dois lados voltaria a recusar pasta que serve.

Com isso, o que era medido contra a CAT 42 passa a ser medido contra o módulo
do trabalho: o que o lote conta como útil, o período que ele anuncia, o que a
tela pinta como aproveitável, e a recusa — que agora nomeia o trabalho e diz o
arquivo que falta *nele* ("Falta a EFD-Contribuições, a ECD ou a EFD
ICMS/IPI").

**Quem decide continua sendo um só.** O motor conhece o tipo do arquivo e o
módulo do trabalho, então é ele que responde `alimenta` por arquivo e `modulo`
no resumo; a API repassa. A tabela do C# entra só onde o motor não está: o lote
já gravado, que a tela relista por tipo.

**O contrato mudou de nome**: `alimenta_a_cat` virou `alimenta` no DTO do lote.
O nome antigo passaria a mentir no primeiro trabalho de PIS/COFINS, e nome que
mente custa mais caro que renomear cedo.

---

## 2026-09-23 — A remessa deixa de ser medida só pela CAT 42

**O defeito.** Quem enviava uma EFD-Contribuições para abrir um trabalho de
PIS/COFINS lia na conferência: *"Nenhum arquivo é EFD ICMS/IPI"*, em tom de
atenção, e *"0 servem à CAT 42"* na contagem de arquivos. Nada estava
bloqueado — o pré-cadastro seguia —, mas a tela dizia que o arquivo não servia
justamente quando ele era o arquivo daquele trabalho. O cadastro nasceu quando
só existia a CAT 42 e ficou medindo toda remessa por ela.

**A escolha.** Cada tipo de SPED passa a declarar **a que módulo serve**
(`TipoSped.modulos`), e a análise devolve duas listas separadas:

- `avisos` — o que exige decisão de quem cadastra: empresas diferentes na
  mesma remessa, matriz deduzida da raiz, arquivos não reconhecidos;
- `observacoes` — o que a remessa alimenta, em tom de informação: *"1 EFD
  Contribuições: serve ao trabalho de PIS/COFINS."* A falta de EFD ICMS/IPI
  virou uma linha dessas, não mais um alerta.

A EFD ICMS/IPI aparece em dois módulos, e é proposital: além de ser o arquivo
da CAT 42, é dela que sai a exclusão do ICMS da base do PIS/COFINS. A ECD
também serve a dois — razão contábil na quebra de SPED, base contábil do lucro
real.

**As chaves de módulo estão duplicadas** entre `Segmento.cs` (catálogo) e
`cabecalho.py` (o mapa acima). Ficou assim porque a frase da tela é escrita no
motor, e nome de módulo é vocabulário estável. Se um terceiro lugar precisar
da lista, ela vira contrato e sobe para um só.

**O passo seguinte veio junto.** O tributo do projeto vinha sempre ICMS, e o
nome nascia "Ressarcimento ST" — de novo, o mundo da CAT 42. Agora o tributo
começa no que os arquivos indicam, entre os que a pessoa enxerga, e o nome
sugerido acompanha o tributo até alguém digitar o seu.

---

## 2026-09-23 — A Gestão vira etapa, e o formato longo no meio do caminho

**O que entrou.** `apuracao_contribuicoes`, a segunda etapa do módulo de
PIS/COFINS: lê a EFD-Contribuições e a ECF do lote e entrega **uma planilha**
com os quatro tributos em abas — PIS e COFINS nos 36 quadros, IRPJ e CSLL do
Lucro Real.

**As duas fontes são independentes, e a etapa roda com o que houver.** Um
trabalho que só tem ECF ainda tem IRPJ/CSLL para mostrar; faltarem as duas é que
é motivo para recusar. Cada ausência vira aviso na rodada — descobrir que a ECF
não entrou só ao abrir a planilha é tarde.

**Não depende da quebra de SPED.** As duas leem os mesmos arquivos, para coisas
diferentes: a quebra produz o par que se confronta com a contabilidade, esta
produz a apuração. Amarrar uma à outra obrigaria a reler 1 GB para ver um
quadro.

**O parquet é longo; a planilha é larga.** O relatório do MA tem uma coluna por
mês, e é assim que se lê. Guardar largo em parquet significaria um esquema que
muda a cada trabalho — doze colunas num, sessenta noutro —, e toda consulta
teria de descobrir os nomes das colunas antes de somar. Então o disco guarda uma
linha por (tributo, quadro, linha, competência), com esquema fixo, e o largo
nasce na saída, que é onde ele faz falta. Quem confere contra o MA baixa o
largo; quem consulta lê o longo.

**Três coisas que o número sozinho não diz, e que viajam com ele:**

* **`externo`** — a linha existe no relatório do MA mas vem de fonte que não
  lemos (DCTF, e-CAC). Fica **nula**, não zerada, e a planilha a mostra vazia e
  cinza. Zero é uma afirmação, e não temos como fazê-la;
* **`unidade`** — quase tudo é dinheiro em centavos, menos o percentual de
  rateio de créditos. Formatar os dois igual faria 85% virar R$ 0,85;
* **`titulo`** — cabeçalho de subquadro, sem valor: sai em negrito e não entra
  em soma nenhuma.

**A tela diz a confiança antes de mostrar o número.** PIS e COFINS foram
conferidos contra o export real do MA em 59 competências; IRPJ e CSLL nunca
passaram por gabarito. Isso aparece em aviso no topo do resultado e em etiqueta
ao lado de cada tributo — não num rodapé. Quem entrega um número precisa saber
de onde vem a confiança nele.

**Um teste que perdeu o caso e ganhou uma costura.** `Etapas` tinha um teste
para a regra "etapa declarada e ainda não construída aparece como indisponível e
não conta no denominador". Ele se apoiava em `apuracao_contribuicoes` ser a
etapa por fazer — e hoje **nenhuma** está por fazer. Em vez de apagar a regra ou
o teste, `Montar` ganhou uma sobrecarga que recebe o roteiro pronto, e o teste
monta um roteiro com uma etapa inventada. Amarrar um teste de regra à existência
de trabalho pendente é perdê-lo no dia em que o trabalho acaba.

---

## 2026-09-23 — A porta de entrada sem moldura, e o menu que recolhe

**O hub perdeu o menu lateral.** É onde se escolhe o **contexto** — e o menu é
justamente o que aquele contexto passa a mostrar. Oferecê-lo antes da escolha é
pedir que a pessoa navegue para dentro de algo que ela ainda não escolheu.

No lugar dele, uma faixa só: logotipo, quem está logado e Sair. Mais a grade de
56px e o halo laranja que a tela de acesso já usava — é o que faz a porta de
entrada parecer porta de entrada, e não mais uma tela interna.

**Do segundo nível em diante o menu volta**, porque aí já há contexto: a pessoa
está dentro de um segmento e precisa circular por ele.

Isto corrige o que eu tinha decidido ao contrário em 23/09/2026, algumas horas
antes: mantive o menu no hub "para haver caminho de volta". O caminho de volta
existe — o item *Segmentos* no próprio menu, das telas internas. O que não
existia era razão para o hub ter menu.

**O menu recolhe, e lembra.** Quem trabalha numa tabela larga — a 037, o razão,
os 36 quadros — quer os 232px de volta. Recolhido sobram os ícones, com o
rótulo no `title`; o texto some por `sr-only`, e não por deixar de ser
renderizado, para que o leitor de tela continue anunciando o item.

A escolha vai para o `localStorage`: é preferência de quem usa, não estado de
tela — quem recolheu quer a tela larga **sempre**, não até o próximo F5. E a
leitura é protegida, porque navegador com armazenamento bloqueado existe: sem o
valor, abre expandido.

O botão não aparece em tela estreita, onde o menu já é uma barra horizontal no
topo e não há largura a recuperar.

---

## 2026-09-23 — A liberação de segmentos ganha tela

**O que faltava.** A API grava o acesso por segmento desde a v0.66.0
(`PUT /usuarios/:id/segmentos`), e **nenhuma tela chamava**: `definirSegmentos`
existia no serviço e não era importado por lugar nenhum. O acesso existia e não
havia como concedê-lo — quem não nascesse com segmento ficava sem, e ninguém
tinha como arrumar pela interface.

Foi assim que o Victor o procurou e não achou. Não estava escondido: não estava
lá.

**Três lugares, e cada um responde a uma pergunta diferente:**

* **a coluna da lista** — quem enxerga o quê, de relance. Sem nenhum segmento,
  a pílula sai em âmbar dizendo "nenhum", porque essa pessoa entra e não vê
  trabalho algum, e isso tem de saltar antes de alguém reclamar;
* **o formulário de criar** — a liberação junto com o cadastro. Criar e liberar
  são dois recursos na API: o usuário nasce sem segmento e recebe os dele em
  seguida;
* **o formulário de editar** — mudar depois, que é o caso comum.

**Gestor e dev aparecem marcados e travados.** Não é escolha: é o que o papel
significa, e o servidor decide assim independentemente do que esteja gravado
(`Papel.EnxergaTodosOsSegmentos`). Oferecer caixas que a API ignoraria seria
mentir sobre quem manda.

**A dica muda conforme a escolha**, porque o efeito não é óbvio: liberar um
segmento decide **onde a pessoa cai ao entrar**, e não só o que ela vê. Com um
só, ela pula o painel; com dois, escolhe; com nenhum, não vê nada. Descobrir
isso depois, porque alguém entrou numa tela inesperada, é caro.

**Validação: não-gestor precisa de ao menos um.** Salvar sem nenhum seria
gravar uma conta que não serve para nada, e o erro só apareceria no primeiro
acesso da pessoa.

---

## 2026-09-23 — Mais duas abas: Exclusões e Histórico

**Exclusões, declarada e sem código.** O que sai da base do PIS/COFINS antes de
apurar — e a principal é o ICMS destacado, o Tema 69. A aba aparece na barra
como indisponível, dizendo o que vai fazer, porque o caminho inteiro visível é
melhor que um buraco entre Apuração e Gestão.

O motor não existe e a razão está escrita desde 22/09/2026: a exclusão **cruza a
EFD-Contribuições com a EFD ICMS/IPI** do mesmo CNPJ e competência, porque o
campo do ICMS no C170 das Contribuições é facultativo e metade dos clientes o
manda em branco. É a decisão que torna o reaproveitamento de leitura entre
trabalhos um requisito, e não uma conveniência.

**Histórico, em todo módulo.** Já existia como tela e rota, alcançável só por um
botão no canto. Virou funcionalidade da barra nos três módulos.

**E precisou de um conceito novo: a funcionalidade que não conta.** O histórico
nunca "conclui" — é consulta, não tarefa. Somá-lo ao denominador faria o cartão
dizer "3 de 6" para sempre e a barra de progresso jamais chegar ao fim com tudo
pronto. `DefinicaoEtapa` ganhou `Conta`, e `Progresso` passou a ignorar quem o
tem falso.

Foi o que os testes cobraram: três deles comparavam o roteiro de ICMS com o do
Python e passaram a comparar só o que conta — com uma asserção a mais dizendo
que o histórico está lá e não entra na conta.

---

## 2026-09-23 — Quebrar e apurar são coisas distintas, e a barra diz isso

**O erro.** Eu tinha empacotado duas funcionalidades na mesma etapa porque as
portei no mesmo dia. A `quebra_de_sped` produzia quatro parquets, e eles
pertenciam a dois assuntos:

| `arquivos.parquet` · `contagens.parquet` · `indices/` | **quebra**: abrir os arquivos |
| `entradas.parquet` (037) · `razao.parquet` (ECD)      | **apuração**: confrontar fiscal × contábil |

Quem quer olhar um C170 não quer esperar a 037 de um ano inteiro; quem quer a
037 não precisa do índice de todos os blocos. Apontado pelo Victor.

**A separação.** `quebra_de_sped` fica com o inventário e o índice; nasce
`apuracao_piscofins` com o par que se confronta. O custo é reler os arquivos —
uma passada a mais sobre a EFD e outra sobre a ECD, porque nenhuma guarda
estado para a outra. É o preço de serem independentes, e é consciente: foi
amarrá-las para economizar leitura que as fundiu numa coisa só.

O que as duas compartilham desceu para `analitico/escrita.py` — gravar parquet
em lotes, parar quando pedem, anotar de quem é o arquivo. Em módulo próprio para
que nenhuma importe o privado da outra e as duas voltem a ser uma pela porta dos
fundos.

**O roteiro linear virou barra.** `| Arquivos | Quebras | Apuração | Gestão |
Quebra XML |`. A lista numerada dizia que o trabalho é uma fila, e não é: a
pessoa vai à funcionalidade de que precisa.

**E nada trava mais.** A situação `Bloqueada` saiu do domínio. A ordem da CAT 42
continua real — não se monta razão sem movimentos —, mas quem a cobra é o
servidor, com a frase que diz o que falta. Uma frase explica; uma aba apagada,
não. Só o que ainda não existe sai inacessível, e a `quebra_xml` é hoje o único
caso.

**Dois testes perderam o caso e foram reescritos**, não apagados: os que
provavam o travamento passaram a provar que nada trava, e o do `EtapaDto`
ganhou o `nome_curto` que a barra usa.

---

## 2026-09-23 — O hub de cards: a porta de entrada que faltava

**O que entrou.** Três telas e um endereço:

```
login ──► /segmentos ──► /segmentos/:chave ──► /modulos/:chave
          (o hub)        (qual frente)          (os trabalhos)
```

* **`/segmentos`** — um card por segmento que a pessoa enxerga, mais o de
  *Gestão de usuários* para quem administra;
* **`/segmentos/:chave`** — dentro do segmento, qual frente: PIS/COFINS ou CBS;
  ICMS ou IBS. O IRPJ/CSLL tem um módulo só e **pula este nível**;
* **`/modulos/:chave`** — a lista de trabalhos recortada por frente. É a mesma
  tela de `/`, com `?modulo=` no servidor: trocar o recorte não muda o que um
  trabalho é.

**Quem decide o caminho é o servidor, e isso já existia.** `Segmentos.Entrada`
resolve o destino desde a v0.66.0 e o login já o devolvia em `usuario.entrada`
— a tela é que ignorava e mandava todo mundo para `/`. Agora o login e a
`RotaPublica` usam o mesmo destino, então quem tem um segmento só entra direto
nele e nunca vê um hub de um card, que não é escolha nenhuma.

A regra fica no servidor porque é a mesma que decide o que cada rota aceita.
Duas cópias divergiriam, e a tela mandaria alguém para uma página que a API
recusa.

**Uma tela chegada por atalho não é erro.** Quem digitar `/segmentos` tendo um
segmento só é redirecionado; quem digitar `/segmentos/icms` sem enxergar ICMS
volta ao hub. Nenhum dos dois vira mensagem de erro — quem barra de verdade é a
API, em toda rota de trabalho, e a tela só evita o beco.

**Os números dos cards vêm de `/segmentos/resumo`**, não de uma contagem no
navegador: o recorte é o mesmo da listagem (só as empresas que a pessoa
enxerga), e contar aqui exigiria baixar a lista inteira de trabalhos para
mostrar dois números. Módulo sem trabalho nenhum sai zerado, e não some: o card
existe de qualquer forma, e "0 trabalhos" é informação — card ausente não é.

**Onde me afastei do handoff, e por quê.**

* **Vocabulário.** O handoff chama de *módulo* o primeiro nível e de *frente* o
  segundo. Aqui o primeiro nível é **segmento** e o segundo é **módulo** —
  porque `frente` já existe no sistema como o TIPO de trabalho (CAT 42, de-para,
  quebra de SPED), com coluna e restrição de unicidade no banco, e `modulo` é a
  coluna que decide o roteiro de etapas desde a v0.66.0. Renomear os dois para
  caber no desenho custaria uma migração e uma reescrita de domínio para ganhar
  nada;
* **O menu lateral fica.** O handoff pede a porta de entrada sem menu. Mantive
  o menu, com um item **Segmentos** no topo: sem ele, quem entrasse direto num
  módulo — que é a maioria, pela regra de entrada — ficaria preso nele até sair
  e entrar de novo. A alternativa do desenho é um atalho de troca na topbar,
  que é a mesma coisa com mais código.

**O que continua fora:** as pílulas de módulo na lista de usuários e os
chips-checkbox de "módulos liberados" nos modais de criar e editar usuário. O
acesso por segmento já é gravável pela API desde a v0.66.0; falta a tela.

---

## 2026-09-23 — Rota registrada não é tela alcançável

**O defeito.** As telas de PIS/COFINS estavam prontas, testadas e no roteador —
e **ninguém conseguia chegar nelas**. Três buracos em série, todos meus, e cada
um sozinho bastava para esconder tudo:

1. **Todo trabalho nascia no módulo de ICMS.** A coluna `modulo` existe desde a
   v0.66.0 e o roteiro de etapas sai dela, mas o `criarProjeto` da tela nunca
   mandava o campo — e o padrão do banco é `icms`. O roteiro de ICMS não tem a
   quebra de SPED, então a etapa nem aparecia na lista;
2. **A etapa `quebra_de_sped` não tinha destino.** O cartão do trabalho traduz
   etapa em rota por uma tabela (`DESTINOS`, em `Projeto.tsx`), e eu registrei a
   rota no roteador sem acrescentar a linha ali. O cartão renderizava — sem
   botão. Um beco;
3. **O razão contábil só abria de dentro de uma quebra concluída com ECD.**
   Como nenhum trabalho tem ECD importada ainda, a porta nunca existiu.

**O que ficou:** um seletor de **Tributo** no formulário de novo trabalho, nos
dois caminhos que criam trabalho (o de empresa já cadastrada e o do cadastro por
SPED), alimentado pelos segmentos que a pessoa enxerga — criar trabalho num
assunto que ela não vê é criar algo que ela não encontraria depois. O padrão é
ICMS quando ela o enxerga; senão, o primeiro módulo que ela vê.

Mais a linha faltante em `DESTINOS`, e o link do razão contábil solto do dado:
a tela já sabia dizer "nenhuma quebra concluída" e "nenhuma ECD neste lote", e
uma tela que explica o que falta é melhor que um link que não existe.

**A lição, que vale para as próximas.** Passei três versões dando por concluído
"ligar as etapas e construir as telas" com base em rota registrada, teste verde
e build limpo. Nenhuma dessas três coisas prova que existe **caminho**: o
roteador aceita rota órfã, o teste testa o componente isolado e o compilador não
sabe o que é navegação. A pergunta que faltou é a mais simples — *partindo da
tela inicial, em quantos cliques se chega lá?* Se a resposta não existir, a tela
não existe.

**O que continua sem caminho, e está anotado:** as rotas `/segmentos` e
`/modulos/:chave` existem em `routes.ts` desde a v0.66.0 e **não estão no
roteador** — o hub de cards do handoff nunca foi construído. E a Gestão
(`apuracao_contribuicoes`) segue `Implementada: false`: sem tela, o cartão sai
como "não disponível", que é o que ele deve dizer.

---

## 2026-09-22 — A ECF entra, e o 0000 ganha um quarto leiaute

**O que entrou.** A Escrituração Contábil Fiscal e o bloco de IRPJ/CSLL do
Lucro Real que sai dela: Parte A do e-Lalur e do e-Lacs (lucro líquido, adições,
exclusões, compensações), o cálculo do imposto e da contribuição, e o saldo das
contas da Parte B.

**A ECF quebrou a âncora do leitor do 0000, e isso era a coisa a acertar.** Os
três leiautes que o domínio já conhecia compartilham uma sequência: data de
início, data de fim, razão social e CNPJ, coladas nessa ordem. O par de datas
servia de âncora e o resto se lia a partir dele. **A ECF não segue essa
sequência** — nela o CNPJ e o nome vêm *antes* das datas. Pior: pode haver uma
terceira data (`DT_SIT_ESP`, situação especial) colada ao par do período, e aí
o *primeiro* par de datas seria (DT_SIT_ESP, DT_INI) — um período que começa na
data da cisão.

Então a ECF tem âncora própria, também por forma: o CNPJ é o campo de catorze
dígitos, o nome é o que vem depois dele, e o período é o **último** par de datas
consecutivas do registro. Nada depois de DT_FIN tem forma de data, então "o
último par" é sempre o certo — com ou sem situação especial. Há teste para os
dois casos.

A alternativa era ler a ECF por posição fixa dentro do leitor da gestão, como o
projeto de origem fazia. Seria a terceira vez que este projeto lê um 0000 por
posição, e as duas primeiras deram errado em silêncio.

**UF e município saem vazios, de propósito.** O 0000 da ECF não os traz — eles
estão no 0030, que é outro registro e não é problema deste leitor. Inventar um
valor seria pior que a ausência.

**`sped_ecf` entrou no catálogo de tipos**, no classificador e no espelho em C#
que a tela usa. Sem a entrada no espelho, o arquivo apareceria como "Não
reconhecido" — e há teste de compatibilidade que cobra as duas tabelas iguais.

**IRPJ e CSLL valem menos que PIS e COFINS, e isso está escrito.** A validação
das 59 competências cobriu PIS e COFINS. O IRPJ/CSLL de referência é de outra
empresa, e a comparação ficou pendente também no projeto de origem. O oráculo
`tools/validar_gestao.py` passou a aceitar os dois tributos e a pasta da ECF —
rodá-lo contra um export real é o que falta.

**Uma suspeita registrada, não corrigida.** Quando o e-Lalur não traz linha de
"compensação do próprio período", a regra portada deduz esse valor da diferença
entre o lucro real antes e depois da compensação. Só que essa diferença é a
compensação **inteira**, inclusive a de períodos anteriores: havendo prejuízo
anterior compensado, o mesmo valor sai nas duas linhas. Provavelmente a dedução
só deveria valer quando não há compensação anterior nenhuma.

Não mudei. Estes quadros nunca passaram por gabarito, e mudar regra fiscal por
raciocínio — sem arquivo que confirme — foi exatamente como o erro da natureza
do crédito nasceu. O comportamento atual está **fixado em teste** e comentado no
código, para que a correção, quando vier, seja deliberada e a suspeita não se
perca no caminho.

---

## 2026-09-22 — A Gestão (36 quadros) entra: o núcleo, e o gabarito que não se versiona

**O que é.** Os mesmos 36 quadros que o Sistema MA exporta na "Gestão" de
PIS/Pasep e COFINS — receita por CST, contribuição apurada, natureza dos
créditos, ajustes, controle de saldos —, montados a partir da
EFD-Contribuições. Cada quadro é uma lista de linhas; cada linha, um valor por
competência.

**A forma do porte: um resumo por arquivo, e os quadros sobre o resumo.**

```
EFD-Contribuições ──► agregador ──► ApuracaoEFD ──► quadros ──► Relatorio
     (1 GB)          uma passada     (poucos MB)      regras     36 quadros
```

O `ApuracaoEFD` guarda os registros de apuração inteiros (são poucos por
arquivo), os ajustes somados por código e os itens dos blocos A/C/D/F agregados
por chave — nunca linha a linha. Cabe em memória quando o arquivo não cabe, e
é ele que os quadros consomem. **Trocar a regra de um quadro não obriga a reler
1 GB**, que é a diferença entre iterar numa regra em segundos e em minutos.

**Centavos inteiros, não float.** Somar float de milhões de linhas acumula
erro, e o MA arredonda o crédito recalculado **por grupo**: um erro de 1e-9 no
lugar errado vira um centavo de diferença. Valores em centavos, alíquotas em
décimos-milésimos de ponto percentual.

**O crédito dos quadros 32 e 33 é recalculado, não somado.** O MA não soma o
`VL_PIS` das linhas: refaz base × alíquota por grupo (registro, CST, CFOP,
natureza, alíquota), arredonda cada grupo ao centavo e só então soma. Somar o
campo do arquivo dá outro número, e o relatório deixaria de bater.

**Portado fiel de novo, e pelo mesmo motivo da 037.** As regras aqui não foram
deduzidas do Guia Prático — foram confrontadas com o export real da Gestão do
MA em **59 competências**, e o que bateu centavo a centavo está marcado
`# VALIDADO` ou `# CONFIRMADO` linha a linha. Sem esse export eu não teria como
redescobri-las nem revalidá-las. Onde eu discordaria, escrevi comentário.

**O 0000 passou pelo domínio, como manda a regra da casa.** O original lia
`c[5], c[6], c[7], c[8]` — que até acerta na EFD-Contribuições, mas é a forma
que já devolveu UF no lugar de CNPJ duas vezes neste projeto. Agora quem lê é
`dominio/sped/cabecalho.py`, que acha cada campo pela forma.

**Uma apuração por competência.** Original e retificadora ficam na mesma pasta,
e a retificadora substitui a original por inteiro: ler as duas dobraria o mês e
misturaria valores de antes e depois da retificação. A retificadora vence;
havendo empate, o arquivo mais novo — e o preterido vira aviso com os dois
nomes, nunca some calado.

**O gabarito não se versiona, então virou ferramenta.** A validação das 59
competências tem por gabarito o CSV da Gestão de uma empresa real. Isso é dado
de cliente: não entra no repositório, e por isso não vira teste automatizado.
O que entrou foi `tools/validar_gestao.py`, que recebe os caminhos por
argumento, compara linha a linha com tolerância **zero** e sai com código 1 se
houver divergência. Foi com tolerância zero que a validação achou as duas
únicas diferenças de R$ 0,01 que existiam em 22.243 valores de COFINS.

Os testes automatizados cobrem as regras sobre uma amostra sintética montada
**pelo nome do campo** — e, de quebra, conferem que os índices do leiaute da
gestão concordam com `sped/registros.py`, que é o leiaute desta casa.

**O que ficou de fora**: IRPJ/CSLL (vem da ECF, é outro leitor e outro conjunto
de quadros) e a etapa em si — fila, planilha e tela vêm em seguida. O que está
aqui é o núcleo: ler e montar.

---

## 2026-09-22 — A tela do razão da ECD: por que não basta o download

**O problema com o download.** A quebra já entregava `razao.parquet` e a
planilha do razão contábil inteiro. Numa ECD de rede de supermercado isso é
milhão de partidas — e quem confronta a escrituração com a contabilidade não
quer o arquivo: quer **uma conta**. Quer a 3.1.1 de junho, com o saldo correndo,
para conferir contra a 037. Abrir um xlsx de milhão de linhas para achar uma
conta é o gesto errado, e é o que a tela existe para evitar.

**Dois passos, não um.** Primeiro o **seletor**: uma linha por conta, com
partidas, débitos, créditos e saldo, buscável por código, por nome e pela conta
referencial. Depois os **lançamentos** da conta escolhida, em ordem de data. Foi
assim que a Ficha 3 da CAT 42 resolveu o mesmo problema, e repetir a forma é o
que faz a segunda tela não precisar ser aprendida.

**Nada é recalculado na leitura.** O saldo corrente de cada linha veio de
`sped/ecd.py::razao`, que conhece a ordem certa — a do tempo, não a do arquivo,
porque o SPED não obriga lançamento a vir em ordem de data. O módulo de leitura
agrega e recorta; a aritmética contábil já aconteceu. Por isso a listagem
**ordena por `data, numero`**, que é exatamente a chave que gerou o saldo:
ordenar por outra coisa faria a coluna de saldo mentir sem dar erro nenhum.

**Os totais são da conta, não da página.** Um total que muda ao virar a página
não serve para conferir nada. Quando há recorte de data ou busca, os totais são
os do recorte — e a resposta diz `recortado: true` para que a tela possa dizê-lo
também, em vez de deixar quem lê achar que aquele é o saldo da conta.

**Saldo devedor e credor, não positivo e negativo.** A coluna mostra o valor
absoluto com um `D` ou `C` ao lado. Sinal de menos num razão é ruído: o contador
lê lado, não sinal.

**Tudo é texto no parquet, e a conversão fica à vista.** O escritor da quebra
grava toda coluna como string de propósito — esquema igual desde a primeira
linha, sem depender do que apareceu no primeiro arquivo. Somar exige `CAST` para
`DECIMAL(24,2)`, que o DuckDB faz na varredura. É barato, e é honesto: o arquivo
guarda o que o SPED escreveu.

**A etapa exigida muda, e o teste cobra.** Há dois razões no sistema, com o
mesmo nome e de módulos diferentes: a Ficha 3 da CAT 42 (etapa `razao`, no ICMS)
e o razão contábil da ECD (etapa `quebra_de_sped`, no PIS/COFINS). Pedir um pela
rota do outro devolve 404, e há teste em C# que o exige — sem isso a confusão
sairia calada, lendo parquet de outra coisa.

---

## 2026-09-22 — O enriquecimento, e a natureza do crédito que vinha do campo errado

**O que entrou.** As colunas que traduzem código em texto passam a sair ao lado
das cruas, nunca no lugar delas: descrição do CFOP, município do participante,
o que cada indicador do C100 quer dizer, o tipo do item por extenso, o período
da competência e a natureza da base de cálculo do crédito. Quem confere precisa
ver o `1102` e o "Compra p/comercial" na mesma linha — se a planilha só trouxer
o texto, ninguém consegue conferir contra o arquivo; se só trouxer o código,
ninguém consegue ler.

**A correção que importa: a natureza do crédito vem do CFOP, não do TIPO_ITEM.**
O C170 e o C191/C195 não têm campo `NAT_BC_CRED` — só o C501, o D101, o D501 e
o bloco F o têm escrito. Nos que não têm, ela é deduzida. Portei do projeto de
origem a dedução pelo `TIPO_ITEM = "00"`, marcada como heurística, e estava
**errada**:

* a regra do TIPO_ITEM tinha sido confirmada contra o relatório de referência de
  duas empresas — uma amostra em que o campo vinha preenchido;
* a regra do CFOP foi conferida contra **43.497 linhas** de um relatório real e
  reconfirmada contra outras **81.150**, em vinte CFOP distintos, sem uma
  exceção. Na segunda amostra o `TIPO_ITEM` vinha constante em `"99"` em **100%**
  das linhas — a regra antiga teria apagado a natureza da base inteira.

O argumento não é só de volume. A natureza descreve a **operação**; o CFOP é o
que codifica a operação. O tipo do item descreve a **mercadoria**, que é outra
coisa. A regra antiga acertava por correlação, não por causa.

**O TIPO_ITEM fica como segunda tentativa**, e só para o código `"00"`: serve ao
CFOP que a tabela não conhece, quando o cadastro diz que a mercadoria é de
revenda. Fora isso, branco de propósito — natureza errada com cara de certa é
pior que coluna vazia.

**Consequência a registrar:** a nossa 037 passa a divergir do relatório de
referência do Sistema MA nas linhas em que o CFOP e o tipo do item discordam.
Isso é a mudança dando certo, não um defeito — mas quem comparar as duas saídas
lado a lado vai ver diferença, e precisa saber por quê.

**O município entrou na 037.** O projeto de origem derivava a UF do código do
IBGE do 0150 e jogava o município fora. Agora os dois saem, do mesmo código, na
mesma passada. Os ramos sem participante — o C190 consolidado, o F120 e o F130 —
ficam com a coluna em branco, que ali é o significado certo: não há de quem.
A 037 vai de 51 para 52 colunas, e o teste de contrato cobrou a mudança, que é
exatamente o que ele existe para fazer.

**Nomes: os do relatório de origem.** As treze colunas traduzidas saem com o
nome de lá, sufixo `_DESC` incluído, e o período em `dd/mm/aaaa` como a 037 já
usava. Todo o resto daquele relatório já sai com o nome de lá — `C170_CFOP`,
`0200_COD_NCM` —, e rebatizar só estas treze faria quem compara os dois lado a
lado tropeçar sem ganhar nada.

---

## 2026-09-22 — A etapa de quebra: o par que se confronta sai junto

**O que a etapa faz.** Primeira do módulo de PIS/COFINS depois da importação.
Lê a EFD-Contribuições e a ECD do lote e escreve quatro parquets — mas dois
deles são o ponto: a **Consulta de Entradas (037)** e o **razão contábil**.

**Por que os dois saem da mesma rodada.** Porque é o par que se confronta: a 037
diz o que a escrituração fiscal registrou como entrada, o razão diz o que a
contabilidade lançou, e onde discordam está o trabalho. Separá-los em duas
etapas obrigaria a juntar depois, sobre bases que podem ter sido montadas em
momentos diferentes — e a primeira pergunta de quem confere é "os dois lados são
da mesma leitura?".

**Por que a extração sai na etapa, e não no download.** A leitura é sequencial e
custa o arquivo inteiro: gerar a 037 na hora do clique obrigaria a reler 5 GB a
cada download. O **índice**, esse sim, fica em cache por arquivo — é o que torna
barato dizer "o que tem aqui dentro" sem reler nada.

**Fora do rito da CAT 42, de propósito.** A quebra não depende de conferência
nem de movimentos: aquelas são etapas do ICMS. O roteiro de PIS/COFINS é
importar e quebrar — e foi para isso que o roteiro virou por módulo, na v0.69.

**Arquivo ilegível não derruba a rodada.** Ele é contado, entra na lista com o
motivo, e a quebra segue. Uma ECD truncada no meio de doze não pode custar as
outras onze.

**Trabalho sem arquivo nenhum produz parquet vazio, não ausência de parquet.** A
etapa seguinte não deveria precisar saber a diferença entre "vazio" e "não
rodou" — e o esquema vem da tabela de registros, não da primeira linha lida.

---


## 2026-09-22 — A Consulta de Entradas (037): porte fiel, e por quê

**O que é.** Equivalente à consulta *037 — Entradas — Todos os Registros —
Completos* do Sistema MA, gerada **só a partir da EFD-Contribuições**. É a saída
que se confronta com o razão da ECD: o que a escrituração fiscal diz ter entrado
contra o que a contabilidade lançou. Prioridade do Victor, junto com a ECD.

**Portado fiel, de propósito.** O que está neste módulo não foi deduzido do
leiaute — foi **confirmado contra arquivo de referência real de duas empresas**,
e sem esse arquivo eu não teria como redescobrir nem revalidar. Onde eu
discordaria, escrevi comentário em vez de mudar a regra. Três coisas que só o
dado real ensina:

* **o C190 variou de 0% a 95%.** Na primeira empresa validada não havia uma
  ocorrência; na segunda era o ramo dominante. Quem tratar o C100/C170 como "o
  caminho normal" acerta num cliente e perde o relatório inteiro no outro;
* **o `COD_PART` do C191/C195 não referencia o 0150** naquela empresa — é o CNPJ
  direto, sem cadastro. Esse ramo sai sem nome de participante, e a UF é só a do
  estabelecimento;
* **o bloco D tem abridor próprio (D010)**, independente do C010. Sem ele,
  documento de **filial** saía com CNPJ de **matriz**. Bug real, achado na
  validação — e agora com teste que o cobra.

**Duas heurísticas, marcadas como tais.** `natureza_do_credito` e
`debito_ou_credito` não saem do arquivo: são deduzidas. Ficam isoladas em
funções próprias, para que ninguém as confunda com leitura — e para que
corrigi-las um dia seja mexer num lugar só. *Foi o que aconteceu com a primeira
no mesmo dia: a dedução pelo `TIPO_ITEM` estava errada e passou a vir do CFOP —
ver a decisão do enriquecimento, no topo deste arquivo.* A segunda segue com
~98% de aderência, com as discordâncias em CFOP de devolução.

**O que ficou de fora**: A100/A170, C395/C396 e F150. Nenhuma empresa validada
teve ocorrência, e inventar regra de preenchimento seria pior que a ausência.

**Uma lição de método.** Montei a amostra de teste contando pipe a olho três
vezes, e errei as três — no C170, no M210 e aqui. Agora a amostra é **gerada por
nome de campo** a partir da tabela de registros: nome errado explode na hora de
montar, em vez de produzir um valor plausível na coluna errada.

---


## 2026-09-22 — A quebra da ECD, e o 0000 que mordeu duas vezes

**Por que ela vem antes da Gestão** (prioridade do Victor, 22/09/2026): a ECD é
a escrituração **contábil**, e o razão dela é o documento contra o qual se
confere o que a escrituração fiscal diz. A receita do razão tem de bater com a
receita da EFD — é daí que sai boa parte do trabalho de PIS/COFINS.

**O desenho que faz isso ser rápido.** Uma passada guarda o plano de contas
(I050) inteiro em memória, a posição de todo I200 num array ordenado, e a
posição de cada I250 **agrupada por conta**. Com isso o razão de *uma* conta lê
só as partidas dela, e o lançamento dono de cada partida sai por **busca
binária** — é o último I200 antes dela, porque o SPED escreve pai antes de
filho. Sem isso, o razão de uma conta custaria o arquivo inteiro.

**Três coisas que mudaram em relação ao original:**

* **dinheiro em `Decimal`, não em `float`.** O saldo corre por milhões de
  partidas, e float acumula centavo que não existe. Centavo inexplicável em
  documento contábil é o tipo de coisa que ninguém consegue defender depois;
* **a ordem é a do tempo, não a do arquivo.** O SPED não obriga os lançamentos a
  virem em ordem de data — e na amostra real eles não vêm;
* **partida anterior ao recorte não vira linha, mas entra no saldo.** Sem isso o
  razão do mês começaria do zero, e o saldo seria ficção.

**O 0000 mordeu de novo.** O porte da EFD já tinha caído nisso: ler o registro
0000 por posição fixa. Na ECD o tropeço se repetiu — um arquivo real trouxe dois
campos a mais antes das datas, e o índice devolveu a data no lugar do CNPJ, sem
erro nenhum. A correção foi a mesma da outra vez: **usar
`dominio/sped/cabecalho.py`**, que acha os campos *pela forma* — o par de datas
de oito dígitos, o CNPJ de catorze — em vez de contar posição.

A lição, escrita aqui para não precisar de uma terceira vez: **nenhum módulo
novo lê o 0000 por conta própria.** Só o domínio lê.

---


## 2026-09-22 — O bloco M: oito joins que eram um

**O que é.** O bloco M da EFD-Contribuições é onde o arquivo diz **no que deu**:
quanto de PIS e de COFINS se apurou no período, por código de contribuição, e o
que foi ajustado para mais ou para menos. Os blocos C e D dizem o que aconteceu;
o M diz o resultado — é dele que sai o número que o cliente pergunta.

**PIS e COFINS são espelhos, registro a registro.**

| | crédito | base do crédito | ajuste | contribuição | detalhe | ajuste |
|---|---|---|---|---|---|---|
| **PIS** | M100 | M105 | M110 | M200 | M210 | M220 |
| **COFINS** | M500 | M505 | M510 | M600 | M610 | M620 |

O projeto de origem tinha **oito funções** para isso, cada uma com suas ~50
linhas, e elas eram byte a byte a mesma coisa com os nomes trocados. Aqui é uma
função e uma tabela de cadeias. A regra que as oito escondiam é simples: *cada
linha sai do registro mais fundo, carregando os de cima, e "o de cima" é o
último que apareceu* — porque o SPED escreve pai antes de filho.

**O que a leitura ingênua estraga.** Quando dois M210 dividem o mesmo M200, o
ajuste do segundo não pode sair carregando o primeiro. Guardar "o último pai
visto" sem limpar os níveis abaixo faz exatamente isso, e o erro é invisível: os
valores existem, são do mesmo período, e só o código de contribuição denuncia.
Trocar de pai limpa o que estava aberto abaixo dele — e virou teste.

**Pai ausente sai em branco, a linha não some.** Arquivo de cliente tem bloco
truncado; perder o ajuste porque o M200 faltou seria perder valor apurado sem
dizer nada.

---


## 2026-09-22 — O caminho consolidado, e a armadilha dos filhos não intercalados

**Por que ele existe.** Metade dos clientes escritura a EFD-Contribuições item a
item, no C170; a outra metade consolida por produto e CFOP, no **C180** (notas
emitidas) e no **C190** (adquiridas). Não é escolha nossa qual ler: é como o
arquivo veio, e a apuração tem de ler os dois.

**A armadilha.** Os filhos que detalham PIS e COFINS **não vêm intercalados**.
Vêm *todos* os de PIS e só depois *todos* os de COFINS, e o casamento é **por
posição** — `C191[i]` com `C195[i]`. Supor 1:1:1 na leitura sequencial, que é a
suposição natural de quem lê o leiaute, soma o PIS de um CFOP com o COFINS de
outro **sem erro nenhum aparecer**: os dois valores existem, os dois são do
mesmo produto, e só o CFOP denuncia. Fato confirmado em dado real no projeto de
origem; aqui virou teste.

**E o grupo não é 1:1 nem em quantidade.** Um C180 pode ter mais filhos que o
vizinho — em base com vários estabelecimentos a contagem de C180 vem menor que a
de C181. Quando as listas têm tamanhos diferentes, sai uma linha por posição
existente, com o lado que faltou em branco: perder a linha seria perder valor
apurado.

**Uma função para os dois.** No projeto de origem eram duas de ~150 linhas quase
idênticas. C180 e C190 têm o mesmo leiaute e o mesmo par de filhos; o que muda é
o nome e o fato de os filhos do C190 trazerem `COD_PART` — a aquisição sabe de
quem se comprou, a venda consolidada não diz para quem se vendeu.

---


## 2026-09-22 — Tema 69: cruzar os dois SPED, e não confiar no C170 sozinho

**A dúvida que a v0.70 levantou.** O C170 da EFD-Contribuições tem `VL_BC_ICMS`,
`ALIQ_ICMS` e `VL_ICMS` no leiaute — é o mesmo registro da EFD ICMS/IPI. Se o
contribuinte os preenche, a exclusão do ICMS da base sairia do próprio arquivo,
sem cruzar nada.

**A decisão do Victor (22/09/2026): cruzar sempre.** O preenchimento desses
campos na EFD-Contribuições **não é obrigatório**. Um arquivo que vem com eles
em branco é um arquivo correto, não um arquivo com defeito — e por isso a
ausência não é exceção a tratar, é o caso normal de metade dos clientes.

**Por que isso decide o desenho, e não só o valor.** Uma apuração que lê o C170
quando ele está preenchido e cruza quando não está teria **dois caminhos de
cálculo para o mesmo imposto**, e o resultado dependeria de como o ERP do cliente
foi configurado. Duas empresas idênticas dariam números diferentes, e a
diferença não estaria em lugar nenhum do relatório. Cruzar sempre custa uma
leitura a mais e dá uma resposta só.

**O que isso implica.** A exclusão do Tema 69 depende da EFD ICMS/IPI do mesmo
CNPJ e da mesma competência — e é por isso que a leitura compartilhada entre
trabalhos (v0.67.0) deixou de ser conveniência e virou requisito: sem ela, o
trabalho de PIS/COFINS teria de reimportar a base que o de ICMS já tem.

> **Revisto em 30/09/2026.** A previsão de que o campo viria em branco "em
> metade dos clientes" não se sustentou na medição: 138.358 itens com ICMS
> destacado nos 57 arquivos da empresa 05, nenhum em branco — e o relatório do MA,
> que é o padrão conferido pelo cliente, sai do mesmo campo. A tese passou a
> sair da EFD-Contribuições sozinha. Ver a decisão de 30/09/2026.

---


## 2026-09-22 — A quebra de SPED entra, e o leitor do 0000 é o que já existia

**O que foi portado.** O núcleo do projeto Quebra de SPED, para
`infraestrutura/sped/`: o **índice** (uma passada, contagem de cada registro e
posição em bytes dos alvos) e o **join do item** (C170 com a nota, o
estabelecimento e as três tabelas do bloco 0). Fica em `infraestrutura/`, e não
dentro de um módulo tributário: ler SPED serve a todos.

**Medido em arquivo real** — EFD ICMS/IPI de 31,3 MB, 601.486 linhas:

| | |
|---|---|
| indexação | 0,8 s (37,7 MB/s) |
| índice do cache | 0,13 s |
| página 5.000 do C170 por `seek` | **0,001 s** |
| join do item | 0,7 s · 17.129 itens |

**O defeito que o arquivo real achou.** O porte trazia o leiaute do registro
0000 da **EFD-Contribuições**, e só dele. Apontado a uma EFD ICMS/IPI — em que
CNPJ, nome e datas ficam em **posições diferentes** —, devolvia a UF no lugar do
CNPJ e a razão social no lugar da data, sem erro nenhum. Nenhum teste de unidade
pegaria isso: a amostra era de Contribuições.

A correção não foi consertar as posições: foi **usar o que já existia**.
`dominio/sped/cabecalho.py` detecta os três leiautes desde sempre, porque a CAT
42 já lia EFD ICMS/IPI, Contribuições e ECD. Portar um segundo leitor do 0000
seria exatamente o que a decisão do dia anterior proibiu — dois leitores da mesma
coisa, que um dia divergem.

**O que ficou de fora desta fatia**, de propósito: o enriquecimento do original
(descrição de CFOP, natureza de crédito, município) e os outros ~20 joins
hierárquicos. São tabelas auxiliares e não fazem falta para a exclusão do ICMS
da base, que é o que motivou o porte.

**Uma pista para a etapa seguinte.** O C170 da EFD-Contribuições tem
`VL_BC_ICMS`, `ALIQ_ICMS` e `VL_ICMS` no leiaute — é o mesmo registro da EFD
ICMS/IPI. Se os clientes os preencherem, a exclusão do Tema 69 sai do próprio
arquivo, sem cruzar nada. Vale medir antes de construir o cruzamento.

---


## 2026-09-22 — Como o banco trata os módulos: o que vira tabela e o que não

**A pergunta do Victor:** com quatro módulos tributários chegando, como ficam as
tabelas?

**A medição, antes da opinião.** O Postgres inteiro tem **66 MB** em 13 tabelas;
o dado fiscal em disco tem **32 GB** de parquet. Essa proporção de 500 para 1 já
é a resposta: nenhuma das 13 tabelas é de CAT 42 — são todas espinha (empresa,
usuário, alocação, segmento, estabelecimento, trabalho, evento, lote, arquivo,
execução, de-para, correção). A apuração nunca tocou o banco.

**A regra.** O Postgres guarda **quem, o quê, quando e quem decidiu**. O dado
fiscal mora em parquet. Dito de outro jeito: *entra no banco o que alguém decide,
aprova ou precisa auditar — não o que se calcula.*

Daí decorre que **a quebra de SPED não cria tabela nenhuma**: o índice (contagem
por registro e posição em bytes) é cache de leitura, vai para disco chaveado pelo
arquivo, com versão de esquema que força reindexar quando o leiaute muda. Pôr
offsets em Postgres seria guardar milhões de inteiros por arquivo para responder
o que o `seek()` responde em tempo constante.

**Quando houver tabela de módulo**, três formas e a escolha:

| | quando |
|---|---|
| prefixo (`piscofins_bct`) | a forma é própria daquele tributo |
| genérica com discriminador | a forma é a mesma — é o que `correcao` já faz |
| schema por módulo | **nunca** |

Schema separado resolve um isolamento que não temos: é uma base, uma casa, e a
separação que importa é **por empresa**, que já é por linha e já tem barreira
dura. O que faz a forma genérica funcionar é `projeto.modulo`: toda tabela
pendurada em `projeto_id` herda o módulo de graça. Por isso `correcao` e
`depara_item` servem PIS/COFINS no primeiro dia, sem migração — `correcao` guarda
campo, valor e motivo, e nada ali é de ICMS.

**O acoplamento real não era o esquema: era o roteiro.** `Etapas.Todas` era uma
lista só, e era a da CAT 42. Um trabalho de PIS/COFINS herdaria sete etapas de
ICMS que nunca rodariam, e o cartão diria "0 de 7" para sempre. Agora catálogo e
roteiro são coisas diferentes: `Todas` é tudo que existe, `Roteiros` diz quais
etapas cada módulo percorre e em que ordem. Acrescentar funcionalidade virou uma
linha no catálogo e uma chave no roteiro.

**Por que o roteiro em código e não em tabela.** Uma etapa só existe se houver
código que a rode. Numa tabela, daria para apontar para uma etapa que ninguém
escreveu, e o erro só apareceria quando alguém clicasse. Em código o compilador
cobra a maior parte, e um teste cobra o resto — ele falha se algum roteiro citar
chave fora do catálogo.

**O que vigiar.** `arquivo_do_lote` é 65 dos 66 MB, com 105 mil linhas e só quatro
trabalhos: ela cresce com arquivos **vezes** trabalhos, porque o mesmo arquivo
entra no lote de cada um. É a única tabela do sistema que cresce com volume.

---


## 2026-09-22 — Leitura compartilhada entre módulos: cópia x reaproveitamento

**O pedido do Victor.** A exclusão do ICMS da base do PIS/COFINS (Tema 69) só se
calcula com o **ICMS destacado**, e ele é autoritativo na EFD ICMS/IPI e no XML —
não na EFD-Contribuições. Então o trabalho de PIS/COFINS precisa ler o arquivo
que o trabalho de ICMS já importou.

**O que o código fazia.** A deduplicação olhava só o próprio trabalho
(`existentes_do_projeto`). Dois trabalhos da mesma empresa liam a mesma EFD do
zero, sem saber um do outro — e o arquivo bruto nem é copiado pelo sistema, só o
caminho, então o desperdício nunca foi disco: é **indexação**. Uma base de
119 GB indexada duas vezes.

**A distinção que passou a existir.** Cópia e reaproveitamento não são a mesma
coisa, e tratá-los igual estragava um dos dois:

* **dentro do mesmo trabalho**, o arquivo repetido é **cópia** e fica de fora —
  o mesmo SPED lido duas vezes dobra os documentos;
* **entre trabalhos da mesma empresa**, é **leitura já feita**. O arquivo
  **entra** no lote novo, marcado com o nome de quem o leu primeiro. Recusá-lo
  deixaria o PIS/COFINS sem o dado de que precisa.

**Casa por caminho e por assinatura, nunca por hash.** O hash só é calculado para
candidato a cópia; exigi-lo aqui obrigaria a ler os 119 GB para descobrir que não
era preciso ler nada. O caminho resolve o caso real — a mesma pasta do cliente no
servidor de arquivos —, e a assinatura (tamanho, tipo, CNPJ, competência e
finalidade) cobre a mesma base copiada para outro lugar.

**A granularidade do cruzamento fica em aberto de propósito** (escolha do Victor,
22/09/2026): a EFD-Contribuições vem item a item (C170) em uns clientes e
consolidada (C180/C190) em outros. A etapa terá de escolher a melhor fonte por
competência, como o razão já faz entre XML e EFD — com o XML como saída quando
não há item para cruzar.

**O que esta fatia entrega, e o que não.** Entrega o *saber*: a inspeção já diz
quantos arquivos outro trabalho da empresa leu. **Não** entrega ainda o
reaproveitamento do material derivado — o parquet extraído continua sendo gerado
por trabalho. Essa é a fatia seguinte, e é ela que corta o tempo.

---


## 2026-09-22 — Acesso por segmento tributário: a terceira dimensão

**O pedido do Victor.** Depois do login, uma tela de cards por tributo —
PIS/COFINS, ICMS, IRPJ/CSLL —, e dentro de cada um os módulos. Quem é gestor vê
todos; os demais caem direto no que o gestor liberou. A gestão de usuários passa
a morar nessa tela principal, e é lá que o gestor indica em que assunto cada
pessoa trabalha.

**O desenho.** O sistema já separava duas dimensões de acesso: **papel** diz o
QUE a pessoa pode fazer, a **alocação por empresa** diz SOBRE QUEM. O segmento é
a terceira e é ortogonal às duas: diz EM QUE ASSUNTO. Um analista alocado na
carteira inteira e liberado só para PIS/COFINS não vê trabalho de ICMS.

**Quatro escolhas, todas do Victor (22/09/2026):**

* **quem enxerga tudo é o papel `gestor`, não o cargo.** O sistema documenta que
  cargo é informação organizacional, sem permissão nenhuma; dar permissão a ele
  criaria dois caminhos para a mesma regra. Gestor e dev enxergam todo segmento
  pela mesma razão que já ignoram o escopo de empresa;
* **a reforma casa com o tributo que sucede:** CBS ao lado de PIS/COFINS, **IBS**
  ao lado de ICMS. O pedido original dizia CBS nos dois; a CBS substitui
  PIS/COFINS e o IBS substitui ICMS/ISS. De 2027 a 2033 é a mesma equipe
  apurando os dois lado a lado — segmento separado para a reforma partiria
  exatamente quem precisa ver os dois juntos;
* **IRPJ e CSLL são um card só**: apuram juntos, mesma base, mesma ECF;
* **com dois ou mais segmentos, a pessoa cai na tela de segmentos filtrada.**
  Com um só, pula essa tela; se esse único segmento tiver um módulo só, pula as
  duas e vai direto ao trabalho. Escolher entre uma opção não é escolha.

**Onde a decisão de entrada é tomada.** No servidor, e vem pronta no login
(`usuario.entrada`). A tela obedece. Quem sabe quais segmentos a pessoa tem é
quem guarda a regra, e repetir a conta em TypeScript daria duas fontes para a
mesma verdade.

**O que a migração precisou fazer, e quase não fez.** A coluna nova nasce negando
tudo a todo mundo: no instante em que a tabela é criada, ninguém tem segmento, e
analista, revisor e leitura ficariam trancados fora do que usam todo dia. Foi um
teste que acusou. A migração preenche: todo usuário que não é gestor nem dev
recebe `icms`, porque **todo trabalho que existe é de ICMS** — o sistema nasceu
na CAT 42. O trabalho ganhou `modulo` com o mesmo padrão, pelo mesmo motivo.

---


## 2026-09-21 — Vigência: o sistema não conhece data de lei, e a ST acaba em 04/2026

**A pergunta do Victor (21/09/2026):** os 25% do art. 55, IV foram conferidos
contra o período em que vigora a monofasia dos itens do capítulo 33 da TIPI?

**O que se conferiu, e o que se achou.**

**1. Não existe "25%" escrito no sistema.** A alíquota do confronto vem do que o
contribuinte declarou na EFD, **por competência** — `aliq_mes` casa
`cnpj + codigo + mês` com o `ALIQ_ICMS` do 0200/C170 — e, na falta dela, da
alíquota da entrada interna. Nenhuma data de lei está codificada em lugar
nenhum. Isso é mais seguro do que uma tabela NCM → alíquota, e o motivo está no
próprio art. 55, IV: a exceção das **preparações anti-solares e bronzeadores**
vive **dentro** da posição 3304, que de resto é 25%. Um protetor solar
3304.99.90 é 18% e um creme facial 3304.99.90 é 25% — mesmo NCM. Só a descrição
separa, e uma tabela por NCM erraria os dois.

**2. No período da empresa 04 (08/2022 a 06/2024) a alíquota não se move.** Nos
23 meses, só 25% (a regra) e 18% (as exceções), sem uma única transição.

**3. E, pela lei, está certo para esse período.** O art. 55, IV não sofreu
alteração, revogação nem suspensão entre 2022 e 2024, e nenhum redutor ou
complemento o alcança: os complementos da Lei 17.293/2020 (1,3% e 2,4%) são dos
arts. 53-A e 54.

**A "monofasia" tem duas leituras, e só uma toca a CAT 42.**

* **PIS/COFINS monofásico (Lei 10.147/2000)** — posições 33.03 a 33.07 e os
  códigos 3401.11.90, 3401.20.10 e 9603.21.00, com 2,20% + 10,30% concentrados
  no industrial/importador e zero no varejo. A lista de NCM é quase a mesma do
  art. 55, IV, o que faz parecer que um regime governa o outro. **Não governa**:
  é tributo federal, não muda a alíquota interna do ICMS nem a Ficha 3;
* **a ST do ICMS**, que é a monofasia que importa aqui — e aí há uma data, mas
  ela é **posterior ao trabalho**.

**A data que importa: 1º/04/2026.** A **Portaria SRE 94/2025** (DOE de
23/12/2025) revoga o Anexo XI da Portaria CAT 68/2019 e tira o segmento de
perfumaria e higiene pessoal dos arts. 313-E e 313-F do RICMS/SP. Dali em
diante não há ST nesses produtos: volta o débito e crédito normal, e o estoque
de 31/03/2026 entra no levantamento da **Portaria CAT 28/2020**. Antes disso a
base do Anexo XI valeu até 31/12/2024, e de 01/01/2025 a 31/03/2026 valeu o
IVA-ST da Portaria SRE 48/2025 (também revogada).

**O que fica em aberto, e é dívida nossa.** O trabalho da empresa 04 termina
em 06/2024 e nada disso o alcança. Mas um trabalho cuja competência cruze
**31/03/2026** monta hoje a ficha como se a ST continuasse: as saídas de 04/2026
em diante deixam de ser CST 60, não baixam estoque da Ficha 3, e o **ICMS
suportado do estoque remanescente — que é exatamente o que a CAT 42 ressarce —
fica parado no saldo**, sem virar pedido. O sistema não tem calendário de
vigência nenhum: nem de alíquota, nem da lista de mercadorias sob ST. Funcionou
até aqui porque todo período trabalhado é homogêneo; deixa de funcionar na
virada de abril de 2026.

Fontes: art. 55, IV do RICMS/SP; Lei 17.293/2020, art. 22; Lei 10.147/2000;
Portaria SRE 94/2025; Portaria CAT 68/2019, Anexo XI; Portaria CAT 28/2020.

---

## 2026-09-20 — A planilha corrigida volta pelo diff, nunca direto para o banco

**O pedido.** Corrigir à mão tem de caber nas duas mãos que já existem: a tela,
linha a linha, e o Excel, onde o analista faz o trabalho de conferência. Esta
decisão é da segunda porta.

**Subir e gravar são dois passos, e isso não se negocia.** A Ficha 3 de uma base
real tem milhões de linhas e 49 colunas. Uma coluna arrastada sem querer, um
"preencher para baixo" a mais, uma planilha do razão anterior — qualquer um dos
três viraria dezenas de milhares de correções silenciosas se subir gravasse. O
motor **compara e devolve o que mudou**; gravar é o mesmo POST da tela, depois
de a pessoa ver de que valor para que valor, em que linha, e com que motivo.

**O que identifica a linha é o que o leiaute já mostra:** CNPJ, código da
mercadoria, chave (ou número do documento, quando não há chave) e número do
item. Quem ordena, filtra ou apaga linhas no Excel continua sendo entendido; a
planilha não precisa voltar inteira nem na mesma ordem. Mexer nas colunas de
identificação, sim, é erro — e volta dito, com o número da linha.

**Linha sem motivo escrito não vira correção, nem erro.** A regra do motivo é do
domínio e vale nas três portas. Daí decorre que a conferência **só reclama de
linha que não casou com a ficha quando ela tem motivo**: numa planilha de dois
milhões de linhas subida por engano, acusar cada uma daria dois milhões de erros
e nenhum deles legível.

**Duas colunas novas na Ficha 3, vazias de propósito:** "Tirar da Ficha
(sim/não)" e "Motivo da Correção". São o espaço da correção, e sair em branco é
o que diz que o sistema não propôs nada ali.

**Tolerância na comparação.** O xlsx guarda número como float e o parquet, como
decimal. Por igualdade, milhares de linhas "mudariam" sem ninguém ter tocado
nelas. Cada campo compara com meia unidade da última casa que mostra; abaixo
disso é arredondamento do Excel, não correção.

**Reincluir linha não passa pela planilha.** A linha excluída sai da ficha e,
portanto, sai da planilha: não há célula para destildar. Trazer de volta é
desfazer a correção na tela, que é onde ela fica listada.

**O razão vai na query, não no formulário.** O corpo multipart atravessa a API em
C# como chegou do navegador — remontá-lo obrigaria a ter o arquivo inteiro em
memória lá também. Um `execucao_id` embutido nesse corpo seria escolhido por
quem sobe o arquivo, e daria para ler a ficha de outro trabalho; na query quem o
escreve é a API, depois de conferir o acesso.

---

## 2026-09-20 — Correção à mão: o que uma pessoa pode mudar no cálculo

**Por que existe.** O sistema lê documento fiscal, e documento fiscal vem
errado: alíquota que o 0200 não traz, enquadramento que nenhum CFOP decide,
nota cancelada que não veio na lista, quantidade digitada errada no ERP. Até
aqui esses casos viravam pendência contada — visível, e parada.

**O desenho, e o precedente.** Correção é decisão humana, e decisão humana já
tem um caminho no sistema: o de-para. Vale para ela o mesmo — o banco guarda,
a API valida, o motor aplica na etapa. Assim a correção **sobrevive à rodada
seguinte**, que é o que uma planilha editada à mão não faz.

**O que se corrige:** alíquota e redução da mercadoria; enquadramento,
quantidade, valor do item e ICMS suportado de uma linha; e tirar ou trazer de
volta a linha da ficha.

**Três regras (decisão do Victor, 20/09/2026):**

* **é do trabalho, não da empresa.** O de-para se herda porque o código do
  fornecedor não muda de ano para ano; alíquota e enquadramento mudam com a lei,
  e o trabalho seguinte tem de olhar de novo;
* **toda correção tem motivo escrito.** É o que a fiscalização vai ler e o que o
  revisor precisa para aprovar a entrega. Sem motivo, não grava;
* **não apaga o original.** O parquet do documento continua como o documento é;
  a correção fica ao lado, a linha sai marcada `corrigida` na Ficha 3, e desfazer
  é tirar a correção, não reescrever o dado.

**Onde entra na conta.** No razão, depois de tudo o que o sistema deduziu — a
correção é a última palavra, inclusive sobre o enquadramento indefinido. A
exclusão vem por último, porque não adianta corrigir o que sai da ficha.

**O histórico mostra o antes e o depois** (pedido do Victor, 20/09/2026). Por
isso a correção guarda `valor_anterior`: o que estava na tela quando a pessoa
corrigiu — não o valor de agora nem o de uma rodada futura, mas o que ela viu e
decidiu mudar. O evento `correcao_aplicada` leva a frase pronta
("Alíquota interna (mercadoria 4002): 18 → 25,0000") e, em `dados.mudancas`,
cada alteração com campo, alvo, de, para e motivo; `correcao_desfeita` registra
o caminho de volta. A linha do tempo mostra as cinco primeiras e abre o resto a
pedido.

---

## 2026-09-20 — Por que a alíquota é a da mercadoria, e não a do papel de trabalho

**A divergência.** O ICMS efetivo na saída a consumidor dá R$ 507.288,50 no
sistema e R$ 471.798,34 na entrega da RVZ. A diferença — R$ 35.905,34 — está
inteira em **10.336 linhas de CFOP 5.106 e 5.105**, onde eles aplicaram 18% e
nós aplicamos 25%. Nas outras 34.117 linhas os dois lados batem ao centavo.

O padrão é este: onde o XML informa o `pICMSEfet`, os dois usam 25%; onde o XML
não informa nada, a RVZ cai num 18% padrão.

| Linhas | CFOP | `pICMSEfet` | RVZ | Sistema |
|---|---|---|---|---|
| 27.580 | 5.405 e 5.102 | 25 | 13% | 13% |
| 10.336 | **5.106 e 5.105** | **ausente** | **9,36%** | **13%** |

**A decisão do Victor (20/09/2026): fica a nossa.** As justificativas, para a
defesa do trabalho:

1. **A lei fixa 25%.** Artigo 55, IV do RICMS/SP: perfumes e cosméticos das
   posições 3303, 3304, 3305 e 3307 têm alíquota de 25%, excetuados o 3305.10 e
   o 3307.20. O Grecin é **3305.90.00** — está no caput da regra, não na
   exceção. O CFOP da venda não entra nessa definição.
2. **O próprio contribuinte declarou 25%.** O registro 0200 da EFD dele traz
   `ALIQ_ICMS 25,0000` nos 12 códigos de 3305.90.00. É declaração ao fisco,
   feita por ele, e é a primeira fonte que o sistema consulta.
3. **A cadeia inteira foi tributada a 25%.** As 158 entradas desses NCM trazem
   `pICMS 25` na operação própria do fornecedor e `pICMSST 25` na retenção. O
   imposto que se busca ressarcir foi retido a 25%: confrontá-lo com um efetivo
   a 18% compararia coisas de bases diferentes.
4. **O cliente emite as próprias notas a 25%.** Em 29.467 itens de saída desses
   NCM o XML traz `pICMSEfet 25,0000` — é o que ele informa ao destinatário como
   alíquota efetiva. Só 23 itens trazem outra coisa, e são interestaduais.
5. **Nas linhas em disputa, o documento não diz nada.** Nos 9.797 itens de CFOP
   5.106 e nos 624 de 5.105, nenhum traz `pICMSEfet` nem destaque. O 18% não
   veio do documento: é o que a ferramenta deles usa quando o campo falta.
6. **O CFOP não muda a alíquota da mercadoria.** 5.106 e 5.105 são vendas em que
   a mercadoria não transita pelo estabelecimento — continuam operações internas
   com o mesmo produto. Nada na legislação vincula alíquota a CFOP.
7. **9,36% não existe na legislação paulista.** É o produto de 18% pela redução
   de 48%; a alíquota que sustenta a conta teria de ser uma das do artigo 55.
8. **Consistência dentro da própria ficha.** A mesma mercadoria teria dois
   efetivos diferentes no mesmo mês conforme o caminho logístico da venda, e o
   ressarcimento de uma unidade dependeria do CFOP com que ela saiu.
9. **O nosso critério é o mais conservador.** 25% produz efetivo maior, logo
   **menos** ressarcimento e mais complemento: R$ 35,9 mil a favor do fisco. Não
   é escolha que aumente o crédito do cliente.
10. **Cada linha mostra o que usou.** A Ficha 3 grava a alíquota do confronto em
    coluna própria, e a ordem de busca é escrita: 0200 do mês, 0200 mais
    recente, 0200 do destino do de-para e, por último, a nota de entrada
    interna. Qualquer linha pode ser refeita à mão.

---

## 2026-09-18 — A entrada diz que há benefício; a lei diz quanto ele vale

**O que se via.** O confronto de uma venda de R$ 39,99 dava R$ 4,88 no sistema
e R$ 5,20 na RVZ. Olhando a nota de entrada que o Victor apontou (chave
...1261213122, item 1012‑N):

```
vProd 123,84 · pRedBC 48,00 · vBC 60,48 · pICMS 25% · vICMS 15,12
```

| Leitura | Base | ICMS que daria |
|---|---|---|
| "reduzir **em** 48%" (base 52%) — a da RVZ | 64,40 | 16,10 |
| "base reduzida **a** 48,84%" (o `vBC` da nota) — a nossa | 60,48 | **15,12** |
| carga de 12% (artigo 34 do Anexo II) | 59,44 | 14,86 |

O fornecedor recolheu **15,12**: a nota contradiz a leitura literal da tag. Mas
ela também não bate nos 12% exatos — ele usou base de 48,84% num item e de 48%
noutro, e recolheu 12,21% aqui e 12,00% ali.

**A decisão do Victor, ao fim do dia 18/09/2026: vale o `pRedBC` declarado.**
O caminho foi longo e fica registrado inteiro porque cada passo mudou o número:
primeiro a redução medida no `vBC` (12,00 a 12,21% de carga), depois a carga
fixa de 12% da lei, e por fim a **tag do documento** — 48% de redução sobre 25%
dá carga de 13%; 66,67% sobre 18% dá 6%. É o campo que a legislação define
como percentual de redução, é o que a entrega da RVZ usa, e é o que o ICMS
efetivo da Ficha 3 passa a mostrar: R$ 5,1987 na venda de R$ 39,99 do produto
1012, não R$ 4,7988.

A incoerência do arquivo do fornecedor — declarar 48% e recolher sobre base de
48,84% — fica documentada em `cat.dominio.cat42.reducao` e não se propaga: o
que entra na apuração é a tag.

**O redutor do Decreto 65.255/2020 não entra** (decisão do Victor, 18/09/2026):
vale a alíquota interna com a carga de 12% em todo o período, e não os 13,3%
que aquele decreto instituiu entre 15/01/2021 e 14/01/2023. O próprio
fornecedor faturou a 12% dentro da janela, e é o que as notas mostram.
`reducao_da_carga` aceita outra carga por parâmetro, então tratar o redutor
depois é trocar um número — mas hoje ele não é aplicado, de propósito.

---

## 2026-09-18 — Duas alíquotas, duas colunas

**O que o Victor viu.** Na Ficha 3 da RVZ a alíquota está preenchida em toda
linha; na nossa, só em parte — e só com 25 e 18.

**Por quê.** São duas coisas diferentes que estavam na mesma coluna:

* a **alíquota da operação**, que o documento traz: 4, 7 ou 12 na venda
  interestadual, 18 ou 25 na interna. Existe em toda linha;
* a **alíquota do confronto**, que é a interna da mercadoria e só aparece onde
  o enquadramento confronta a saída (1 e 3) — no 2 e no 4 o confronto vem do
  ICMS próprio da entrada, e não há alíquota nenhuma a mostrar.

A nossa coluna "Alíquota do ICMS" levava a segunda. Agora leva a primeira, e a
do confronto foi para o bloco do confronto, ao lado da redução de base.

**No CST 60 não há destaque**, e é aí que a RVZ mostra 25 ou 18: é a alíquota
que o próprio emitente informa como efetiva no grupo do ICMS60 (`pICMSEfet`, da
NT 2020.005), que a v0.60.0 passou a ler. Mas nem todo emitente preenche esse
campo — na empresa 04, 35.448 dos 81.157 itens de CST 60. Nas outras, a ficha
mostra a **alíquota interna da mercadoria**, que é o que a operação teria.

A coluna fica então, nesta ordem: alíquota destacada no documento; a efetiva
que o emitente informou; a interna da mercadoria. Assim toda linha tem alíquota,
como na Ficha 3 deles.

---

## 2026-09-18 — As colunas 15 a 19 levam o ICMS suportado, não o valor da saída

**A correção do Victor.** Na primeira versão do leiaute, as colunas de
enquadramento — (15) a (19) — saíram com o VL_ITEM da linha. Está errado: elas
levam o **ICMS suportado que sai da ficha** naquela saída, por enquadramento.

A Ficha 3 da RVZ mostra a conta inteira na horizontal:

```
(13) qtd saída 1,00 × (14) suportado unitário 2,14958 = (15) 2,15
(20) confronto 5,20 → (26) complemento 3,05      (5,20 − 2,15)
(21) confronto 0,63 → (25) ressarcimento 1,52    (2,15 − 0,63)
```

É esse o desenho do leiaute: a coluna do enquadramento guarda o imposto baixado,
o confronto guarda o que a operação teria de imposto, e a diferença vira
ressarcimento ou complemento. Com o VL_ITEM ali, a linha não fechava.

---

## 2026-09-18 — VL_ITEM é a base de cálculo do ICMS, não o valor da mercadoria

**O que a comparação mostrou.** Confrontando a nossa Ficha 3 com a da RVZ,
17.044 linhas divergiam no VL_ITEM, R$ 309.357,59. O Victor achou o motivo
olhando a DANFE: **a coluna que o leiaute chama de "VL_ITEM" leva a base de
cálculo do ICMS**, não o valor do item.

A nota 71782 (5 itens, CFOP 6.108) mostra isso inteiro. O emitente já rateia o
frete por item, dentro do XML:

| Item | `vProd` | `vFrete` | `vBC` = o que a RVZ grava | o que gravávamos |
|---|---|---|---|---|
| 1421 | 23,71 | 2,52 | **26,23** | 23,71 |
| 1424 | 17,26 | 1,83 | **19,09** | 17,26 |
| 1425 | 17,26 | 1,84 | **19,10** | 17,26 |
| 1426 | 17,83 | 1,89 | **19,72** | 17,83 |
| 1427 | 17,83 | 1,90 | **19,73** | 17,83 |

A DANFE traz 26,23 em "B.CALC ICMS", e o total da nota tem `vBC` 103,87 contra
`vProd` 93,89: o imposto do emitente foi calculado sobre produto **mais frete**,
como manda o artigo 37, § 1º, 1 do RICMS/SP.

**A regra adotada** (`ItemDoXml.base_da_operacao`), na ordem do documento:

1. `vBC`, a base que o emitente destacou — já com frete e desconto, e já
   reduzida quando há benefício (CST 20 e 70);
2. `vBCEfet`, que o CST 60 informa como base do imposto que a ST encerrou — é o
   caso da venda a consumidor, que não destaca nada;
3. sem as duas, a soma: mercadoria mais frete, seguro e outras despesas, menos
   o desconto.

Medido na empresa 04: 47.048 saídas passam a bater exatamente com a base que a
RVZ usou, e as 15.920 de CST 60 ganham o frete. No enquadramento 1 são
R$ 132.079,41 a mais de base.

**A coluna passa a se chamar "VL_ITEM (base de cálculo do ICMS)"** na planilha.
O nome do leiaute fica, porque é por ele que se confere; a explicação vai junto,
porque foi exatamente o rótulo que criou a divergência.

---

## 2026-09-18 — A Ficha 3 sai no leiaute do papel de trabalho

**O pedido do Victor.** A planilha da Ficha 3 passa a ter o desenho do papel de
trabalho da CAT 42 — o mesmo que o cliente já recebe de outro escritório —, e o
cabeçalho azul daquele modelo vale para **todas** as planilhas do projeto.

**Como ficou.** Cabeçalho de três linhas: faixa mesclada por bloco (Dados
Gerais, Entradas, Saídas, Valor de Confronto, Saldo, Apuração, Inconsistências),
título e, embaixo, o **número do campo no leiaute**, de (1) a (27). Quem
confere compara coluna com coluna, sem tradução no meio. O estilo — `#001E50`,
Arial 10 negrito branco, centralizado — é do projeto, não da Ficha 3: qualquer
planilha nova nasce com ele.

**As nossas adaptações**, que o papel de trabalho não tem: CST, origem do dado
(EFD, XML ou relatório), alíquota do confronto e redução de base por linha — é
o que permite refazer a conta sem abrir outro arquivo —, e as inconsistências
marcadas **na linha** em vez de na ficha. Ficam de fora a alíquota do ICMS ST e
a MVA do NCM, que não temos por linha: coluna vazia em planilha de conferência
custa mais do que ajuda.

**O que a Ficha 3 passou a guardar para isso:** `descricao`, `ncm`,
`unidade_estoque` e `valor_item` (o VL_ITEM do documento). Rodada antiga sai com
essas colunas vazias, em vez de a etapa recusar o download.

---

## 2026-09-18 — O artigo 34 não alcança a saída a consumidor: premissa em aberto

**O que a pesquisa achou.** O benefício que o fornecedor da empresa 04 aplica é
o **artigo 34 do Anexo II do RICMS/SP** (perfumes, cosméticos e produtos de
higiene pessoal): reduz a base na saída interna de fabricante ou atacadista de
forma que a carga fique em 12%. Os NCM batem um a um com o que as notas mostram:

| Produto | NCM | Inciso | Alíquota interna (art. 55, IV) |
|---|---|---|---|
| Grecin | 3305.90.00 | VIII | 25% |
| 4008 | 3304.99.90 | VII | 25% |
| Vagisil desodorante | 3307.20.10 / .90 | IX | 18% (exceção do 3307.20) |
| Vagisil sabonete | 3401.20.10 | X | 18% |
| Gel lubrificante (1413) | 3006.70.00 | **fora da lista** | 18% |

A única entrada sem redução (CST 10) é a do 3006.70.00, que não está no artigo —
a lei e os dados fecham sozinhos.

**Vigência.** Decreto 48.959/2004, sem prazo desde o Decreto 58.761/2012. O
Decreto 65.255/2020 pôs um complemento de 1,3% — carga de **13,3%** — por 24
meses a partir de 15/01/2021, ou seja até 14/01/2023; o trabalho da empresa 04
(08/2022 a 06/2024) pega essa faixa até 14/01/2023, mas as notas do fornecedor
mostram 12% também ali. Prorrogações: Dec. 67.524/2023 (31/12/2024), 69.292/2025
(31/12/2025), 70.293/2025 (31/12/2026).

**O problema.** O **§ 1º** do artigo 34 diz que a redução **não se aplica a
saída destinada a consumidor final**, e a **RC 23455/2021** é expressa: *"o
benefício fiscal de redução da base de cálculo do artigo 34 não poderá ser
aplicado no cálculo do valor do imposto a ser recolhido a título de substituição
tributária"*. A venda da empresa 04 a consumidor final é exatamente o
enquadramento 1 — logo, pela letra da lei, o ICMS efetivo dela seria a alíquota
cheia, e não a base reduzida que a v0.57 passou a usar.

**O tamanho.** Com a redução (como está hoje): efetivo de R$ 464.923,00,
complemento de R$ 140.038,22, apuração de **+R$ 407.210,25 a receber**. Com a
alíquota cheia: efetivo de R$ 950.248,91, complemento de R$ 623.079,89, apuração
de **−R$ 77.779,52 a pagar**. Diferença de R$ 484.989,77, com troca de sinal.

**A decisão do Victor (18/09/2026): por enquanto fica como está** — a redução
continua no confronto do enquadramento 1. A premissa fica registrada aqui como
aberta: adotar a alíquota cheia é o caminho literal da lei, e manter a redução
precisa de tese fiscal escrita de que o "imposto efetivo" da CAT 42 mede a carga
da cadeia, não a tributação da operação isolada.

Fontes: art. 34 do Anexo II do RICMS/SP, RC 23455/2021, RC 28913/2023, Decreto
65.255/2020, RC 18477/2018 (alíquota do art. 55, IV).

---

## 2026-09-17 — Só a entrada interna empresta alíquota e redução

**O que se via.** Na primeira rodada com a alíquota da entrada, 3.160 saídas da
empresa 04 confrontaram a 4%, 7%, 8%, 9,5% e 12% — alíquotas de **compra
interestadual**, e uma delas (9,5%) nem existe: era a mediana de um dia com uma
entrada a 7% e outra a 12%. Essas linhas sozinhas respondiam por R$ 21,9 mil dos
R$ 24,3 mil de ressarcimento do enquadramento 1.

**A correção.** O confronto do enquadramento 1 é de uma saída **dentro do
estado**: a alíquota e a redução de base só podem vir de entrada interna. No XML
o CFOP é o do emitente (5.xxx é interna); na EFD é o nosso (1.xxx). Mercadoria
que só entrou de fora fica sem alíquota, contada, como já era antes.

---

## 2026-09-17 — Sem 0200, a alíquota vem da nota de entrada

**O que se via.** 13.909 saídas da empresa 04 ficavam sem valor de confronto —
os códigos 4002, 4009, 4008 e 4007, que **não têm registro 0200 em arquivo
nenhum**, nem no próprio CNPJ nem em outro. Sem alíquota não há ICMS efetivo, e
sem efetivo não há ressarcimento nem complemento nessas linhas; a RVZ apurou
todas elas.

**A decisão do Victor (17/09/2026).** Quando o cadastro não tem a alíquota, ela
vem da **nota de entrada** da mesma mercadoria: é a alíquota que o fornecedor
usou na operação própria dele, pelo mesmo NCM e pela mesma regra de data da
redução de base — a entrada mais recente até a saída, e antes dela a primeira
que houver. A ordem completa fica: 0200 do mês, 0200 mais recente, 0200 do
destino do de-para e, por último, a nota de entrada.

**Como fica marcado.** A Ficha 3 grava a `aliquota` que fez o confronto em cada
linha, e o resumo do razão traz `aliquota_da_entrada` com quantas saídas
precisaram desse último recurso. Os quatro códigos da empresa 04 têm NCM no
XML da saída (3305.90.00, 3304.99.90 e 3401.20.10), então todos são alcançados.

---

## 2026-09-17 — A redução de base da entrada entra no ICMS efetivo da saída

**O que se via.** O complemento do enquadramento 1 da empresa 04 dava
R$ 380 mil contra R$ 148,7 mil da RVZ, e a diferença inteira era a alíquota: o
sistema confrontava valor × 25% (Grecin) e × 18% (Vagisil), a RVZ usava 13% e
6%. Nenhum dos dois números tinha fundamento escrito no papel de trabalho dela.

**Onde estava a resposta.** Nas **entradas**. O fornecedor (139 notas, 210
itens, um só CNPJ) emite com **CST 70** — redução de base com ST — e informa a
base que usou:

| NCM | Alíquota | `pRedBC` declarado | Base usada (`vBC`) | Carga |
|---|---|---|---|---|
| 3305.90.00, 3304.99.90 (Grecin) | 25% | 48,00 | 48% do valor | 12% |
| 3401.20.10, 3307.20.10/.90 (Vagisil) | 18% | 66,67 | 66,67% do valor | 12% |
| 3006.70.00 (gel, CST 10) | 18% | — | sem redução | 18% |

O `pRedBC` está preenchido **ao contrário**: o fornecedor põe ali a base que
sobra, não o que reduziu. Lido ao pé da letra dá 13% num grupo e 6% no outro —
foi o que a RVZ fez — e nenhum dos dois reproduz o `vICMS` da própria nota. Pelo
`vBC`, os dois grupos dão a mesma carga de **12%**.

**A decisão do Victor (17/09/2026).** O ICMS efetivo da saída passa a incidir
sobre a base já reduzida, e a redução é a **real**, calculada por
`1 - vBC / (vProd - vDesc)` — nunca pelo `pRedBC`. Vale **só no enquadramento
1**: o 3 segue com a alíquota cheia, e o 2 e o 4 confrontam com o ICMS próprio
da entrada, onde a redução já vem embutida no `vICMS` da nota.

**Como funciona.** A redução é da mercadoria, então a chave é o **NCM** — o da
nota, e o do 0200 quando ela não traz (venda de PDV do relatório). Cada saída
herda a redução da entrada mais recente até a data dela; antes da primeira
entrada, a primeira que houver. O dia com mais de uma entrada fica com a
mediana. A Ficha 3 grava `reducao_base` em cada linha, a ficha conta
`saidas_com_reducao` e o resumo traz `reducao_de_base` com quanto a redução
tirou do confronto.

**O que muda na empresa 04.** Nas 44.469 linhas de saída de enquadramento 1 e
3, o ICMS efetivo cai de R$ 950,2 mil (alíquota cheia) para R$ 463,7 mil, e o
complemento de R$ 623,1 mil para R$ 139,1 mil — a RVZ apurou R$ 148,8 mil com
os 13%/6% dela.

**O que ainda falta.** Registrar o fundamento legal do benefício de carga 12%
por NCM: hoje o sistema só sabe o que a nota de entrada declara.

---

## 2026-09-17 — Estoque negativo abre a ficha, em vez de tirá-la do total

**O que se via.** Na empresa 04, 6 mercadorias ficavam com saldo negativo em
algum ponto, e o sistema tirava a ficha inteira do total: R$ 100,7 mil que a RVZ
apurou ficavam de fora. Em três delas o negativo era de 1 a 3 unidades.

**O que a RVZ faz.** A ficha dela nunca fica negativa porque começa com uma
abertura do tamanho do déficit, sem nota que a sustente: 54 unidades no 4001,
41 no 3132, 25 no 3133, 3 no 1111, 1 no 1116 e 1 no 1413 — quase exatamente o
pior saldo do sistema em cada uma. A Ficha 3 dela tem a coluna de inconsistência
"Saldo Inicial sem ICMS suportado".

**A decisão do Victor (17/09/2026): fazer o mesmo, marcado.** Quando o saldo
ficaria negativo, a ficha abre com a quantidade que faltaria, **sem ICMS
suportado**, e continua no total. O efeito é conservador: as unidades abertas
entram com imposto zero, então a média ponderada cai e a saída que as consome
gera menos ressarcimento (ou complemento). No exemplo do teste, a saída que
antes dava R$ 7,00 de ressarcimento passa a dar R$ 13,00 de complemento.

**Como fica marcado:** `ficou_negativo` continua, e a ficha ganha
`abertura_por_saldo_negativo` com a quantidade aberta; o resumo do razão traz
`abertas_por_saldo_negativo` (fichas e quantidade); a apuração conta
`fichas_negativas` e a competência fica bloqueada pelo motivo novo
`estoque_negativo` — entra no total, mas não vira arquivo digital sem alguém
olhar. `retirada` fica para sempre falso: as rodadas antigas continuam
legíveis, e o motivo `ficha_retirada` segue existindo para elas.

---

## 2026-09-17 — Lista de canceladas: só a aba de canceladas, só a linha cancelada

**Como apareceu.** Na comparação das fichas negativas com a RVZ, o Victor notou
que o sistema não trazia as devoluções: no 3132, a ficha da RVZ tinha 59 e a do
sistema, nenhuma. Das 59, 35 tinham sido tiradas como "canceladas na SEFAZ" — e
nenhuma tinha evento de cancelamento.

**A causa.** O relatório "NF-e Canceladas-Devoluções" (pasta 09) tem duas abas:
"NF-e Canceladas" (180 notas) e "NF-e Devoluções" (245 notas que não foram
canceladas). A leitura da lista pegava a chave de qualquer aba. E a lista do
cliente tinha 6 linhas cujo retorno da SEFAZ dizia o contrário do nome:
"Rejeição: Pedido de Cancelamento..." (4) e "Autorizado o uso da NF-e" (2).

**A regra agora:**

* numa planilha de canceladas, vale a aba com "cancel" no nome; sem nenhuma
  assim, todas menos a que diz "devol";
* a linha (da planilha ou do texto) cujo retorno fala em rejeição, uso
  autorizado ou denegação, sem falar em cancelamento autorizado ou homologado,
  não conta;
* o que ficou de fora vai ao log, com a contagem.

**Na empresa 04:** a planilha "Canceladas-Devoluções" passa de 425 para 180
chaves, e a do cliente de 890 para 885. As devoluções escrituradas voltam à
movimentação.

---

## 2026-09-17 — A base da multa sem valor no XML vem da nota vizinha

**A pergunta que estava aberta.** Na empresa 04, a saída não escriturada é
quase toda CST x60 em 5.949/6.949, sem ICMS destacado: com a base do XML, a
multa de 75% dava R$ 32,57. A RVZ aplicou 18% sobre o valor.

**A decisão do Victor:** vale o XML; quando o XML não traz a base, pega-se uma
nota anterior ou posterior do mesmo produto, o valor por unidade dela, e
calcula-se a base da nota apurada. Como ficou:

* a base é o valor do item na entrada e o ICMS destacado na saída;
* sem ela (zero ou vazia), vale a nota **mais próxima em data** do mesmo
  estabelecimento, operação e código que traga a base, entre todos os XML do
  estabelecimento — escriturados ou não —, fora cancelada e devolução (a
  devolução carrega o valor da operação de origem). No empate, a anterior;
* base = valor por unidade da referência × quantidade da nota apurada;
* cada item leva `origem_da_base` (xml, nota anterior, nota posterior, sem
  referência), a nota de referência, a data e o valor por unidade — a planilha
  mostra de onde veio cada número;
* sem nota nenhuma do produto com a base, o item fica com base zero, contado.

**Na empresa 04:** 2.238 itens de saída sem ICMS, todos com referência — venda
6.108 do mesmo código, mediana de 0 dia de distância e máximo de 7. ICMS das
saídas R$ 50.643,67, multa R$ 37.985,16 (a RVZ: ICMS R$ 69.962,86 a 18% sobre o
valor, multa R$ 52.472,14 antes da SELIC). Entradas: todas com valor no XML,
multa R$ 89.463,60.

---

## 2026-09-17 — O de-para da empresa 04 pelo sistema, contra o da RVZ

**Como se testou.** A empresa 04 entrou no sistema como um trabalho de verdade
(trabalho 5, 0004-21, 08/2022 a 06/2024), pela API: EFD de
`10 - RETIFICAÇÃO SPEDS/SPEDS` (decisão do Victor; os 24 arquivos são os de
`01 - SPEDS` com a retificadora de 08/2022 — 23 deles dizem "original" no 0000,
e importar as duas pastas dobraria os meses), XML de `XML's` e
`04 - CAPTAÇÃO DOCUMENTOS FALTANTES` (os 12 zips de `10 - RETIFICAÇÃO/XML'S`
foram recusados como cópia) e as listas de `09 - NOTAS CANCELADAS`. Conferência,
movimentos e suportado rodaram pela fila. As propostas de de-para foram
comparadas com a aba "04. De-Para" da entrega da RVZ: 10 pares do cliente e 44
da RVZ, com o fator do kit tirado da descrição ("KIT 3X").

**O que a comparação ensinou.** O código da EFD tem espaços (`4002           08`)
e a RVZ o escreveu sem (`400208`): comparado sem espaço, a v0.55.1 acertava 35
dos 44 pares da RVZ — destino e fator —, deixava os 10 do cliente como "sem par"
e não propunha nada a mais. Faltavam 9:

* **8 kits de compra** (`3133K3         08`, "GRECIN 5 PG PRETO KIT 3X"). O kit
  vem da descrição, e a unidade se procurava pela descrição igual sem o kit.
  Dois tropeços: a unidade existe com dois códigos (`3133` e `3133           08`)
  e a regra desistia; e a descrição do kit abrevia a da unidade ("CAST. ESC" e
  "CAST. ESCURO"). Agora, entre dois códigos, fica o que começa o código do kit;
  e, sem descrição igual, vale o código mais longo que começa o do kit, com o
  mesmo NCM e descrição compatível;
* **1 código só com devolução de compra** (`4004`, CFOP 5.411). Devolução não
  conta para escolher o destino, mas é movimento da ficha: a do `4004` só tinha
  a devolução, e juntar com `4004           08` a conserta. Passou a contar para
  decidir se o grupo conserta alguma ficha.

**Depois:** os 44 pares da RVZ iguais, os 10 do cliente como "sem par" (códigos
de marketplace sem GTIN nem parentesco de código — é o que o cliente preenche)
e nenhuma proposta a mais. Na empresa 19, as propostas não mudaram (2 antes e depois).

---

## 2026-09-17 — Certificado digital não se abre nem se lista

**O risco.** A inspeção do lote lê o começo de todo arquivo da pasta e grava o
nome de cada um. A pasta da empresa 04 tem `05 - CERTIFICADO` e
`10 - RETIFICAÇÃO SPEDS/CERTIFICADOS`, com o A1 do cliente em .pfx — e o nome
do arquivo carrega a senha. Apontar a raiz da pasta levaria o certificado para
a leitura e o nome para o banco. Nenhum lote gravou certificado até aqui
(conferido pela contagem, sem ler nome).

**A regra (decisão do Victor):**

* pasta com a palavra "certificado" ou "certificados" no nome não é aberta — a
  palavra inteira, sem acento e sem caixa: "Certificadora Parceira" é aberta;
* arquivo .pfx/.p12, e compactado (.zip, .rar, .7z) com essa palavra no nome,
  não é lido;
* o mesmo vale dentro de zip, nas etapas 2 e 3 e na pré-validação: membro em
  pasta de certificado, .pfx e zip de certificado são pulados sem ir para log
  nem para os recusados;
* a pasta escolhida que é de certificado, ou está dentro de uma, é recusada;
* fica só a contagem, num aviso da inspeção, e no log sem nome.

**Medido na empresa 04:** inspecionar a raiz inteira classificou 1.098
arquivos em 18 s, nenhum de caminho de certificado, e avisou das 2 pastas.

---

## 2026-09-16 — A mesma nota em vários XML, a nota denegada e o lote que muda de tipo

**A pergunta do Victor:** como a v0.54 trata a duplicidade de XML, no caso de
reimportar a pasta de um lote antigo. Medido na empresa 04, três coisas.

**1. Reimportar não reclassificava.** Arquivo com o caminho já no trabalho era
"já importado" e ficava com o tipo de quando entrou: o zip de 2026-09-15
continuava `compactado` e o evento continuava `xml_outro`, e a importação
recusava com 409. Agora a inspeção devolve o tipo gravado, e o registro atualiza
onde está o arquivo cujo tipo mudou — sem lote novo, sem remover o lote antigo.
Remover e importar de novo continua possível, mas não é mais o caminho.

**2. Nota denegada.** O sistema não olhava o `cStat` do protocolo. Na
empresa 04, 16 notas com uso denegado (301/302); 15 entraram na contingência
(R$ 130,83 de multa) e contavam como documento entregue na conferência. Agora
só 100 e 150 autorizam; a denegada sai das etapas 2 e 3 com todas as cópias,
contada e avisada. O XML sem protocolo (do ERP) e o CF-e continuam valendo.

**3. Cópias da mesma chave.** Das 179.417 XML que o lote da empresa 04 deixa
entrar (os 12 zips idênticos já ficam de fora pelo hash), 28.407 chaves estão em
mais de um arquivo: 29.306 arquivos a mais. Em 22.726 os bytes diferem — só a
declaração `<?xml ...?>` — e nenhuma cópia diverge no que se lê. Mesmo assim, a
regra passou a ser explícita: a cópia com protocolo autorizado vence a sem
protocolo; entre iguais, a primeira na ordem do caminho. O parquet é gravado em
fluxo, então a cópia melhor que chega depois é gravada também, com `leitura`
maior, e uma passada no fim deixa uma por chave — só quando houve troca ou nota
denegada. A etapa 2, que descartava a repetida sem dizer, agora conta.

**Na empresa 04, depois da regra:** etapa 2 em 19,7 s, 119.714 chaves (as 16
denegadas fora), 29.306 repetidos; etapa 3 em 96 s, 119.713 notas e 132.446
itens, nenhuma cópia trocada (todas tinham protocolo).

---

## 2026-09-16 — XML dentro de zip, sem extrair

**O caso.** A empresa 04 entregou 357.948 XML em 26 zips — e 290 mil deles em
60 zips dentro dos zips, gravados sem compressão, de até 201 MB. Até aqui o lote
marcava tudo como `compactado` e nenhuma etapa lia. Extrair para ler foi medido
na validação e custou mais que ler: o antivírus examina cada arquivo que nasce.

**Como ficou.** O zip é um arquivo só no lote, tipo `xml_compactado`, quando
algum dos primeiros 50 XML de dentro é NF-e/CF-e (reconhecida pelo `Id`, porque
CT-e também tem `<infNFe>`) ou evento de cancelamento de NF-e. O CNPJ é o da
primeira nota, e separa zip de outra empresa como no XML solto. As etapas 2 e 3
leem os membros na memória, um por vez; o zip de dentro sem compressão é lido
por posição dentro do de fora, e o comprimido vai para a memória até 256 MB.
Zip de terceiro nível não é aberto. Membro ou zip quebrado vai para os
recusados e a leitura segue.

**Descartado:** um registro no lote por XML de dentro do zip. Daria competência
e CNPJ por nota na tela do lote, mas multiplicaria as linhas do banco pelo
número de notas (357 mil numa empresa) para uma informação que a conferência já
dá.

**Medido na empresa 04:** classificar os 26 zips, 7,6 s; contar os XML, 3,2 s;
a leitura da etapa 2, 33 s, com 119.730 chaves — as mesmas 119.729 da leitura
completa feita antes, mais uma nota sem item. Dois zips cuja amostra caiu num
evento ficaram sem CNPJ na primeira versão; agora a amostra prefere nota, e o
evento de cancelamento de CT-e (também 110111, mas com `<chCTe>`) não conta.

---

## 2026-09-16 — A contingência das notas não escrituradas

**O que é.** Nota não escriturada não entra na ficha, mas o fisco que a achar
fora da EFD cobra multa, e o cliente precisa do número para decidir se
retifica. A RVZ calculou na empresa 04; aqui sai na etapa 3, que é onde o XML
é lido por inteiro, em `contingencia.parquet` (um item por linha), no resumo e
numa planilha.

**Quem entra.** XML do estabelecimento (emitente ou destinatário com EFD no
projeto), emitido num mês que tem EFD dele, sem a chave na EFD dele e não
cancelado na SEFAZ. Mês sem EFD fica de fora: ali não se sabe. A operação é a
do estabelecimento — emitida por ele com `tpNF` 1 é saída, com `tpNF` 0 é
entrada; recebida, o contrário.

**A multa, sem SELIC** (a CAT 42 não se atualiza pela SELIC — orientação dos
colegas do Victor). Infração do art. 215 do RICMS/SP:

* entrada — art. 527, V, "a": 10% do valor do item;
* saída — art. 527, I, "b": 75% do ICMS **destacado no XML**.

**Na empresa 04.** Entradas: 19.432 notas, R$ 908.908,64, multa
R$ 90.893,31 — a RVZ chegou a R$ 902.270,47 de valor e R$ 90.227,05 de multa
antes da SELIC. Saídas: 1.740 notas, R$ 388.760,93 de valor, mas só R$ 43,40 de
ICMS destacado (quase tudo CST x60 em CFOP 5.949/6.949), multa R$ 32,57. A RVZ
aplicou 18% sobre o valor das "saídas tributadas" (ICMS R$ 69.962,86, multa
R$ 52.472,14 antes da SELIC). Aqui vale o XML, e mercadoria com ST retida não
tem imposto próprio na saída interna. **Fica para o Victor decidir** se a saída
sem destaque deve ter alíquota imputada.

---

## 2026-09-16 — Canceladas na SEFAZ saem da movimentação

**O problema.** A EFD pode trazer como regular a nota que o emitente cancelou na
SEFAZ, e o XML autorizado continua na pasta — o de cancelamento é outro
arquivo. Pedir ressarcimento sobre ela é pedir sobre operação que não houve. A
RVZ consultou a SEFAZ nota a nota com o certificado do cliente; o sistema não
guarda certificado de cliente, então a cancelada entra pelo lote.

**Dois tipos novos no lote, os dois alimentam a CAT.**

* `xml_cancelamento` — `procEventoNFe` com `tpEvento` 110111. CNPJ e competência
  vêm da chave cancelada. Carta de correção e outros eventos continuam
  `xml_outro`.
* `lista_de_canceladas` — TXT ou CSV com "cancel" no nome e chave de acesso em
  pelo menos metade das linhas; planilha com "cancel" no nome e alguma chave
  escrita como texto. O nome é a trava: uma lista de chaves qualquer (a de
  conferidos, a de notas ausentes) não pode tirar nota da apuração. Chave que o
  Excel gravou como número já perdeu os dígitos do fim e não se adivinha.

**Na etapa 3.** A extração grava `chaves_canceladas.parquet` (sempre, mesmo
vazio, para a pasta não herdar lista de rodada anterior). A consolidação tira da
movimentação o C170 e o item do XML de chave cancelada, e conta: chaves lidas,
documentos que a EFD trazia e movimentos que saíram, com aviso de que a EFD pede
retificação. O documento fica em `documentos.parquet` — é a escrituração como
veio.

**Na empresa 04.** As duas listas da pasta (a extraída pela RVZ e a do cliente)
dão 1.011 chaves; 911 estão na EFD, 814 já como canceladas e **97 como
regulares** — 101 movimentos de saída, R$ 9.968,61, que agora saem.

**Lote antigo.** Evento importado antes da v0.54.0 ficou como `xml_outro`; a
pasta precisa ser inspecionada de novo para virar `xml_cancelamento`.

---

## 2026-09-16 — O motor abre processos de verdade

**O que se viu.** A primeira rodada da v0.53 na empresa 19 (#57) correu dentro do
servidor do motor, sem processo filho. A checagem `_processos_viaveis()` exigia
que o `__main__` tivesse arquivo ou nome de módulo — e o servidor do uvicorn nasce
de um `spawn`, com um `__main__` que não tem nenhum dos dois. O motor caía no
"um processo só" com aviso no log, e o mesmo valia para a etapa 7 e para a
pré-validação em paralelo da v0.52: o ganho medido existia nos testes e nos
scripts, não no motor.

**A regra certa.** O `spawn` refaz o `__main__` pelo nome, pelo arquivo ou não
refaz. Só quebra quando o `__main__` diz ter um arquivo que não existe (o
script lido da entrada padrão). Um teste abre, de dentro de um processo nascido
de `spawn`, um pool — que é exatamente o que o motor faz.

---

## 2026-09-16 — Sufixo só entre descrições compatíveis

Na primeira chamada do de-para sobre a empresa 19 (97 s, 72 estabelecimentos), o sufixo
propôs `1024078 → 102407` com "sufixo 8, repetido em 4 pares": num catálogo
numérico grande, código + um dígito coincide por acaso. O sufixo passa a valer
só entre pares de descrição compatível, e a repetição conta só esses pares. Na
empresa 04, 41 pares em vez de 46 — os kits seguem ligados pela regra do kit — e
o ressarcimento de R$ 274.950,74 para R$ 274.878,90.

---

## 2026-09-16 — O que a CAT 42 da empresa 04 ensinou: XML, de-para, art. 271 e X.949

**De onde veio.** A CAT 42 que a RVZ entregou para a empresa 04
(44.000.001/0004-54, 08/2022 a 06/2024, R$ 406.362,34) foi comparada com o que
o sistema faria. **Decisões do Victor:** corrigir tudo, nesta ordem — itens do
XML, de-para automático com revisão na tela, enquadramento 4 com o art. 271,
X.949 fora da ficha — e validar rodando a base deles.

**1. O item do XML.** A EFD deles tem 92.928 NF-e de saída sem C170: sem ler o
XML, o sistema não teria saída nenhuma — o mesmo buraco das lojas de SP da
empresa 19. A etapa 3 passou a ler o item de NF-e, NFC-e e CF-e: completa o
documento escriturado sem item e fica ao lado do C170 que existe, com os
valores do XML vencendo na etapa 4. O que a base real mostrou, e virou regra:

| Achado | Regra |
|---|---|
| 72 mil CT-e lidos como nota sem chave (o CT-e cita as notas num `infNFe`) | NF-e só com `infNFe` dentro de `NFe` |
| 13.676 NF-e declaradas UTF-8 com o `º` em Latin-1 | relê como Latin-1 quando o UTF-8 falha |
| C170 com o custo (ST e IPI embutidos) e XML com a mercadoria: nenhum item casava pelo valor | casa pelo número do item com quantidade ou valor; contagem só em nota de um item |
| 44.781 NF-e de venda a pessoa física sem enquadramento | `indFinal` do XML diz consumidor final (1) ou não (0) |

Resultado na empresa 04: 92.723 das 93.599 saídas completadas; 211 de 215 C170
com o XML ao lado; ICMS suportado das entradas de R$ 0 para R$ 1.248.698,47,
tudo destacado no documento; 2 XML ilegíveis de 357.950 arquivos.

**2. De-para de códigos.** O mesmo produto tinha até quatro códigos: `1111` na
venda, `1111K3` no kit, `1111K3         08` na compra (código de venda + espaços
+ "08") e `X00450IETL` no marketplace. O sistema propõe grupos por GTIN, sufixo
que se repete (no mínimo 3 pares), kit (com fator) e descrição + NCM, e escolhe
o código de mais saídas. Três travas vieram da base real: `K3` é kit, não
sufixo; GTIN não liga kit a unidade nem descrições incompatíveis (o 0200 deles
tinha no `1114` o GTIN do `1050`, e o GTIN sozinho juntava seis produtos); fator
em conflito derruba a confiança. O par é da empresa (`depara_item`), gravado
pela API; o razão aplica só os aprovados e guarda `codigo_original`. O que não
casa vai numa planilha para o cliente — como a RVZ fez com os 10 códigos de
marketplace. Na empresa 04: 46 pares propostos, todos de confiança alta; 10
códigos sem par, os mesmos que o cliente preencheu para a RVZ.

**3. Enquadramentos 2 e 4 e o art. 271.** A coluna 21 é o ICMS próprio das
entradas mais recentes da ficha até a saída (item 3.3.8, a regra que já valora a
abertura). Ressarcimento = suportado baixado − coluna 21; no enquadramento 4, a
coluna 21 é também o crédito do art. 271 (coluna 27), que a apuração soma e o
arquivo digital leva no VL_CONFR. Conferido com a Ficha 3 da RVZ: 2,15 de
suportado, 0,63 da entrada, 1,52 de ressarcimento e 0,63 de crédito. Na
empresa 04, 57.440 saídas confrontadas e nenhuma pendente.

**4. X.949 fora da ficha.** Remessa e retorno (armazém, depósito) não são compra
nem venda: saem da ficha e ficam contados, como o uso e consumo.

**Comparação com a RVZ (fichas válidas).** Enquadramento 4, ressarcimento +
crédito: R$ 389.531,17 contra R$ 548.490,22; crédito do art. 271: R$ 114.663,40
contra R$ 160.557,57; complemento: R$ 178.109,69 contra R$ 148.770,53. A
diferença está nas 6 fichas que ficaram negativas e fora do total: a RVZ incluiu
na CAT notas de entrada não escrituradas ("PRESENTES NA CAT 42" na planilha
dela), e o sistema as deixa de fora. **Decisão do Victor (16/09/2026): continua
de fora.** Incluí-las foi pedido particular da empresa 04 na época, não regra do
trabalho; nota não escriturada segue na lista da conferência, para cobrar.

**Sem SELIC (decisão do Victor, 16/09/2026).** A RVZ atualizou a contingência das
notas não escrituradas pela SELIC. Aqui não: a CAT 42 não se atualiza pela SELIC
(orientação dos colegas do Victor). A contingência, quando entrar, é só a multa
do art. 527 do RICMS/SP — 10% do valor nas entradas, 75% do ICMS nas saídas.

**Canceladas na SEFAZ (decisão do Victor, 16/09/2026).** Entram pelos eventos de
cancelamento em XML (`procEventoNFe`, 110111) e por lista de chaves canceladas
(TXT ou planilha, como a que a RVZ extraiu e a que o cliente mandou); a nota
cancelada sai da movimentação e fica contada. Sem consulta à SEFAZ: não se guarda
certificado de cliente no sistema.

---

## 2026-09-16 — A rodada num processo próprio, e o índice sem `mode()`

**O que caiu.** A etapa 4 da empresa 19 falhou duas vezes por falta de memória
(#55 e #56), com o motor chegando a 16 GB. Medido fase a fase, com trava de 8 GB:
ler 20 GB de relatórios chega a 2,8 GB e devolve; percorrer 8,7 milhões de
itens, 3,9 GB (o teto do DuckDB); o agrupamento por documento passava de 8 GB
**mesmo com teto de 2 GB** — o `mode()` guarda uma tabela por documento fora do
controle de memória do DuckDB.

**O que mudou.** O índice conta por documento e CST, e por documento e fonte, e
escolhe com `arg_max` sobre número pequeno: 82 s e 2,0 GB de pico nos mesmos
8,7 milhões de itens. E cada rodada da fila roda num processo filho: a memória
volta ao sistema quando ela acaba, e o filho que morre vira falha com motivo em
vez de derrubar o motor. `CAT_RODADAS_EM_PROCESSO=false` volta ao que era.

---

## 2026-09-16 — Base grande: CSV pelo DuckDB e arquivos digitais em paralelo

**CSV.** A Ficha 3 de uma loja da empresa 19 (1,17 milhão de linhas) levava 60 s
para virar CSV, escrita linha a linha pelo módulo `csv`; o dossiê de uma base
do tamanho da empresa 17 faz uma por filial. Agora o DuckDB escreve o corpo e o Python
só o cabeçalho com o BOM. Os bytes são os mesmos — `;`, aspas só onde precisa,
CRLF, vírgula decimal, `Sim`/`Não` —, e um teste compara as duas escritas para
que não divirjam.

**Arquivos digitais.** Escrever e pré-validar um arquivo é Python puro e não
depende dos outros: num perfil de 12 arquivos da empresa 19, 48% do tempo era
pré-validação e 40% escrita. A etapa 7 passa a separar em disco, por
estabelecimento e mês, o que cada arquivo lê, e cada processo filho monta o
seu; os 12 arquivos caíram de 15,8 s para 7,9 s com o mesmo SHA-256. A
pré-validação dos arquivos do cliente segue a mesma ideia: o processo principal
lê só a primeira linha de cada arquivo e decide ali o que é repetido,
substituição e nome; a leitura inteira vai a um filho, e os totais são somados
no fim, só com os arquivos que valem. O zip aninhado fica no disco até o fim,
porque um filho pode estar lendo dele. Sessenta prévias da empresa 19, metade soltas e metade
num zip: 41,2 s com um processo, 10,0 s com seis, o mesmo resumo e as mesmas
linhas.

Quantos processos: `CAT_PROCESSOS_DO_ARQUIVO_DIGITAL`, e 0 escolhe núcleos
menos 4, entre 1 e 4, para deixar folga à API e ao Postgres — o teto é pela
memória: cada filho pode passar de 1 GB, e a apuração do suportado da empresa 19
(#55) falhou por falta de memória com a máquina em 4 GB livres. Com 1 nada muda do
que era. Os testes rodam as duas formas e exigem o mesmo resultado. Quando o
módulo principal não se reimporta num processo novo (script lido da entrada
padrão), cai para um processo com aviso no log; um filho que morre (memória)
vira erro que manda definir 1.

---

## 2026-09-16 — Série no 1200 e a substituição entre arquivos do cliente

**Série.** O 1200 saía sem SER: a série era lida no C100 e não chegava à
movimentação. Agora passa pela movimentação, pelo suportado e pela Ficha 3 até
o arquivo, sem máscara (`U-2` vira `U2`, como o manual pede). Etapas montadas
antes desta versão não têm a coluna e o 1200 sai como saía.

**Substituição.** Entre dois arquivos do cliente do mesmo estabelecimento e mês,
valia o primeiro lido — que podia ser o original de uma remessa que o cliente
já tinha substituído. Agora a substituição (COD_FIN 02) vence o que não é
substituição: lida depois, ela é validada e o original vira `substituido`, fora
dos totais, das ocorrências e da continuidade dos saldos; lida antes, o original
que vem depois é só repetido. Entre dois iguais, segue valendo o primeiro.

---

## 2026-09-16 — Abertura pelas entradas anteriores, uso e consumo fora da ficha, 5929 como a empresa 17

**Abertura sem imposto.** O inventário da empresa 19 veio sem ICMS em 842 mil
linhas, e a abertura entrava com valor zero em 400.984 fichas — o complemento
saía inflado e a devolução de compra deixava ICMS negativo. O manual não diz
como valorar a abertura; diz, no item 3.3.8, como achar o valor quando não se
identifica a entrada: **as entradas mais recentes, suficientes para comportar a
quantidade, com média ponderada**. **Decisão do Victor:** usar essa regra com as
entradas até o dia do inventário.

- A regra é do domínio (`valor_da_abertura`), testada com o exemplo do próprio
  manual (10 un a R$ 15 e 20 un a R$ 10, saída de 12: R$ 170, R$ 14,17 a unidade).
- Devolução de venda e uso e consumo não são de onde o estoque veio: ficam de fora.
- Quando as entradas não alcançam a quantidade, o resto vai pela média delas, e a
  ficha fica marcada `abertura_parcial`. Sem entrada nenhuma, zero e marcada.
- O período do razão passou a ser o do **cadastro do trabalho**. O que a base tem
  antes dele não entra na ficha: serve para valorar a abertura. Para valer na
  empresa 19, é preciso importar as EFD de antes de 01/2021.
- A etapa 6 abre o 1050 do primeiro mês com esse ICMS, e não mais com zero.

**Uso e consumo.** 1.407, 1.556, 1.557, os 2.xxx e as saídas 5/6.556 e 5/6.557
não são estoque de comercialização. **Decisão do Victor:** saem da ficha e ficam
contadas (`fora_da_ficha.uso_e_consumo`). Na empresa 19 eram 366 entradas.

**CFOP 5.929** (NF-e de venda já registrada em cupom). **Decisão do Victor:** fica
como a empresa 17 transmitiu e a SEFAZ aceitou — saída comum, enquadramento 0. Só
documentado; na empresa 19 não há nenhuma linha.

---

## 2026-09-16 — Uma pendência por problema, com a medida de cada etapa

**O que a entrega da empresa 19 mostrou.** 26 pendências, e várias eram o mesmo
problema contado de novo: o confronto pendente dos enquadramentos 2 e 4 aparecia
como linhas no razão, competências na apuração, arquivos na etapa 7 e
ocorrências de VL_CONFR na pré-validação. O revisor lia quatro problemas onde
havia um.

**Como ficou.** O domínio da entrega junta por assunto — saída sem alíquota,
enquadramento indefinido, confronto pendente, estoque negativo, fora de SP e
entrada sem ICMS suportado (o que falta na etapa 4 é o ICMS_TOT zero da etapa
7). A pendência fica com a etapa mais cedo, que é onde se resolve, a gravidade
mais alta entre as etapas e a lista de medidas; regras da mesma etapa na mesma
unidade somam. O relatório ganhou a coluna «Como cada etapa viu». No piloto,
26 pendências viraram 15.

---

## 2026-09-16 — O cadastro do trabalho muda, e a base fora do período aparece

**O que o piloto mostrou.** O trabalho da empresa 19 nasceu como "Ressarcimento ST
2025", de 01/2025 a 12/2025, e as 884 EFD importadas eram todas de 2021. Nada
avisava: a importação aceita a base, e não havia como corrigir o cadastro sem
ir ao banco.

**Decisão do Victor.** O trabalho é de 2021: recadastrar. Para isso o cadastro
passou a ser editável pela API (`PATCH /api/projetos/{id}/cadastro`), por quem
escreve, sempre com evento no histórico — o de e o para do nome e do período.
Nada mudando é recusa, não evento vazio.

**E a divergência passa a aparecer.** O detalhe do trabalho diz de quando é a
base e quantas EFD caem fora do período (comparando o mês, não o dia gravado).
A tela avisa e oferece a edição. Na empresa 19, antes do recadastro: 884 de 884
fora; depois: nenhuma.

---

## 2026-09-16 — Etapa 8: relatórios e entrega

**Decisões do Victor.** A etapa produz **relatório e dossiê**; o relatório
mostra **toda** competência, pronta ou não, e o dossiê leva **só** o que vai à
SEFAZ — prévia nunca entra no pacote do pedido; **gerar não conclui**: um
revisor ou gestor aprova, e é a aprovação que fecha a etapa; o pacote é
**baixado pela tela** — copiar para a rede fica com quem baixou, conferindo o
SHA-256 pelo manifesto.

**O que sai.** `relatorio_da_entrega.xlsx` (Resumo, Filial x competência, Por
filial, Por mês, Pendências e Trilha das execuções), `dossie/<CNPJ>/` só dos
estabelecimentos com competência pronta (TXT de envio, Ficha 3 em CSV, saldos
do 1050, apuração e pré-validação daquelas competências), e `MANIFESTO.txt`
com tamanho e SHA-256 de cada arquivo e de onde cada número saiu. Tudo num zip.

**O TXT do dossiê é o que foi pré-validado.** A cópia é conferida pelo
SHA-256 que a etapa 7 gravou; se não bate, a montagem falha em vez de levar
arquivo que ninguém conferiu.

**Pendências numa língua só.** Cada etapa grava o resumo com nomes próprios. O
domínio (`cat42/entrega.py`) traduz o que existe — documentos a cobrar,
entradas sem suportado, saídas sem alíquota, confronto pendente, fichas
retiradas, abertura sem ICMS, motivos da etapa 6, travas e regras da etapa 7 —
em gravidade (trava, atenção, informação), quantidade, de quê e o que fazer.
"Não apta" da etapa 7 não entra: repete, arquivo a arquivo, os motivos da 6.

**Quem aprova.** Revisor e gestor (`Capacidades.PodeAprovarEntrega`). Dev não:
conta técnica não substitui responsável pelo negócio, a mesma razão de ele não
contar como gestor. Analista monta e não aprova. Aprovação vai em coluna da
execução (`aprovada_por`, `aprovada_em`, migração `b8d3e61f2a47`), não no
resumo — o resumo é do motor, a aprovação é da API — e vira o evento
`entrega_aprovada` no histórico. Recusa: rodada que não concluiu, entrega já
aprovada, entrega superada por outra mais nova, arquivo digital gerado de novo
depois dela, trabalho parado.

**Recusa antes da fila** a entrega de um arquivo digital feito sobre apuração
velha: o pacote levaria números que a etapa 6 já não mostra.

**Piloto (execução 52, empresa 19).** 0,9 s. 775 competências no relatório — 234
prévias de SP e 541 fora de SP —, nenhum estabelecimento no dossiê, 26
pendências (16 travam, 7 pedem atenção, 3 informam). O pacote leva o relatório
e o manifesto. Dois acertos que o piloto mostrou: o relatório passou a dizer o
**período apurado** (dos dados) ao lado do **período do cadastro** — o trabalho
está cadastrado como 2025 e os dados são de 2021 —, e a etapa 6 passou a somar
o total com as competências já arredondadas (dava R$ 66.681,16 no resumo e
R$ 66.681,15 somando as competências).

**O que fica para a lapidação.** O Victor, como dev, não aprova — a entrega do
piloto espera um gestor; a Ficha 3 do dossiê em CSV pode levar minutos numa
base do tamanho da empresa 17; e o `PLANEJAMENTO.md` ainda descreve o roteiro antigo.

---

## 2026-09-16 — Revisão da etapa 7: o que se conferiu e o que se corrigiu

**Como se conferiu.** Sete arquivos CAT 42 que a SEFAZ aceitou da empresa 17
(2021 a 2024) medidos registro a registro contra o gerador, e a Ficha 3, os
saldos e as 234 prévias do piloto da empresa 19 (execuções 48 a 50) lidos de volta.
O gerador já fazia igual à empresa 17 no que decide o arquivo: CRLF e Latin-1; 1050
só de item movimentado no mês (nos sete arquivos, nenhum 1050 sem 1100); 0150
com os fornecedores das NF-e e o próprio estabelecimento; todos os CFOPs de
devolução que aparecem lá (1202, 1411, 5202, 5411, 6411) no conjunto de
devoluções; na Ficha 3 da empresa 19 de SP, nenhuma quantidade com mais de 3 casas,
nenhum nº de item acima de 999 e nenhuma linha repetida.

**O que se corrigiu.**

| Defeito | Onde pesava | Correção |
|---|---|---|
| A alíquota do confronto (enq. 1 e 3) era a do cadastro do **fim do período** | 23.065 itens da empresa 19 mudam de alíquota em 2021 (12% → 13,3% em fevereiro): a venda de janeiro confrontava com a de dezembro, e o VL_CONFR ia errado para o arquivo | razão usa a alíquota do 0200 do **mês da saída**; a mais recente só onde o mês não traz. Resumo conta `saidas_com_aliquota_do_mes` |
| O 0200 do arquivo de janeiro saía com descrição e alíquota de dezembro | o manual pede a última ocorrência **do período**, que é o mês | 0200 do `itens_da_efd` do mês, campo a campo; a **unidade** fica a mais recente, que é a da ficha convertida (mudar de unidade no meio quebraria o saldo) |
| A data do movimento era a **emissão** (DT_DOC) | 5,55% das entradas da empresa 19 entraram em mês diferente do emitido: custo médio deslocado e DATA do 1100 fora do mês | a movimentação usa a data de entrada/saída (DT_E_S); a emissão só quando a EFD não a informa. A conferência com o XML continua pela emissão |
| O 0150 só olhava a EFD do mês | 127 das 234 prévias travavam: a nota escriturada em outro mês cita participante que só está no 0150 de outro mês | procura na EFD do mês e, sem ele, na mais recente do estabelecimento |
| ICMS negativo com estoque positivo caía na trava "saldo negativo", com texto de ficha retirada | 813 saldos de fichas válidas da empresa 19: devolução de compra sobre abertura sem ICMS (item 3.3.8) | trava própria, `valor_negativo`, com o que fazer certo |
| Entrada sem ICMS suportado ia como `0,00` sem ninguém saber | 95.904 entradas de SP da empresa 19 (7%) | contada por arquivo e no resumo (`entradas_sem_icms`), com aviso no log e na tela. Não trava: zero pode ser verdade |
| Falha no meio de um arquivo deixava `.corpo`/`.cabeca` na pasta | — | rascunhos apagados, com log |
| O recorte por trava usava `LIKE`, em que `_` casa qualquer letra | — | código inteiro |
| Pré-validação do cliente: dois arquivos com o mesmo nome misturavam as ocorrências | outra ferramenta pode chamar todo mês de `CAT42.txt` | o segundo ganha `(<CNPJ> <aaaa-mm>)` no nome |

**Piloto da correção (execução 51, só a etapa 7, sobre o razão 48 e a apuração
49 — em 7 min 16 s).** Participante sem cadastro: de 127 arquivos para
**nenhum** (o 0150 ganhou os 230 que faltavam). Dos 707.676 registros 0200,
9.541 mudaram de alíquota, 47.770 de descrição, 17.199 de CEST, 8.868 de código
de barras e 3.986 de NCM; nenhum de unidade (ex.: a mussarela da loja 004265
sai com 12% em janeiro de 2021, e não com os 18% de dezembro). 95.904 entradas
contadas com ICMS_TOT zero. A recomposição segue fechando 707.607 de 707.607
itens. O ICMS negativo com estoque positivo não aparece em SP: os 813 casos são
das lojas do PR e do MS. Seguem as 234 prévias, todas por `nao_apta` da etapa
6; 12 com `confronto_pendente` (as 393 transferências 6409, enquadramento 4) e
10 com `saldo_negativo`.

**Para valer por inteiro na empresa 19**, as etapas 3 a 6 rodam de novo: a data de
entrada muda a movimentação, e a alíquota do mês muda o razão.

**O que continua aberto.** O 1200 sai sem SER (a série é lida no C100 e não
chega à movimentação); ECF_FAB, 0205 e o fato gerador sem documento (CHV 0,
item 999); entre dois arquivos do cliente do mesmo mês, vale o primeiro lido, e
não a substituição (COD_FIN 02); na Ficha 3 da empresa 19 entram entradas de uso e
consumo (1407, 1556, 2556, 2557 — 91 linhas) e o 5929 (lançamento de cupom
também registrado em ECF) não é tratado como duplicidade; a abertura sem ICMS
(item 3.3.8) segue sendo a causa do complemento inflado e do ICMS negativo.

---

## 2026-09-16 — Pré-validar o que o cliente já transmitiu

**Decisão do Victor.** A pré-validação da etapa 7 vale **também para o arquivo
que o cliente gerou com outra ferramenta** — a auditoria da empresa 17 e da empresa 20,
que já entregam a CAT 42.

**Fora do roteiro.** Não depende de etapa nenhuma e não entra na conta de
etapas concluídas: trabalho de auditoria pode nem ter EFD, só os TXT. A tela do
trabalho tem um atalho próprio para ela.

**Lê do lote, inclusive de dentro de zip.** O classificador reconhece o arquivo
digital pelo `0000|mmaaaa|` sem `|` no começo (tipo `cat42_arquivo_digital`,
que não alimenta a apuração). Os zips do lote são abertos na rodada: cada TXT
é lido em fluxo, sem extrair. O zip dentro de zip é exceção — lido por dentro,
cada membro descomprimiria o de fora desde o começo —, e vai compactado à pasta
da execução, que é apagado no fim.

**O que só se vê com o conjunto.** Arquivo de outra raiz de CNPJ fica de fora e
contado. O mesmo estabelecimento e mês visto duas vezes (o zip que é cópia de
outro, na empresa 17) fica listado como repetido, sem ler de novo. E o saldo inicial
de cada item tem de ser o final da **última competência em que o item
apareceu** — não do mês anterior, porque o 1050 só traz item com movimento. Se
não é, falta arquivo no meio ou o estoque foi ajustado por fora: aviso, com as
duas competências na mensagem.

---

## 2026-09-16 — Etapa 7: o arquivo digital, a prévia e a pré-validação

**Decisões do Victor.** Competência de SP que não está pronta **sai como
prévia** (PREVIA no nome, zip separado), em vez de não gerar nada; e a
pré-validação vale **também para arquivo que o cliente já transmitiu** (vem na
próxima entrega).

**O formato foi medido antes de escrito.** Três arquivos reais da empresa 17 (24, 33 e
77 MB) confirmaram o leiaute e resolveram o que o manual deixa em aberto: a
linha não começa com `|` e só termina com `|` quando o último campo é vazio;
CRLF; quantidade com 3 casas e valor com 2, sempre; nº do item com 3 dígitos;
país `1058`; todo item do 0200 tem 1050. O nome dos arquivos
(`CAT5_SP_<CNPJ>_<M>_<AAAA>.txt`, mês sem zero) é o que a empresa 17 usou.

**A pré-validação recompõe a Ficha 3 a partir do próprio arquivo** — é o que o
Pós-Validador faz. Lendo só o 1050 inicial e o 1100, o mesmo `RazaoDoItem` do
sistema chegou ao 1050 final em **100% das quantidades** e em 99,99% dos
valores a até 5 centavos, nos arquivos da empresa 17. Daí as severidades: quantidade
que não fecha é **erro**; valor fora de 5 centavos é **aviso**, com a
diferença dita.

**Calibrada contra o que a SEFAZ aceitou.** Nos quatro arquivos reais a
pré-validação não acusa erro nenhum (875.789 linhas em 25 s o maior). Duas
coisas viraram aviso por isso: item de nota com **dois códigos** (3 casos num
arquivo aceito — kit desmembrado, provavelmente) e saldo em valor de item
zerado em que a empresa 17 guardou resíduo (R$ 6,27 e R$ 29,60).

**Envio só com tudo limpo.** Vai para `envio/` a competência apta na etapa 6,
sem trava de escrita e sem erro lendo o arquivo de volta do disco. As travas
desta etapa: linha da Ficha 3 sem documento (a venda de PDV do relatório não
tem chave nem nº do item), saída sem enquadramento, devolução de venda sem a
venda original, confronto pendente, saldo negativo, item ou participante sem
cadastro na EFD, estabelecimento sem EFD no mês e erro de pré-validação.

**O que sai de onde.** 0000 e 0150 do bloco 0 da EFD vigente do mês (lido até o
0990, sem atravessar o bloco C) — o 0150 só com os participantes citados, fora
os de modelo 02, 2D, 59, 60 e 65, e o próprio estabelecimento; 0200 do cadastro
de itens da etapa 3; 1050 dos saldos da etapa 6; 1100 e 1200 da Ficha 3.

**Devolução de venda sem a nota original.** O COD_LEGAL dela é o da venda.
Sem a nota referenciada, só dois casos se resolvem: a interestadual (4) e, no
trabalho com o cupom no 0, a de dentro do estado (0). O resto trava, em vez de
enquadrar no escuro.

**Recusa antes da fila** o que daria arquivo de uma coisa e apuração de outra:
razão montado com outra escolha de venda a consumidor, razão mais novo que a
apuração, razão de antes de a Ficha 3 guardar o documento de cada linha.

**Memória constante.** 1100 e 1200 vão a um rascunho enquanto se descobre o que
citam; o arquivo é o cabeçalho seguido do rascunho. Ocorrências: todas contadas,
as 200 primeiras de cada regra guardadas.

**O que ainda não se resolve aqui:** série do documento não eletrônico (o 1200
sai sem SER, a etapa 3 não a guarda), ECF_FAB, o 0205 (só para quem não
escritura EFD) e o fato gerador presumido sem documento (CHV 0, item 999).

---

## 2026-09-16 — A venda a consumidor final é escolha do trabalho

**O que o arquivo real mostrou.** Antes de escrever o gerador da etapa 7, três
arquivos CAT 42 que a empresa 17 transmitiu (2022 a 2024, de 24 a 77 MB) foram
medidos registro a registro. O formato bate com o leiaute. O enquadramento,
não: a venda de cupom (CF-e SAT, CFOP 5.405) vai com **COD_LEGAL 0**, no
arquivo e na Ficha 3 (coluna `ENQ0_DEMAIS_SAIDAS`). Só a perda (5.927) entra
no enquadramento 2, com valor de confronto. Não há complemento.

| Operação no arquivo real | COD_LEGAL | VL_CONFR |
|---|---|---|
| 5.405 em CF-e SAT (97% das linhas) | 0 | vazio |
| 5.927 em NF-e | 2 (e parte em 0) | preenchido no 2 |
| 1.411 devolução de venda | 0 | vazio |

O sistema punha o cupom no **1**, pelo modelo do documento (decisão de
14/09/2026), que é o que o manual diz. No piloto da empresa 19, o R$ 1,53 milhão de
complemento vem inteiro desse enquadramento.

**Decisão do Victor.** A escolha é **por trabalho**: `projeto.venda_a_consumidor`
vale `enquadramento_1` (o manual: ressarcimento e complemento) ou
`demais_saidas` (como a empresa 17: só a perda e a interestadual geram ressarcimento).
Todo trabalho existente ficou no enquadramento 1, que é como o razão já vinha
montando.

- A regra mora no domínio (`VendaAConsumidor`, em `cat42/enquadramento.py`, e o
  espelho em `Cat.Dominio/Projeto`). Em `demais_saidas`, a venda comum é 0 dos
  dois lados — consumidor ou revendedor —, e a NF-e modelo 55 deixa de ser
  indefinida: não há mais o que perguntar sobre quem comprou.
- O que o manual fixa não muda: 5.927 segue no 2, saída para outro estado no 4,
  isenção no 3.
- O razão grava no resumo qual escolha usou, e a tela do razão avisa quando o
  último montado usou a outra. Mudar pede confirmação e fica no histórico
  (`parametro_alterado`, com `de` e `para`).

**A Ficha 3 passa a guardar o documento de cada linha** — chave, nº do item,
modelo, participante e número —, que é o que o 1100 e o 1200 exigem. A venda de
PDV do relatório fica sem chave e sem nº do item: calcula a ficha, mas não vira
registro do arquivo.

---

## 2026-09-16 — Etapa 6: o período fecha por estabelecimento e mês

**Decisões do Victor.** Ressarcimento e complemento **separados** (o líquido é
leitura, nunca o valor do pedido); competência com pendência **apura e fica
marcada**, em vez de bloquear o número; e o crédito da operação própria do art.
271 entra como **coluna preparada e zerada**, até o confronto dos enquadramentos
2 e 4 existir.

**Por estabelecimento e mês** porque é a unidade do arquivo digital: o registro
0000 leva CNPJ, IE e o período `mmaaaa`. Apurar pela empresa daria um número que
não vira arquivo nenhum.

**Apurar não é poder entregar.** O valor aparece sempre; ao lado dele, o que
trava — fora de SP, ficha retirada, confronto pendente, saída sem alíquota,
enquadramento indefinido, saldo que não fecha com o inventário, mês sem bloco H.
Cada motivo diz o que fazer, e o resumo separa `ressarcimento` (tudo) de
`ressarcimento_apto` (o que dá para pedir hoje).

**O piloto (execução 47, 46 segundos).** 775 competências em 71
estabelecimentos, 2.464.669 saldos gravados, R$ 66.681,16 de ressarcimento e
R$ 1.534.323,19 de complemento — e **nenhuma competência apta**.

| UF | Lojas | Competências | Ressarcimento |
|---|---|---|---|
| PR | 47 | 517 | R$ 0,00 |
| **SP** | **22** | **234** | **R$ 0,00** |
| MS | 2 | 24 | R$ 66.681,15 |

O que o quadro diz, e que nenhuma tela dizia antes: **a empresa 19 tem 22
estabelecimentos em São Paulo, e todo o valor apurado é de lojas do Mato Grosso
do Sul**, que não entram na CAT 42. As 234 competências paulistas têm entrada e
não têm saída — o relatório de saídas que o download entregou é das lojas MS e
do CD do Paraná. Sem o relatório de saídas das lojas de SP (ou o XML dos
cupons), o pedido paulista é zero por falta de dado, não por falta de direito.

Travas: 638 competências divergem do inventário, 541 são de fora de SP, 137 não
têm bloco H no mês, 52 dependem do confronto dos enquadramentos 2 e 4, 46 têm
ficha retirada, 6 têm saída sem alíquota e 3 têm enquadramento indefinido.

**Os saldos saem prontos para o 1050.** Uma linha por (estabelecimento, mês,
mercadoria) com quantidade e ICMS suportado no início e no fim — os quatro
campos do registro 1050. O saldo inicial é o final do mês anterior da mesma
ficha; no primeiro mês em que a mercadoria se move, é a abertura do inventário.
Nada é recalculado: vem da coluna de saldo da própria Ficha 3.

---

## 2026-09-15 — Ficha com estoque negativo sai do total até os dados chegarem

**O que o piloto mostrou.** Primeira montagem do razão sobre a empresa 19
(execução 45: lojas MS e CD 003 PR, saídas de jan–mar/2021): R$ 584,7 milhões
de "ressarcimento" — mais que todo o ICMS suportado das entradas do ano. **99,99%
vinham de 4.037 fichas cujo estoque ficou negativo.** Com saldo perto de zero
o custo médio explode: uma mercadoria do CD chegou a R$ 1,8 milhão por
unidade, e uma transferência de 312 unidades baixou R$ 570 milhões. A mediana
do unitário nas saídas é R$ 0,28 e o percentil 99, R$ 6,45: a cauda domina.

As fichas que nunca ficaram negativas somavam R$ 65.348,48 — ainda
subestimado, porque a abertura entra sem ICMS.

**Por que acontece.** Estoque negativo é movimento que falta: perdas do CFOP
5.927 (relatório à parte), meses e lojas do relatório de saídas que falharam
no download, produção e desmontagem. A regra do domínio foi conferida contra
dados completos (empresa 17) e não tem o que fazer com saída que o estoque não
explica.

**Decisão do Victor.** Entre usar o custo das entradas mais recentes (item
3.3.8 do manual), zerar o ressarcimento dessas linhas, ou tirar as fichas do
total: **tirar as fichas do total até os dados chegarem.**

- a ficha com estoque negativo em qualquer linha fica `retirada`;
- não soma ressarcimento, complemento, enquadramento nem competência;
- continua gravada e marcada, na lista e nas planilhas; o resumo diz quantas
  e quanto elas mostrariam, separado do total;
- a lista abre nas válidas, e as retiradas vão para o fim quando se pede todas.

O critério é um só por enquanto — estoque negativo. Quando o relatório de
saídas completo e as perdas chegarem, a quantidade de fichas retiradas é a
medida de quanto ainda falta.

**O piloto com a regra (execução 46, 14 min 14 s).**

| | |
|---|---|
| Fichas | 497.700, das quais 4.037 retiradas (413.782 linhas) |
| Ressarcimento nas válidas | R$ 66.681,16 |
| Complemento nas válidas | R$ 1.534.323,19 |
| Enquadramento 1: suportado baixado × confronto | R$ 1.253.522,55 × R$ 2.721.164,58 |
| Enquadramento 4 (confronto pendente) | R$ 5.439.997,11 baixados |
| Demais saídas | R$ 10.032.822,07 baixados |

O complemento maior que o ressarcimento **não é conclusão fiscal**: a abertura
entra sem ICMS suportado (o inventário do cliente não traz o imposto), o custo
médio sai baixo, e o confronto — que é real, alíquota × valor de venda — passa
dele. É o próximo buraco a fechar, junto com o confronto dos enquadramentos 2
e 4 e as saídas que faltam.

---

## 2026-09-15 — Unidade de conversão: a ficha é na unidade do inventário

**A regra.** A Ficha 3 é escriturada na unidade do 0200 (UNID_INV). O item de
nota vem na unidade dele, e nota em caixa não se soma a venda em unidade. O
fator é o do **registro 0220** da própria EFD, que o Guia Prático define como
o que **multiplica** a unidade da nota para chegar à do inventário. A extração
de movimentos passou a ler o 0220 (amarrado ao 0200 logo acima, que ele não
repete), e o razão converte entrada, saída da EFD e inventário.

**Sem 0220, não se adivinha fator.** Quando o rótulo da nota difere do cadastro
e não há 0220, a quantidade fica como veio e a linha é marcada
(`unidade_sem_fator`). É pendência visível, não conversão inventada.

**O que a empresa 19 mostrou, e por que isso importa.**

| Medida | Resultado |
|---|---|
| Registros 0220 na EFD | **nenhum** (uma filial: 17.745 itens no 0200, zero 0220) |
| Entradas com rótulo diferente do cadastro | 56.986 de 8.761.002 (0,65%); UN→CX 31.799, CX→FD 14.446 |
| Quantidade da EFD = "Qtde;Unitária" do relatório, 05/2021 | **100%**, em todos os pares de unidade — inclusive rótulo CX com 2.500 unidades |

Ou seja: na empresa 19 a quantidade da EFD **já vem na unidade básica**, e o rótulo
CX/FD é o nome da embalagem no ERP. Converter pelo rótulo teria multiplicado
errado. A regra "sem 0220 fica como veio" é, aqui, também a certa.

**O juiz da unidade é o inventário.** Ficha que soma caixa com unidade não
fecha com o estoque declarado. O razão agora confere o saldo de cada ficha em
cada data de bloco H do período: bate, até 2%, diverge, ou **suspeita de
unidade** — quando a razão entre os dois é inteira e de 4 vezes ou mais. Item
ausente do bloco H numa data é estoque zero.

**Medido à mão antes de codar** (lojas MS, jan/2021, abertura + entradas −
saídas do relatório contra o H010 de 31/01): 49,4% dos itens fecham exato e
61,8% até 2%; só **1,6%** têm diferença com cara de fator. As maiores
diferenças são entrada grande sem saída correspondente — movimento que falta
(perdas do CFOP 5.927, que o cliente manda em relatório à parte;
transferências; produção e desmontagem no açougue e na padaria), não
conversão. A conferência passa a mostrar isso ficha a ficha.

---

## 2026-09-15 — Etapa 5: o razão dos itens, e de onde vem a saída

**O obstáculo que decidiu o desenho.** O razão baixa da ficha cada saída de
cada mercadoria. Na empresa 19, 36,5 milhões de documentos de saída (R$ 5,8
bilhões) **não têm item na EFD**: NFC-e e CF-e SAT vão à escrituração só com o
analítico por CST e CFOP. Com item, a EFD traz R$ 6 milhões de saída. Sem outra
fonte não há ficha.

**Decisões do Victor, em 15/09/2026.**

1. **Saída: o relatório gerencial de saídas do cliente como base, e o XML
   vencendo quando houver.** Na mesma nota, a EFD com item vence o relatório
   (a linha do relatório com a chave de uma nota da EFD sai, contada). O XML
   dos cupons, quando vier, entra como a fonte que vence as duas.
2. **Entra no razão a mercadoria com saída CST 60** em qualquer loja do
   período. É a vendida com o imposto já retido, que é a matéria da CAT 42.
   Resolve de passagem a questão aberta da etapa 4: o "suportado" de item CST
   00 e 20 — 54% do total — não vira ficha.
3. **Construir já, com um piloto** sobre o que o download entregou.

**O relatório de saídas diz loja e documento, não CNPJ nem modelo.** Duas
colunas novas no leitor: `Unidade` e `Descrição Tipo Dcto`. A venda de PDV
("Estoque / Venda De Produtos PDVs") é **cupom, logo consumidor final pelo
tipo do documento** — a mesma regra do modelo 65 e 59, não suposição sobre
quem comprou. O CNPJ da unidade sai de duas pistas que se confirmaram na
amostra real: a chave da nota emitida pela loja e a coluna CNPJ/CPF da venda de
PDV, que traz a própria loja ("005" → 44.000.002/0034-14 pelas duas). Linha que
nenhuma pista alcança fica contada, não suposta.

**O cálculo é o do domínio, linha a linha.** O mesmo `RazaoDoItem` conferido
contra a Ficha 3 da empresa 17. O SQL junta, filtra e ordena; não calcula.

| Parte | De onde | Estado no piloto |
|---|---|---|
| Entrada e suportado | apuração da etapa 4 (que passou a gravar data, CFOP e item) | completo |
| Devolução de venda | entrada com CFOP de devolução, lançada como saída com a marca | completo |
| Devolução de compra | saída com CFOP de devolução, lançada como entrada com a marca | completo |
| Saída com item | EFD | completo |
| Saída de cupom | relatório de saídas | só CD 003 PR e lojas MS, jan–mar/2021 |
| Enquadramento | PDV → 1; modelo; CFOP; o resto indefinido | completo |
| Confronto nos enquadramentos 1 e 3 | alíquota interna do 0200 × valor da saída (leiaute, VL_CONFR) | completo |
| Confronto nos enquadramentos 2 e 4 | ICMS da operação própria da entrada | **pendente**, contado |
| Abertura | quantidade do bloco H do dia anterior ao período | **sem valor**: o inventário do cliente traz as colunas de imposto vazias; item 3.3.8 ainda não derivado |

**O que a tela diz antes do número.** Fichas fora de SP (a CAT 42 é paulista,
e o piloto é PR e MS), abertura sem ICMS suportado, confronto pendente, saída
sem alíquota, estoque negativo, enquadramento indefinido e loja sem CNPJ
aparecem como lista de pendências acima do total. É a regra da etapa 4: o
número nunca aparece sem o que falta para ele valer.

**Duas economias de leitura.** Relatório que não mostra saída nas primeiras
5.000 linhas é de entradas e o razão não o lê inteiro; o simétrico vale na
etapa 4 para relatório só de saídas. Sem isso, cada etapa leria os 20 GB de
entradas e os 21 GB de saídas por inteiro.

**A mecânica de rodada virou módulo** (`casos_de_uso/rodada.py`): diário,
freio, cancelar e formatação do log, usados pelas etapas 4 e 5. A lista de
etapas canceláveis mora ali.

---

## 2026-09-15 — A primeira rodada real da etapa 4, e o que ela mostrou

**Rodou pela tela sobre a empresa 19 inteiro** (execução 11): 94 relatórios do
cliente, 20 GB, e os 8.761.002 itens de entrada de 2021, em 32 min 50 s. Os
números batem com a medição feita por script: cobertura de 68,79%, R$
337.688.895,48 apurados, fração documental de 100%, e CST 40 com 75,6% dos
itens sem apuração.

**Três defeitos que só a base real mostrou.**

1. **Nota sem chave virava um documento só.** O analítico agrupava pela chave,
   e as 667 notas modelo 1 (904 itens) caíam todas na chave vazia. O
   documento passa a ser a chave quando há, e estabelecimento + participante
   + modelo + número + competência quando não há. Índice gravado antes disso é
   ignorado — a página sai calculada na hora — até ser regravado.
2. **A leitura dos relatórios segurava tudo em memória.** Eram 14,1 milhões de
   itens num dicionário do Python, ao longo de 26 minutos, numa máquina com 1
   GB livre. Agora cada relatório vira uma parte em parquet e a soma entre
   relatórios é do DuckDB: a memória fica no tamanho do maior relatório.
3. **O banco não voltava sozinho.** O Docker Desktop reiniciou no meio da
   rodada; os contêineres com política de reinício voltaram, o do CAT não, e a
   API respondeu 500 a toda consulta da tela. O `docker-compose.yml` ganhou
   `restart: unless-stopped`. A rodada em si sobreviveu: o progresso que não
   gravou foi descartado sem derrubar nada, e ela concluiu quando o banco
   voltou.

**A questão aberta ficou maior.** Com todos os relatórios, a fonte 2 dá R$
120,95 milhões a CST 00 e R$ 61,78 milhões a CST 20 — 54% dos R$ 337,7 milhões
vêm de CST sem substituição. Continua sem decisão (ver a entrada abaixo).

---

## 2026-09-15 — Etapa 4 ganha rodada, tela e cancelamento

**O que entrou.** A apuração do ICMS suportado deixou de ser script e virou
etapa: `st_suportado` na fila do motor, rotas na API em C#
(`/api/projetos/{id}/suportado`) e a tela desenhada no handoff da etapa 4
(`/projetos/{id}/suportado`). O roteiro do trabalho passa a mostrar a etapa 4
como disponível.

**Não apurável se divide em dois.** O domínio devolve, junto do "não
apurável", uma `Pendencia`: `sem_o_que_apurar` (CST que não é de substituição
— 40, 00, 20…) ou `falta_dado` (60, 10/30/70 sem destaque, 90, sem CST). A
tela depende disso para não pintar isento de alerta. CST 90 sem valor cai em
falta dado porque, medido em 2021-05, metade dos CST 90 que casaram com o
relatório tinha imposto informado.

Na mesma passada saiu um defeito antigo: os conjuntos de CST traziam "500" e
"201", que nunca casavam — o domínio compara só os dois últimos dígitos, e no
EFD "500" é origem 5 com CST 00, não CSOSN.

**Leitura numa pasta, gravação em outra.** A apuração lê o
`movimentos.parquet` da última extração concluída e grava na pasta da própria
execução. Na mesma pasta, rodar a apuração de novo sobrescreveria material da
etapa 3. Pelo mesmo motivo, contar e paginar usam DuckDB em memória (com teto e
onde derramar), e não o banco em arquivo do confronto, que deixaria um
`.duckdb` na pasta de outra etapa.

**Cancelar é cooperativo.** A tela grava "cancelando"; a rodada confere isso
entre um relatório e outro e entre um lote de 200 mil itens e outro, e para
apagando o parquet parcial. Matar a linha de execução no meio da gravação
deixaria um arquivo com cara de inteiro. Só as etapas que conferem o freio
aceitam o pedido — nas outras o motor recusa com 422, em vez de a tela dizer
que vai parar uma rodada que vai até o fim. Motor que reinicia com uma rodada
"cancelando" a marca como cancelada, não como falha.

**O que o handoff pedia e ficou diferente.**

| Handoff | Implementado | Por quê |
|---|---|---|
| rota `/trabalhos/:id/apuracao` | `/projetos/:id/suportado` | "apuracao" é a chave da etapa 6 (ressarcimento e complemento); o resto do sistema usa `/projetos` |
| exportação assíncrona com link no histórico | download direto, com o modal de confirmação | é o mecanismo das outras sete listas: salvar como, em fluxo, cancelável |
| "uma aba por fonte" | uma aba, com a coluna Fonte; quebra em abas acima de 900 mil linhas | o filtro por fonte já dá a lista de uma fonte só |
| nome do fornecedor | código do participante | o 0150 ainda não é extraído |
| código da requisição na falha | número da execução | a rodada roda fora da requisição; o id da execução é o que acha a linha no log |
| progresso por SSE | consulta a cada 2 s | é o que as etapas 2 e 3 fazem, e o resumo carrega andamento e log |

**Resumo com versão.** O resumo grava `versao: 2`. Apuração sem esse campo é
de antes da lista por fonte, e a tela diz "rode de novo" em vez de mostrar
cartão zerado como se zero fosse o resultado.

**Medido na base real (empresa 19, 2021, movimentação da execução 9, com os três
relatórios de entradas de 05/2021).**

| | |
|---|---|
| Relatórios lidos (721 mil linhas de entrada) | 65 s, 510.443 itens com imposto informado |
| Cascata sobre 8.761.002 itens | 134 s, 65 mil itens/s |
| Índice por documento | 93 s, 28 MB |
| Página do analítico por documento, sem busca | 0,1 a 0,6 s — **antes do índice, 17,7 s a primeira e 26,2 s a de número 5.000** |
| Página com busca (agrupa na hora) | ≈ 5,7 s |
| Cobertura de 05/2021 | 68,65% — os outros meses ficam perto de 1%, porque só havia o relatório de maio |

O índice existe por causa da segunda linha de baixo para cima: agrupar 8,7
milhões de itens a cada clique não é tela. Ele guarda o analítico inteiro e o
de cada fonte já agrupados e numerados; a busca continua agrupando na hora,
porque procura dentro dos itens. A página funda do escopo "por item" sem
filtro (deslocamento de milhões) ainda ordena tudo — ≈ 10 s na página 100.000,
que ninguém alcança clicando em "Próxima".

**Questão aberta, anotada para decidir.** A fonte 2 dá valor também a item de
CST 00 e 20 — o relatório informa o ICMS próprio da operação, e
`imposto_suportado` o soma. Só com o relatório de maio foram R$ 8,39 milhões
em CST 00 e R$ 4,06 milhões em CST 20 (carne resfriada, por exemplo). Item sem
substituição não tem ICMS suportado para a Ficha 3; se isso deve ficar fora da
apuração ou sair só no razão, pelo cadastro de mercadorias de ST, é decisão
fiscal que não foi tomada aqui.

---

## 2026-09-14 — O razão foi confrontado com a Ficha 3 de um cliente, e fecha

**O que se fez.** O razão da Ficha 3 foi rodado contra a Ficha 3 **já
calculada** da empresa 17, uma filial e um mês, reconstruindo cada ficha a
partir dos mesmos movimentos e comparando linha a linha.

| | |
|---|---|
| Itens conferidos | 10.741 |
| Itens sem divergência | 10.741, ou 100% |
| Linhas comparadas | 550.862 |
| Saldo em quantidade batendo | 100,0000% |
| Ressarcimento batendo | 100,0000% |
| Ressarcimento do sistema | R$ 3.049,73 |
| Ressarcimento do arquivo | R$ 3.049,73 |
| Diferença | R$ 0,00 |

É a primeira vez que o cálculo deste sistema é medido contra um resultado
produzido por outra ferramenta, sobre dado real, sem nenhum ajuste.

**Onde estão as referências.** `Z:\CLIENTE\Implementação
. Baixa de
Estoque\Trabalho ST (RVC)` tem quatro empresas. A **empresa 17** traz a Ficha 3
completa, 35 colunas, de janeiro de 2021 a dezembro de 2025, com todos os
enquadramentos. O **EMPRESA 08** traz um book consolidado de 1.255.373 linhas,
mas só de CFOP 5.927, isto é, só o enquadramento 2.

**O book da empresa 08 confirmou a fórmula do suportado.** Em 100% de 1.242.621
linhas, `ENT_VLR_SUPORTADO` é igual a ICMS mais ST mais FECOP, que é
exatamente o que `cat42/suportado.py` calcula. E o ressarcimento é igual ao
unitário da entrada vezes a quantidade saída, em 100% das 782.693 linhas com
unitário.

**Duas armadilhas que a conferência cobrou.** A primeira: CFOP `0001` não é
CFOP, é a linha de abertura de estoque gerada do registro 1050 — tratá-la como
entrada normal infla a base em mais de dez vezes. A segunda: a Ficha 3 traz
**devolução com quantidade negativa**, embora o manual exija que no arquivo
digital ela vá sem sinal. O razão recusa quantidade negativa de propósito e
exige a marca `devolucao`, que é o que evita espalhar sinal por toda a regra de
cálculo. Cem itens do arquivo só apuraram depois que o leitor passou a traduzir
o sinal em marca.

---

## 2026-09-14 — O enquadramento sai do modelo do documento, não de chute

**Decisão.** O enquadramento legal da saída ganhou módulo próprio,
`cat42/enquadramento.py`, e ele separa o que é regra do que é suposição. O que
não dá para saber devolve `None`, e a linha entra contada como indefinida.

**Por que isso importa.** O enquadramento decide em qual coluna da Ficha 3 o
valor cai, de 15 a 19, e contra o quê ele é confrontado: o ICMS efetivo da
saída ou o da entrada. Errar aqui não dá número errado num item, dá apuração
inteira errada — e do jeito que passa despercebido.

**O manual fixa pouco:** baixa de estoque em CFOP 5.927 é enquadramento 2,
saída para outro estado é 4, isenção ou não incidência é 3. O CFOP resolve mais
um caso, a transferência, que segue para revenda e por isso é "demais saídas".

**O que sobrava era quase tudo.** Numa base real, 91.007.428 linhas de saída,
os CFOP 5.102 e 5.405 somam 98% do movimento, e o enquadramento deles depende
de **quem comprou**: consumidor final cai no 1, contribuinte que revende cai no
0. O CFOP não distingue os dois.

**A saída não foi chutar, foi olhar o modelo do documento.** NFC-e (65) e CF-e
SAT (59) existem para documentar venda a consumidor final. Não é suposição
sobre o comprador: é o que o modelo é. Na base medida, 66,1% das linhas são
NFC-e e 32,3% são CF-e SAT. O modelo 55, que de fato serve aos dois casos, é
1,6%, e quase todo ele é transferência, que o CFOP já resolve.

**O resultado, medido sobre as 91.007.428 linhas:**

| Enquadramento | Linhas | Valor |
|---|---|---|
| 1, consumidor final | 73,4% | R$ 2.285.542.618,46 |
| 3, isenção ou não incidência | 25,2% | R$ 1.348.901.257,58 |
| 0, demais saídas | 0,8% | R$ 1.313.218.175,20 |
| 4, outro estado | 0,4% | R$ 649.844.435,07 |
| **Indefinido** | **0,19%** | R$ 223.444.140,40 |
| 2, fato gerador não realizado | 507 linhas | R$ 2.497.064,16 |

Sobrou 0,19% indefinido, e ele aparece na conta em vez de virar um
enquadramento escolhido no escuro.

**Uma armadilha que virou teste.** CST 60 não é isenção. Mercadoria com ST já
retida é justamente o caso do ressarcimento, e classificá-la como isenta
jogaria a apuração inteira na coluna errada, em silêncio. E nenhum CFOP pode
estar em devolução e em transferência ao mesmo tempo: se estivesse, a ordem
das regras decidiria o resultado, que é como se esconde um erro de
classificação.

---

## 2026-09-14 — O relatório do cliente entra como fonte 2, e destrava a etapa 4

**Decisão.** A apuração do ICMS suportado passa a cruzar a EFD com o relatório
gerencial de entradas do cliente, por `(chave de acesso, código do item)`.

**O resultado, medido na base real de 2021, 8.761.002 itens de entrada:**

| | Antes | Depois |
|---|---|---|
| Cobertura por item | 0,92% | **68,79%** |
| ICMS suportado | R$ 1.482.436,74 | **R$ 337.688.895,48** |
| Apoiado em documento | 100% | 100% |
| CST 60 apurado | 0,00% | **93,04%** |

O CST 60, que é 42% das entradas e vinha zerado na EFD, passou a R$
133.301.191,53 apurados. Era exatamente o buraco que a etapa existia para
fechar.

**O que ainda não apura não é o mesmo buraco.** Dos 2.734.465 itens restantes,
**75,6% são CST 40**, isento ou não tributado, que não tem imposto suportado a
apurar por definição. O resto real são 249.918 itens de CST 60 sem informação,
cerca de 2,9% das entradas.

**A junção é por chave e código, nunca só pela chave.** Uma nota tem muitos
itens, e casar só por nota daria o imposto de um item a outro. Na base, 99,99%
dos itens de entrada da EFD têm chave de 44 dígitos e 99,83% das linhas do
relatório também, então a junção não perde quase nada.

**Quem soma é o domínio do gerencial.** `MovimentoGerencial.imposto_suportado`
já escolhe entre XML, ERP e retido anteriormente, e já sabe que no retido
anterior não se soma o ICMS da operação, porque a mercadoria veio tributada.
Refazer essa conta na infraestrutura daria duas verdades.

**Um defeito que custou treze minutos.** O esquema do parquet guardava duas
casas decimais, e o relatório traz ICMS com quatro ("2,3341" numa linha real).
O pyarrow recusa a gravação inteira com "Rescaling Decimal value would cause
data loss", e a primeira extração morreu depois de ler 8,7 GB. O esquema passou
a seis casas, e há teste que grava um valor de quatro casas e confere que ele
sobrevive. O teste também passou a usar o esquema do próprio módulo: a cópia
com duas casas que ele tinha antes escondia justamente esse defeito.

---

## 2026-09-14 — Etapa 4 começa pelo ICMS suportado, e ele é uma cascata

**Decisão.** O ICMS suportado na entrada ganhou módulo próprio de domínio,
`cat42/suportado.py`, e não é uma soma: é uma **cascata de fontes** que devolve
o valor **e de onde ele veio**.

**Por quê.** O manual define o suportado como o imposto da operação própria do
substituto somado ao retido, com FECOEP. Somar dois campos do C170 parece
resolver. Não resolve, e o motivo está na base real, 8.761.002 itens de entrada:

| CST | Itens | Traz ICMS | Traz ST |
|---|---|---|---|
| 60 | 3.705.774 | 0,0% | 0,0% |
| 40 | 2.066.118 | 0,0% | 0,0% |
| 00 | 1.235.767 | 99,9% | 2,0% |
| 20 | 1.073.629 | 98,9% | 0,0% |
| 10 | 58.339 | 99,5% | 95,9% |

O CST 60 é 42% das entradas e vem zerado nos dois campos, corretamente: o
imposto foi retido antes e o remetente não destaca nada. Uma soma devolveria
zero e pareceria certa.

**As quatro fontes, em ordem de prova.** Destacado na entrada; informado pelo
fornecedor, no `infAdFisco` da nota ou na coluna "ST integral" do relatório do
cliente; reconstruído por base e alíquota; e não apurável, com o motivo escrito.

Guardar a procedência por linha não é luxo. Um valor lido da nota e um valor
reconstruído por alíquota não podem virar a mesma coluna sem aviso: é a
diferença entre um pedido de ressarcimento sustentável e um chute. O resumo
separa `valor_documental` do total justamente para essa pergunta.

**O que a medição mostrou.** Rodando a cascata sobre a base real, **só 0,92%
dos itens têm suportado apurável hoje**, R$ 1.482.436,74, todos por destaque na
entrada. A reconstrução por base e alíquota não salva nada: a BC ST também vem
zerada no CST 60.

**O caminho está medido.** O relatório gerencial de entradas do cliente traz
"ST integral" preenchido em 43,40% das linhas, somando R$ 335.819.112,61. É a
fonte 2 da cascata, e ligá-la é o próximo passo da etapa 4. Sem ela, esta etapa
não tem o que apurar.

---

## 2026-09-14 — O rascunho da planilha sai do disco do Windows

**Decisão.** O xlsxwriter passa a escrever o rascunho na pasta do arquivo que
está sendo gerado, e não na pasta temporária do sistema.

**Por quê.** Com `constant_memory`, cada linha vai para disco na hora — é o
que permite montar planilha maior que a memória. O preço é o volume do
rascunho: a lista de movimentos de uma base real tem 8.769.348 linhas, e o XML
intermediário disso passa de 7 GB.

A pasta temporária do sistema fica no C:, que nesta casa é o disco menor.
Medido enquanto um download acontecia: o C: caía 0,16 GB por minuto e encheria
em 74 minutos, antes de a planilha ficar pronta. O download não ia terminar, e
o disco de sistema ia junto.

O DuckDB já fazia certo desde o começo — `temp_directory` aponta para a pasta
do destino. O xlsxwriter era o único que ainda usava o TEMP do sistema.

**Por que não a pasta que o usuário escolheu.** Duas razões. O servidor nunca
fica sabendo dela: o "salvar como" é do navegador, e o caminho não viaja na
requisição. E quando esse destino é pasta de rede, escrever rascunho lá seria
repetir um defeito que este projeto já pagou para aprender — gravação em rede
que atrasa e se perde. Gera-se local, entrega-se depois.

**De quebra.** O arquivo de teste tinha `class TestCsv` duplicada, cópia byte a
byte, de um script de edição que rodou duas vezes. A segunda definição anulava
a primeira em silêncio: sete testes pareciam existir e nunca rodavam. Removida.

---

## 2026-09-14 — Fim da migração: sem repasse, motor sem rota pública, versão em VERSAO

**O que saiu.** O repasse YARP do C# ao motor: rota que a API não conhece
responde 404 com `detail` e não chega ao Python. Do motor saíram a
`/api/saude` pública (virou `GET /interno/saude`, com o segredo), o CORS e a
documentação interativa (`/docs`, `/redoc`, `/openapi.json`). E todo o código
Python que só existia para as rotas públicas: `seguranca.py`, senha e token
(`infraestrutura/auth`), o repositório e o domínio de usuário, as portas, e as
dependências `python-jose`, `argon2-cffi` e `bcrypt`. Um teste do motor falha se
aparecer nele rota fora de `/interno`.

**Senha e token deixaram de cruzar ao vivo com o Python.** Não há mais código
Python que confira senha ou leia token. O que prova que quem já tinha senha
continua entrando são os vetores gravados pelo Python
(`Cat.Compatibilidade.Testes`), que ficam. O cruzamento ao vivo segue para o que
os dois lados ainda compartilham: o dígito do CNPJ e a tabela de tipos de arquivo.

**Três pendências do plano, decididas com o usuário.**

- **A versão mora no arquivo `VERSAO`, na raiz**, lido pela API e pelo motor.
  O `pyproject.toml` fica com `0.0.0` e não é lido: o setuptools não aceita
  buscar o número fora de `backend/`, e duas cópias do número é o defeito que
  a regra existe para evitar.
- **`backend/` não vira `motor/`.** Renomear moveria a `.venv` (que quebra), o
  `.env` e a pasta de trabalho com dados reais; e as execuções guardam o caminho
  absoluto da pasta — planilhas antigas dariam 410 e excluir trabalho recusaria
  apagar a pasta, por estar "fora" da pasta de trabalho.
- **Postgres obrigatório.** O `instalar.ps1` para, com instrução, sem Docker
  instalado e rodando. A instalação com SQLite nunca funcionou (migração
  `62fe3d195ce5`) e a API em C# fala só Postgres. O SQLite fica só na bateria
  de testes do motor.

---

## 2026-09-13 — Conferência e movimentos pedidos em C#, rodando na fila do motor

**O que entrou.** Pedir a conferência e os movimentos, listar as rodadas de um
trabalho, acompanhar uma e baixar as planilhas, tudo em C#. Do Python saíram
`conferencia_router.py`, `movimentos_router.py` e `infraestrutura/tarefas.py`.
Das rotas públicas o motor agora só tem `/api/saude`; o resto dele é o canal
interno.

**A thread da rota virou fila.** Antes, a rota Python abria uma thread no
próprio processo e a rodada vivia nela. Com a rota em C#, isso não se sustenta:
o pedido passa a gravar a execução `na_fila`, e `workers/fila.py`, que sobe junto
com o motor, pega uma por vez (`FOR UPDATE SKIP LOCKED`). Duas consequências
escolhidas: rodadas de trabalhos diferentes esperam a vez em vez de disputar
memória e DuckDB ao mesmo tempo; e a rodada que estava `rodando` quando o motor
caiu vira `falhou` ao subir, com o motivo escrito e o evento no histórico — antes
ficava "rodando" para sempre e travava a etapa.

**Quem cria a execução é o motor, e não o C# — diferente do plano.** O plano
dizia que o C# gravaria a execução pendente. Mas saber se há o que fazer
depende do que foi lido (há lote que a CAT lê? a conferência terminou e deixou
parquet?), e isso é do motor. O C# confere acesso e capacidade e chama
`POST /interno/execucoes`; o motor confere as condições, grava a fila e
responde o id. As recusas (409 já em curso, 422 trabalho parado ou nada a fazer)
chegam à tela com o texto dele.

**Planilha: o motor escreve, o C# entrega.** `POST /interno/planilhas` gera a
planilha dos parquets (ou reaproveita a do disco, se o parquet não mudou desde
então) e devolve o caminho. O C# serve o arquivo em fluxo, com suporte a
retomada, e só se o caminho estiver dentro da pasta de trabalho — um caminho de
fora vira 502 no log, não um arquivo servido. O prazo da chamada é de 60 min: a
planilha de dezenas de milhões de linhas é escrita inteira antes do primeiro
byte sair.

**Ensaiado de ponta a ponta com a pilha no ar**, base simulada (EFD com duas
notas, um XML): movimentos antes da conferência recusado com o texto certo;
conferência e movimentos pedidos pelo C#, rodados pelo trabalhador e concluídos;
as três planilhas da conferência baixadas em xlsx e em csv (com BOM), a de
movimentos só dos pendentes (filtro no nome do arquivo) e a de itens de novo
depois do reinício; formato desconhecido recusado; trabalho pausado recusado; uma rodada deixada em `rodando`
virou `falhou` ao reiniciar; o motor direto responde 404 às rotas antigas.
**Falta a rodada com base real no escritório** antes de ir para a `main`.

---

## 2026-09-13 — Lotes e remessa em C#, e o limite de 30 MB que a fundação tinha criado

**O que entrou.** Inspecionar a pasta de um lote, registrar, listar, remover, e
a análise da remessa do cadastro. O motor ficou só com o que lê disco, pelo
canal interno: `POST /interno/lotes/inspecionar` e `POST /interno/remessas/analisar`.
Do Python saíram `lote_router.py`, `importacao_router.py` e `excluir_trabalho.py`;
depois desta fatia, das rotas públicas o motor só atende conferência e
movimentos.

**Onde passa a linha.** Reconhecer arquivo, detectar cópia por hash, separar o
que é de outra empresa e escrever os avisos (cópia, retificadora, não baixado)
é leitura, e fica no motor — ele recebe só o id do trabalho e a pasta, e busca
sozinho a raiz do CNPJ e o que já foi importado, com os hashes. A API em C#
decide quem pode e aplica as regras de registrar: pasta só de cópias é 409 com
a mensagem de cópia (e não a genérica), pasta sem nada que a CAT leia é 422,
arquivo já no trabalho não entra de novo, e o período do lote é o do que a CAT
lê. Grava o lote, os arquivos e o evento no histórico.

**A tabela de tipos de arquivo existe dos dois lados, conferida.** O motor
reconhece o tipo; a tela precisa de rótulo, grupo e se alimenta a CAT, também
na listagem, que não passa pelo motor. A tabela em C# é conferida contra o enum
do Python de verdade: um tipo que alimentasse a CAT num lado e não no outro
faria a tela dizer que a base serve quando não serve.

**Um defeito meu, da fundação (v0.28.0).** O Kestrel recusa corpo acima de
30 MB por padrão, e a tela sobe a remessa do cadastro — "SPED de empresa grande
passa de um GB", diz o próprio código dela. Desde a fundação, uma remessa acima
de 30 MB era cortada no C#, e o repasse relatava **502, "o motor não
respondeu"**: a falha aparecia no lugar errado. Confirmado antes de corrigir:
1 MB passava, 40 MB dava 502. Agora a rota da remessa desliga o limite só para
ela e repassa o multipart em fluxo, sem montar o arquivo em memória; e o
repasse genérico responde 413 com texto claro quando é tamanho, em vez de culpar
o motor.

**Cada chamada ao motor tem o seu prazo**: apagar pasta, 5 minutos;
inspecionar, 30 (milhares de arquivos na rede); remessa, 60. Recusa com motivo do
motor (pasta que não existe, remessa sem SPED) chega à tela com o texto dele.

**Verificado com o motor real e base simulada**, com conta, empresa, trabalho
e pastas temporários apagados ao final: inspeção pelo C# achando utilidade,
outra empresa, cópia e retificadora com os três avisos; registro com
retificadora e hash gravados; recusas de pasta repetida (409), só cópia (409) e
inexistente (422, texto do motor); listar, remover e os dois eventos no
histórico; e **uma remessa real de 40 MB subindo pelo C# até o motor, com 200**.

**Falta a rodada com base real**, combinada para o escritório: pasta de rede em
`Z:`, milhares de arquivos (a maior medida tem 7.036), remessa acima de 1 GB. O
que ela prova e a simulação não: o prazo de 30 minutos da inspeção, a memória
do motor com a remessa grande (o motor ainda lê o arquivo inteiro, como antes),
e a gravação de milhares de arquivos de uma vez.

Baterias: C# 236 (91 de domínio, 23 de compatibilidade, 122 de API — com uma
remessa de 40 MB contra um motor falso); Python 420 (eram 427: saíram os de
registrar, listar e remover lote e o arquivo de remoção de lote; entraram os do
canal interno de lote e remessa).

---

## 2026-09-13 — Histórico em C#, com a linha do tempo escrita pelos dois lados

**O que entrou.** As seis rotas do histórico: ler a linha do tempo (paginada
por `antes_de`, com filtro de comentários), comentar, o catálogo de status,
mudar status, a lista de quem pode receber o trabalho e a sucessão. O domínio
veio junto: status com rótulo, explicação e exigência de motivo, validação do
comentário, as frases do sistema e os rótulos de cada tipo de evento.

**Desta vez metade ficou no motor, de propósito.** Registrar evento de lote e
de etapa e barrar etapa em trabalho parado (`exigir_que_ande`) são feitos pelas
próprias etapas, que moram no motor. O histórico passa a ser **escrito pelos
dois lados** na mesma tabela e no mesmo formato: o C# grava criação,
comentário, status e sucessão; o motor grava lote importado ou removido e etapa
iniciada, concluída ou falhou. Do Python saíram `historico_router.py`, a leitura,
o comentário, a mudança de status, a sucessão e as regras de tela do domínio;
ficaram `registrar`, `registrar_de_etapa`, `exigir_que_ande`, o status e o tipo
de evento.

**Um defeito corrigido: sucessão contava acesso encerrado.** Para decidir se
quem recebe o trabalho precisa de acesso à empresa, o Python contava qualquer
alocação, inclusive a encerrada. Quem teve o acesso retirado aparecia como quem
não precisa, a transferência não realocava, e a pessoa passava a responder por
um trabalho que não enxergava. Agora só conta alocação vigente, na lista de
sucessores e na transferência. Com teste dos dois casos.

**O escopo de empresa ganhou um lugar só em C#** (`Escopo.Exigir`), com o log
de acesso por exceção de dev que o `exigir_empresa` do Python tinha e que a
fatia 3 não trazia. Projetos, exclusão e histórico passam por ele.

**Verificado na pilha real**, com conta, analista, empresa e trabalho
temporários apagados ao final: lote importado **pelo motor**, comentário, pausa
e sucessão **pelo C#**, e a linha do tempo lida pelo C# com os seis eventos dos
dois lados na ordem em que aconteceram. Pausado pelo C#, o trabalho foi barrado
na conferência pelo motor; retomado, voltou a andar. A sucessão alocou a
analista na empresa, e o motor respondeu 404 às rotas migradas.

Baterias: C# 215 (84 de domínio, 22 de compatibilidade, 109 de API); Python 427
(eram 455: saíram 29 portados, entrou 1 guarda). O teste de integração do
histórico no motor ficou com o que é dele: pausado e cancelado não rodam etapa,
retomado e concluído rodam.

---

## 2026-09-13 — Empresas, projetos e exclusão em C#, e o canal interno com o motor

**O que entrou.** `GET/POST /api/empresas`, `GET /api/frentes`, `GET/POST
/api/projetos`, o detalhe com as etapas, a prévia e a exclusão de trabalho. O
domínio veio junto: CNPJ nos dois formatos (inclusive o alfanumérico da
Receita), as etapas da CAT 42 com a regra de bloqueio e o progresso, os rótulos
de status e de frente. Criar projeto grava o evento "criado" no mesmo formato
que o histórico em Python lê — o histórico é a fatia 4.

**A análise da remessa ficou no motor**: lê o arquivo enviado, e ler arquivo
fiscal é do motor. No Python, `importacao_router.py` ficou só com ela;
`excluir_trabalho.py` ficou só com remover lote (rota de lotes, fatia 5);
`dominio/cat42/etapas.py` e a capacidade `pode_excluir_trabalho` saíram.

**O canal interno nasceu aqui.** Apagar trabalho leva junto as pastas de
trabalho das execuções, e disco é do motor. `POST /interno/pastas/apagar`, no
motor, com três portas fechadas: só escuta em 127.0.0.1, `/interno` não entra no
repasse público do C#, e toda chamada traz `CAT_MOTOR_SEGREDO`. Sem o segredo
configurado o canal responde 503 — fechado, e não aberto.

**E o canal apaga menos do que o Python apagava.** O Python fazia `rmtree` no
caminho que estivesse gravado na execução, sem conferir. Agora só apaga o que
está **dentro** da pasta de trabalho; o que está fora, a própria raiz e caminho
com `..` voltam como recusados e ficam no log. Um valor torto no banco, ou uma
pasta de trabalho trocada no `.env`, não manda mais apagar outra coisa.

**Ordem da exclusão: senha, pastas, banco.** Se o motor não responder, a
resposta é 502 e **nada** foi apagado — a pessoa tenta de novo, em vez de sobrar
pasta sem dono. Trabalho sem execução não precisa do motor. Senha errada
continua sem contar tentativa de login.

**Duas diferenças deliberadas.**

1. **Criar projeto confere o escopo.** O Python só conferia se a pessoa podia
   escrever: um analista criava projeto em empresa que não enxergava — e em
   seguida não via o que acabara de criar. Agora é 403, como em todo acesso a
   empresa.
2. **A listagem de projetos deixou de fazer quatro consultas por projeto.** O
   cartão (base, última rodada de cada etapa, comentários) sai de poucas
   consultas para a lista inteira.

**O segredo chega às máquinas que já existem.** O `instalar.ps1` gera
`CAT_MOTOR_SEGREDO` em instalação nova e o acrescenta a um `.env` antigo que não
o tenha — ao contrário da pimenta, trocá-lo não invalida nada.

**Os testes do motor deixaram de usar as rotas migradas como preparação.** Oito
arquivos criavam empresa e projeto pela API; agora usam
`tests/integracao/cadastro.py`, que grava o mesmo que o C# grava. Onde
conferiam a etapa do projeto, conferem o **fato** de que ela depende (há base no
lote, a última conferência concluiu) — a regra de montar o roteiro tem teste em
C#, e recalcular no Python seria manter duas.

**Verificado na pilha real**, com conta temporária e empresa temporária,
apagadas ao final: cadastro de empresa e projeto pela tela, evento "criado"
lido pelo histórico do motor, etapas refletindo execuções gravadas, prévia,
senha errada com 403 sem tocar em nada, exclusão com a senha certa apagando a
pasta de trabalho real pelo motor e as linhas do banco, 404 do motor nas rotas
migradas, `/interno` com 404 pela porta pública e 403 sem segredo. Direto no
motor real: a pasta fora da raiz, a raiz e o caminho com `..` foram recusados e
preservados.

Baterias: C# 192 (74 de domínio, 22 de compatibilidade — agora com o dígito do
CNPJ cruzado em 300 casos, inclusive alfanuméricos —, 96 de API); Python 455
(eram 466: saíram 16 portados, entraram 5 do canal interno e das guardas).

---

## 2026-09-13 — Usuários e acesso em C#, e dois defeitos que a portagem achou

**O que entrou.** As 12 rotas de `/api/usuarios` (listar, criar, redefinir
senha, trocar a própria, papel, cargo, dados, situação, desbloquear, listar e
definir acesso a empresas) e os comandos `semear` e `emergencia`, agora em
`api/src/Cat.Ferramentas`. As regras vieram com as mesmas mensagens: política
de senha, nome de usuário e e-mail, senha provisória gerada pelo sistema com o
mesmo alfabeto sem caractere ambíguo, mínimo de três gestores ativos (dev não
conta), ninguém rebaixa nem desativa a si mesmo, ninguém tira o próprio acesso
a uma empresa, e alocação encerrada em vez de apagada.

**Tudo isso saiu do Python na mesma entrega**, pela razão da fatia 1: regra
viva em dois lugares diverge. Apagados `usuarios_router.py`,
`gerir_usuarios.py`, `alocar_em_empresas.py`, os dois comandos e as regras de
cadastro do domínio (`validar_*`, `gerar_senha_provisoria`, mínimo de
gestores). `test_usuarios_api.py`, `test_gerir_usuarios.py` e a parte de
política de `test_usuario.py` foram portados para C# e apagados; o teste de
histórico deixou de usar a rota de usuários como ferramenta. O motor ganhou um
teste que falha se `/api/usuarios` voltar a existir nele.

**Dois defeitos do Python, corrigidos de propósito, cada um com teste.**

1. **Senha atual errada na troca derrubava a sessão.** A rota respondia 401, e
   a tela entende 401 com token como sessão vencida: quem errava a senha atual
   na tela de troca era mandado para o login. Agora é **403**, o mesmo código
   que a confirmação de exclusão de trabalho já usa para senha errada — e
   justamente para não expulsar ninguém.
2. **Rebaixar um gestor inativo era recusado com exatamente três ativos.** A
   checagem descontava da contagem quem já não estava nela. `definir_situacao`
   olhava se o alvo estava ativo; `alterar_papel` não olhava. Agora os dois olham.

**Outras diferenças deliberadas.** Corpo JSON inválido ou campo fora do
formato dá 422 com texto em `detail` (o FastAPI mandava a própria lista de
erros, que a tela não lê). `semear` roda numa transação só: pela metade, o
banco ficaria com menos de três gestores e "já existe usuário" impediria semear
de novo. E as ferramentas não criam tabela: em banco sem esquema, mandam rodar
o Alembic.

**O instalador compila o C# antes de semear**, porque é por ele que os
gestores nascem agora. As migrações continuam no Alembic.

**Correção do que a fatia 1 registrou.** Ali ficou dito que o motor deixaria
de mexer em senha depois desta fatia. Não é exato: a exclusão de trabalho pede
a senha de confirmação e ela é conferida no motor — sai na fatia 3, junto das
rotas de projeto. Os testes do motor também seguem gerando resumo para montar
os próprios usuários.

**Verificado na pilha real**, pela porta da tela, com uma conta temporária de
manutenção criada pelo `criar-dev` em C# e apagada ao final: listagem e acesso
a empresas atendidos pelo C#, recusa de rebaixar a si mesmo, senha atual errada
com 403, o mesmo token aceito por uma rota do motor, e 404 do motor em
`/api/usuarios`. O `listar-gestores` em C# leu o banco real e mostrou os mesmos
três gestores que a versão Python mostrava.

Baterias: C# 152 (54 de domínio, 21 de compatibilidade, 77 de API e
ferramentas, com um banco vazio próprio para o `semear`); Python 466 (eram
527: saíram 62 de usuários e política, entrou 1).

---

## 2026-09-13 — Login em C#: provado nos dois sentidos, e o que ficou para trás

**O que entrou.** `POST /api/auth/token` e `GET /api/auth/eu` passam a ser
atendidos pela API em C#, com o domínio de acesso portado regra por regra
(bloqueio em 5, 15 minutos e 20; inativo antes de bloqueado; escopo pelas
alocações vigentes; papel desconhecido no banco rebaixa para leitura).

**A compatibilidade foi provada antes de qualquer rota.** Dois tipos de teste,
porque cada um prova só uma direção:

1. **Vetores gravados pelo Python** (`tests/Cat.Compatibilidade.Testes/vetores-python.json`):
   resumos Argon2id com e sem pimenta, com acento e emoji, com mais de 72
   bytes, um bcrypt legado, um Argon2 de parâmetros defasados e um token. O
   C# confere todos. Pimenta e segredo ali são de teste.
2. **Cruzamento ao vivo**: o C# gera o resumo e emite o token, e o código
   Python de verdade confere — e diz que **não** quer regravar. Se quisesse,
   cada login alternaria o resumo entre os dois lados para sempre.

O detalhe que decidia tudo: a pimenta entra por HMAC-SHA256, e o que vai ao
Argon2 é o **hexadecimal** do HMAC, não os bytes. Errar isso passa em todo
teste feito só de um lado.

**Ensaio na pilha real.** Com o motor Python **derrubado de propósito**, o
login, o `/auth/eu` e a recusa de senha funcionaram pela porta da tela — quem
respondeu foi o C#. Com o motor de volta, o token emitido pelo C# foi aceito
pelas rotas do Python, que aplicou a própria regra de permissão (papel
`leitura` recebeu 403 em `/api/usuarios`). Feito com um usuário temporário,
apagado ao final.

**O login saiu do Python na mesma entrega.** A primeira versão desta fatia
deixava `auth_router.py` e o caso de uso `autenticar.py` no motor, porque dez
arquivos de teste de integração obtinham token pela rota — e a regra de login
ficaria viva nos dois lados, com toda mudança precisando ir aos dois. Pesou
mais não ter duas regras: os dois arquivos foram apagados.

- Os testes do motor pegam o token por `tests/integracao/sessao.py`, que
  **confere a senha e o estado da conta antes de emitir**. Sem essa conferência,
  "a senha nova funciona" passaria com qualquer senha.
- O ciclo da senha provisória e o bloqueio por tentativas, que antes passavam
  pela rota de login, agora conferem o resumo e o estado gravados — que é o que
  o login em C# lê.
- `test_auth_api.py` e `test_autenticar.py` saíram. Os três cenários do
  segundo que a bateria em C# ainda não provava explicitamente vieram para
  ela (inativo recusado antes de conferir a senha, senha errada não regrava,
  resumo atual não é regravado). Saúde, identificador de requisição e senha
  irrecuperável do banco ficaram no motor, em `test_motor_api.py`, junto de um
  teste que falha se a rota de login voltar a existir nele.

O que o motor **ainda** faz com autenticação, e até quando: valida o token nas
rotas que atende (até cada uma migrar) e gera resumo de senha em criar, trocar e
redefinir senha e nos comandos `semear` e `emergencia` (até a fatia 2).

Baterias depois da remoção: 527 no Python (eram 547; saíram 24 de login e
entraram 4) e 84 no C#.

**Três diferenças deliberadas.**

- **Formulário incompleto dá 422 com texto em `detail`.** O FastAPI devolvia
  a própria lista de erros de validação, que a tela não lê: aparecia a
  mensagem genérica.
- **Segredo do token com menos de 32 bytes impede a API de subir.** A
  biblioteca recusa chave HS256 abaixo de 256 bits, e sem este aviso nenhum
  login funcionaria, com um erro que não diz o motivo. O instalador já gera 64
  caracteres.
- **A carga do token é escrita à mão**, sem descritor: o descritor acrescenta
  `nbf` e reordena campos. Igual ao Python é mais fácil de conferir do que
  equivalente.

**Testes em Postgres de verdade.** O banco `cat_testes_csharp` é recriado a
cada rodada e migrado pelo Alembic, no mesmo contêiner do desenvolvimento e
sem tocar em dado de trabalho. Os testes precisam do Docker de pé e do
ambiente Python instalado — a compatibilidade com o motor não se prova sem ele.
84 testes em C#: 29 de domínio, 21 de compatibilidade, 34 de API.

---

## 2026-09-13 — Fundação da API em C#: o que o repasse precisou saber

**O que entrou.** A API em C# (`api/`, .NET 10) sobe na 8010 e atende
`/api/saude`; todo o resto vai por repasse (YARP) ao motor Python, que passou
para `127.0.0.1:8020`. A tela não mudou uma linha: o proxy do Vite continua
apontando para a 8010. `subir.ps1` sobe os três processos e `instalar.ps1`
exige o .NET 10 e compila a API.

**Cinco detalhes que um repasse ingênuo erraria, cada um com teste.**

1. **O `X-Request-Id` volta para o pedido, não só para a resposta.** Só assim
   ele segue ao motor, que já reusa o que recebe: a linha de log do C# e a do
   Python saem com o mesmo `requisicao_id`.
2. **O `Origin` não segue para o motor.** O C# responde o CORS; se o cabeçalho
   seguisse, o FastAPI poria o próprio `Access-Control-Allow-Origin` e a
   resposta sairia com dois, que o navegador recusa.
3. **Trinta minutos sem atividade, não os 100 s padrão.** A planilha de dezenas
   de milhões de linhas é gerada antes do primeiro byte; o padrão cortaria o
   download que a entrega de 12/09 acabou de fazer funcionar.
4. **Motor fora do ar vira `{"detail": ...}` com 502.** O YARP devolve corpo
   vazio, e a tela mostraria só "erro".
5. **`127.0.0.1`, não `localhost`.** No Windows, `localhost` tenta `::1`
   primeiro, e o motor escuta só em IPv4: cada repasse pagaria a tentativa
   frustrada.

**A saúde ganhou dois campos.** `api`, para saber quem respondeu, e `motor`,
com situação e versão do Python. Versões diferentes nos dois lados é o sinal
de que um processo não foi reiniciado depois do `git pull` — o mesmo defeito
que já fez o `/api/saude` mentir uma vez, agora com dois lugares onde
acontecer. E a saúde da API não cai junto com a do motor: quem pergunta quer
saber justamente qual dos dois está fora.

**Um arquivo de segredos por máquina.** O C# lê o mesmo `backend/.env`, com a
mesma precedência do pydantic-settings (ambiente, arquivo, padrão). A pasta de
trabalho relativa resolve contra `backend/`, e não contra o diretório de onde o
processo subiu — que para o C# é outro.

**O `subir.ps1` recusa porta ocupada.** No ensaio, o processo-filho do
`--reload` do uvicorn herdou o socket da 8010 depois de o pai morrer, e a porta
seguiu ocupada sem dono aparente. Subir por cima faria a tela conversar com o
processo velho sem aviso nenhum.

**Log.** Mesmos campos do `cat/log.py` (`instante`, `nivel`, `origem`,
`mensagem`, `local`, contexto), com `local` vindo do arquivo e linha de quem
chamou. O ASP.NET e o YARP ficam em aviso para cima: narram cada requisição, e
a linha da API já diz o que importa.

**Verificado** com os três processos no ar, pela porta da tela: saúde com as
duas versões iguais, login recusado com `detail` e `X-Request-Id`, rotas
autenticadas atendidas pelo motor através do C#, 401 sem token, `/docs` e
`/openapi.json` pelo repasse. 15 testes no C#, com um motor falso em socket
real — o YARP usa o próprio cliente HTTP e não enxerga servidor em memória.

---

## 2026-09-13 — A API vai para C#; o motor pesado fica em Python

**O pedido.** Migrar o sistema para C#. Tudo que não for quebra de arquivo nem
automação passa a ser escrito em C#: API, endpoints, regras de acesso,
cadastros.

**A pergunta que o pedido deixava aberta.** Metade do backend não é "quebra"
nem "API": a leitura da EFD e dos XML que grava parquet, o confronto e a
conferência em DuckDB, a extração de movimentos e a geração das planilhas
grandes. De que lado isso fica decide o tamanho da migração inteira.

**Decisão.** Fica em Python, junto da quebra. A regra passa a ser:

| Vai para C# | Fica em Python (o "motor") |
|---|---|
| as rotas públicas da API, todas | quebra de SPED e automações |
| autenticação, token, senha | leitura de pasta, remessa, EFD e XML |
| usuários, acesso a empresa, salvaguardas | extração para parquet |
| empresas, projetos, histórico | confronto e conferência (DuckDB) |
| registro de lote e de execução | extração de movimentos |
| acompanhar execução e servir o download | geração das planilhas xlsx/csv |

O critério de corte é um só: **o que lê arquivo fiscal ou atravessa volume é
motor; o que conversa com a pessoa é API.**

**Por quê, e não "tudo em C#".**

1. **É o código mais caro de acertar, e já está acertado.** O confronto passou
   por uma sequência de correções que só apareceu em base real: filtrar antes
   de agrupar, derramar em disco em vez de morrer, um plano que cabe em 4 GB,
   XML de fornecedor, SPED retificador. Validado em 400 milhões de linhas e
   numa rodada de 884 EFD. Reescrever isso não entrega nada novo à pessoa que
   usa e reabre cada um desses defeitos.
2. **O ecossistema é melhor do lado de lá.** DuckDB, pyarrow e xlsxwriter em
   memória constante são o que o volume pede. Em .NET existem equivalentes,
   mas nenhum com a mesma maturidade para parquet e para planilha de milhões
   de linhas sem carregar tudo em memória.
3. **É a mesma natureza do que já ficou em Python por pedido do dono.** Quebra
   de arquivo e leitura de arquivo são o mesmo trabalho: fluxo, disco, volume.
   Separar os dois poria a leitura da EFD num lado e o índice por offset dela
   no outro.

**Como os dois convivem.**

- **O front fala só com o C#.** O Python perde a porta pública.
- **Pedido demorado passa pelo banco, não por chamada.** O C# grava a linha em
  `execucao` como pendente; o motor pega a linha, trabalha e grava progresso e
  conclusão. É o contrato que a ARQUITETURA §5 já previa, e é exatamente a
  troca que `infraestrutura/tarefas.py` anunciava: "o dia da migração troca
  este arquivo e mais nada". Sem Redis, sem Celery.
- **Pedido rápido que lê disco é chamada interna.** Inspecionar pasta, analisar
  remessa e gerar planilha respondem na hora; o C# chama o motor em
  `localhost`, e o motor não aceita conexão de fora.
- **Um banco, um dono do esquema.** O Alembic continua sendo o único a criar e
  alterar tabela. O C# mapeia as tabelas que existem e não gera migração. Dois
  donos do mesmo esquema divergem em silêncio.
- **Senha e token são intercambiáveis.** O C# confere o mesmo Argon2id com a
  mesma pimenta e emite o mesmo JWT com o mesmo segredo. Um token emitido de
  um lado vale do outro, o que deixa migrar rota por rota sem derrubar sessão.

**Como migra.** Por substituição gradual: o C# nasce na frente de tudo,
repassando ao Python o que ainda não foi portado, e cada rota migrada sai do
repasse. O front não muda. Plano, ordem e critério de pronto em
`MIGRACAO_CSHARP.md`.

**O que isto não decide.** Se um dia o motor for para C#. A fronteira fica
num contrato — tabela `execucao` e três chamadas internas — justamente para
essa troca, se vier, não arrastar a API junto.

---

## 2026-09-12 — Baixar escolhendo a pasta, e cancelar o que carrega

**Decisão.** Três coisas, que vieram juntas porque uma depende da outra.

**1. A pessoa escolhe onde salvar.** O download abre o "salvar como" do
navegador (`showSaveFilePicker`) em vez de despejar na pasta de downloads.
Pedido de quem tem pouco espaço em disco: encher a pasta padrão sem escolha e
depois ter de mover o arquivo.

**2. O arquivo não passa mais pela memória.** O jeito antigo fazia
`await r.blob()` — o download inteiro em memória antes de um byte chegar ao
disco. A lista analítica de uma base real tem 37,9 milhões de documentos, um
CSV de vários GB: a aba morre antes de salvar. Com o seletor dá para canalizar
a resposta direto para o arquivo, e a memória deixa de depender do tamanho.

Isto **não é um bônus do item 1, é o motivo de ele funcionar**. Sem o
destino em disco não há para onde canalizar, e sem canalizar o item 1 seria
só cosmético num arquivo que nunca caberia.

**3. Cancelar virou padrão.** `useAcao`, em `hooks/`, é o padrão da casa para
qualquer ação que carrega: estado do botão, erro e cancelamento num lugar só.
O botão que está carregando vira "Cancelar" — mesmo lugar, onde a pessoa já
está olhando.

**Duas regras que o padrão carrega.**

*O Cancelar só aparece depois de 400 ms.* Ação que acaba em 200 ms faria o
botão piscar, e botão que pisca ninguém acerta — só faz a tela tremer.

*Cancelar é de verdade ou não existe.* Onde abortar desfaz o trabalho, há
Cancelar: os sete downloads e o envio do SPED, que é análise e não grava nada.
Onde o servidor já concluiu — criar empresa, criar usuário, comentar — **não
há Cancelar**, porque um botão que diz ter cancelado a criação de um usuário
que foi criado é pior do que não ter botão.

**O que o cancelamento não alcança.** A planilha é gerada no servidor antes do
primeiro byte sair. Cancelar solta o navegador na hora, mas a geração segue até
o fim do outro lado. Não é trabalho perdido: o arquivo fica em cache na pasta
da execução e o próximo pedido responde na hora. Parar a geração no servidor é
outra coisa, e precisaria de cancelamento de execução, que não existe.

**Onde o seletor não existe** — Firefox, Safari, página fora de contexto
seguro — cai no caminho antigo, com a pasta padrão do navegador e o arquivo
em memória. Continua funcionando; só não escolhe pasta.

---

## 2026-09-12 — CSV ao lado do xlsx, nas sete listas

**Decisão.** O gerador de planilha passou a receber `formato`, e cada lista
ganhou um botão CSV ao lado do botão de planilha.

**Por quê.** Duas coisas que o xlsx não faz.

Ele tem teto: o Excel para pouco acima de um milhão de linhas por aba, e o
gerador já quebrava em abas de 900 mil para não estourar em silêncio. A lista
analítica de uma base real desta casa tem 37,9 milhões de documentos, o que
daria 43 abas — um arquivo que ninguém abre. CSV não tem limite nem aba.

E ele é formato de leitura, não de carga. Quem vai levar a lista para o DuckDB,
o Power BI ou o sistema do cliente precisa de CSV, e estava exportando à mão.

**Onde mora.** No mesmo `gerar` que as sete listas já usavam, e não num módulo
à parte. O filtro por modelo e por classificação é o que decide o que entra na
cobrança: dois caminhos de filtro dariam, um dia, dois totais para a mesma
lista. Aqui o filtro é um só e o formato é o último passo.

**O que o CSV não faz.** Não altera valor para agradar o Excel. A chave de
acesso sai com os 44 dígitos que tem. Abrir esse CSV com dois cliques no Excel
transforma a chave em notação científica e não há volta — é exatamente o
defeito que passamos esta manhã diagnosticando no relatório de um cliente.
Fingir tipo resolveria o Excel e quebraria DuckDB, Power BI e banco, que são
justamente para quem o CSV existe. Quem precisa do Excel tem o xlsx ao lado,
que é imune; o botão diz isso ao passar o mouse.

**Consequência.** `?formato=` nas duas rotas de download, com 404 para valor
desconhecido, e o formato entrando no nome do arquivo em cache — sem isso o
xlsx já gerado responderia ao pedido de csv.

---

## 2026-09-12 — Linha sem chave: três motivos, e só um é problema de leitura

**Decisão.** O aviso de "linha sem chave de acesso válida" foi partido em três,
pelo que a linha de fato tem, e o que não é erro saiu do bloco de erro.

| A linha tem | É | Vai para |
|---|---|---|
| algo na coluna que não são 44 dígitos | chave ilegível, aí sim costuma ser o Excel | `recusados` |
| chave vazia, mas número de documento | nota sem chave, não dá para cruzar | `recusados` |
| nem chave nem número | movimentação interna, nunca teve nota | `observacoes` |

**Por quê.** A mensagem antiga chutava uma causa só para os três casos, e
chutava a mais rara: "costuma ser chave que o Excel converteu em número".

Medido nos relatórios da empresa 19, três arquivos de 2020.01, 670.156 linhas:

| | |
|---|---|
| Linhas sem chave | 1.270 (0,190%) |
| Com a coluna vazia | 1.270 (100%) |
| Estragadas pelo Excel | 0 |
| Sem número de documento | 1.205 |
| ST que carregam | R$ 0,00 |
| ST do arquivo inteiro | R$ 9.482.165,30 |

Ou seja: nenhuma era o caso que a mensagem citava, e 95% delas nem documento
eram — CFOP 1.949, movimentação interna das centrais de Reciclável, Açougue,
Padaria e Confeitaria. Sobram 65 linhas, 42 notas, todas sem ST.

**Consequência.** Nos mesmos arquivos, o bloco "Arquivos com problema na
leitura" saiu de 3 alarmes para 1, e esse 1 é achado de verdade: 65 linhas de
documento identificado sem chave. O resto aparece como informação, no tom
`info`, porque quem confere quer saber o que ficou de fora sem ser avisado de
um erro que não houve.

O motivo de fazer isso, e não só reescrever a frase: aviso que grita onde não
há problema treina quem lê a ignorá-lo. Eram 21 linhas de alarme por remessa,
e o dia em que um arquivo não abrir de verdade a mensagem vai estar no meio
delas.

**Contrato.** `observacoes` é campo novo no resumo da conferência e no de
movimentação. Opcional no front, porque execução gravada antes desta versão
não o tem.

---

## 2026-09-12 — Gestor enxerga toda a carteira, sem alocação

**Decisão.** `Papel.ignora_escopo_de_empresa` passa a valer para **gestor** além
de dev. O escopo por empresa continua valendo para analista, revisor e leitura.

**Por quê.** Três razões, e a primeira é a que dói.

No banco de verdade, **dois dos três gestores não enxergavam empresa alguma**.
Entravam no sistema e viam uma lista vazia, porque a alocação só nascia de um
jeito: quem cadastra a empresa pelo SPED fica alocado nela. Exigir que alguém
alocasse cada gestor em cada empresa nova era trabalho que ninguém ia fazer — e
não fez.

Segundo, a regra era incoerente com o que o papel já podia. Gestor administra
usuários, apaga um trabalho inteiro e passa trabalho de uma pessoa para outra.
Negar-lhe a leitura de uma empresa não protegia nada: bastava se alocar.

Terceiro, gestor aqui é diretor, gerente e coordenador. Quem coordena responde
pela carteira inteira; "sobre quem eu trabalho" é um recorte de quem executa.

**Consequência.** `acessa_por_excecao` ficou só do dev. Marcar o gestor como
exceção encheria o log a cada requisição e afogaria o sinal do que é mesmo
excepcional — que é justamente o bypass de manutenção.

A tela de alocação continua, para quem executa. Para gestor e dev ela mostra um
aviso de que não muda nada, e o botão vermelho de "sem acesso a empresa nenhuma"
não aparece mais para eles: a contagem zero não quer dizer nada nesses papéis.
O front espelha a regra num lugar só, `IGNORA_ESCOPO_DE_EMPRESA` em
`constants/roles.ts`, porque três telas precisavam dela.

**De quebra.** Os dois testes da salvaguarda do mínimo de gestores quebraram com
essa mudança, e não deviam: eles contavam o banco inteiro, que a bateria de
integração compartilha, e passavam só porque nenhum outro módulo semeava gestor.
O módulo de histórico passou a semear um, a contagem virou quatro, rebaixar
passou a ser permitido. Agora o teste constrói a própria premissa — deixa
exatamente o mínimo ativo, prova a recusa, e devolve os outros.

---

## 2026-09-09 — Python com DuckDB como base, não outra linguagem

**Decisão.** Python para leitura e varredura, DuckDB para agregação, xlsxwriter
para planilha.

**Por quê.** Medição, não preferência. A mesma varredura de 119,82 GB e
400.381.153 linhas levou 711 segundos quebrando toda linha e 293 segundos
filtrando por bytes. Mesma linguagem, 2,4 vezes de diferença. No segundo caso o
processo já rodava na velocidade do descompactador, então o teto deixou de ser a
linguagem. Reescrever em Rust ou Go daria ganho perto de zero e jogaria fora o
ecossistema e os projetos que já existem.

**Consequência.** Rust e Go só voltam à mesa se um perfil mostrar gargalo de CPU
em parsing, o que hoje não existe.

---

## 2026-09-09 — Front em React, saindo do Streamlit

**Decisão.** React com TypeScript, falando só por API com o FastAPI.

**Por quê.** O Streamlit reexecuta o script a cada interação. Isso não sustenta
tabela de 1,28 milhão de linhas, processo de onze minutos, múltiplos usuários com
separação por cliente, nem tela com regra visual própria.

**O ponto que importa mais que o framework.** O erro a evitar não é usar
Streamlit, é deixar regra de negócio dentro da tela. Com a lógica num pacote e
API por cima, o front vira detalhe substituível.

---

## 2026-09-09 — Postgres desde o início, não SQLite

**Decisão.** Postgres, com segurança em nível de linha nas tabelas fiscais.

**Por quê.** Usuário, papel, vínculo com cliente, auditoria e execução exigem
transação e concorrência real. O reenquadrador usa SQLite e funciona para o
escopo dele, mas não escala para vários analistas em processos longos
simultâneos.

---

## 2026-09-09 — Log obrigatório em todo código

**Decisão.** Nenhum código entra sem log estruturado. Detalhe em ARQUITETURA.md,
seção 12.

**Por quê.** Pedido do dono do produto. Os processos são longos e sobre arquivos
enormes; quando falha, não dá para reproduzir observando. A informação precisa
estar gravada na primeira execução.

---

## 2026-09-09 — Módulo por frente, nunca por cliente

**Decisão.** `cat42`, `depara`, `sped`, `notafiscal`. Cliente é dado.

**Por quê.** Já são quatro empresas e vão entrar mais. Se cliente virar pasta de
código, cada empresa nova custa desenvolvimento em vez de cadastro.

---

## 2026-09-09 — Reaproveitar estrutura do reenquadrador, nunca o conteúdo

**Decisão.** Extrair `MotorClassTrib`, `MotorRegras` e `PreProcessadorTexto` para
uso comum. A base de conhecimento tributária **não** é reaproveitada.

**Por quê.** A mecânica de hierarquia de prefixo de NCM, exceção com escopo e
escala de confiança já passou por produção e levaria meses para reinventar. Mas o
conteúdo é de PIS e COFINS e não vale para ICMS-ST. Misturar os dois produziria
enquadramento errado com aparência de fundamentado.

---

## 2026-09-09 — De-para com cascata determinística antes do modelo

**Decisão.** Casar por código de barras, depois por NCM com CEST e descrição
normalizada, depois por descrição, e só então similaridade textual. O modelo
recebe candidatas, nunca a pergunta em aberto.

**Por quê.** Medição na empresa 17: 24.730 itens distintos, 98,1% com código de barras,
100% com NCM e CEST, e **zero** códigos com barras divergente entre as 21
filiais. Onde existe chave exata, usar similaridade é trocar certeza por
probabilidade.

**Duas armadilhas registradas na mesma data.** Primeira: "código de barras sem
par" não é fila de IA; se o código não existe do outro lado, não há decisão a
tomar e pedir decisão induz invenção. Segunda: no escore de similaridade o
denominador tem de somar o peso de **todos** os termos da consulta, usando peso
máximo para termo ausente do outro catálogo. Sem isso, um cigarro casou com uma
cerveja com escore 1,00 porque a única palavra em comum era "orange".

---

## 2026-09-09 — Gerar em disco local e copiar depois

**Decisão.** Nenhuma escrita longa direto em unidade de rede. Gerar local,
copiar, conferir hash.

**Por quê.** Histórico de gravações perdidas, agora explicado: o drive Y está em
100% de uso, com 36 GB livres de 3,7 TB. Não era instabilidade de rede.

---

## 2026-09-09 — Parquet como formato de trabalho, CSV só para entrega

**Decisão.** Entre etapas, parquet. CSV e xlsx só no que vai ao cliente.

**Por quê.** Menor, tipado, e o DuckDB lê muito mais rápido. Um extrato de 470 MB
em CSV é lento de reler a cada análise.

---

## 2026-09-10 — Senha com Argon2id, não com criptografia

**Decisão.** Senha protegida por resumo de mão única com Argon2id, sal por senha
e pimenta opcional. Nunca criptografia.

**Por quê.** Criptografia é reversível: quem tem a chave recupera o valor
original. Guardar senha assim significa que um administrador de banco, um backup
vazado ou um invasor com a chave recuperaria a senha em claro de todos os
usuários. Como as pessoas reaproveitam senha, o estrago passaria deste sistema
para os outros acessos delas. **O sistema não pode ser capaz de descobrir a senha
de ninguém.**

Argon2id é o vencedor da Password Hashing Competition e a recomendação atual da
OWASP. É caro em memória, não só em tempo, o que tira a vantagem de quem ataca
com placa de vídeo — exatamente onde o bcrypt fica atrás. Custa cerca de 50 ms
por conferência, imperceptível para quem entra e caro para quem tenta milhões de
combinações.

**Três camadas.** Sal aleatório por senha, para que duas pessoas com a mesma
senha tenham resumos diferentes. Pimenta em `CAT_SENHA_PIMENTA`, segredo do
servidor guardado fora do banco. E reprocessamento transparente no login, que
regrava resumo em formato antigo sem pedir troca de senha a ninguém.

**Onde criptografia é a ferramenta certa**, e aí sim deve ser usada: no tráfego,
com HTTPS obrigatório; no disco, cifrando o volume do banco e os backups; e no
segredo do token, que é chave de verdade.

---

## 2026-09-10 — Migração de algoritmo sem forçar troca de senha

**Decisão.** Ao entrar, se o resumo estiver em formato antigo ou com parâmetros
defasados, ele é regravado no formato atual.

**Por quê.** O login é a única janela em que a senha em claro está em mãos, e
portanto a única oportunidade de regravar. Sem isso, endurecer parâmetros no
futuro obrigaria a redefinir a senha de toda a base, o que é caro e gera
chamado de suporte. Com isso, a migração acontece sozinha conforme as pessoas
usam o sistema.

---

## 2026-09-10 — Gestão de usuários só na mão dos gestores

**Decisão.** Não há autocadastro nem redefinição de senha por e-mail. Cadastrar,
redefinir, alterar papel e desbloquear são atos de gestor.

**Por quê.** O sistema roda na rede interna, a base de usuários é fechada e
conceder acesso a dado fiscal de cliente precisa ser ato deliberado de quem
responde pela equipe. Redefinição por e-mail seria pior aqui: moveria a
confiança para a caixa de e-mail, muitas vezes menos protegida que o próprio
sistema, e exigiria servidor de envio para um evento raro.

**As três salvaguardas que esse modelo exige**, sem as quais ele vira ponto
único de falha:

1. **Mínimo de três gestores ativos**, que são direção, gerência e coordenação.
   O sistema recusa rebaixar ou desativar quem deixaria a conta abaixo disso, e
   ninguém se rebaixa ou se desativa. É regra de domínio, não de tela, para valer
   também na API.
2. **A redefinição gera senha provisória de uso único**, com troca obrigatória no
   primeiro acesso. O gestor nunca escolhe a senha de ninguém: se escolhesse,
   passaria a saber a senha da pessoa e o resumo de mão única perderia sentido.
3. **Saída de emergência por linha de comando no servidor**
   (`cat.apresentacao.cli.emergencia`), capaz de promover, redefinir e
   desbloquear. Exigir acesso ao sistema de arquivos é um segundo fator razoável
   num sistema interno e não depende de ninguém estar disponível.

---

## 2026-09-10 — Bloqueio em dois níveis

**Decisão.** Cinco erros bloqueiam por quinze minutos, e a espera se resolve
sozinha. Vinte erros bloqueiam de vez e exigem gestor.

**Por quê.** Destravar é muito mais frequente que redefinir senha. Bloqueio
permanente logo no quinto erro geraria chamado toda semana sem ganho de
segurança: quinze minutos de espera já inviabilizam tentativa por força bruta.

---

## 2026-09-10 — Cargo é diferente de papel

**Decisão.** `Papel` define permissão. `Cargo` é posição na empresa, informação
organizacional.

**Por quê.** São eixos independentes e fundi-los engessa. Um diretor pode ter
papel de leitura num período; um analista pode ser gestor do sistema. Já existe
um terceiro eixo, a alocação, que diz sobre quais empresas a pessoa enxerga.

---

## 2026-09-10 — Postgres de verdade, com migrações versionadas

**Decisão.** O banco do sistema passa a ser Postgres, em contêiner na porta
55432, com Alembic para migrações. SQLite fica só na bateria de testes.

**Por quê.** Dois motivos concretos do mesmo dia. Primeiro, um erro de fuso
horário: o SQLite não guarda fuso e devolve data ingênua, o que quebrou o
bloqueio temporário. O Postgres usa `timestamp with time zone` e não tem esse
problema. Segundo, acrescentamos três colunas sem ter ferramenta de migração, e
`create_all` não altera tabela existente — em produção isso viraria SQL na mão.

**Duas consequências.** A aplicação **não cria mais tabela**: na subida ela
apenas confere e avisa se faltar, com o comando que resolve. E os testes
continuam em SQLite de propósito: sem fuso horário, é o ambiente mais severo
para essa parte, e protege contra regressão daquele mesmo erro.

**Porta 55432 e não 5432.** Esta máquina já tem Postgres local nas portas 5432 e
5433. Não mexemos neles.

---

## 2026-09-10 — Papel DEV, com bypass do escopo de empresa auditável

**Decisão.** Existe um papel `dev` acima de gestor. Ele administra usuários e
**ignora o escopo de empresa**: enxerga qualquer cliente, com ou sem alocação.

**Por quê.** Manutenção precisa reproduzir problema em qualquer cliente. Alocar
o dev em cada empresa nova na mão seria esquecido na primeira semana, e aí a
investigação de um incidente pararia para pedir alocação a um gestor.

**O preço, cobrado explicitamente.** Todo acesso que só passou por ser dev é
registrado como exceção, com `sem_alocacao: true`. O bypass existe, mas nunca
vira rotina invisível no meio do tráfego normal.

**DEV não conta para o mínimo de gestores.** Conta técnica não substitui
responsável pelo negócio. Se contasse, dois gestores mais um dev pareceriam três
e a salvaguarda estaria furada.

**Só nasce pela linha de comando** (`emergencia criar-dev`). Conta que ignora
escopo de confidencialidade não deve nascer por clique na tela.

---

## 2026-09-10 — Rota exige capacidade, nunca papel

**Decisão.** As rotas perguntam por uma **capacidade** do domínio, como
`administra_usuarios`, em vez de enumerar papéis.

**Por quê.** Descoberto ao criar o papel dev: a rota listava `Papel.GESTOR`
explicitamente, então o dev entrou no sistema com todo o poder no domínio e
levou 403 na porta. Enumerar papel em rota significa que todo papel novo obriga
a caçar rotas para atualizar, e a que for esquecida vira bug silencioso de
permissão. Com capacidade, o domínio continua sendo a única fonte de quem pode
o quê.

---

## 2026-09-10 — Todo botão declara o `type`

**Decisão.** Nenhum `<button>` sem `type` explícito.

**Por quê.** Descoberto testando a troca de senha. Sem `type`, o navegador
assume `submit` quando o botão está dentro de `<form>`. Isso é frouxo em dois
sentidos: um botão de ação dentro de formulário passa a enviar o formulário sem
querer, e um seletor por `[type=submit]` não encontra o botão que de fato envia,
o que fez o teste automatizado falhar sem apontar a causa.

---

## 2026-09-10 — Cores corrigidas a partir dos arquivos oficiais

**Decisão.** A paleta vem dos arquivos oficiais da marca, não de captura de
tela. Marinho `#021D44` e laranja `#FF7F00`.

**Por quê.** Os primeiros valores saíram de uma captura de tela comprimida e
estavam deslocados. O marinho errou pouco (`#081C41`), mas o laranja errou
bastante: `#EE8633` contra o real `#FF7F00`, um tom visivelmente mais apagado.
Compressão de imagem desloca cor, e captura de tela nunca serve como fonte de
paleta.

**Consequência.** A escala derivada do laranja foi recalculada. O mínimo para
texto sobre fundo claro subiu de `#B85E18` para `#B35400`, porque o tom oficial
é mais claro e precisa escurecer mais para passar em contraste.

---

## 2026-09-10 — Importação lê só o cabeçalho, e não grava arquivo

**Decisão.** A tela de importação lê apenas a primeira linha de cada arquivo, e
nada é gravado em disco nesta etapa.

**Por quê.** O registro 0000 já traz razão social, CNPJ, UF, IE e competência —
tudo que o pré-cadastro precisa. Uma remessa real desta casa tem 7.036 arquivos;
ler o conteúdo levaria minutos para responder o que a primeira linha responde em
segundos. E guardar gigabytes antes de o usuário confirmar seria desperdício.

**Medido:** 180 arquivos analisados em 0,02 s.

---

## 2026-09-10 — XML vence o SPED no valor de ST

**Decisão.** Quando as duas fontes divergirem no ICMS-ST da mesma nota, vale o
XML. O SPED serve de conferência.

**Por quê.** Decisão do dono do produto, e coerente com o fato de o XML ser o
documento fiscal. Reforçada por evidência: no maior arquivo de EFD ICMS/IPI que
examinamos, com 16.862 itens de documento, **nenhum** trazia valor de ICMS-ST.
Numa distribuidora que compra de substituído e transfere entre filiais, o ST não
está na nota de entrada — está no XML, em `vICMSSubstituto` ou no campo de
informação adicional que a própria CAT 42 define.

---

## 2026-09-10 — Relatório gerencial é lido por descoberta, não por cadastro

**Decisão.** O sistema descobre o leiaute do relatório gerencial do próprio
arquivo — separador, codificação, onde começa o cabeçalho e quantos níveis ele
tem — e casa as colunas por **nome**, contra um catálogo fixo de campos-alvo.
Não existe cadastro de formato por empresa.

**Por quê.** Muitas empresas não liberam o XML, só o relatório do ERP delas, e
o formato muda de empresa para empresa e de um ano para o outro na mesma
empresa. Cadastro de formato por cliente envelhece e ninguém mantém: o
trabalho pararia sempre que o ERP mudasse uma coluna de lugar. O que não muda
é **o que o trabalho precisa** — data, item, quantidade, CFOP, ICMS, ST. Então
o que é fixo é a lista de campos, e o que é flexível é onde encontrá-los.

**Medido.** 135 relatórios reais da empresa 19: 133 lidos (99 de movimento, 20 de
resumo, 14 de inventário). Os 2 que sobraram não são relatório — um é de-para
de fornecedor, outro é log de erro, e o sistema recusa os dois dizendo o que
faltou. Um arquivo de 194 MB e 191.691 linhas lê em 6 segundos.

**Consequência.** O casamento resolve **toda** correspondência exata antes de
qualquer parcial. Se fosse campo a campo, `Valor` (do valor do item) levaria a
coluna `Valor ICMS` só por vir antes no catálogo.

---

## 2026-09-10 — "Relatório gerencial" são três espécies, não um formato

**Decisão.** A pasta de relatório gerencial de uma empresa traz espécies
diferentes de arquivo — movimento por documento, inventário e resumo por
produto — e cada uma tem seu catálogo e seus campos obrigatórios. A espécie é
descoberta pelo que as colunas dizem, não pelo nome do arquivo nem por prefixo
de ERP, e ganha a espécie mais exigente que fecha.

**Por quê.** Ler as três com o mesmo catálogo reprova arquivo bom por falta de
campo que aquela espécie nunca teve — foi o que aconteceu na primeira versão.
O desempate pela mais exigente também é necessário: o resumo por produto tem
uma coluna `Qtde Perdas Estoque`, que casa com o `estoque` que o inventário
exige, e cairia como inventário.

**Consequência.** Só o movimento alimenta o razão da Ficha 3 — é o único que
tem data e CFOP por linha. O inventário serve de estoque de abertura (item
4.1.1) e o resumo serve de conferência de totais.

---

## 2026-09-10 — Campo em branco e valor corrompido são contados em separado

**Decisão.** Linha com campo obrigatório vazio é **incompleta**: conta, aparece
no log e segue. Linha cujo valor não converte é **inválida**, e passar de 5%
delas aborta a leitura do arquivo.

**Por quê.** As duas coisas parecem a mesma e não são. Relatório de ERP vem
cheio de linha sem CFOP — na empresa 19 o campo vem escrito `'  .      '`, e são
milhares. Isso é dado incompleto, normal. Já valor que não converte é sintoma
de coluna mapeada errada, e seguir em frente aí produz uma apuração inteira em
cima de coluna trocada — número plausível e errado, que é o pior defeito
possível num trabalho fiscal. Na primeira versão as duas caíam no mesmo
contador e o CFOP em branco abortava a leitura de arquivos perfeitos.

**Consequência.** A proporção só passa a valer depois de 500 linhas lidas. Num
arquivo pequeno, ou nas primeiras linhas de um grande, um punhado de registros
ruins seguidos estoura qualquer proporção sem que haja nada de errado.

---

## 2026-09-10 — Cadastro e entrada de dados são telas separadas

**Decisão.** Dois caminhos distintos, com telas, rotas e tabelas próprias:

| | Cadastro (`/importar`) | Base de dados (`/projetos/:id/arquivos`) |
|---|---|---|
| o que faz | cria empresa e projeto | alimenta um projeto que já existe |
| entrada | envio de uma amostra do SPED | caminho de uma pasta |
| quantas vezes | uma por trabalho | quantas a empresa mandar arquivo |
| grava | empresa, estabelecimento, projeto | lote e arquivos do lote |

**Por quê.** Estavam colapsados, e o link "Importar mais arquivos" de dentro do
projeto levava de volta ao cadastro — que recomeçaria a criação da empresa.
Redundância que produzia trabalho duplicado, apontada pelo dono do produto.

**Consequência.** A etapa "Importar base de dados" só conclui quando existe
lote com arquivo que a CAT lê. Antes concluía por existir o projeto, o que
dizia ao usuário que havia base quando não havia.

---

## 2026-09-10 — O lote aponta para uma pasta; não sobe arquivo

**Decisão.** A entrada de dados recebe o **caminho** de uma pasta de rede. O
conteúdo não é copiado para dentro do sistema: guarda-se onde cada arquivo
está e o que ele é.

**Por quê.** Medido nas bases desta casa: a pasta de EFD ICMS/IPI da
empresa 12 tem **7.036 arquivos e 100 GB**; a de relatórios da empresa 19 tem
**53,9 GB**. Subir isso pelo navegador não é lento, é inviável. E o dado já
vive no servidor de arquivos, com a política de guarda da casa — duplicá-lo
dentro do sistema só multiplicaria material sigiloso.

**Consequência 1.** A varredura é paralela: identificar arquivo em disco de
rede é espera, não cálculo. Na pasta da empresa 19, 325 arquivos caíram de **49 s
para 1,2 s**. O tamanho vem da própria listagem do diretório, o que poupa uma
ida à rede por arquivo.

**Consequência 2.** Fica a conta a pagar: a pasta de 7.036 SPED leva **~5
minutos na primeira varredura** e ~50 s depois, com o cache do Windows quente.
Se isso incomodar no uso, o passo seguinte é rodar a varredura como tarefa de
fundo com progresso, em vez de segurar a requisição.

**Consequência 3.** O servidor passa a ler caminho que o cliente informa.
Enquanto o sistema roda na máquina de quem trabalha, isso é o próprio disco do
usuário. Existe `CAT_PASTAS_PERMITIDAS` para fechar as origens, e ela **precisa
estar preenchida** no dia em que o sistema virar servidor compartilhado.

---

## 2026-09-10 — Arquivo de outra empresa é barrado sem perguntar

**Decisão.** Ao ler uma pasta, todo arquivo cuja raiz de CNPJ não bate com a do
projeto fica de fora. O usuário é informado, não consultado.

**Por quê.** Pasta de rede é compartilhada e mistura cliente. Arquivo de uma
empresa entrar no trabalho de outra contamina a apuração das duas de uma vez —
é o acidente mais caro que este sistema pode causar. Pedir confirmação seria
transferir para o usuário uma checagem que a máquina faz melhor.

**Exceção deliberada.** Relatório gerencial não traz CNPJ: quem o produziu foi
o ERP da própria empresa, e ele não se identifica. Sem CNPJ, o arquivo passa —
chutar que é de outra empresa deixaria de fora justamente a fonte de quem não
libera XML.

---

## 2026-09-10 — Conferência de documentos: o confronto é pela chave de acesso

**Decisão.** A primeira análise do trabalho cruza o que a EFD escriturou
(**C100** e **C800**) com o documento que o cliente entregou (XML ou relatório
gerencial). O casamento é pela **chave de acesso** de 44 dígitos.

**Por quê.** A chave é única por documento e existe nos quatro lugares:
`CHV_NFE` no C100, `CHV_CFE` no C800, o atributo `Id` no XML e a coluna
`Chave DFe` no relatório do ERP. Casar por número e série seria frágil — série
se repete entre estabelecimentos e número reinicia.

**Consequência.** Documento sem chave fica fora do confronto, e isso é
deliberado: nota modelo 1 e cupom antigo não têm chave, e tratá-los como
pendência mandaria o cliente atrás de algo que nunca existiu. Numa amostra
real, 124 de 321.464 documentos.

**Os dois destinos.** A diferença não é uma lista só; são duas, com destinos
opostos:

| | O que é | O que se faz |
|---|---|---|
| Não escriturada | está na pasta, não está na EFD | sai da análise |
| Sem documento | está na EFD, o documento não veio | cobra-se do cliente |

Nota não escriturada não compõe apuração: ressarcimento se pede sobre o que foi
declarado ao fisco, e incluir o que não foi declarado é construir crédito em
cima de documento que a SEFAZ não vê.

---

## 2026-09-10 — Nota cancelada não entra na cobrança

**Decisão.** Documento com situação 02, 03, 04 ou 05 (cancelado, cancelado
extemporâneo, denegado, numeração inutilizada) conta como pendência, mas fica
**fora da planilha de cobrança**.

**Por quê.** Não há documento a pedir. Para cancelado e denegado a operação não
existe; para numeração inutilizada, documento nenhum chegou a existir. Mandar
isso ao cliente numa lista de cobrança queima a conversa e atrasa o que
interessa. Numa amostra real, 92 de 64.268 pendências.

---

## 2026-09-10 — Cupom de consumidor domina o volume, e por isso há filtro

**Decisão.** A planilha de cobrança aceita filtro por modelo de documento, e a
tela mostra a contagem por modelo ao lado do botão.

**Por quê.** Medido em 20 arquivos reais da empresa 12: **307.319 dos 321.337
documentos eram NFC-e** e apenas 14.018 eram NF-e. Uma cobrança sem filtro sai
dominada por cupom de consumidor — que ninguém vai atrás de XML por XML — e a
lista inteira perde serventia pelo volume. O sistema não decide por quem
trabalha: mostra a distribuição e deixa escolher.

---

## 2026-09-10 — Processamento pesado: execução registrada, fila em processo

**Decisão.** Cada rodada pesada vira linha na tabela `execucao`, com passo,
progresso, bytes lidos, documentos e resumo. A fila é um `ThreadPoolExecutor`
de uma linha só dentro do processo da API, não Celery.

**Por quê.** A arquitetura pede Celery, e é para lá que vai quando o sistema
sair da máquina de quem trabalha. Hoje, Celery exigiria subir Redis ou
RabbitMQ só para enfileirar uma tarefa por vez — mais peça para instalar,
manter e quebrar do que o problema pede. O que **não** muda com a troca já está
no lugar: a tarefa não vive na requisição, a rodada é linha no banco e o front
acompanha por identificador. O dia da migração troca um arquivo.

**Uma execução por vez, de propósito.** Duas extrações simultâneas disputariam
a mesma rede e o mesmo disco e terminariam as duas mais devagar.

**Medido.** 20 arquivos de EFD, 108 MB: **321.464 documentos em 4,1 s**
(79 mil/s), parquet de 3,4 MB. Confronto em 0,9 s. Planilha de 64.176 linhas em
5,1 s.

**Consequência.** Se a API reiniciar no meio, a execução fica com situação
`rodando` para sempre. Ainda não há varredura de execução órfã na subida — é a
próxima dívida deste desenho.

---

## 2026-09-10 — Nada sai da lista de pendências (revoga decisão do mesmo dia)

**Decisão.** Documento cancelado, denegado, com numeração inutilizada ou sem
chave de acesso **continua na lista de pendências**, marcado na coluna
Classificação. A planilha sai inteira por padrão; filtrar é escolha de quem
trabalha, e os filtros estão na tela.

**Revoga** as duas decisões de hoje que mandavam excluir cancelada da cobrança
e deixar documento sem chave fora do confronto.

**Por quê.** O argumento que derrubou a versão anterior é do dono do produto, e
só aparece quando se olha o ciclo inteiro: **o trabalho não termina na primeira
conferência**. O cliente manda o que faltava, a conferência roda de novo. O que
tiver sido excluído nunca mais é olhado — some do controle sem nunca ter sido
resolvido. Marcar é reversível; excluir não é.

O raciocínio original continua válido como *informação* — de nota cancelada
realmente não se espera documento —, e é isso que a marcação diz. O erro foi
transformar informação em exclusão.

**Consequência.** A tela mostra a divisão das pendências em três: a cobrar,
cancelada/denegada/inutilizada, e sem chave (que precisa de conferência
manual). Cada uma é um filtro da planilha.

---

## 2026-09-10 — A conferência compara com a rodada anterior

**Decisão.** Toda conferência a partir da segunda compara suas pendências com
as da última rodada concluída e informa quantas foram **resolvidas**, quantas
**permanecem** e quantas são **novas**.

**Por quê.** É o que responde "o cliente mandou os documentos, e agora?".
Sem isso, a segunda rodada só diz "ainda faltam 62.973" e ninguém sabe se
andou. O ciclo do trabalho é: cobrar → cliente envia → importar os arquivos
novos na base → conferir de novo → ver o que saiu da lista.

**Como.** A comparação é entre os `sem_documento.parquet` das duas execuções,
pela chave (ou pelo identificador sintético, quando não há chave). Quando a
pasta da execução anterior já foi limpa, a comparação não aparece e o resultado
da rodada atual continua completo.

---

## 2026-09-10 — Condição extra dentro do ON derruba o plano do DuckDB

**Defeito e correção.** O confronto passou de **0,9 s para 512 s** com uma
mudança que parecia inócua: `LEFT JOIN pasta p ON e.tem_chave AND e.chave =
p.chave`. Não sendo igualdade pura, o DuckDB deixa de planejar junção por
dispersão e cai para junção em bloco — 321 mil × 257 mil linhas.

**Regra.** Condição que depende de um lado só vai para o `WHERE` ou para uma
tabela já filtrada; o `ON` fica com a igualdade e nada mais. E vale materializar
com `CREATE TABLE AS` o que é consultado várias vezes: como visão, cada consulta
do resumo refazia o agrupamento inteiro sobre o parquet.

**Voltou a 1,2 s** sobre as mesmas 321.460 linhas.

---

## 2026-09-10 — Apagar um trabalho pede a senha de novo

**Decisão.** Excluir um trabalho exige (1) papel com a capacidade
`pode_excluir_trabalho` — hoje **dev e gestor**, que são o diretor, o gerente e
o coordenador —, (2) **a senha de acesso digitada outra vez** e (3) uma
confirmação que mostra o que vai sumir. É a única operação do sistema que pede
senha de quem já está logado.

**Por quê.** A sessão dura uma jornada de trabalho inteira. Uma tela deixada
aberta em máquina destravada não pode ser suficiente para desfazer meses de
apuração. É a mesma razão pela qual banco pede senha para transferir depois de
você já ter entrado.

**Analista e revisor não apagam.** Eles escrevem, apuram e entregam — a
capacidade é separada de `pode_escrever` de propósito. E é capacidade própria,
não `administra_usuarios`: recaem hoje sobre os mesmos papéis, mas são
responsabilidades diferentes, e no dia em que uma mudar a outra não deve mudar
junto.

**Errar a senha na confirmação não bloqueia o login.** Contaria como tentativa
falha e trancaria a pessoa fora do sistema por ter hesitado numa confirmação.
Fica registrado no log como evento de segurança.

**Não há lixeira.** Manter projeto apagado meio-vivo no banco cria dois estados
para tudo que consulta projeto, e mais cedo ou mais tarde alguém conta um
trabalho excluído num relatório. O que resta é o registro no log: quem apagou,
quando, e quantos lotes, arquivos e execuções havia dentro.

---

## 2026-09-10 — Remover um lote não pede senha, e não toca no arquivo

**Decisão.** Tirar um lote de um trabalho exige só `pode_escrever`, com
confirmação na própria tela. E remove **o registro da importação**, nunca o
arquivo do cliente em disco.

**Por quê.** Desfazer uma importação não é o mesmo que apagar meses de
trabalho: é a correção de quem apontou a pasta errada, e travá-la atrás de
senha faria o analista chamar o gestor por um engano de dois minutos. Quanto ao
arquivo: o lote é só o registro de onde ele está — o dado vive no servidor de
arquivos com a política de guarda da casa, e não cabe a este sistema apagá-lo.

**Consequência.** A confirmação avisa que a conferência precisará ser refeita:
toda conferência já concluída olhou aquele lote.

---

## 2026-09-10 — A bateria de testes gravou por cima de uma execução real

**O que aconteceu.** Um download real da planilha de notas não escrituradas
veio com CNPJ `88991122000138` e uma chave de 44 setes — dados de fixture do
módulo `test_conferencia_api.py`.

**Causa.** `CAT_PASTA_DE_TRABALHO` era `data/trabalho`, **relativo**, e o
`conftest` isolava o banco mas não o disco. O teste roda com o diretório de
trabalho no `backend/`, cria a execução número 1 no banco SQLite de teste e
grava em `backend/data/trabalho/execucao-1` — exatamente a pasta da execução
número 1 do Postgres de verdade. Dois bancos diferentes, o mesmo disco, os
mesmos identificadores.

**Correções, três.**

1. O `conftest` define `CAT_PASTA_DE_TRABALHO` para a pasta temporária da
   bateria. Isolar o banco e não isolar o disco é meio isolamento.
2. `Config.raiz_de_trabalho` devolve caminho **absoluto**. Relativo depende de
   onde o processo subiu, e dois processos com diretórios diferentes gravariam
   em lugares diferentes sem ninguém perceber.
3. A planilha em cache só vale se for **mais nova que o parquet** que a
   originou. Guardar por nome e nunca conferir a idade servia planilha velha
   depois de a conferência rodar de novo — defeito independente do primeiro, e
   que sozinho já bastaria para entregar número errado.

**Lição.** Isolamento de teste não é só banco de dados. É todo recurso
compartilhado que tenha nome fixo: disco, porta, fila, arquivo temporário.

---

## 2026-09-10 — Cobertura zero tem uma causa provável, e o sistema passa a dizê-la

**Decisão.** Quando nenhum documento casa, o sistema compara os
estabelecimentos dos dois lados e, se não houver interseção, avisa que são
filiais diferentes.

**Por quê.** Num uso real: EFD do estabelecimento `44000001000101` contra XML
do `44000001000454` — mesma empresa, filiais diferentes. Resultado: 10.605
pendências e nenhum documento conferido. Sem o aviso, aquilo parece falta
gigantesca de documento e vira cobrança indevida ao cliente; com o aviso, é o
que é — importaram a EFD de uma filial e os XML de outra.

**Como.** O CNPJ do emitente já está na chave de acesso, posições 7 a 20. Não
é preciso reabrir XML nenhum para saber de quem ele é.

---

## 2026-09-11 — O confronto filtra antes de agrupar, e derrama em disco

**O que aconteceu.** Uma empresa grande gerou **37.930.719 documentos** de C100
e C800. O confronto morreu com `Out of Memory Error: Allocation failure`, e a
API ficou sem responder junto — o processo brigava por RAM com o resto da
máquina.

**Três causas, em camadas.**

1. **Banco analítico em memória não derrama.** A correção de desempenho do dia
   anterior trocou `VIEW` por `CREATE TABLE`, e tabela em banco DuckDB em
   memória, sem `temp_directory`, não tem para onde escrever o que não couber:
   morre em vez de usar disco. Agora o banco é **em arquivo**, dentro da pasta
   da execução, com `temp_directory`, `memory_limit` e teto de linhas de
   execução declarados — e `preserve_insertion_order` desligado, que é o que
   mais economiza memória em parquet grande.

2. **O plano estava invertido.** Agrupava a base inteira por chave e só depois
   tirava o que já tinha documento. Numa base saudável a maior parte dos
   documentos **tem** o XML e deveria sair do caminho antes do agrupamento.
   Agora filtra primeiro e agrupa só o que sobrou. As contagens gerais passaram
   a usar `count(DISTINCT agrupador)` numa coluna só, em vez de agregar as
   dezesseis colunas do registro inteiro.

3. **Disco.** A pasta de trabalho estava no `C:`, com 12,9 GB livres. Um
   confronto desse tamanho passou de 13 GB só de rascunho. Mudou para
   `D:\cat-trabalho` via `CAT_PASTA_DE_TRABALHO`, e o limite de rascunho deixa
   2 GB de folga: encher a unidade derruba mais que a execução.

**Regra que fica.** Filtrar antes de agregar não é micro-otimização quando a
diferença é entre concluir e não concluir. E todo motor analítico precisa saber
**onde derramar** e **até onde pode ir** — sem isso, o modo de falha não é
lentidão, é o processo morrer levando a API junto.

**Configuração nova:** `CAT_PASTA_DE_TRABALHO` (disco com espaço),
`CAT_MEMORIA_ANALITICA` (padrão 4GB) e `CAT_THREADS_ANALITICAS` (padrão 4).

---

## 2026-09-11 — O confronto grande: o plano importa mais que o operador

**O que aconteceu.** Base de 37,9 milhões de documentos. Três tentativas
morreram ou travaram: `Allocation failure` em memória; `failed to pin block`;
e por fim 88 minutos com 26 GB de rascunho, 13% de CPU e zero linhas escritas.

**Diagnóstico, por eliminação e por `EXPLAIN`.**

1. `count(DISTINCT)` sobre 37,9 milhões passa em **20 s** — não era ele.
2. O `GROUP BY` de dezesseis colunas sobre ~38 milhões de grupos não cabe, com
   ou sem `ORDER BY` — e é quase todo desperdício: só **832.782** agrupadores
   se repetem (2,2%).
3. Separar únicos de repetidos resolveria — mas a primeira forma (dois ramos
   numa `UNION ALL` com `EXISTS` correlacionado) fez o DuckDB **materializar
   o subplano comum** (`CTE __common_subplan_1`, 38 milhões × 16 colunas) e
   descorrelacionar com `LEFT_DELIM_JOIN`. Foi isso que travou.

**Decisão.** Cada ramo num `COPY` próprio, com `ANTI JOIN`/`SEMI JOIN`
explícitos contra a tabela pequena de repetidos. Reler 400 MB de parquet custa
segundos; materializar 38 milhões de linhas custa gigabytes.

**Medido, mesmos 4 GB e 4 threads:** únicos 0,5 min, repetidos 0,1 min, união
0,3 min, ordenação final 6,4 min — **8 min no total, 1,9 GB de rascunho**. E é
o pior caso possível: pasta sem nenhum XML, todos os 37,9 milhões viram
pendência. Numa base real a maior parte sai antes.

**Regra que fica.** Quando uma consulta grande trava, pedir o `EXPLAIN` antes
de mexer em memória ou threads. Duas armadilhas conhecidas do DuckDB: a mesma
visão referenciada duas vezes vira CTE materializada; `EXISTS` correlacionado
vira delim join. As duas se evitam com comandos separados e junções explícitas.

---

## 2026-09-11 — A empresa pode ser emitente OU destinatário do XML

**Decisão.** Um XML é da empresa se a raiz do CNPJ do projeto estiver no
emitente **ou** no destinatário. Só é "de outra empresa" quando nenhuma das
pontas conhecidas bate.

**Por quê.** A primeira versão comparava só o emitente. Numa nota que a
empresa **recebe** do fornecedor — a entrada com ST retido, insumo principal
da CAT 42 — o emitente é o fornecedor. Todo XML de compra seria jogado fora.
Não apareceu no primeiro teste real porque os 884 XML eram de emissão própria.

**Consequência.** A amostra lida do XML subiu de 8 para 16 KB: o `<dest>` só
vem depois do `<emit>` com endereço inteiro, e 8 KB nem sempre alcançava.

---

## 2026-09-11 — A retificadora substitui a original, e o sistema age

**Decisão.** O cabeçalho lê `COD_FIN` (ICMS/IPI) e `TIPO_ESCRIT`
(Contribuições) a partir da âncora das datas. Quando o lote tem original e
retificadora do mesmo estabelecimento e período, a conferência **lê só a
retificadora**. A original continua no lote — registrada, contada, avisada —
mas fora da leitura.

**Por quê.** É a regra fiscal: a retificadora substitui a original por
inteiro. Ler as duas dobrava os documentos do período e, pior, o confronto
fazia `max(valor)` e `min(situacao)` entre as duas versões — misturava a nota
de antes e a de depois numa linha só. Não é ruído; é número errado. E as duas
na mesma pasta é o caso comum (pasta `10 - RETIFICAÇÃO SPEDS` da empresa 04).

**Limite conhecido.** Mais de uma retificadora para o mesmo período entram
todas: o registro 0000 não traz a data de recepção, e sem ela não há como
saber qual é a última. Fica no log.

---

## 2026-09-11 — A planilha mostra quantas vezes a chave apareceu, e o sistema avisa quando é arquivo em dobro

**Decisão.** A planilha de pendências ganha a coluna **Ocorrências na EFD**, e
a conferência avisa quando mais de **5%** das pendências têm chave repetida.

**Por quê.** O confronto sempre colapsou chaves repetidas numa linha só — e
isso absorvia, em silêncio, tanto o caso legítimo (a mesma nota escriturada em
duas filiais) quanto o acidental (o mesmo arquivo importado duas vezes). A
coluna deixa quem baixa ver a diferença; o aviso deixa quem confere ver de
longe.

**O corte de 5% vem de medição.** Numa base real de 37,9 milhões de
documentos, 2,2% das chaves se repetiam legitimamente. O mesmo lote importado
em dobro daria perto de 100%. Entre um e outro há margem de sobra.

---

## 2026-09-11 — Cópia exata não entra duas vezes, e o hash só se calcula de quem tem par

**Decisão.** A importação passa a recusar **cópia exata** — mesmo conteúdo,
byte a byte — de outro arquivo da mesma pasta ou de um já importado no
trabalho. A cópia fica de fora com aviso dizendo de quem ela é cópia.

**Por quê.** A deduplicação era só por caminho. O mesmo SPED copiado em duas
pastas (a empresa 12 tem `EFD Fiscal - EFD ICMS IPI`, `Sped FISCAL
segregado` e `Prescritos`) entrava duas vezes e dobrava os documentos do
período. O confronto absorvia em silêncio.

**Como, sem ler 100 GB.** Hash SHA-256 **só de candidatos**: arquivos que
coincidem em tamanho, tipo, CNPJ, competência e finalidade com outro da pasta
ou com um já importado. Assinatura igual e conteúdo diferente existe, então a
assinatura escolhe quem hashar; quem decide é o hash. Numa importação sem
pares nada é lido inteiro. O hash fica gravado (`arquivo_do_lote.hash_conteudo`)
para a importação seguinte comparar; arquivo importado antes desta regra não
tem hash e é lido na hora — está em disco, o caminho é conhecido.

**Duas fronteiras que precisaram ficar explícitas.** (1) Caminho que já está
no trabalho é "já importado", domínio do roteador — não passa pelo hash, que
o compararia consigo mesmo. Só caminho novo com conteúdo igual é cópia.
(2) Uma pasta só de cópias responde 409 "são cópias exatas de arquivos que já
estão no trabalho", antes da recusa genérica "nada alimenta a CAT" — que
seria verdadeira e enganosa.

**Entre iguais, sobrevive o de pasta mais rasa.** Não muda o resultado; muda
o que a pessoa vê como "o original", e a cópia costuma estar em `backup/`.

---

## 2026-09-11 — O progresso da conferência não rebaixa o que já contou

**O que aconteceu.** Numa conferência real de 37,9 milhões de documentos, a
tela mostrou "885 de 960 arquivos · 1 documentos · 0 B" durante o confronto.
Parecia travada; estava na última fase, trabalhando.

**Causa.** Cada fase de extração conta a própria coisa — a EFD conta C100 e
C800, a leitura da pasta conta chaves de XML. O relógio de progresso escrevia
os números da segunda fase por cima dos da primeira, e o limitador de dois
segundos engoliu o tique final da EFD (por isso 885 e não 960).

**Decisão.** Ao encerrar a EFD, os totais dela ficam **congelados** na
execução e gravados na hora; a fase seguinte só avança o contador de arquivos.
Ao entrar no confronto, o contador fecha em `totais/totais`. O teto de 95%
antes do confronto continua: os últimos 5% são o confronto de verdade.

---

## 2026-09-11 — A lista de cobrança não se deduplica por número

**A pergunta.** "As notas que encontramos para cobrar o cliente provavelmente
estão duplicadas." Foi medido antes de decidir, em duas bases reais
(`sem_documento.parquet` das execuções 3 e 6, com 92.786 e 37.097.934
pendências).

**Por chave: zero repetição, nas duas.** É por construção — as repetições da
EFD (a mesma nota escriturada em duas filiais, ou o mesmo arquivo importado em
dobro) já viram a coluna `Ocorrências na EFD`, uma linha por chave.

**Por número: parecia duplicado, e não era.** Agrupando por
(estabelecimento, modelo, série, número) apareceram 109 "notas repetidas" na
base pequena e 2.384.075 na grande (10.958.509 linhas). Olhando de perto:

* **Modelo 59 (2.368.348 grupos):** o número do CF-e reinicia em cada
  equipamento SAT. O mesmo número 4555 aparece em dezenas de chaves, cada uma
  com um `nrSAT` diferente (posições 23 a 31 da chave). São cupons distintos.
* **Modelo 55:** o C100 não traz o CNPJ do emitente, só o `COD_PART`; o CNPJ
  na extração é o do estabelecimento (registro 0000). Uma saída própria e uma
  entrada de fornecedor podem ter o mesmo número e série — e foi exatamente
  isso nos exemplos (saída de jan/2022 e entrada de jun/2022, mesmo número).

**Decisão.** Não há o que remover, e uma "validação por número" apagaria
10,9 milhões de documentos legítimos. O que entrou foi uma **guarda**: o
resumo mede `count(DISTINCT chave)` na lista escrita e, se um dia houver chave
repetida, registra erro no log e avisa na tela para não cobrar por aquela
lista. É conferência do pipeline, não filtro do dado — coerente com a regra
de marcar em vez de excluir. Custo: uns 20 segundos em 37,9 milhões.

**Se um dia for preciso casar por identidade de nota** (sem chave, por
exemplo), a identidade tem de ser (CNPJ do emitente tirado da chave, posições
7 a 20; modelo; série; número; e `nrSAT` para o modelo 59). Nunca
(estabelecimento, modelo, série, número).

---

## 2026-09-11 — A conferência tem três listas, não duas

**A pergunta.** "Onde eu visualizo o que foi escriturado e entregue — o
resultado positivo?" Não havia onde: o lado positivo era só um número na tela
(`conferidos`), e a lista em si nunca era gravada.

**Decisão.** O confronto passa a gravar `conferidos.parquet` — está na EFD
**e** o documento veio — ao lado de `sem_documento.parquet` e
`nao_escrituradas.parquet`. Mesma forma da lista de pendências (uma linha por
chave, `ocorrencias` contadas, arquivo da EFD) mais **de onde veio o
documento**: origem (XML ou relatório do cliente) e o arquivo. Sai pela rota
`/conferencias/{id}/planilhas/conferidas` como `notas_conferidas.xlsx`, com
filtro por modelo, e ganhou o terceiro cartão na tela.

**O que mudou por dentro.** A deduplicação (únicos em fluxo, repetidos pelo
GROUP BY largo, cada ramo num COPY próprio) virou a função
`_uma_linha_por_chave`, usada pelas duas listas. O resumo agora lê os dois
lados dos parquets já gravados — sumiu a última consulta que voltava à base
(`entregues JOIN efd`), inclusive nos recortes por modelo e operação.
Conferido na execução 3 real: números idênticos aos gravados, 2 segundos.

**Sem ORDER BY na lista positiva, de propósito.** Numa base saudável este é o
lado grande. Ordenar 37 milhões de linhas custou 6,4 min na lista de
pendências, onde a classificação justifica; aqui não há classificação.

**Execuções antigas não têm a lista.** O botão responde 410 dizendo isso e
pedindo para rodar de novo — não se fabrica o parquet por fora do pipeline.

---

## 2026-09-11 — As fontes viajam com o app

**O que aconteceu.** O rótulo "ESCRITURADAS NA EFD" da ficha de conferência
saiu "bugado" na tela de um gestor. Os tokens pediam `"Inter"` com peso 650
para os rótulos, mas nada carregava a Inter: não havia `@font-face`, `<link>`
nem pacote. O navegador caía no que estivesse instalado — Segoe UI, que não
tem peso 650 e vira Bold (700) — e cada máquina renderizava de um jeito.

**Decisão.** As fontes vêm embarcadas no build, pelos pacotes
`@fontsource-variable/inter` (variável: tem o 650 de verdade) e
`@fontsource/ibm-plex-mono` (400, 500 e 600). Importadas em `main.tsx` antes
dos tokens, e `--fonte` passa a apontar para `"Inter Variable"` primeiro. Sem
CDN de propósito: o sistema roda em rede interna e não pode depender de
fontes do Google carregarem.

**Verificado** com captura do Chrome sem interface na mesma página, antes e
depois: antes, Segoe UI Bold; depois, Inter no peso desenhado.

---

## 2026-09-11 — Relatório do cliente no confronto: o que a simulação mostrou

**O pedido.** Validar a opção de subir um relatório gerencial para o
comparativo, simulando o pior cenário, o médio usual e um perfeito. Entraram
como testes de ponta a ponta (`test_cenarios_relatorio_api.py`, 200
documentos por cenário: 120 NF-e e 80 CF-e) e como testes de unidade do
caminho do relatório (`test_conferencia_por_relatorio.py`).

**O que já funcionava.** Relatório sozinho confirma a nota; uma linha por
item vira um documento só; nota do relatório que a EFD não tem sai como não
escriturada; quando XML e relatório trazem a mesma chave, **o XML vence**
(regra da casa); arquivo ilegível não derruba os outros.

**Três falhas que a simulação achou, e as correções.**

1. **Chave suja era perdida em silêncio.** `NFe` na frente, espaço em volta,
   chave em blocos: o comparador exigia exatamente 44 caracteres e descartava
   sem contar. Agora ficam só os dígitos; 44 é chave.
2. **Chave que o Excel estragou** ("3,52105E+43" — os dígitos foram embora ao
   virar número) **e linha sem chave** também não eram contadas. Agora cada
   relatório informa "N linha(s) sem chave de acesso válida, ignoradas" na
   lista de recusados, com a causa provável. A nota cai como pendente, e quem
   for cobrar sabe que o relatório a trazia.
3. **Inventário no lugar do movimento** dava "0 documentos" sem explicação.
   A extração agora recusa com o motivo. (Pela API ele nem chega: a
   conferência só pega XML e relatório de movimento do lote — mas o relatório
   de movimento com a chave destruída chega, e é o caso 2.)

**E uma na tela.** A lista de recusados ia no JSON e ninguém via. Agora
aparece no cartão do resultado, arquivo por arquivo, com o motivo.

**Os três cenários, como ficaram.** Perfeito: 200/200, sem aviso, sem
recusado. Médio usual: 175 conferidas (170 pelo relatório, 5 pelo XML), 25
pendentes das quais 4 canceladas marcadas, 5 não escrituradas, 8 linhas sem
chave avisadas. Pior (inventário + movimento com chave destruída + relatório
da outra filial): 0 conferidas, 203 pendentes, 50 não escrituradas, e a tela
diz as três coisas — "filiais diferentes" com os dois CNPJ, "400 linha(s) sem
chave" no arquivo certo, e as sem chave e canceladas marcadas.

---

## 2026-09-11 — Etapa 3, histórico de movimentação: o que a EFD tem e o que não tem

**O pedido.** "Vamos começar a trabalhar na parte de histórico da movimentação
do que foi encontrado — a etapa 3."

**O que os SPED reais mostraram antes de qualquer código.** Em duas empresas
(empresa 12, 884 EFD; empresa 04, 68 EFD), o C170 só existe nas
**entradas**: 27.448 registros de item e nenhum com CFOP de saída. Para NF-e
de emissão própria a EFD dispensa o item. E o cupom SAT não traz C810 — em
171.652 cupons reais de São Paulo, nenhum; o SAT vai para a EFD só com o
**C850**, o analítico por CST/CFOP. Ou seja: **a EFD não tem item de saída**.
O item das saídas — inclusive as de CST 60, que são o coração do ressarcimento
— terá de vir do XML (NF-e e CF-e), na etapa seguinte.

**Decisão.** A etapa 3 extrai o que a EFD tem, marca cada movimento pelo que a
conferência achou e diz com número o que falta:

* `documentos.parquet` — cada C100/C800 com quantos itens e analíticos trouxe;
* `movimentos.parquet` — cada C170/C810 com o documento pai, o cadastro
  (descrição, código de barras, NCM, CEST do 0200 mais recente) e a
  **classificação da conferência**: conferido, pendente, sem chave. Ordenado
  por estabelecimento, item e data — a ordem em que a ficha se lê;
* `analitico.parquet` — cada C190/C850 com `tem_item`, decidido na própria
  leitura (os analíticos de um documento esperam em memória até ele fechar).
  É por aqui que se sabe quanto de CST 60 saiu sem detalhe;
* `itens.parquet` — o 0200 que vale, por estabelecimento e código;
* `inventario.parquet` — o bloco H, item a item, com a data do H005.

A etapa exige conferência concluída: é a lista de conferidos dela que marca
os movimentos. "Do que foi encontrado" é isto — o que tem documento sustenta
o razão; o que não tem entra marcado e perde a marca quando o cliente mandar
o que falta.

**Duas escolhas de escala, medidas na conferência e repetidas aqui.** A marca
da conferência é feita pelo lado pequeno: reduz-se a lista de conferidos
(dezenas de milhões de chaves numa base saudável) às chaves distintas dos
movimentos (só entradas, poucos milhões) por SEMI JOIN, e só então se marca.
E o `tem_item` do analítico sai da extração, não de uma junção de 100 milhões
de analíticos contra 38 milhões de documentos.

**Leiautes conferidos em arquivo real, não no manual:** 0200 (12 campos),
C170 (37, chave do pai vem da ordem do arquivo), C190 (11), C850 (7, sem ST),
H005 (3), H010 (10). O C810 segue o manual, porque não apareceu.

**Rodada real, logo depois (empresa 12, 884 EFD, 44 min).** 37.930.719
documentos; 8.769.348 movimentos de item, todos de entrada; 92.936.619
analíticos; 1.017.100 linhas de cadastro (72 estabelecimentos); 784
inventários com 7.757.063 itens. **36.542.970 saídas sem item** — NFC-e 24,0 M,
SAT 11,6 M, NF-e 964 mil — R$ 5,80 bi, dos quais **R$ 1,66 bi com CST 60**.
E 179.333 entradas sem C170, **todas de emissão própria** (devolução de venda,
produtor rural, retorno): mesma regra da saída própria, não anomalia. O
resumo passou a separar entrada própria sem item (regra, item vem do XML) de
entrada de terceiros sem item (aí a EFD exige o C170 e faltar é sinal de
arquivo incompleto). Parquets: 1,6 GB no total; o analítico sozinho tem 874 MB.

---

## 2026-09-11 — Instalação numa máquina nova, a um comando

**O pedido.** Trabalhar de casa, noutra máquina. A sessão de desenvolvimento
roda na máquina do escritório e não alcança a de casa; o que se pode fazer é
tornar a instalação trivial e reprodutível.

**Decisão.** `scripts\instalar.ps1` faz tudo de uma vez — pré-requisitos
(com `-InstalarPreRequisitos` instala via winget), venv, `.env` com JWT e
pimenta **novos** (segredo de servidor não viaja entre máquinas), Postgres em
Docker ou SQLite na falta dele, migrações, gestores iniciais, `npm install` —
e `scripts\subir.ps1` sobe API e tela. Idempotente: rodar de novo não apaga
`.env`, banco nem senha. Receita no README.

**O ensaio achou dois defeitos que valiam para qualquer máquina limpa.**

1. `pip install -e ".[dev]"` **nunca funcionou**: o setuptools achava `cat`,
   `tests`, `migracoes` e `workers` na raiz do backend e recusava. O ambiente
   do escritório tinha sido montado à mão, por isso ninguém viu. Corrigido
   com `[tool.setuptools.packages.find] include = ["cat*"]`.
2. Com o pacote instalado em modo editável, `versao()` lia primeiro os
   metadados do pacote — que congelam a versão do dia da instalação e não
   acompanham o `git pull`. O `/api/saude` voltaria a mentir. Agora o
   `pyproject.toml` vem primeiro; os metadados são o recurso de quando não há
   `pyproject` ao lado.

E o PowerShell 5.1 lê `.ps1` sem BOM como ANSI: um travessão virou aspa e
quebrou o script. Os scripts vão com BOM UTF-8.

**O que não vem junto.** Cada máquina tem o próprio banco (usuários,
empresas, trabalhos) e o próprio `.env`. O dado fiscal do cliente fica onde
está — de casa só se alcança pela VPN, e o sistema do escritório continua no
ar para quem chegar até ele pela rede interna.

---

## 2026-09-12 — Front reorganizado: Tailwind, providers e roteador em árvore

**O que entrou** (trabalho feito de casa, na branch `feat/frontend-tailwind`,
integrado no main como v0.19.0). O front deixa de ser um `App.tsx` com
estado de sessão e rotas soltas e passa a ter:

* **Tailwind v4** pelo plugin do Vite, ligado aos tokens da marca por
  `styles/tema.css` — os tokens continuam sendo a fonte da cor; o Tailwind é
  a ponte. As primitivas antigas (`.botao`, `.campo`, `.aviso`, `.tabela`,
  `.cartao`) ficam em `styles/legacy-kit.css` até cada tela migrar;
* **providers**: sessão (`AuthProvider`), tema claro/escuro, toasts e
  confirmação, cada um com o seu hook;
* **roteador em árvore** (`routers/index.tsx`): rota pública, rota protegida,
  exigência de papel, página 404, e os caminhos num lugar só
  (`constants/routes.ts`) — mudar um caminho deixa de ser caça a template
  string;
* componentes de UI (`Botao`, `Campo`, `Aviso`, `Modal`, `Etiqueta`,
  `Carregando`, `LogoBMS`), leiaute com barra e menu lateral, tela de login
  redesenhada — que, de quebra, resolve o logotipo marinho invisível no tema
  escuro;
* **pastas em inglês** (`pages`, `services`, `components`, `styles`, `types`,
  `hooks`, `layout`, `lib`, `constants`) com nomes de arquivo e de símbolo
  em português. É a convenção daqui para a frente no front; o backend segue
  em português.

Sem *lazy loading* por enquanto: enquanto uma página depender do CSS de
outra, dividir o bundle deixa tela sem botão. Entra no fechamento, com o
preflight.

**Dois ajustes na integração.** (1) A branch trazia `backend/.env.bak-instalador`
— cópia do `.env` da máquina de casa, com segredos. Saiu do repositório e o
`.gitignore` da raiz passa a barrar qualquer `.env*` que não seja o exemplo.
Os segredos eram os daquela máquina; para zerar o risco, basta gerar outros
lá. (2) `alembic` entra nas dependências: o instalador e o README rodam
`alembic upgrade head`, e numa máquina limpa ele não estava.

**Achado do instalador em casa.** No PowerShell 5.1, `docker info *> $null`
dentro de `try/catch` cai no `catch` mesmo com o Docker no ar (redirecionar o
stderr de executável nativo vira `NativeCommandError`). O script pergunta a
versão do servidor e decide por ela.

---

## 2026-09-12 — Tela de Usuários reconstruída a partir do handoff

**O que chegou.** Um pacote de design (`spec-screen-usuarios.md` +
protótipo HTML) com a tela de Usuários redesenhada: métricas, busca, filtros
por situação, tabela com avatar e ações em ícone, modais de criação, edição e
confirmação, combobox com busca no lugar de todo `<select>`, e banner de
senha provisória com botão Copiar. A spec é referência visual — a
implementação usa os componentes do sistema, não o HTML do protótipo.

**O que a spec pedia e o sistema não tinha.** Editar **nome e e-mail** de um
usuário: existiam rotas para papel, cargo e situação, e nenhuma para os
dados. Entrou `PATCH /usuarios/{id}/dados`, com a mesma validação da criação
(e-mail válido, nome não vazio) e a checagem que faltava — e-mail já usado
por outro usuário responde 409, o próprio e-mail não conta como duplicado. O
nome de usuário continua imutável: é a identidade nos logs e nas alocações.

**Dois componentes novos, porque servem a mais telas.** `Combobox` (busca,
teclado ↑↓ Enter Esc Home End, papéis ARIA, abre para cima quando não há
espaço abaixo — tudo o que a spec listava como "a implementar na versão
real") e `BotaoIcone` (34×34, exige rótulo, porque ícone sozinho não tem nome
para leitor de tela).

**A confirmação ganhou ícone e tom** (`useConfirm` com `icone` e `tom`), que
é o que diferencia "gerar senha" de "desativar" num diálogo de duas linhas.

**Achado da conferência visual.** Sem o preflight do Tailwind — desligado de
propósito enquanto houver CSS legado —, `<button>` e `<dialog>` chegam com
borda e fundo do navegador. Aparecia como caixa cinza em volta de cada botão
do kit. Corrigido nos próprios componentes (`bg-transparent`, `border-0`),
não na tela. E o `<dialog>` precisou de `overflow-visible`: o padrão cortava
o painel do combobox dentro do modal.

**Saiu de cena:** `pages/Usuarios.css` (220 linhas) e o componente
`SenhaProvisoria`, que o banner de flash substitui.

---

## 2026-09-12 — O front inteiro no desenho novo, e o CSS legado acabou

**O que chegou.** Um segundo pacote de design, agora com as sete telas
(`frontend/claude/design/`): Login, Trabalhos, Cadastro, Detalhe do trabalho,
as três etapas e Usuários. Mesma regra do primeiro: a spec é referência
visual; a implementação usa os componentes do sistema.

**O que foi feito.** Todas as telas migraram. Com elas nasceram as peças que
estavam copiadas tela a tela e agora existem uma vez só:

* `Pagina.tsx` — cabeçalho de página (com o brilho e a faixa de luz),
  métricas, seção, número grande, barra de progresso, estado vazio, voltar;
* `Filtros.tsx` — toolbar, busca, segmentado, contador, chips de filtro;
* `Tabela.tsx` — tabela de dados com rolagem própria;
* `Andamento.tsx` — o progresso de execução longa, compartilhado pelas duas
  etapas que rodam em segundo plano;
* `ForcaDaSenha.tsx` — medidor de força e lista de requisitos;
* `lib/competencia.ts` — competência é mês: `MM/AAAA` na tela, ISO na API.
  Estava escrita de três jeitos, e o wizard usava `type="date"` com um dia
  que ninguém escolheu e que reaparecia na tela depois.

**Duas decisões de produto no caminho.**

1. **Novo trabalho para empresa já cadastrada** virou modal no Início, como a
   spec pede. Empresa nova continua entrando pelo wizard de cadastro: é o
   SPED que traz CNPJ, razão social, IE e UF, e digitar isso à mão é como o
   cadastro erra.
2. **As rotas não mudaram.** A spec sugere `/trabalhos/:id`; ficou
   `/projetos/:id`, que é o que já está no ar e em links salvos. Trocar rota
   sem ganho é churn.

**O fim do CSS legado.** Com a última tela migrada, nenhuma classe de
`styles/legacy-kit.css` era mais usada — o arquivo saiu, e com ele o
impedimento que estava escrito em `styles/tema.css` desde a branch de casa:
**o preflight do Tailwind entrou**. Some com isso a correção manual que cada
componente carregava (`bg-transparent` em botão, `border-0` em dialog,
sublinhado de link) — que, aliás, foi o que apareceu na conferência visual:
todo botão que navega vinha sublinhado em azul, e o `<dialog>` com borda
preta.

**Dividir o pacote continua fora**, agora por outro motivo: cabe inteiro em
110 kB comprimidos, e o sistema roda em rede interna. Trocar uma carga única
por um piscar de Suspense a cada navegação não se paga. A nota em
`routers/index.tsx` registra quando reavaliar.

**Backend:** nada mudou nesta entrega. 489 testes seguem passando.

---

## 2026-09-12 — O trabalho passa a ter memória: histórico, status e sucessão

**O pedido.** Um histórico por trabalho onde se veja tudo que foi feito, com
chat de comentários e atividades, o nome de quem fez cada coisa, status que
aparece no cartão, o nome de quem criou o projeto visível para o gestor, e
sucessão — o gestor passa o trabalho para outra pessoa.

**Por que não cabia num campo.** Um trabalho da CAT dura meses e passa por
várias mãos. "De qual base saiu este número" a execução já respondia; "por
que ficou parado em março", "quem recebeu isto quando o fulano saiu de
férias" não tinha onde. Entrou uma linha do tempo com duas naturezas de
entrada **misturadas de propósito**: o que o sistema fez (lote importado,
conferência concluída, status alterado) e o que a pessoa escreveu. Separá-las
mentiria sobre a ordem dos fatos — o comentário "o cliente vai mandar o que
falta" só faz sentido logo abaixo da conferência que achou 92 mil pendências.

**Evento não se apaga nem se edita.** É registro, não anotação: histórico que
se reescreve não responde pergunta de auditoria. Comentário errado se corrige
com outro comentário.

**Quatro status, e eles valem.** Em andamento, pausado, cancelado, concluído.
Pausar e cancelar **exigem motivo** — sem ele, a pergunta de três meses depois
não tem resposta. E trabalho pausado ou cancelado **não roda etapa**: sem
isso, "pausado" seria só uma cor no cartão enquanto uma extração de 44 minutos
continuaria disparando num trabalho que a equipe decidiu parar. Concluído
roda, porque refazer uma conferência depois da entrega é exatamente o que se
faz quando o cliente questiona um número.

**Criador e responsável são campos diferentes.** Quem criou não muda nunca;
quem responde muda a cada sucessão. Os projetos que já existiam herdaram o
criador como responsável — é a verdade mais próxima disponível, e melhor que
deixá-los sem dono.

**Sucessão é de gestor**, e só para conta **ativa** com papel que escreve.
Passar um trabalho para conta desativada é exatamente como ele fica sem dono
sem ninguém perceber.

**Registrar evento nunca derruba a operação que o gerou.** Se gravar a linha
do histórico falhar, o lote continua importado e a conferência continua
concluída; o que se perde é a anotação, e isso vai para o log. O contrário
seria uma extração de 44 minutos desfeita porque uma frase não coube no banco.

**Paginação por cursor, não por offset.** Com evento entrando enquanto se lê,
offset repete linha e pula linha.

O contrato das seis rotas está em `docs/CONTRATOS.md` §6 — o front desta
funcionalidade será desenhado à parte.

---

## 2026-09-12 — A tela do histórico, e o trabalho parado que se recusa a andar

**O que entrou.** A tela do histórico, do handoff `README-Historico.md`: linha
do tempo com ícone por tipo, filtros (Tudo · Comentários · Situação ·
Arquivos · Etapas), seletor de situação com confirmação e justificativa,
painel de sucessão para gestores, resumo e o campo de comentário com
`Ctrl + Enter`. Mais o que ela trouxe nas outras telas: botão **Histórico do
projeto** e o fato **Criado por** no detalhe, e os quatro status nos cartões
do Início, com filtro e a métrica de pausados/cancelados.

**O pedido explícito, que contraria a spec — e vence.** O handoff dizia que
em trabalho pausado "as etapas seguem acessíveis, card marcado". O pedido foi
o contrário: pausado **desabilita as etapas e avisa**. É o comportamento
certo, e já era o do servidor desde a v0.21.0 — o que faltava era a tela
dizer isso antes do clique, em vez de deixar a pessoa descobrir no 422.
Agora o aviso aparece no detalhe e nas três telas de etapa, com um caminho de
saída ("Abrir o histórico"), e os botões de ação ficam desabilitados.

**O defeito que só a conferência visual achou.** A lista de sucessores
oferecia qualquer pessoa ativa com papel de escrita — inclusive quem **não
tem alocação na empresa**. Passar o trabalho para essa pessoa entregava um
trabalho que ela não consegue abrir: 403 na primeira tela. Agora a lista
filtra por acesso à empresa e a rota recusa com a explicação. Mesmo raciocínio
da conta desativada, que já estava coberto.

**Nota sobre migrações em SQLite.** A migração do histórico usa
`batch_alter_table`, que é o que o SQLite exige. Mas a cadeia inteira ainda
não roda lá: a migração `62fe3d195ce5` (bem anterior) usa `create_foreign_key`
direto e quebra. Fica registrado — o caminho sem Docker do `instalar.ps1`
depende disso e ainda não foi exercitado de verdade.

**Correção logo em seguida (v0.22.1).** O painel do combobox era cortado por
qualquer ancestral com `overflow` — no seletor de situação, dentro do cartão
de cabeçalho (que tem `overflow-hidden` para conter o brilho), a lista
aparecia pela metade e "Concluído" sumia. O painel passou a ser renderizado
em **portal** com posição fixa presa ao botão, recalculada em rolagem e
redimensionamento. Some com isso a exigência que o `Modal` carregava de não
ter `overflow` por causa do dropdown.

**E a sucessão que ficou impossível (v0.22.2).** A regra que entrou na
v0.22.0 — só recebe quem já tem alocação na empresa — estava certa no
diagnóstico e errada no remédio. **Não existe tela para alocar ninguém numa
empresa**: a alocação nasce só de quem cadastra a empresa. Com isso a lista
de sucessores vinha vazia e a funcionalidade não funcionava.

Agora o acesso à empresa **não é condição, é consequência**: quem não alcança
a empresa aparece na lista marcado (`precisa_de_acesso`, e a tela diz "ganha
acesso"), e a transferência cria a alocação. É o que passar o trabalho quer
dizer — junto vai o acesso —, e o evento de sucessão registra que foi assim
(`dados.alocou_na_empresa`), com aviso no log.

Fica anotado o que isto revelou: **alocar pessoa a empresa não tem tela**. Os
três gestores reais do sistema não enxergam empresa alguma. Enquanto não
houver essa tela, a sucessão é o único caminho para dar acesso — o que é
pouco.

---

## 2026-09-12 — Alocar pessoa a empresa ganhou tela

**O que faltava.** O escopo de visibilidade do sistema sai das alocações:
`Usuario.empresas` são as vigentes, e toda consulta a dado fiscal passa por
`exigir_empresa`. Só que a alocação **só nascia de um jeito** — quem cadastra
a empresa pelo SPED fica alocado nela. Não havia como dar acesso a mais
ninguém. No banco real isso ficou visível: dos três gestores, um tinha uma
alocação e dois não tinham nenhuma; entravam no sistema e não viam trabalho
algum.

**A tela.** Na lista de usuários, um botão por linha abre *Acesso às
empresas*: todas as empresas com caixa de seleção, marcando as que a pessoa
alcança. O botão fica **vermelho quando a pessoa não tem empresa nenhuma** —
sem isso, o problema continuaria invisível até alguém reclamar que não vê
nada.

**Tirar acesso não apaga a alocação.** Preenche `fim` e `motivo_saida`, como
o modelo pedia desde o início e ninguém tinha exercitado. Quem tinha acesso a
um dado em março continua respondível em setembro.

**Ninguém tira o próprio acesso** — mesma família da regra que impede alguém
de se desativar. Para conta `dev` a tela avisa que o papel já enxerga todas,
e que alocação ali não muda nada.

Com isto, a sucessão deixa de ser o único caminho para conceder acesso — ela
continua concedendo, porque passar o trabalho implica passar o acesso, mas
agora é atalho e não gambiarra.

# DECISÕES — CRM Fiscal

> Registro datado das escolhas e do porquê. Decisão sem motivo escrito vira
> discussão de novo daqui a seis meses.

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

**2. No período da Advertising (08/2022 a 06/2024) a alíquota não se move.** Nos
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

**O que fica em aberto, e é dívida nossa.** O trabalho da Advertising termina
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
campo — na Advertising, 35.448 dos 81.157 itens de CST 60. Nas outras, a ficha
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

Medido na Advertising: 47.048 saídas passam a bater exatamente com a base que a
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

**O que a pesquisa achou.** O benefício que o fornecedor da Advertising aplica é
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
meses a partir de 15/01/2021, ou seja até 14/01/2023; o trabalho da Advertising
(08/2022 a 06/2024) pega essa faixa até 14/01/2023, mas as notas do fornecedor
mostram 12% também ali. Prorrogações: Dec. 67.524/2023 (31/12/2024), 69.292/2025
(31/12/2025), 70.293/2025 (31/12/2026).

**O problema.** O **§ 1º** do artigo 34 diz que a redução **não se aplica a
saída destinada a consumidor final**, e a **RC 23455/2021** é expressa: *"o
benefício fiscal de redução da base de cálculo do artigo 34 não poderá ser
aplicado no cálculo do valor do imposto a ser recolhido a título de substituição
tributária"*. A venda da Advertising a consumidor final é exatamente o
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
Advertising confrontaram a 4%, 7%, 8%, 9,5% e 12% — alíquotas de **compra
interestadual**, e uma delas (9,5%) nem existe: era a mediana de um dia com uma
entrada a 7% e outra a 12%. Essas linhas sozinhas respondiam por R$ 21,9 mil dos
R$ 24,3 mil de ressarcimento do enquadramento 1.

**A correção.** O confronto do enquadramento 1 é de uma saída **dentro do
estado**: a alíquota e a redução de base só podem vir de entrada interna. No XML
o CFOP é o do emitente (5.xxx é interna); na EFD é o nosso (1.xxx). Mercadoria
que só entrou de fora fica sem alíquota, contada, como já era antes.

---

## 2026-09-17 — Sem 0200, a alíquota vem da nota de entrada

**O que se via.** 13.909 saídas da Advertising ficavam sem valor de confronto —
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
precisaram desse último recurso. Os quatro códigos da Advertising têm NCM no
XML da saída (3305.90.00, 3304.99.90 e 3401.20.10), então todos são alcançados.

---

## 2026-09-17 — A redução de base da entrada entra no ICMS efetivo da saída

**O que se via.** O complemento do enquadramento 1 da Advertising dava
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

**O que muda na Advertising.** Nas 44.469 linhas de saída de enquadramento 1 e
3, o ICMS efetivo cai de R$ 950,2 mil (alíquota cheia) para R$ 463,7 mil, e o
complemento de R$ 623,1 mil para R$ 139,1 mil — a RVZ apurou R$ 148,8 mil com
os 13%/6% dela.

**O que ainda falta.** Registrar o fundamento legal do benefício de carga 12%
por NCM: hoje o sistema só sabe o que a nota de entrada declara.

---

## 2026-09-17 — Estoque negativo abre a ficha, em vez de tirá-la do total

**O que se via.** Na Advertising, 6 mercadorias ficavam com saldo negativo em
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

**Na Advertising:** a planilha "Canceladas-Devoluções" passa de 425 para 180
chaves, e a do cliente de 890 para 885. As devoluções escrituradas voltam à
movimentação.

---

## 2026-09-17 — A base da multa sem valor no XML vem da nota vizinha

**A pergunta que estava aberta.** Na Advertising, a saída não escriturada é
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

**Na Advertising:** 2.238 itens de saída sem ICMS, todos com referência — venda
6.108 do mesmo código, mediana de 0 dia de distância e máximo de 7. ICMS das
saídas R$ 50.643,67, multa R$ 37.985,16 (a RVZ: ICMS R$ 69.962,86 a 18% sobre o
valor, multa R$ 52.472,14 antes da SELIC). Entradas: todas com valor no XML,
multa R$ 89.463,60.

---

## 2026-09-17 — O de-para da Advertising pelo sistema, contra o da RVZ

**Como se testou.** A Advertising entrou no sistema como um trabalho de verdade
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
e nenhuma proposta a mais. No Amigão, as propostas não mudaram (2 antes e depois).

---

## 2026-09-17 — Certificado digital não se abre nem se lista

**O risco.** A inspeção do lote lê o começo de todo arquivo da pasta e grava o
nome de cada um. A pasta da Advertising tem `05 - CERTIFICADO` e
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

**Medido na Advertising:** inspecionar a raiz inteira classificou 1.098
arquivos em 18 s, nenhum de caminho de certificado, e avisou das 2 pastas.

---

## 2026-09-16 — A mesma nota em vários XML, a nota denegada e o lote que muda de tipo

**A pergunta do Victor:** como a v0.54 trata a duplicidade de XML, no caso de
reimportar a pasta de um lote antigo. Medido na Advertising, três coisas.

**1. Reimportar não reclassificava.** Arquivo com o caminho já no trabalho era
"já importado" e ficava com o tipo de quando entrou: o zip de 2026-09-15
continuava `compactado` e o evento continuava `xml_outro`, e a importação
recusava com 409. Agora a inspeção devolve o tipo gravado, e o registro atualiza
onde está o arquivo cujo tipo mudou — sem lote novo, sem remover o lote antigo.
Remover e importar de novo continua possível, mas não é mais o caminho.

**2. Nota denegada.** O sistema não olhava o `cStat` do protocolo. Na
Advertising, 16 notas com uso denegado (301/302); 15 entraram na contingência
(R$ 130,83 de multa) e contavam como documento entregue na conferência. Agora
só 100 e 150 autorizam; a denegada sai das etapas 2 e 3 com todas as cópias,
contada e avisada. O XML sem protocolo (do ERP) e o CF-e continuam valendo.

**3. Cópias da mesma chave.** Das 179.417 XML que o lote da Advertising deixa
entrar (os 12 zips idênticos já ficam de fora pelo hash), 28.407 chaves estão em
mais de um arquivo: 29.306 arquivos a mais. Em 22.726 os bytes diferem — só a
declaração `<?xml ...?>` — e nenhuma cópia diverge no que se lê. Mesmo assim, a
regra passou a ser explícita: a cópia com protocolo autorizado vence a sem
protocolo; entre iguais, a primeira na ordem do caminho. O parquet é gravado em
fluxo, então a cópia melhor que chega depois é gravada também, com `leitura`
maior, e uma passada no fim deixa uma por chave — só quando houve troca ou nota
denegada. A etapa 2, que descartava a repetida sem dizer, agora conta.

**Na Advertising, depois da regra:** etapa 2 em 19,7 s, 119.714 chaves (as 16
denegadas fora), 29.306 repetidos; etapa 3 em 96 s, 119.713 notas e 132.446
itens, nenhuma cópia trocada (todas tinham protocolo).

---

## 2026-09-16 — XML dentro de zip, sem extrair

**O caso.** A Advertising entregou 357.948 XML em 26 zips — e 290 mil deles em
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

**Medido na Advertising:** classificar os 26 zips, 7,6 s; contar os XML, 3,2 s;
a leitura da etapa 2, 33 s, com 119.730 chaves — as mesmas 119.729 da leitura
completa feita antes, mais uma nota sem item. Dois zips cuja amostra caiu num
evento ficaram sem CNPJ na primeira versão; agora a amostra prefere nota, e o
evento de cancelamento de CT-e (também 110111, mas com `<chCTe>`) não conta.

---

## 2026-09-16 — A contingência das notas não escrituradas

**O que é.** Nota não escriturada não entra na ficha, mas o fisco que a achar
fora da EFD cobra multa, e o cliente precisa do número para decidir se
retifica. A RVZ calculou na Advertising; aqui sai na etapa 3, que é onde o XML
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

**Na Advertising.** Entradas: 19.432 notas, R$ 908.908,64, multa
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

**Na Advertising.** As duas listas da pasta (a extraída pela RVZ e a do cliente)
dão 1.011 chaves; 911 estão na EFD, 814 já como canceladas e **97 como
regulares** — 101 movimentos de saída, R$ 9.968,61, que agora saem.

**Lote antigo.** Evento importado antes da v0.54.0 ficou como `xml_outro`; a
pasta precisa ser inspecionada de novo para virar `xml_cancelamento`.

---

## 2026-09-16 — O motor abre processos de verdade

**O que se viu.** A primeira rodada da v0.53 no Amigão (#57) correu dentro do
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

Na primeira chamada do de-para sobre o Amigão (97 s, 72 estabelecimentos), o sufixo
propôs `1024078 → 102407` com "sufixo 8, repetido em 4 pares": num catálogo
numérico grande, código + um dígito coincide por acaso. O sufixo passa a valer
só entre pares de descrição compatível, e a repetição conta só esses pares. Na
Advertising, 41 pares em vez de 46 — os kits seguem ligados pela regra do kit — e
o ressarcimento de R$ 274.950,74 para R$ 274.878,90.

---

## 2026-09-16 — O que a CAT 42 da Advertising ensinou: XML, de-para, art. 271 e X.949

**De onde veio.** A CAT 42 que a RVZ entregou para a Advertising Operations
(43.112.531/0004-21, 08/2022 a 06/2024, R$ 406.362,34) foi comparada com o que
o sistema faria. **Decisões do Victor:** corrigir tudo, nesta ordem — itens do
XML, de-para automático com revisão na tela, enquadramento 4 com o art. 271,
X.949 fora da ficha — e validar rodando a base deles.

**1. O item do XML.** A EFD deles tem 92.928 NF-e de saída sem C170: sem ler o
XML, o sistema não teria saída nenhuma — o mesmo buraco das lojas de SP do
Amigão. A etapa 3 passou a ler o item de NF-e, NFC-e e CF-e: completa o
documento escriturado sem item e fica ao lado do C170 que existe, com os
valores do XML vencendo na etapa 4. O que a base real mostrou, e virou regra:

| Achado | Regra |
|---|---|
| 72 mil CT-e lidos como nota sem chave (o CT-e cita as notas num `infNFe`) | NF-e só com `infNFe` dentro de `NFe` |
| 13.676 NF-e declaradas UTF-8 com o `º` em Latin-1 | relê como Latin-1 quando o UTF-8 falha |
| C170 com o custo (ST e IPI embutidos) e XML com a mercadoria: nenhum item casava pelo valor | casa pelo número do item com quantidade ou valor; contagem só em nota de um item |
| 44.781 NF-e de venda a pessoa física sem enquadramento | `indFinal` do XML diz consumidor final (1) ou não (0) |

Resultado na Advertising: 92.723 das 93.599 saídas completadas; 211 de 215 C170
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
marketplace. Na Advertising: 46 pares propostos, todos de confiança alta; 10
códigos sem par, os mesmos que o cliente preencheu para a RVZ.

**3. Enquadramentos 2 e 4 e o art. 271.** A coluna 21 é o ICMS próprio das
entradas mais recentes da ficha até a saída (item 3.3.8, a regra que já valora a
abertura). Ressarcimento = suportado baixado − coluna 21; no enquadramento 4, a
coluna 21 é também o crédito do art. 271 (coluna 27), que a apuração soma e o
arquivo digital leva no VL_CONFR. Conferido com a Ficha 3 da RVZ: 2,15 de
suportado, 0,63 da entrada, 1,52 de ressarcimento e 0,63 de crédito. Na
Advertising, 57.440 saídas confrontadas e nenhuma pendente.

**4. X.949 fora da ficha.** Remessa e retorno (armazém, depósito) não são compra
nem venda: saem da ficha e ficam contados, como o uso e consumo.

**Comparação com a RVZ (fichas válidas).** Enquadramento 4, ressarcimento +
crédito: R$ 389.531,17 contra R$ 548.490,22; crédito do art. 271: R$ 114.663,40
contra R$ 160.557,57; complemento: R$ 178.109,69 contra R$ 148.770,53. A
diferença está nas 6 fichas que ficaram negativas e fora do total: a RVZ incluiu
na CAT notas de entrada não escrituradas ("PRESENTES NA CAT 42" na planilha
dela), e o sistema as deixa de fora. **Decisão do Victor (16/09/2026): continua
de fora.** Incluí-las foi pedido particular da Advertising na época, não regra do
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

**O que caiu.** A etapa 4 do Amigão falhou duas vezes por falta de memória
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

**CSV.** A Ficha 3 de uma loja do Amigão (1,17 milhão de linhas) levava 60 s
para virar CSV, escrita linha a linha pelo módulo `csv`; o dossiê de uma base
do tamanho da BOA faz uma por filial. Agora o DuckDB escreve o corpo e o Python
só o cabeçalho com o BOM. Os bytes são os mesmos — `;`, aspas só onde precisa,
CRLF, vírgula decimal, `Sim`/`Não` —, e um teste compara as duas escritas para
que não divirjam.

**Arquivos digitais.** Escrever e pré-validar um arquivo é Python puro e não
depende dos outros: num perfil de 12 arquivos do Amigão, 48% do tempo era
pré-validação e 40% escrita. A etapa 7 passa a separar em disco, por
estabelecimento e mês, o que cada arquivo lê, e cada processo filho monta o
seu; os 12 arquivos caíram de 15,8 s para 7,9 s com o mesmo SHA-256. A
pré-validação dos arquivos do cliente segue a mesma ideia: o processo principal
lê só a primeira linha de cada arquivo e decide ali o que é repetido,
substituição e nome; a leitura inteira vai a um filho, e os totais são somados
no fim, só com os arquivos que valem. O zip aninhado fica no disco até o fim,
porque um filho pode estar lendo dele. Sessenta prévias do Amigão, metade soltas e metade
num zip: 41,2 s com um processo, 10,0 s com seis, o mesmo resumo e as mesmas
linhas.

Quantos processos: `CAT_PROCESSOS_DO_ARQUIVO_DIGITAL`, e 0 escolhe núcleos
menos 4, entre 1 e 4, para deixar folga à API e ao Postgres — o teto é pela
memória: cada filho pode passar de 1 GB, e a apuração do suportado do Amigão
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

## 2026-09-16 — Abertura pelas entradas anteriores, uso e consumo fora da ficha, 5929 como a BOA

**Abertura sem imposto.** O inventário do Amigão veio sem ICMS em 842 mil
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
  antes dele não entra na ficha: serve para valorar a abertura. Para valer no
  Amigão, é preciso importar as EFD de antes de 01/2021.
- A etapa 6 abre o 1050 do primeiro mês com esse ICMS, e não mais com zero.

**Uso e consumo.** 1.407, 1.556, 1.557, os 2.xxx e as saídas 5/6.556 e 5/6.557
não são estoque de comercialização. **Decisão do Victor:** saem da ficha e ficam
contadas (`fora_da_ficha.uso_e_consumo`). No Amigão eram 366 entradas.

**CFOP 5.929** (NF-e de venda já registrada em cupom). **Decisão do Victor:** fica
como a BOA transmitiu e a SEFAZ aceitou — saída comum, enquadramento 0. Só
documentado; no Amigão não há nenhuma linha.

---

## 2026-09-16 — Uma pendência por problema, com a medida de cada etapa

**O que a entrega do Amigão mostrou.** 26 pendências, e várias eram o mesmo
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

**O que o piloto mostrou.** O trabalho do Amigão nasceu como "Ressarcimento ST
2025", de 01/2025 a 12/2025, e as 884 EFD importadas eram todas de 2021. Nada
avisava: a importação aceita a base, e não havia como corrigir o cadastro sem
ir ao banco.

**Decisão do Victor.** O trabalho é de 2021: recadastrar. Para isso o cadastro
passou a ser editável pela API (`PATCH /api/projetos/{id}/cadastro`), por quem
escreve, sempre com evento no histórico — o de e o para do nome e do período.
Nada mudando é recusa, não evento vazio.

**E a divergência passa a aparecer.** O detalhe do trabalho diz de quando é a
base e quantas EFD caem fora do período (comparando o mês, não o dia gravado).
A tela avisa e oferece a edição. No Amigão, antes do recadastro: 884 de 884
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

**Piloto (execução 52, Amigão).** 0,9 s. 775 competências no relatório — 234
prévias de SP e 541 fora de SP —, nenhum estabelecimento no dossiê, 26
pendências (16 travam, 7 pedem atenção, 3 informam). O pacote leva o relatório
e o manifesto. Dois acertos que o piloto mostrou: o relatório passou a dizer o
**período apurado** (dos dados) ao lado do **período do cadastro** — o trabalho
está cadastrado como 2025 e os dados são de 2021 —, e a etapa 6 passou a somar
o total com as competências já arredondadas (dava R$ 66.681,16 no resumo e
R$ 66.681,15 somando as competências).

**O que fica para a lapidação.** O Victor, como dev, não aprova — a entrega do
piloto espera um gestor; a Ficha 3 do dossiê em CSV pode levar minutos numa
base do tamanho da BOA; e o `PLANEJAMENTO.md` ainda descreve o roteiro antigo.

---

## 2026-09-16 — Revisão da etapa 7: o que se conferiu e o que se corrigiu

**Como se conferiu.** Sete arquivos CAT 42 que a SEFAZ aceitou da IRMAOS BOA
(2021 a 2024) medidos registro a registro contra o gerador, e a Ficha 3, os
saldos e as 234 prévias do piloto do Amigão (execuções 48 a 50) lidos de volta.
O gerador já fazia igual à BOA no que decide o arquivo: CRLF e Latin-1; 1050
só de item movimentado no mês (nos sete arquivos, nenhum 1050 sem 1100); 0150
com os fornecedores das NF-e e o próprio estabelecimento; todos os CFOPs de
devolução que aparecem lá (1202, 1411, 5202, 5411, 6411) no conjunto de
devoluções; na Ficha 3 do Amigão de SP, nenhuma quantidade com mais de 3 casas,
nenhum nº de item acima de 999 e nenhuma linha repetida.

**O que se corrigiu.**

| Defeito | Onde pesava | Correção |
|---|---|---|
| A alíquota do confronto (enq. 1 e 3) era a do cadastro do **fim do período** | 23.065 itens do Amigão mudam de alíquota em 2021 (12% → 13,3% em fevereiro): a venda de janeiro confrontava com a de dezembro, e o VL_CONFR ia errado para o arquivo | razão usa a alíquota do 0200 do **mês da saída**; a mais recente só onde o mês não traz. Resumo conta `saidas_com_aliquota_do_mes` |
| O 0200 do arquivo de janeiro saía com descrição e alíquota de dezembro | o manual pede a última ocorrência **do período**, que é o mês | 0200 do `itens_da_efd` do mês, campo a campo; a **unidade** fica a mais recente, que é a da ficha convertida (mudar de unidade no meio quebraria o saldo) |
| A data do movimento era a **emissão** (DT_DOC) | 5,55% das entradas do Amigão entraram em mês diferente do emitido: custo médio deslocado e DATA do 1100 fora do mês | a movimentação usa a data de entrada/saída (DT_E_S); a emissão só quando a EFD não a informa. A conferência com o XML continua pela emissão |
| O 0150 só olhava a EFD do mês | 127 das 234 prévias travavam: a nota escriturada em outro mês cita participante que só está no 0150 de outro mês | procura na EFD do mês e, sem ele, na mais recente do estabelecimento |
| ICMS negativo com estoque positivo caía na trava "saldo negativo", com texto de ficha retirada | 813 saldos de fichas válidas do Amigão: devolução de compra sobre abertura sem ICMS (item 3.3.8) | trava própria, `valor_negativo`, com o que fazer certo |
| Entrada sem ICMS suportado ia como `0,00` sem ninguém saber | 95.904 entradas de SP do Amigão (7%) | contada por arquivo e no resumo (`entradas_sem_icms`), com aviso no log e na tela. Não trava: zero pode ser verdade |
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

**Para valer por inteiro no Amigão**, as etapas 3 a 6 rodam de novo: a data de
entrada muda a movimentação, e a alíquota do mês muda o razão.

**O que continua aberto.** O 1200 sai sem SER (a série é lida no C100 e não
chega à movimentação); ECF_FAB, 0205 e o fato gerador sem documento (CHV 0,
item 999); entre dois arquivos do cliente do mesmo mês, vale o primeiro lido, e
não a substituição (COD_FIN 02); na Ficha 3 do Amigão entram entradas de uso e
consumo (1407, 1556, 2556, 2557 — 91 linhas) e o 5929 (lançamento de cupom
também registrado em ECF) não é tratado como duplicidade; a abertura sem ICMS
(item 3.3.8) segue sendo a causa do complemento inflado e do ICMS negativo.

---

## 2026-09-16 — Pré-validar o que o cliente já transmitiu

**Decisão do Victor.** A pré-validação da etapa 7 vale **também para o arquivo
que o cliente gerou com outra ferramenta** — a auditoria da BOA e da Casa
Avenida, que já entregam a CAT 42.

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
outro, na BOA) fica listado como repetido, sem ler de novo. E o saldo inicial
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

**O formato foi medido antes de escrito.** Três arquivos reais da BOA (24, 33 e
77 MB) confirmaram o leiaute e resolveram o que o manual deixa em aberto: a
linha não começa com `|` e só termina com `|` quando o último campo é vazio;
CRLF; quantidade com 3 casas e valor com 2, sempre; nº do item com 3 dígitos;
país `1058`; todo item do 0200 tem 1050. O nome dos arquivos
(`CAT5_SP_<CNPJ>_<M>_<AAAA>.txt`, mês sem zero) é o que a BOA usou.

**A pré-validação recompõe a Ficha 3 a partir do próprio arquivo** — é o que o
Pós-Validador faz. Lendo só o 1050 inicial e o 1100, o mesmo `RazaoDoItem` do
sistema chegou ao 1050 final em **100% das quantidades** e em 99,99% dos
valores a até 5 centavos, nos arquivos da BOA. Daí as severidades: quantidade
que não fecha é **erro**; valor fora de 5 centavos é **aviso**, com a
diferença dita.

**Calibrada contra o que a SEFAZ aceitou.** Nos quatro arquivos reais a
pré-validação não acusa erro nenhum (875.789 linhas em 25 s o maior). Duas
coisas viraram aviso por isso: item de nota com **dois códigos** (3 casos num
arquivo aceito — kit desmembrado, provavelmente) e saldo em valor de item
zerado em que a BOA guardou resíduo (R$ 6,27 e R$ 29,60).

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
arquivos CAT 42 que a IRMAOS BOA transmitiu (2022 a 2024, de 24 a 77 MB) foram
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
14/09/2026), que é o que o manual diz. No piloto do Amigão, o R$ 1,53 milhão de
complemento vem inteiro desse enquadramento.

**Decisão do Victor.** A escolha é **por trabalho**: `projeto.venda_a_consumidor`
vale `enquadramento_1` (o manual: ressarcimento e complemento) ou
`demais_saidas` (como a BOA: só a perda e a interestadual geram ressarcimento).
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

O que o quadro diz, e que nenhuma tela dizia antes: **o Amigão tem 22
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

**O que o piloto mostrou.** Primeira montagem do razão sobre o Amigão
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
dados completos (BOA) e não tem o que fazer com saída que o estoque não
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

**O que o Amigão mostrou, e por que isso importa.**

| Medida | Resultado |
|---|---|
| Registros 0220 na EFD | **nenhum** (uma filial: 17.745 itens no 0200, zero 0220) |
| Entradas com rótulo diferente do cadastro | 56.986 de 8.761.002 (0,65%); UN→CX 31.799, CX→FD 14.446 |
| Quantidade da EFD = "Qtde;Unitária" do relatório, 05/2021 | **100%**, em todos os pares de unidade — inclusive rótulo CX com 2.500 unidades |

Ou seja: no Amigão a quantidade da EFD **já vem na unidade básica**, e o rótulo
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
cada mercadoria. No Amigão, 36,5 milhões de documentos de saída (R$ 5,8
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
PDV, que traz a própria loja ("005" → 11.517.841/0034-55 pelas duas). Linha que
nenhuma pista alcança fica contada, não suposta.

**O cálculo é o do domínio, linha a linha.** O mesmo `RazaoDoItem` conferido
contra a Ficha 3 da BOA. O SQL junta, filtra e ordena; não calcula.

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

**Rodou pela tela sobre o Amigão inteiro** (execução 11): 94 relatórios do
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

**Medido na base real (Amigão, 2021, movimentação da execução 9, com os três
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
calculada** da IRMAOS BOA, uma filial e um mês, reconstruindo cada ficha a
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

**Onde estão as referências.** `Z:\GRUPO PLURIX\Implementação
. Baixa de
Estoque\Trabalho ST (RVC)` tem quatro empresas. A **BOA** traz a Ficha 3
completa, 35 colunas, de janeiro de 2021 a dezembro de 2025, com todos os
enquadramentos. O **SUPERPAO** traz um book consolidado de 1.255.373 linhas,
mas só de CFOP 5.927, isto é, só o enquadramento 2.

**O book do Superpão confirmou a fórmula do suportado.** Em 100% de 1.242.621
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

Medido nos relatórios do Amigão, três arquivos de 2020.01, 670.156 linhas:

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

**Por quê.** Medição na BOA: 24.730 itens distintos, 98,1% com código de barras,
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

**Medido.** 135 relatórios reais do Amigão: 133 lidos (99 de movimento, 20 de
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
cheio de linha sem CFOP — no Amigão o campo vem escrito `'  .      '`, e são
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
Sulamericana tem **7.036 arquivos e 100 GB**; a de relatórios do Amigão tem
**53,9 GB**. Subir isso pelo navegador não é lento, é inviável. E o dado já
vive no servidor de arquivos, com a política de guarda da casa — duplicá-lo
dentro do sistema só multiplicaria material sigiloso.

**Consequência 1.** A varredura é paralela: identificar arquivo em disco de
rede é espera, não cálculo. Na pasta do Amigão, 325 arquivos caíram de **49 s
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

**Por quê.** Medido em 20 arquivos reais da Sulamericana: **307.319 dos 321.337
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

**Por quê.** Num uso real: EFD do estabelecimento `43112531000189` contra XML
do `43112531000421` — mesma empresa, filiais diferentes. Resultado: 10.605
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
na mesma pasta é o caso comum (pasta `10 - RETIFICAÇÃO SPEDS` do Advertising).

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
pastas (a Sulamericana tem `EFD Fiscal - EFD ICMS IPI`, `Sped FISCAL
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
(Sulamericana, 884 EFD; Advertising, 68 EFD), o C170 só existe nas
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

**Rodada real, logo depois (Sulamericana, 884 EFD, 44 min).** 37.930.719
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

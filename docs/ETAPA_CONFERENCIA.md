# Etapa de Conferência — cruzar as notas com a EFD

A primeira etapa de todo trabalho de CAT 42. Confronta o que a empresa
**escriturou** na EFD ICMS-IPI com o **documento** que ela entregou, e separa a
diferença em duas listas que têm destinos opostos.

Existe porque as duas fontes quase nunca fecham, e porque a apuração não pode
começar sem saber de que tamanho é o buraco.

---

## 1. As duas listas, e por que elas não se misturam

| lista | o que é | o que se faz com ela |
|---|---|---|
| **Pendentes de documento** | a nota está na EFD, o documento não veio | **cobra-se do cliente** |
| **Não escrituradas** | o documento está na pasta, a nota não está na EFD | **sai da análise** |

A assimetria é a regra fiscal, não uma escolha de engenharia:

- **Sem o documento não há ICMS-ST retido**, e sem ST retido não há
  ressarcimento daquela nota. Por isso a pendência é cobrança.
- **Ressarcimento se pede sobre o que foi declarado ao fisco.** Incluir nota
  que não está na EFD é construir crédito sobre documento que a SEFAZ não vê.
  Por isso a não escriturada sai — vira aviso na tela, para alguém decidir se é
  erro de escrituração do cliente.

## 2. A amarra é a chave de acesso

Os 44 dígitos, e só eles. A chave é única por documento e está presente nos
quatro lugares que importam:

| fonte | onde |
|---|---|
| EFD, nota fiscal | `C100`, campo `CHV_NFE` |
| EFD, cupom (CF-e-SAT) | `C800`, campo `CHV_CFE` |
| XML | no próprio documento |
| relatório gerencial | coluna `Chave DFe` |

**Não se casa por número e série.** Série se repete entre estabelecimentos e
número reinicia — casar assim junta documentos de filiais diferentes e o erro
só aparece na apuração, quando já é tarde.

**Documento da EFD sem chave** (nota modelo 1, cupom antigo) não tem como ser
confrontado. Ele **não é descartado**: entra na lista marcado como `sem_chave`,
identificado por CNPJ + modelo + série + número + data. Não é pendência
resolvida nem por resolver — é pendência de conferência manual.

## 3. O caminho do dado

Três passos, sempre nesta ordem, fora da requisição HTTP. A API cria a execução,
devolve o identificador e a tela acompanha o progresso.

```
1. EFD    → parquet com todo C100 e C800
2. pasta  → parquet com a chave de cada XML e de cada linha do relatório
3. confronto (DuckDB) → três listas em parquet + resumo no banco
```

Código:

| passo | arquivo |
|---|---|
| orquestração | `backend/cat/aplicacao/casos_de_uso/conferir_documentos.py` |
| extração das duas fontes | `backend/cat/infraestrutura/analitico/extracao.py` |
| o confronto em DuckDB | `backend/cat/infraestrutura/analitico/confronto.py` |
| as regras e o resumo | `backend/cat/dominio/icms/cat42/conferencia.py` |
| as planilhas | `backend/cat/infraestrutura/planilhas/conferencia.py` |

Os parquets ficam em **disco local**, numa pasta por execução. Disco de rede
perde gravação longa (ARQUITETURA §8) e uma execução dessas grava por minutos.

### Passo 1 — a EFD

Lê **só `C100` e `C800`**. Duas regras de leitura que valem tempo medido:

- **filtrar antes de quebrar a linha** — comparar os primeiros bytes e só então
  dividir em campos valeu **2,4 vezes** numa varredura de 119,82 GB. Num arquivo
  real há 92.335 linhas `C190` contra 39.265 `C100`: a maioria das linhas não
  interessa;
- **ler em binário** — o prefixo é ASCII, então a comparação funciona em bytes
  e só o que passa é decodificado. O SPED é ISO 8859-1, lido como `latin-1`.

Grava de 250 mil em 250 mil linhas.

De cada documento saem: chave, modelo, situação, número, série, data,
data de entrada/saída, valor, participante, operação (entrada/saída) e emitente
(própria/terceiro).

**Retificadora substitui a original por inteiro.** Se o lote tem as duas do
mesmo estabelecimento e período, a original fica fora da leitura e o resumo diz
quantas foram.

### Passo 2 — a pasta

Duas origens possíveis, e as duas podem conviver no mesmo lote:

| origem | rótulo na tela |
|---|---|
| `XML` | XML |
| `GERENCIAL` | Relatório do cliente |

Dois filtros aqui:

- **XML repetido** (solto e dentro do zip, ou em dois zips) vale uma vez; o
  resto é contado e aparece no resumo;
- **XML com protocolo de uso denegado** (`cStat` 301, 302, 303) **não é
  documento**. A chave sai da lista da pasta: a SEFAZ não autorizou a nota.

### Passo 3 — o confronto

Em DuckDB, sobre os dois parquets. Três saídas:

| arquivo | conteúdo |
|---|---|
| `sem_documento.parquet` | pendentes — o que se cobra |
| `nao_escrituradas.parquet` | o que está na pasta e fora da EFD |
| `conferidos.parquet` | o que fechou, com de qual arquivo veio o documento |

Vão para parquet e não para o Postgres porque qualquer uma pode ter milhões de
linhas — numa base real foram **37,9 milhões** de documentos. **O que vai para
o banco é só o resumo**, que é o que a tela mostra e o que fica registrado na
execução.

A lista de pendências é **agrupada por chave**. Uma nota pode estar na EFD mais
de uma vez de forma legítima — emitida por um estabelecimento e recebida por
outro do mesmo grupo são dois `C100` da mesma chave. Pedir duas vezes o mesmo
XML ao cliente é ruído, então cada chave vale uma linha e as repetições viram a
coluna **Ocorrências na EFD**.

Cada pendência sai classificada:

| `classificacao` | significado |
|---|---|
| `a_cobrar` | tem chave e a situação espera documento — é cobrança |
| `sem_documento_a_pedir` | cancelada, denegada ou numeração inutilizada |
| `sem_chave` | não dá para confrontar; conferência manual |

As situações de que **se espera** documento são `00`, `01`, `06`, `07` e `08`
(regular, extemporâneo e complementar, da Tabela 4.1.2). O resto continua na
lista, marcado.

**Nada sai da lista.** A primeira versão excluía cancelada e denegada por serem
improváveis de cobrar, e isso estava errado por um motivo que só aparece
pensando no ciclo inteiro: o trabalho não termina na primeira rodada. O que for
excluído nunca mais é olhado — some do controle sem ter sido resolvido. Marcar é
reversível; excluir não é. **Quem decide pedir ou não é quem trabalha, não o
sistema.**

## 4. Como rodar

Pela tela, na etapa **Conferência** do trabalho. Por API:

```
POST /api/projetos/{projetoId}/conferencias      cria a execução
GET  /api/projetos/{projetoId}/conferencias      lista as execuções
GET  /api/conferencias/{execucaoId}/planilhas/{qual}
```

`qual` é `a-cobrar`, `nao-escrituradas` ou `conferidas`, e aceita filtro por
modelo — é o que torna a lista de cobrança utilizável, porque separa nota de
cupom.

Antes de rodar, o lote precisa ter **EFD** e **pelo menos uma origem de
documento**. Sem documento para confrontar, a conferência não diz nada, e ela
avisa isso em vez de devolver zero.

## 5. Como ler o resultado

O número que resume tudo é a **cobertura**: a fração das notas escrituradas que
têm documento (`conferidos ÷ escriturados`). A etapa **fecha** quando não há
pendência nem não escriturada.

Os avisos da tela não são decoração — cada um corresponde a um erro que já
custou retrabalho:

| aviso | o que ele está dizendo |
|---|---|
| **nenhum documento casou, e não é falta de documento** | a EFD importada é de uma filial e os XML são de outra. Quando os estabelecimentos não se cruzam, nada pode casar |
| **pendências com a mesma chave mais de uma vez acima de 5%** | não é filial repetida, é **arquivo importado em dobro**. Numa base real de 37,9 milhões, 2,2% das chaves se repetiam legitimamente; o mesmo lote em dobro daria perto de 100% |
| **EFD originais substituídas** | havia retificadora do mesmo estabelecimento e período |
| **documentos sem chave de acesso** | nota modelo 1 ou cupom antigo; vão para conferência manual |
| **XML com uso denegado** | a SEFAZ não autorizou; não contam como documento nem como não escriturada |
| **pendências marcadas** | canceladas, denegadas, inutilizadas ou sem chave |
| **linhas a mais com chave repetida** | **é defeito do sistema, não do dado.** A lista cobraria o cliente em dobro. Não cobre por ela; avise o suporte |

Esse último merece atenção: por construção o número é zero — o pipeline entrega
uma linha por chave. Foi medido zero em 92.786 e em 37.097.934 pendências. Se um
dia não for zero, é bug.

## 6. Rodar de novo é o normal, não a exceção

O cliente manda o que faltava e a conferência roda outra vez. Quando há execução
anterior, o resumo compara com o `sem_documento.parquet` dela e diz o que andou:

```
resolvidas, novas, ainda pendentes
```

Sem isso, a segunda rodada só diria "ainda faltam 62.973" e ninguém saberia se
houve progresso. É o que dá sentido a repetir.

## 7. As planilhas

Três botões, cada um em **xlsx** ou **CSV**, e a escolha não é de gosto:

- **xlsx é para abrir e ler.** Acima de 900 mil linhas quebra em abas — o limite
  do Excel é pouco mais de um milhão e estourar **não dá erro, corta o resto em
  silêncio**. Identificador com zero à esquerda (chave, CNPJ, série) vai como
  texto; chave de 44 dígitos virando notação científica é pior que perder o
  zero, porque parece certa e não é. Valor e data vão tipados, senão não se soma
  nem se monta dinâmica.
- **CSV é para carregar em outro lugar** — DuckDB, Power BI, banco, o sistema do
  cliente — e para quando a lista passa do que o Excel aguenta. Sai com `;`,
  vírgula decimal e BOM. **E não finge tipo para agradar o Excel:** a chave vai
  como os 44 dígitos que ela é. Abrir esse CSV com dois cliques no Excel
  transforma a chave em notação científica. Quem precisa do Excel baixa o xlsx,
  que é imune.

A geração é de **memória constante**: a lista de cobrança de uma base grande
passa de um milhão de linhas, e montar tudo em memória antes de gravar derruba o
processo.

## 8. Cuidados de operação

- **Disco.** O confronto reserva 2 GB de folga e não encosta neles. Encher a
  unidade de rascunho derruba o sistema operacional junto, não só a execução.
- **Memória.** Duas decisões no SQL existem por medição, não por estilo: tirar
  primeiro o que já tem documento e só então agrupar (a ordem inversa estourou
  5,5 GB e morreu em nove minutos numa base de 37,9 milhões), e deduplicar só o
  que se repete, em comandos separados (a versão com `UNION ALL` e `EXISTS`
  correlacionados materializou a fonte inteira: 26 GB de rascunho sem terminar
  em 88 minutos). Depois: **1,5 min com 1,9 GB de rascunho**. Quem mexer no SQL
  precisa saber disso antes.
- **`NOT IN` com subconsulta que tem `NULL` devolve nada, calado.** O confronto
  usa `ANTI JOIN` e `SEMI JOIN` explícitos.

## 9. O que esta etapa não faz

- Não calcula ressarcimento nem complemento — isso é a Apuração.
- Não decide se uma nota não escriturada deve entrar; ela só informa.
- Não busca XML em lugar nenhum. O que não está no lote não existe para ela.
- Não confere valor nem item: o confronto é de **existência do documento**, pela
  chave. Divergência de valor entre EFD e XML é outro problema, de outra etapa.

---

Leia junto: `docs/DOMINIO.md` (a regra fiscal), `docs/ARQUITETURA.md` §7 e §8
(parquet entre etapas, e por que se grava local) e §9 (as regras de Excel).

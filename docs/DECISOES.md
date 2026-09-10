# DECISÕES — Sistema CAT

> Registro datado das escolhas e do porquê. Decisão sem motivo escrito vira
> discussão de novo daqui a seis meses.

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

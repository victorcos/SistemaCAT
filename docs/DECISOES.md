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

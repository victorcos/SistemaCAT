# DECISÕES — Sistema CAT

> Registro datado das escolhas e do porquê. Decisão sem motivo escrito vira
> discussão de novo daqui a seis meses.

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

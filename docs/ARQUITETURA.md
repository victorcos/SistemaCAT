# ARQUITETURA — CRM Fiscal

> Responsabilidade única: responder "como este sistema é montado e por quê".
> A regra fiscal está em DOMINIO.md. As escolhas datadas estão em DECISOES.md.

---

## 1. O princípio que decide tudo

**Domínio puro, separado de entrada e saída.**

O cálculo do ressarcimento tem de rodar num teste de unidade com dez linhas
inventadas, em milissegundos, sem tocar em disco. Se para testar a fórmula for
preciso abrir um arquivo compactado de 119 GB, o desenho está errado.

Consequência prática: `dominio/` não importa DuckDB, nem xlsxwriter, nem
zipfile, nem FastAPI. Recebe estruturas simples e devolve resultado.

## 2. As camadas

São dois programas desde a migração de 13 e 14/09/2026 (`MIGRACAO_CSHARP.md`):
a **API em C#** (`api/`), com as mesmas camadas em projetos separados, atende
a tela — login, usuários, empresas, trabalhos, histórico, lotes, execuções,
download; e o **motor Python** (`backend/`), sem rota pública, faz o que lê
arquivo fiscal ou atravessa volume, pedido pela API pelo canal interno. O
desenho abaixo é o do motor.

```
backend/cat/
├── dominio/          regra fiscal pura, sem framework, sem I/O
│   ├── comum/        NCM, CEST, CFOP, competência, dinheiro
│   ├── icms/         o que é de imposto estadual
│   │   └── cat42/    fichas, enquadramento legal, apuração
│   ├── piscofins/    base, créditos e exclusões das contribuições
│   ├── depara/       cascata de casamento de item
│   ├── sped/         regras dos registros — servem a TODOS os módulos
│   └── notafiscal/
├── aplicacao/
│   └── casos_de_uso/ orquestra domínio + portas, uma classe por operação
├── infraestrutura/   tudo que fala com o mundo
│   ├── arquivos/     leitura em fluxo de rar, zip e txt
│   ├── analitico/    DuckDB e parquet
│   ├── planilhas/    xlsxwriter e openpyxl
│   ├── sped/         indexador por offset e extrator
│   ├── xml/          leitor de NF-e, cabeçalho e item
│   ├── ia/           agente, fila de julgamento, cache
│   └── repositorios/ Postgres
├── apresentacao/
│   └── api/          FastAPI só com o canal interno (/interno), pedido pela API em C#
└── workers/          a fila de execuções (fila.py), uma rodada por vez
```

Senha, token e usuário moram só em C# (`api/src/Cat.Infraestrutura/Auth`); o
motor não confere quem pede — confia no segredo do canal, e quem decide se a
pessoa pode é a API, antes de chamar.

O front vive em `frontend/`, em React com TypeScript, e conversa **só por API**.
Nunca importa nada do backend.

### 2.1 Um módulo por tributo

O sistema nasceu na CAT 42, e por isso a regra dela morava na raiz do domínio
como se fosse o domínio inteiro. Desde 22/09/2026 cada tributo tem o seu lugar:
**a CAT 42 é uma obrigação do ICMS**, não o contrário.

O que **não** desce para dentro de um módulo: ler SPED, ler nota fiscal, o
de-para e o lote de arquivos. Eles servem a todos — a exclusão do ICMS da base do
PIS/COFINS lê a mesma EFD que a CAT 42 lê, e duplicá-la por módulo seria o começo
de dois leitores que divergem.

## 3. Regras de dependência

Uma camada só conhece a de dentro. Nunca o contrário.

| Camada | Pode importar | Não pode |
|---|---|---|
| `dominio` | nada do projeto | tudo o mais |
| `aplicacao` | `dominio` | infraestrutura concreta, framework |
| `infraestrutura` | `dominio`, `aplicacao` | apresentação |
| `apresentacao` | `aplicacao` | domínio direto, infraestrutura direta |

`aplicacao` declara **portas**, isto é, interfaces. `infraestrutura` fornece as
implementações. É o que permite trocar Postgres por outra coisa, ou testar um
caso de uso com um repositório falso.

## 4. Um módulo por frente, nunca por cliente

Cliente é **dado**, não código. Quando entrar a quinta empresa, nada em
`backend/` deve mudar. Se alguém precisar criar uma pasta com nome de cliente
dentro do código, o desenho falhou.

## 5. Processamento pesado não vive na requisição

A extração completa de uma empresa lê mais de 100 GB e leva cerca de onze
minutos. Isso vai para `workers/` com Celery, e a API devolve um identificador
de execução que o front acompanha.

Cada execução vira **linha na tabela `execucao`**, com parâmetros, bytes lidos,
linhas lidas, arquivos gerados e hash de cada um. É o que permite responder de
onde veio um número meses depois.

## 6. Leitura de arquivo grande

Duas regras aprendidas medindo.

**Uma passagem só.** Arquivos RAR sólidos re-descomprimem do início a cada
abertura. Abrir 1.152 arquivos um a um é ordens de grandeza mais lento que
despejar tudo em fluxo com `UnRAR p` e filtrar. Não se perde a origem porque
cada linha da Ficha 3 carrega CNPJ e período.

**Filtrar antes de quebrar a linha.** A mesma varredura de 119,82 GB levou 711
segundos quebrando toda linha em 35 campos, e 293 segundos comparando bytes no
início da linha. Mesma linguagem, 2,4 vezes de diferença. O gargalo raramente é
a linguagem; quase sempre é o algoritmo.

## 7. Formato intermediário

CSV é formato de **entrega**, não de trabalho. Entre etapas vale parquet: menor,
tipado, e o DuckDB lê muito mais rápido. Um extrato de 470 MB em CSV agrega em
cerca de dois segundos no DuckDB, mas relê devagar.

## 8. Escrita em disco de rede

Gerar sempre em disco local e **copiar depois**, conferindo hash. Gravação longa
direto em unidade de rede se perde. Vale também porque o drive Y está em 100% de
uso, com 36 GB livres.

## 9. Excel

Acima de 900 mil linhas, quebrar em várias abas; o limite do Excel é pouco mais
de um milhão. Usar xlsxwriter em modo de memória constante. Identificador com
zero à esquerda (CNPJ, inscrição estadual, chave da nota, série) vai como
**texto**; valor, quantidade e data vão tipados, senão não se soma nem se monta
dinâmica.

O cabeçalho é o mesmo em **toda** planilha do projeto (decisão do Victor,
18/09/2026): faixa `#001E50`, Arial 10 em negrito branco, centralizado, com
quebra de linha e altura de 51. O estilo mora em
`planilhas/conferencia.py` (`ESTILO_DO_CABECALHO`), e não em cada gerador —
planilha com cara diferente a cada etapa é o que o cliente percebe primeiro.
Uma coluna pode declarar `bloco` e `numero`: aí o cabeçalho vira três linhas —
faixa mesclada por bloco, título e o número do campo no leiaute —, que é como
sai a Ficha 3. Com `constant_memory`, essas três linhas têm de ser escritas de
cima para baixo: o xlsxwriter despeja a linha anterior em disco assim que a
seguinte começa.

## 10. Onde a IA entra, e onde não entra

O cálculo do ressarcimento é determinístico e **não usa modelo**. Mandar detalhe
linha a linha para um modelo custaria três ordens de grandeza a mais e seria
menos confiável que o código.

A IA entra no julgamento: revisar resultado agregado e apontar anomalia,
decidir de-para que a cascata determinística não resolveu, e explicar divergência
ao revisor. A cascata sempre precede o modelo, e o modelo recebe candidatas, não
a pergunta em aberto.

## 11. Reaproveitamento de outros projetos

| De onde | O quê |
|---|---|
| ReenquadradorTributario-PISCOFINS | `MotorClassTrib` (hierarquia de prefixo de NCM, exceção com escopo), `MotorRegras` (escala de confiança calibrada), `PreProcessadorTexto` (stopwords de varejo), módulo de autenticação com JWT e papéis |
| Quebra de SPED | indexador por offset de byte e extrator com seek, registro `C190_ICMS`, leitor de NF-e, Gestão Fiscal (36 quadros), Consulta de Entradas (037), **crédito outorgado** (triagem de item por NCM e descrição) |

A base de conhecimento do reenquadrador é de PIS e COFINS e **não serve** para a
CAT. Reaproveitar estrutura, nunca conteúdo.

## 12. Log — requisito obrigatório, não opcional

**Todo código deste sistema tem de registrar log.** A regra é do dono do
produto e vale para módulo novo, script avulso e worker. Código sem log não
entra.

O motivo é direto: quando um erro aparece em produção, sobre um arquivo de 100 GB
que levou onze minutos para processar, não há como reproduzir rodando de novo até
entender. A informação tem de estar gravada na primeira vez.

**O que todo log precisa carregar**, em todas as camadas:

| Campo | Por quê |
|---|---|
| `execucao_id` | amarra a linha ao registro na tabela `execucao` |
| `projeto_id` e `empresa` | diz de quem é o dado |
| `usuario_id` | quem disparou |
| `etapa` | onde estava, ex.: leitura, cálculo, escrita |
| `arquivo` e `linha` | qual insumo e qual posição dentro dele |

**Regras de escrita:**

- Formato **estruturado** (JSON por linha), não texto solto. Log que só um humano
  lê não se consulta depois.
- **Nunca engolir exceção.** `except` sem log é proibido. Se a decisão for
  seguir adiante, registrar o motivo e contar a ocorrência.
- **Contexto do dado que falhou**, não só a mensagem. "Erro ao converter valor"
  não ajuda; "valor `1.2,34` inválido no arquivo X, linha 4.512, coluna
  VL_RESSARCIMENTO" resolve em segundos.
- **Contadores de descarte.** Toda etapa que ignora linha tem de informar quantas
  ignorou e por quê. Silêncio aqui vira número errado entregue ao cliente.
- **Progresso em processo longo**, com bytes lidos, linhas lidas e tempo
  decorrido, para dar para saber se travou ou está só demorando.
- **Nunca registrar senha, token ou conteúdo integral de documento fiscal.**

Níveis: `DEBUG` para desenvolvimento, `INFO` para marcos de etapa, `WARNING` para
o que foi contornado, `ERROR` para o que falhou e precisa de gente. Log de
execução fica em `data/` e no banco; o resumo de cada execução é persistido na
tabela `execucao`.

## 13. Banco

Postgres desde o início. Usuário, papel, vínculo com cliente, auditoria e
execução exigem transação e concorrência real.

Segurança em nível de linha nas tabelas de dado fiscal, com a política derivando
da alocação do usuário ao projeto. Se uma consulta esquecer o filtro, o banco
não devolve o que não deve.

## 14. Como o sistema é servido

Dois modos, e a diferença é quem entrega o front.

**Desenvolvimento.** Vite na 5173, API na 8010, motor na 8020. O front fala com a
API por caminho relativo e o Vite faz proxy — sem CORS. É o padrão, e nada
precisa ser configurado.

**Rede, para os outros usarem.** A API serve o front construído, na mesma
origem, em HTTPS:

```
cd frontend && npm run certificado && npm run build
```

e no `backend/.env`:

```
CAT_PASTA_DO_FRONT=../frontend/dist
CAT_TLS_CERTIFICADO=../frontend/certificado/dev.pem
CAT_TLS_CHAVE=../frontend/certificado/dev.key
```

Os três são opt-in: sem eles a API sobe em HTTP e não serve front nenhum, que é
o que o desenvolvimento quer — Vite rodando e a API servindo uma cópia velha por
cima seria o pior dos dois mundos.

### Por que na mesma origem

Quatro razões, e a primeira foi o que motivou tudo:

* **contexto seguro**. `http://<ip>:5173` não é, e fora dele o navegador não tem
  seletor de pasta: o download antigo segurava o arquivo inteiro na memória da
  aba, o que não passa numa lista de milhões de linhas (02/10/2026);
* **um salto menos** no caminho dos bytes. Em desenvolvimento eles vão
  disco → API → proxy do Vite → navegador; aqui o proxy sai;
* **sem CORS e sem `allowedHosts`** — some a lista de máquinas autorizadas que
  alguém tem de manter;
* o front passa a ser **arquivo estático**, que é o que ele é.

### A fronteira entre as duas coisas que a API serve

O desvio do SPA atende **qualquer** caminho. Se ele ganhar de
`/api/{**resto}`, uma rota de API inexistente devolve `index.html` com 200, e a
tela recebe HTML onde esperava JSON — "erro" sem dizer qual. O ASP.NET resolve
pela especificidade do padrão (segmento literal ganha de curinga), e
`FrontTestes` guarda isso.

**Cache**: `assets/` tem o resumo do conteúdo no nome, então nome igual é
conteúdo igual e vale cache eterno. O `index.html` é o oposto — nome fixo
apontando para os resumos novos —, e em cache deixaria a pessoa numa versão que
já não existe, pedindo arquivos que foram embora. As duas regras vivem numa
**única** `StaticFileOptions`, usada pelo `UseStaticFiles` e pelo
`MapFallbackToFile`: quando eram duas, o mesmo arquivo saía com `no-cache`
pedido como `/index.html` e sem cabeçalho nenhum pedido como `/`.

### Liberar na rede

Serve o front e escuta em `0.0.0.0`, e ainda assim nenhuma outra máquina chega:
em 02/10/2026 o Windows tinha a rede como `Public` e **nenhuma regra de entrada**
para as portas do sistema. `scripts/liberar-na-rede.ps1` faz as duas coisas que
exigem administrador — reclassifica a rede da empresa como `Private` e abre a
porta da API com perfil `Private,Domain`, que não vale em rede pública.

**Uma porta, não duas**, porque a API serve o front.

**O endereço é o IP, e o certificado cobre a sub-rede /24 inteira** para que a
troca de DHCP não o invalide — 260 entradas no `subjectAltName`. O nome da máquina
também está lá e funciona pela API (pelo Vite não: `allowedHosts` devolve 403),
mas usá-lo depende do DNS interno, e isso depende da equipe de infra. Sub-rede
diferente exige `npm run certificado -- --refazer`.

### O que ainda não é

Certificado **autoassinado**: avisa na primeira visita. Para produção de
verdade, certificado de autoridade reconhecida — ou a autoridade local instalada
em cada máquina (`mkcert -install`). E o processo ainda sobe à mão; não há
serviço nem reinício automático.

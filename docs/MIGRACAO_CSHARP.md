# MIGRAÇÃO PARA C# — CRM Fiscal

> Plano da troca da API de Python para C#. A decisão e o porquê estão em
> `DECISOES.md`, 13/09/2026. Este documento diz **como** e **em que ordem**.
> Atualizado a cada fatia entregue.

## Onde estamos

| # | Fatia | Situação |
|---|---|---|
| 0 | Fundação | **entregue em 13/09/2026, v0.28.0** — C# na 8010 repassando tudo ao motor na 8020 |
| 1 | Autenticação | **entregue em 13/09/2026, v0.29.0** — `auth/token` e `auth/eu` só em C# (apagados do Python); senha e token cruzados com o Python |
| 2 | Usuários e acesso | **entregue em 13/09/2026, v0.30.0** — as 12 rotas de `/api/usuarios`, `semear` e `emergencia` só em C# |
| 3 | Empresas e projetos | **entregue em 13/09/2026, v0.31.0** — empresas, frentes, projetos, etapas e exclusão só em C#; canal interno com o motor no ar |
| 4 | Histórico | **entregue em 13/09/2026, v0.32.0** — linha do tempo, comentário, status e sucessão só em C#; registrar evento de etapa e barrar trabalho parado seguem no motor |
| 5 | Lotes | **entregue em 13/09/2026, v0.33.0** — inspecionar, registrar, listar e remover lote e a análise da remessa em C#; leitura de disco pelo canal interno. **Falta rodada com base real** (pasta de rede, milhares de arquivos, remessa acima de 1 GB) |
| 6 | Execuções | **entregue em 13/09/2026, v0.34.0** — pedir, acompanhar e baixar planilhas de conferência e movimentos em C#; a thread da rota virou a fila do motor. **Falta rodada com base real** (conferência de base grande, planilha de milhões de linhas) |
| 7 | Desligamento | **entregue em 14/09/2026, v0.35.0** — sem repasse: o C# não leva nada ao motor, e rota desconhecida responde 404 aqui; o motor ficou só com `/interno` (a saúde também), sem documentação pública; senha, token e usuário apagados do Python; versão no arquivo `VERSAO`; Postgres obrigatório na instalação |

---

## 1. O desenho de chegada

```
                 ┌──────────────────────────────┐
  navegador ───► │  front (React)   :5173        │
                 └──────────────┬───────────────┘
                                │ /api/*
                 ┌──────────────▼───────────────┐
                 │  API em C#       :8010        │  única porta que o front conhece
                 │  auth, usuários, empresas,    │
                 │  projetos, histórico, lotes,  │
                 │  execuções, download          │
                 └───────┬──────────────┬───────┘
     canal interno       │              │  lê progresso
     (127.0.0.1+segredo) │              │
                 ┌───────▼──────┐  ┌────▼─────────────────┐
                 │ motor Python │  │      Postgres        │
                 │ :8020 interno│◄─┤  execucao = a fila   │
                 │ + worker     │  │  Alembic = dono      │
                 └──────────────┘  └──────────────────────┘
                   quebra, leitura, parquet, DuckDB, planilhas
```

**Durante a migração** o C# repassou ao Python toda rota que ainda não tinha
sido portada (proxy reverso, YARP). O front apontou para o C# desde a primeira
fatia e não percebeu a troca. **Desde a fatia 7 não há repasse:** rota que o C#
não conhece responde 404 com `detail`, e o motor só tem o canal interno.

---

## 2. Estrutura da solução

Espelha as camadas da ARQUITETURA §2 e §3, com a mesma regra de dependência:
uma camada só conhece a de dentro.

```
api/                                 (C#; o Python segue em backend/)
├── SistemaCat.slnx
├── src/
│   ├── Cat.Dominio/                 regra pura: Usuario, Papel, Cargo, políticas
│   ├── Cat.Aplicacao/               casos de uso + portas (interfaces)
│   ├── Cat.Infraestrutura/          EF Core/Npgsql, Argon2, JWT, cliente do motor
│   └── Cat.Api/                     ASP.NET Core, rotas finas, proxy, middleware
└── tests/
    ├── Cat.Dominio.Testes/          xUnit, milissegundos, sem banco
    ├── Cat.Compatibilidade.Testes/  senha e token cruzados com o Python
    └── Cat.Api.Testes/              integração contra Postgres real
```

Os sete projetos existem desde a fatia 1. O log estruturado (`Registro`) mora
em `Cat.Aplicacao`: o caso de uso registra log, e só a infraestrutura sabe o
formato em que ele sai.

| Peça | Escolha | Observação |
|---|---|---|
| Runtime | **.NET 10 LTS** | a máquina tem o SDK 8; o suporte do .NET 8 termina em novembro de 2026 |
| Banco | EF Core + Npgsql, **sem migrações** | mapeia as tabelas do Alembic |
| Senha | Argon2id em formato PHC + bcrypt legado | biblioteca escolhida pelo teste de compatibilidade, não por preferência |
| Token | JwtBearer, HS256 | mesmo segredo, mesmas reivindicações |
| Proxy | ~~YARP~~ | serviu da fatia 0 à 6; saiu na 7, com a última rota portada |
| Log | JSON por linha, mesmo formato do `cat/log.py` | ARQUITETURA §12 vale igual |
| Testes | xUnit; Postgres real no Docker | não SQLite: o Postgres é o de produção |

---

## 3. Os contratos que não podem quebrar

A migração é invisível para quem usa **só se estes pontos forem idênticos**.
Cada um vira teste antes de a fatia correspondente ser dada como pronta.

### 3.1 Senha

Resumo gravado pelo `argon2-cffi`:
`$argon2id$v=19$m=65536,t=3,p=4$<sal>$<resumo>`.

Antes do Argon2, a senha passa por `HMAC-SHA256(pimenta, senha)` e vira
**hexadecimal minúsculo** — é esse texto que entra no Argon2, não a senha.
Resumo que começa com `$2` é bcrypt legado, conferido **sem** pimenta e cortado
em 72 bytes. Depois de conferir com sucesso, regrava se estiver em formato
antigo ou com parâmetros defasados.

**Teste de pronto:** resumo gerado pelo Python confere no C#, resumo gerado
pelo C# confere no Python, senha errada falha nos dois.

### 3.2 Token

HS256, segredo `CAT_JWT_SEGREDO`, validade `CAT_JWT_MINUTOS`. Reivindicações:
`sub` (id, texto), `usr`, `pap`, `emp` (lista de inteiros), `iat`, `exp`.
A cada requisição o usuário é **relido do banco**: desativado ou sem alocação
perde o acesso na hora, mesmo com token válido.

**Teste de pronto:** token emitido por um lado é aceito pelo outro.

### 3.3 Resposta

- Erro sai como `{"detail": "<mensagem em português>"}`. O front lê `detail`
  como texto (`services/api.ts`); a lista de erros de validação do FastAPI não
  é lida e não precisa ser imitada, mas **texto em `detail` é obrigatório**.
- Toda resposta carrega o cabeçalho `X-Request-Id`; se o pedido trouxer um, ele
  é mantido e repassado ao motor, para uma linha de log casar com a outra.
- Nomes de campo em `snake_case`, datas em ISO 8601 com fuso.
- Mesmos códigos: 401 sessão, 403 permissão ou escopo, 404, 409 conflito,
  410 material apagado, 422 recusa de regra.
- O login leva no mínimo 350 ms, acertando ou errando, para não entregar pelo
  relógio quais contas existem.

### 3.4 Configuração

O C# lê o **mesmo `backend/.env`**, com o mesmo prefixo `CAT_`. Uma máquina,
um arquivo de segredos. Pimenta e segredo de token nunca têm cópia.

### 3.5 Log

Uma linha, um JSON: `instante`, `nivel`, `origem`, `mensagem`, `local`, mais o
contexto (`requisicao_id`, `usuario_id`, `projeto_id`, `execucao_id`, `etapa`).
Os mesmos nomes de campo que o Python já grava, para uma busca servir aos dois.
Senha, token e chave saem como `***`.

---

## 4. A fronteira com o motor

| Operação | Hoje | Depois |
|---|---|---|
| Conferência, movimentos | ~~a rota dispara uma thread no mesmo processo~~ | **feito (fatia 6):** o C# decide quem pode e pede por `POST /interno/execucoes`; o motor confere se há o que fazer (lote lido, conferência antes dos movimentos, nada em curso), grava `execucao` na fila e a fila do motor (`workers/fila.py`) pega com `FOR UPDATE SKIP LOCKED`, uma por vez. Rodada que estava `rodando` quando o motor caiu vira `falhou` ao subir |
| Acompanhar execução | ~~rota Python lê `execucao`~~ | **feito (fatia 6):** o C# lê a mesma tabela |
| Inspecionar pasta, analisar remessa | ~~rota Python lê o disco~~ | **feito (fatia 5):** `POST /interno/lotes/inspecionar` (o motor busca a raiz do CNPJ e o que já foi importado pelo id do trabalho) e `POST /interno/remessas/analisar` (o multipart segue em fluxo, sem limite de tamanho). O C# aplica as regras de registro e grava |
| Gerar planilha | ~~rota Python gera e serve~~ | **feito (fatia 6):** o C# pede por `POST /interno/planilhas`; o motor gera (ou reaproveita, se o parquet não mudou) e devolve o caminho; o C# serve o arquivo em fluxo e só de dentro da pasta de trabalho |
| Excluir trabalho | ~~rota Python apaga banco e pasta~~ | **feito (fatia 3):** o C# confere a senha e apaga o banco; as pastas vão ao motor por `POST /interno/pastas/apagar`, que só apaga dentro da pasta de trabalho |
| Saúde do motor | ~~`/api/saude` pública no motor~~ | **feito (fatia 7):** `GET /interno/saude`, com o segredo; o `/api/saude` do C# mostra o que o motor respondeu, ou `http 403` se o segredo não confere |

O motor só aceita conexão de `localhost` e exige um segredo interno em
cabeçalho (`X-Cat-Motor-Segredo`, valor em `CAT_MOTOR_SEGREDO` no `backend/.env`).
Não recebe token de usuário: quem decide se a pessoa pode é o C#, antes de
chamar. Sem o segredo configurado, o canal fica **fechado** (503), não aberto.
O motor não publica `/docs`, `/redoc` nem `/openapi.json`, e um teste falha se
aparecer nele rota fora de `/interno`.

---

## 5. Ordem das fatias

Cada fatia é um ramo `feat/csharp-<assunto>`, sobe versionada (MINOR) e só
fecha quando **a rota Python equivalente sai do repasse** — portar sem desligar
o original deixa duas regras vivas para divergir.

| # | Fatia | Rotas | Pronto quando |
|---|---|---|---|
| 0 | **Fundação** | `/api/saude` + repasse de tudo | as sete telas funcionam passando pelo C#; `subir.ps1` e `instalar.ps1` sobem os três processos |
| 1 | **Autenticação** | `auth/token`, `auth/eu` | testes cruzados de senha e token passando; bloqueio em 5 tentativas, 15 min e 20 idêntico |
| 2 | **Usuários e acesso** | as 12 de `/api/usuarios` | mínimo de três gestores, não alterar a si mesmo e senha provisória com as mesmas regras |
| 3 | **Empresas e projetos** | `empresas`, `frentes`, `projetos`, detalhe, exclusão | exclusão apaga a pasta pelo motor, não pelo C# |
| 4 | **Histórico** | as 6 de histórico e status | sucessão passa trabalho e acesso juntos |
| 5 | **Lotes** | `lotes`, `lotes/inspecionar`, `importacoes/analisar` | leitura de disco só no motor |
| 6 | **Execuções** | conferências, movimentos, planilhas | `tarefas.py` substituído pelo worker; rodada real de ponta a ponta |
| 7 | **Desligamento** | — | o motor não tem rota pública; routers FastAPI apagados; documentação atualizada |

As fatias 1 a 4 não tocam arquivo fiscal e dão para validar numa máquina sem
base de cliente. A 5 e a 6 pedem uma rodada com dado real antes de fechar.

As ferramentas de linha de comando (`semear`, `emergencia`) foram portadas na
fatia 2, para a regra de senha provisória não existir em dois lugares. Moram em
`api/src/Cat.Ferramentas` e rodam com `dotnet run --project api/src/Cat.Ferramentas -- <comando>`.

---

## 6. Riscos

| Risco | O que acontece | Defesa |
|---|---|---|
| Resumo de senha incompatível | ninguém entra | teste cruzado é o primeiro código da fatia 1 |
| Regra de domínio duplicada | Python e C# decidem diferente por um tempo | a rota Python sai do repasse na mesma entrega |
| Dois donos de esquema | tabela divergente em silêncio | só o Alembic migra |
| Fuso horário | `timestamptz` lido como hora local | `DateTimeOffset` em UTC no mapeamento; teste de bloqueio temporário |
| Texto de erro diferente | tela mostra mensagem trocada | mensagens copiadas do Python; teste compara `detail` |
| Três processos para subir | instalação vira ritual | a fatia 0 atualiza os scripts antes de qualquer rota |
| .NET 8 fora de suporte | sem correção de segurança a partir de nov/2026 | começar em .NET 10 |

---

## 7. Decidido na fatia 7 (14/09/2026)

- **Fonte única da versão:** o arquivo `VERSAO` na raiz, lido pela API e pelo
  motor. O `version` do `pyproject.toml` fica em `0.0.0` e não é lido
  (`VERSIONAMENTO.md` §4).
- **Nome das pastas:** `backend/` **fica**. Renomear para `motor/` moveria a
  `.venv` (que quebra), o `.env` e a pasta de trabalho com os dados reais, e as
  execuções gravadas guardam o caminho absoluto da pasta — planilha antiga daria
  410, e excluir trabalho recusaria apagar pasta "fora" da pasta de trabalho.
- **SQLite:** a instalação exige Docker e Postgres. O SQLite ficou só na
  bateria de testes do motor, que cria o esquema sem o Alembic.

## 8. O que ficou para depois da migração

- **Rodada com base real** das fatias 5 e 6 (pasta de rede, milhares de
  arquivos, remessa acima de 1 GB, conferência de base grande, planilha de
  milhões de linhas), antes de subir para a `main`.
- **O motor ainda escreve eventos** de lote e etapa na linha do tempo
  (`historico_do_projeto.registrar_de_etapa`), no mesmo formato do C#. É escrita
  de quem roda a etapa, não regra de tela, e fica onde está.

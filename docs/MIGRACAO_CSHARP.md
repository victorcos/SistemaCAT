# MIGRAÇÃO PARA C# — Sistema CAT

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
| 5 | Lotes | próxima |
| 6–7 | — | não iniciadas |

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
     chamada interna     │              │  grava execução pendente,
     (localhost, rápida) │              │  lê progresso
                 ┌───────▼──────┐  ┌────▼─────────────────┐
                 │ motor Python │  │      Postgres        │
                 │ :8020 interno│◄─┤  execucao = a fila   │
                 │ + worker     │  │  Alembic = dono      │
                 └──────────────┘  └──────────────────────┘
                   quebra, leitura, parquet, DuckDB, planilhas
```

**Durante a migração** o C# repassa ao Python toda rota que ainda não foi
portada (proxy reverso). O front aponta para o C# desde a primeira fatia e não
percebe a troca.

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
| Proxy | YARP | cada rota migrada sai da tabela de repasse |
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
| Conferência, movimentos | a rota dispara uma thread no mesmo processo | o C# grava `execucao` pendente; o worker do motor pega com `FOR UPDATE SKIP LOCKED`, uma por vez |
| Acompanhar execução | rota Python lê `execucao` | o C# lê a mesma tabela |
| Inspecionar pasta, analisar remessa | rota Python lê o disco | o C# chama o motor em `localhost:8020` e devolve o resumo |
| Gerar planilha | rota Python gera e serve | o C# pede ao motor, que gera e devolve o caminho; o C# serve o arquivo em fluxo |
| Excluir trabalho | ~~rota Python apaga banco e pasta~~ | **feito (fatia 3):** o C# confere a senha e apaga o banco; as pastas vão ao motor por `POST /interno/pastas/apagar`, que só apaga dentro da pasta de trabalho |

O motor só aceita conexão de `localhost` e exige um segredo interno em
cabeçalho (`X-Cat-Motor-Segredo`, valor em `CAT_MOTOR_SEGREDO` no `backend/.env`).
Não recebe token de usuário: quem decide se a pessoa pode é o C#, antes de
chamar. Sem o segredo configurado, o canal fica **fechado** (503), não aberto.
As rotas `/interno` não entram no repasse público nem no `/openapi.json`.

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

## 7. Pendente de decisão

- **Fonte única da versão.** Hoje é o `backend/pyproject.toml`. Com dois
  programas, sugestão: um arquivo `VERSAO` na raiz, lido pelos dois.
- **Nome das pastas no fim.** Sugestão: `api/` para o C# e, na fatia 7,
  `backend/` vira `motor/`.
- **SQLite.** A instalação sem Docker já não funciona (migração
  `62fe3d195ce5`). Com o C# testando só em Postgres, a pergunta é consertar
  ou declarar o Docker obrigatório.

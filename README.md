# CRM Fiscal

Sistema de apuração e conferência das obrigações da CAT, começando pela
Portaria CAT 42/2018 de São Paulo (ressarcimento e complemento do ICMS retido
por substituição tributária).

## Frentes previstas

| Frente | Situação |
|---|---|
| CAT 42 — ressarcimento e complemento de ICMS-ST | leiaute decifrado e fórmula validada |
| De-para de produto | cascata determinística medida e definida |
| Quebra de SPED ICMS-IPI | motor existente a portar |
| Nota fiscal (XML) | leitor de cabeçalho existente, falta nível de item |

## Documentação

Ler nesta ordem:

1. `docs/DOMINIO.md` — a regra fiscal, sem código
2. `docs/ARQUITETURA.md` — como o sistema é montado e por quê
3. `docs/CONTRATOS.md` — o que cada camada promete
4. `docs/DECISOES.md` — as escolhas, datadas e justificadas
5. `docs/PLANEJAMENTO.md` — o que já foi apurado e o roteiro
6. `docs/VERSIONAMENTO.md` — como se sobe código neste projeto
7. `docs/IDENTIDADE.md` — a paleta da marca BMS e como aplicá-la
8. `docs/MIGRACAO_CSHARP.md` — a troca da API para C#, em fatias

## Estrutura

```
api/        C#: a API que a tela usa, em migração a partir do Python
backend/    Python: o motor (leitura, DuckDB, planilhas) e as rotas ainda não portadas
frontend/   React + TypeScript, fala só por API
data/       entrada, trabalho e saída (não versionado)
docker/
scripts/
```

## Regras que não se negociam

- Domínio puro, sem I/O. O cálculo roda em teste de unidade em milissegundos.
- Todo código com log estruturado. Ver ARQUITETURA.md, seção 12.
- Cliente é dado, não pasta de código.
- Gerar em disco local e copiar para a rede depois, conferindo hash.
- Toda implementação nova sobe versionada. Ver VERSIONAMENTO.md.
- Dado fiscal de cliente **nunca** entra no repositório.

## Instalar numa máquina nova (Windows)

Três comandos, do zero ao primeiro login. Precisa de Git, Python 3.11+,
Node 20+ e .NET 10 SDK (o script instala o que faltar via `winget` com
`-InstalarPreRequisitos`) e Docker Desktop aberto — o banco é Postgres em
contêiner, sem alternativa.

```
gh auth login                           # o repositório é privado: entrar no GitHub uma vez
gh repo clone victorcos/SistemaCAT      # ou: git clone https://github.com/victorcos/SistemaCAT.git
cd SistemaCAT
.\scripts\instalar.ps1                  # venv, .env com segredos novos, banco, migrações, gestores, API C#, front
.\scripts\subir.ps1                     # motor na 8020, API na 8010, tela na 5173, abre o navegador
```

O `instalar.ps1` é idempotente e imprime as senhas provisórias dos três
gestores uma vez só — anote. Cada máquina tem o próprio `.env` (JWT e
pimenta não viajam) e o próprio banco: usuários, empresas e trabalhos não
vêm junto do repositório, e o dado fiscal do cliente continua onde está —
de fora do escritório, as pastas em `Z:` só existem pela VPN.

## Como rodar

### No dia a dia: dois atalhos

Quem só vai usar o sistema não precisa de terminal. Os atalhos ficam na Área
de Trabalho e são criados uma vez por máquina:

```
.\scripts\atalhos.ps1          # cria "Sistema CAT" e "Sistema CAT - Parar"
```

| atalho | o que faz |
|---|---|
| **Sistema CAT** | sobe o que faltar e abre a tela. Se já estiver no ar, só abre a tela |
| **Sistema CAT - Parar** | derruba motor, fila, API e tela. O Postgres fica de pé |

O `abrir.ps1`, por trás do primeiro atalho, existe porque o `subir.ps1`
**recusa** subir com porta ocupada — e com razão, já que duas cópias no ar
fazem a tela falar com o processo errado sem nenhum aviso. Num atalho de um
clique isso vira beco sem saída, então o `abrir.ps1` separa os três casos:
já no ar (abre a tela), parado (sobe) e pela metade (manda parar antes).
Quem decide se está no ar é o `/api/saude`, não a porta: processo travado
mantém a porta aberta e não responde à tela.

O `parar.ps1` para **por porta**, não por janela, e cuida de dois casos que
fechar as janelas à mão não resolve:

- a **fila** (`workers.rodar`) não escuta porta nenhuma — parar por porta
  nunca a alcançaria, e ela ficaria rodando etapa com o resto derrubado;
- o **neto órfão do uvicorn** sobrevive à morte do pai e continua segurando a
  8020, com o socket atribuído a um PID já morto (24/09/2026). O que o
  identifica é o pai não existir mais, não a linha de comando.

### À mão

São três processos. A tela fala só com a API em C#, e a API pede ao motor
Python, pelo canal interno, tudo o que é de disco: ler lote e remessa, conferir,
extrair movimentos, gerar planilha (`docs/MIGRACAO_CSHARP.md`). O motor não tem
rota pública. O `subir.ps1` sobe os três; à mão, é assim.

Banco:

```
docker compose -f docker/docker-compose.yml up -d
```

Motor Python:

```
cd backend
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
cp ../.env.example .env          # e preencha CAT_JWT_SEGREDO e CAT_MOTOR_SEGREDO
alembic upgrade head                     # cria o esquema
dotnet run --project ../api/src/Cat.Ferramentas -- semear   # cria os três gestores
python -m uvicorn cat.apresentacao.api.app:app --reload --host 127.0.0.1 --port 8020
```

API em C# (lê o mesmo `backend/.env`):

```
cd api/src/Cat.Api
dotnet watch run --non-interactive --no-launch-profile
```

Front:

```
cd frontend
npm install
npm run dev
```

A tela abre em http://localhost:5173. Quem está no ar, e com qual versão de
cada lado: http://localhost:8010/api/saude.

Para entregar o front a quem vai desenhar — rotas, telas, componentes, tokens,
endpoints e os buracos de navegação, tudo levantado do código:

```
cd frontend
npm run handoff        # escreve docs/HANDOFF-FRONT.md
```

Se um gestor perder o acesso e não houver outro disponível, a saída é pelo
servidor:

```
cd api
dotnet run --project src/Cat.Ferramentas -- emergencia listar-gestores
dotnet run --project src/Cat.Ferramentas -- emergencia promover <usuario>
dotnet run --project src/Cat.Ferramentas -- emergencia redefinir <usuario>
dotnet run --project src/Cat.Ferramentas -- emergencia desbloquear <usuario>
```

Testes:

```
cd backend && .venv/Scripts/python -m pytest
cd api && dotnet test SistemaCat.slnx
```

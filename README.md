# Sistema CAT

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
`-InstalarPreRequisitos`); Docker Desktop é opcional — sem ele o banco é SQLite.

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

São três processos. A tela fala só com a API em C#; a API atende o que já foi
portado e repassa o resto ao motor Python, que também faz o trabalho pesado
(`docs/MIGRACAO_CSHARP.md`). O `subir.ps1` sobe os três; à mão, é assim.

Banco, opcional em desenvolvimento (sem ele usa SQLite):

```
docker compose -f docker/docker-compose.yml up -d
```

Motor Python:

```
cd backend
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
cp ../.env.example .env          # e ajuste CAT_JWT_SEGREDO
alembic upgrade head                     # cria o esquema
python -m cat.apresentacao.cli.semear    # cria os três gestores
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

A tela abre em http://localhost:5173 e a documentação da API em
http://localhost:8010/docs.

Se um gestor perder o acesso e não houver outro disponível, a saída é pelo
servidor:

```
python -m cat.apresentacao.cli.emergencia listar-gestores
python -m cat.apresentacao.cli.emergencia promover <usuario>
python -m cat.apresentacao.cli.emergencia redefinir <usuario>
```

Testes:

```
cd backend && .venv/Scripts/python -m pytest
cd api && dotnet test SistemaCat.slnx
```

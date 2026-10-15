# TRABALHO EM PARALELO — uma sessão por frente

> **Leitura obrigatória para toda sessão do Claude que for mexer neste
> repositório.** Desde 15/10/2026 duas sessões trabalham ao mesmo tempo, cada
> uma numa frente tributária. Esta é a regra de convivência. O `CLAUDE.md` da
> raiz aponta para cá.

---

## 1. Quem é quem

| Frente | Sessão cuida de | Branch | Pasta (worktree) |
|---|---|---|---|
| **PIS/COFINS** (+ CBS) | apuração de PIS/COFINS, exclusões da base (Tema 69), Gestão Fiscal, quebra de SPED, razão contábil, consulta de saídas | `frente/piscofins` | `..\SistemaCAT-piscofins` |
| **ICMS** (+ IBS) | CAT 42 inteira, crédito outorgado, combustível, de-para, relatório gerencial | `frente/icms` | `..\SistemaCAT` |

O corte não foi inventado: é o mesmo que o sistema já faz em
`Cat.Dominio/Acesso/Segmento.cs` (segmentos) e `Cat.Dominio/Projeto/Etapas.cs`
(`TrilhasPorModulo`).

**Para saber em que frente você está:** `git branch --show-current`.

## 2. As regras, curtas

1. **Ninguém desenvolve na `main`.** Ela só recebe integração. Cada sessão
   trabalha na sua pasta, na sua branch.
2. **Cada sessão mexe no que é dela.** Arquivo da outra frente só com motivo
   forte, e avisando antes (§6).
3. **Zona compartilhada pede cuidado:** mudança pequena, em commit próprio,
   integrada logo, para a outra frente receber cedo (§4).
4. **Commit nomeando cada arquivo.** Nunca `git add -A`, `git add .` nem
   `git commit -a`.
5. **Commit e push sempre, na branch da frente.** `git push` empurra para
   `frente/<sua>`, nunca para a `main`.
6. **A `main` só recebe por `scripts/integrar.sh`**, que é também o único
   lugar onde o `VERSAO` muda (§5).

## 3. De quem é cada arquivo

O mapa vive em **`.claude/frentes.json`**: é a fonte única, e é o que o hook lê.
São quatro categorias, checadas nesta ordem:

| Categoria | O que é | Exemplo |
|---|---|---|
| `so_na_integracao` | só muda pelo script de integração | `VERSAO` |
| `compartilhado` | as duas frentes dependem | leitor de SPED, `rodada.py`, `planilhas.py`, `rascunho.py`, `progresso.py`, `planilhas/conferencia.py`, `Etapas.cs`, `Segmento.cs`, rotas e layout do front, `CONTRATOS.md` |
| `frentes.piscofins` / `frentes.icms` | dono é uma frente; casa por pasta e por **pedaço do nome** (`*exclus*`, `*gestao*`, `*cat42*`, `*combustivel*`...) — arquivo novo com nome do assunto já nasce com dono | `analitico/piscofins.py`, `dominio/icms/cat42/*` |
| livre | não casa com nada: autenticação, usuários, componentes de UI, testes genéricos | `components/ui/Botao.tsx` |

**Tirar dúvida sobre um arquivo:**

```bash
node .claude/hooks/guarda-da-frente.mjs --classificar backend/cat/infraestrutura/analitico/rascunho.py
node .claude/hooks/guarda-da-frente.mjs --classificar          # todos os versionados
```

Arquivo mal classificado? Corrigir o `frentes.json` é mudança compartilhada:
commit próprio, e avisar.

## 4. Zona compartilhada

O conflito de verdade não é de texto, é de significado: uma frente muda o leitor
de SPED e quebra a outra sem que o git perceba. Por isso:

- **Mudança mínima.** Precisa de comportamento novo? Prefira parâmetro opcional,
  com o padrão de hoje, a mudar o que já existe.
- **Commit próprio, só com o compartilhado**, e com o efeito na outra frente
  escrito no corpo:

  ```
  fix(rascunho): nome provisório na geração da planilha

  Afeta a frente de ICMS: ...  (ou "Sem efeito na frente de ICMS: ...")
  ```

- **Integrar logo** (§5), sem esperar o resto da entrega, para a outra sessão
  receber cedo e no pedaço pequeno.
- **Avisar a outra sessão** pelo usuário, com o que mudou e o efeito esperado.
  A outra sessão também vê no log quando integra: o script lista o que veio
  da `main`.

## 5. Integrar na `main`

Ao fechar uma entrega (funcionalidade ou correção pronta e testada):

```bash
bash scripts/integrar.sh minor      # funcionalidade nova
bash scripts/integrar.sh patch      # correção
bash scripts/integrar.sh major      # quebra contrato (raro antes da 1.0)
```

O script, na ordem: confere árvore limpa e branch `frente/*` → `fetch` +
**rebase na `origin/main`** → roda **motor, API e front** → sobe o `VERSAO` num
commit `chore(versao): vX.Y.Z` com a lista do que entrou → etiqueta → push na
`main` **só por avanço rápido** → atualiza a branch da frente.

- **Conflito no rebase:** o script para. Quem resolve é a própria sessão, que
  sabe o que quis fazer: resolver, `git add <arquivo>`, `git rebase --continue`,
  rodar o script de novo. Desistir: `git rebase --abort`.
- **A outra frente integrou no meio:** o push é recusado, o script desfaz o
  bump e pede para rodar de novo. Nada se perde.
- **`--sem-testes`** existe para emergência; o CI pega depois, mas a `main`
  pode ficar quebrada até lá.
- **Antes de integrar**, a regra de sempre (docs/VERSIONAMENTO.md §6):
  `DECISOES.md` e `PLANEJAMENTO.md` em dia, log no código novo.
- **Integrar com frequência.** Branch que fica dias longe da `main` acumula
  conflito.

**Mudança em relação a antes:** a versão sobe **uma vez por integração**, não
a cada commit, porque duas branches subindo o `VERSAO` cada uma por si brigam
no mesmo número.

`test_versao.py` compara o `VERSAO` com a etiqueta alcançável do `HEAD`, então
uma branch atrás da `main` não quebra esse teste.

## 6. A guarda (hook)

`.claude/settings.json` liga `.claude/hooks/guarda-da-frente.mjs` antes de toda
edição e todo comando de shell. Ele **pergunta, não bloqueia**, quando:

| Situação | Quando pergunta |
|---|---|
| a pasta está na `main` | uma vez por sessão |
| arquivo da outra frente | uma vez por arquivo, por sessão |
| arquivo da zona compartilhada | uma vez por arquivo, por sessão |
| `VERSAO` | uma vez por sessão |
| `git add -A`, `git add .`, `git commit -a` | sempre |
| `push` para a `main` fora do script | sempre |
| `commit` estando na `main` | sempre |

A pergunta aparece para o usuário, que aprova ou recusa. **Recusou, a sessão
não insiste nem contorna**: muda de abordagem ou pergunta. Se o hook falhar por
defeito próprio, ele deixa passar e escreve o erro no stderr.

O hook e o `CLAUDE.md` são lidos **quando a sessão começa**. Sessão aberta antes
de eles existirem não os vê até ser reiniciada.

## 7. CI

`.github/workflows/testes.yml` roda motor, API (com Postgres de serviço) e front
a cada push na `main` e nas `frente/**`. Falhou na `main`: a frente que integrou
por último conserta, numa correção integrada como `patch`.

## 8. Preparar a pasta de uma frente

Worktree novo não traz o que o git ignora: `.venv`, `node_modules`, `.env`,
`data/`. Uma vez por pasta:

```powershell
# a partir da pasta principal
git worktree add ..\SistemaCAT-<frente> -b frente/<frente> origin/main

cd ..\SistemaCAT-<frente>
& "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe" -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
Copy-Item ..\SistemaCAT\backend\.env backend\.env
cd frontend; npm ci; cd ..
```

**Banco de teste:** os testes da API criam um banco com o nome da pasta como
sufixo (`cat_testes_csharp_sistemacat_piscofins`), então as duas pastas testam
ao mesmo tempo sem derrubar uma à outra. Os testes do motor usam SQLite
temporário, sem conflito.

**Subir o sistema:** `scripts/subir.ps1` usa portas fixas (8020, 8010, 5173),
então **só uma pasta sobe o sistema por vez**. Hoje é a `..\SistemaCAT`. Para
ver a tela de uma frente antes de integrar, pare os serviços de lá e suba a
partir da pasta da frente. *Pendente:* portas configuráveis no `subir.ps1` para
as duas subirem juntas. Atenção ao banco: as duas pastas usam o mesmo Postgres
de desenvolvimento, então migração nova de uma frente vale para a outra assim
que roda.

## 9. Passagem para o modelo novo (15/10/2026)

- A frente de PIS/COFINS já está em `..\SistemaCAT-piscofins`, na
  `frente/piscofins`.
- **A sessão de ICMS fica na pasta de sempre, `..\SistemaCAT`**, onde estão os
  serviços no ar, o `.env` e o `data/`. Ela só troca de branch. Na primeira vez,
  com a árvore como estiver (o que não estiver commitado vai junto):

  ```bash
  git pull --ff-only origin main
  git switch -c frente/icms
  git push -u origin frente/icms
  ```

  Depois disso, **reiniciar a sessão** do Claude nessa pasta, para carregar o
  hook e o `CLAUDE.md`.

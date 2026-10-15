# Sistema CAT

## Antes de tudo: duas sessões trabalham neste repositório ao mesmo tempo

Cada sessão do Claude cuida de uma frente tributária, na sua pasta e na sua
branch. A regra completa está em **`docs/TRABALHO_EM_PARALELO.md`**, e deve ser
lida antes da primeira mudança.

| Branch (`git branch --show-current`) | Esta sessão é a de | Pasta |
|---|---|---|
| `frente/piscofins` | PIS/COFINS (+ CBS) | `..\SistemaCAT-piscofins` |
| `frente/icms` | ICMS (+ IBS) | `..\SistemaCAT` |
| `main` | ninguém desenvolve aqui: trocar para a branch da frente | — |

Em resumo:

- Mexer só no que é da sua frente. Dono de cada arquivo:
  `node .claude/hooks/guarda-da-frente.mjs --classificar <arquivo>`.
- Zona compartilhada (leitor de SPED, `rodada.py`, `planilhas.py`, `Etapas.cs`,
  rotas do front...): mudança mínima, commit próprio com o efeito na outra
  frente escrito no corpo, integrar logo, avisar o usuário.
- `git add` nomeando cada arquivo. Push só na branch da frente.
- A `main` só recebe por `bash scripts/integrar.sh patch|minor|major`, que
  também é o único lugar onde o `VERSAO` muda.
- O hook `.claude/hooks/guarda-da-frente.mjs` pergunta antes de passar dessas
  linhas. Pergunta recusada não se contorna.

## Documentação (fonte de verdade, ler daqui e não de memória)

- `docs/ARQUITETURA.md`: camadas, motor Python × API C# × front React
- `docs/DOMINIO.md`: regra fiscal da CAT 42 (frente de ICMS)
- `docs/CONTRATOS.md`: contratos entre motor, API e tela
- `docs/DECISOES.md`: decisões fechadas, não rediscutir
- `docs/VERSIONAMENTO.md`: versão semântica, commits, o que nunca sobe
- `docs/PLANEJAMENTO.md`: roteiro

Nenhum nome ou CNPJ de cliente entra no repositório (`docs/VERSIONAMENTO.md` §5).

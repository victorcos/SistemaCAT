#!/usr/bin/env bash
# Integra a branch da frente na main: o ÚNICO caminho para a main.
#
#   bash scripts/integrar.sh patch|minor|major [--sem-testes]
#
# Roda de dentro da pasta da frente (worktree na branch frente/*). Na ordem:
#   1. confere que a árvore está limpa e que a branch é de frente
#   2. traz a main (fetch + rebase) — conflito para aqui, e quem resolve é
#      a própria sessão, que sabe o que quis fazer
#   3. roda as três baterias: motor (pytest), API (dotnet test), front (vitest)
#   4. sobe o VERSAO num commit próprio e etiqueta (docs/VERSIONAMENTO.md §4)
#   5. empurra para a main só se for avanço rápido; se a outra frente integrou
#      no meio, desfaz o bump e pede para rodar de novo
#   6. atualiza a branch da frente no GitHub
#
# Regra completa: docs/TRABALHO_EM_PARALELO.md.

set -euo pipefail

log()   { printf '[integrar %s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
parar() { log "PAROU: $*"; exit 1; }

nivel="${1:-}"
pular_testes=0
[[ "${2:-}" == "--sem-testes" ]] && pular_testes=1
case "$nivel" in
  patch|minor|major) ;;
  *) parar "uso: bash scripts/integrar.sh patch|minor|major [--sem-testes]" ;;
esac

raiz="$(git rev-parse --show-toplevel)"
cd "$raiz"
branch="$(git branch --show-current)"
[[ "$branch" == frente/* ]] \
  || parar "rode de dentro da pasta de uma frente (branch frente/*); esta pasta está em '$branch'"
[[ -d "$(git rev-parse --git-path rebase-merge)" || -d "$(git rev-parse --git-path rebase-apply)" ]] \
  && parar "há um rebase pela metade: termine com 'git rebase --continue' ou desista com 'git rebase --abort'"
[[ -z "$(git status --porcelain)" ]] \
  || parar "há mudança não commitada. Commite nomeando os arquivos, ou guarde num commit WIP, e rode de novo"

# ---- 2. trazer a main
log "buscando a main ($branch)"
git fetch --quiet --tags --prune origin
# o que a outra frente integrou desde a última vez: é aqui que a mudança
# compartilhada dela chega a esta pasta (docs/TRABALHO_EM_PARALELO.md §4)
veio="$(git log --format='- %s' HEAD..origin/main)"
if [[ -n "$veio" ]]; then
  log "a main trouxe (leia antes de seguir, sobretudo o compartilhado):"
  printf '%s\n' "$veio" >&2
fi
if ! git rebase --quiet origin/main; then
  parar "conflito ao trazer a main. Resolva cada arquivo, 'git add <arquivo>', 'git rebase --continue', e rode este script de novo. Para desistir: 'git rebase --abort'"
fi

entrando="$(git log --format='- %s' origin/main..HEAD)"
[[ -n "$entrando" ]] || parar "nada a integrar: $branch não tem commit que a main não tenha"
log "commits que entram na main:"
printf '%s\n' "$entrando" >&2

# ---- 3. testes
if (( pular_testes )); then
  log "ATENÇÃO: testes pulados a pedido (--sem-testes). O CI do GitHub roda depois, mas a main pode quebrar até lá"
else
  py="backend/.venv/Scripts/python.exe"
  [[ -x "$py" ]] || py="backend/.venv/bin/python"
  [[ -x "$py" ]] || parar "esta pasta não tem backend/.venv. Prepare o worktree (docs/TRABALHO_EM_PARALELO.md §5)"
  log "testes do motor (pytest)"
  (cd backend && "../$py" -m pytest -q -x -p no:cacheprovider) || parar "testes do motor falharam"
  log "testes da API (dotnet test; precisa do Postgres do docker na 55432)"
  dotnet test api/SistemaCat.slnx --nologo -v quiet || parar "testes da API falharam"
  log "testes do front (vitest)"
  [[ -d frontend/node_modules ]] || parar "esta pasta não tem frontend/node_modules: rode 'npm ci' em frontend/"
  (cd frontend && npm test --silent) || parar "testes do front falharam"
fi

# ---- 4. versão
atual="$(tr -d '\r\n\357\273\277' < VERSAO)"
IFS=. read -r maior menor correcao <<< "${atual%%-*}"
case "$nivel" in
  major) nova="$((maior + 1)).0.0" ;;
  minor) nova="$maior.$((menor + 1)).0" ;;
  patch) nova="$maior.$menor.$((correcao + 1))" ;;
esac
git rev-parse -q --verify "refs/tags/v$nova" >/dev/null && parar "a etiqueta v$nova já existe"
log "versão $atual -> $nova"
printf '%s' "$nova" > VERSAO
git add VERSAO
git commit --quiet -m "chore(versao): v$nova" -m "Integra $branch na main:" -m "$entrando"
git tag -a "v$nova" -m "v$nova ($branch)"

# ---- 5. main, só por avanço rápido
log "empurrando para a main"
if ! git push --quiet origin HEAD:main; then
  git tag -d "v$nova" >/dev/null
  git reset --quiet --keep HEAD~1
  parar "a main andou enquanto este script rodava (a outra frente integrou). Bump desfeito; rode o script de novo"
fi
git push --quiet origin "v$nova"

# ---- 6. branch da frente (o rebase reescreveu, daí o force-with-lease)
git push --quiet --force-with-lease -u origin "$branch"

# a main local, se nenhuma pasta estiver com ela aberta
git fetch --quiet origin main:main 2>/dev/null \
  || log "a main local está aberta em outra pasta; lá ela se atualiza com 'git pull'"

log "pronto: v$nova está na main. A outra frente recebe na próxima integração dela"

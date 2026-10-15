// Guarda da frente: avisa antes de uma sessão mexer fora do que é dela.
//
// Duas sessões do Claude trabalham ao mesmo tempo, cada uma num worktree e numa
// branch (frente/piscofins, frente/icms). Este hook roda antes de Edit/Write/
// NotebookEdit e de Bash, e PEDE CONFIRMAÇÃO — não bloqueia — quando:
//   - a pasta está na main (ninguém desenvolve na main; ela só recebe integração)
//   - o arquivo é de outra frente
//   - o arquivo é da zona compartilhada, ou é o VERSAO
//   - o comando git varre a árvore inteira (add -A, commit -a) ou empurra
//     direto para a main fora de scripts/integrar.sh
//
// O mapa de dono vive em .claude/frentes.json; a regra, em
// docs/TRABALHO_EM_PARALELO.md. Para arquivo, pergunta uma vez por sessão:
// a segunda edição do mesmo arquivo já foi uma escolha consciente.
//
// Qualquer falha aqui (sem git, JSON quebrado) deixa passar em silêncio, com o
// erro no stderr: guarda que trava o trabalho por defeito próprio é pior que
// guarda nenhuma.

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const REGRA = "docs/TRABALHO_EM_PARALELO.md";

function log(msg, extra = {}) {
  process.stderr.write(`[guarda-da-frente] ${msg} ${JSON.stringify(extra)}\n`);
}

function perguntar(motivo) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "ask",
      permissionDecisionReason: `${motivo} (regra: ${REGRA})`,
    },
  }));
  process.exit(0);
}

// glob -> regex: ** cruza pasta, * não, {a,b} é alternativa (pode aninhar)
function globParaRegex(glob) {
  let i = 0;
  function ler(ateFecha) {
    const alternativas = [[]];
    while (i < glob.length) {
      const c = glob[i];
      if (ateFecha && c === "}") { i++; break; }
      if (ateFecha && c === ",") { alternativas.push([]); i++; continue; }
      const atual = alternativas[alternativas.length - 1];
      if (c === "{") { i++; atual.push(`(?:${ler(true)})`); continue; }
      if (c === "*" && glob[i + 1] === "*") {
        i += 2;
        if (glob[i] === "/") { i++; atual.push("(?:.*/)?"); } else atual.push(".*");
        continue;
      }
      if (c === "*") { i++; atual.push("[^/]*"); continue; }
      if (c === "?") { i++; atual.push("[^/]"); continue; }
      atual.push(c.replace(/[.+^$()|[\]\\]/g, "\\$&"));
      i++;
    }
    return alternativas.map((a) => a.join("")).join("|");
  }
  return new RegExp(`^(?:${ler(false)})$`, "i");
}

const casa = (padroes, rel) => padroes.some((p) => globParaRegex(p).test(rel));

function classificar(mapa, rel) {
  if (casa(mapa.so_na_integracao ?? [], rel)) return { tipo: "integracao" };
  if (casa(mapa.compartilhado ?? [], rel)) return { tipo: "compartilhado" };
  for (const [chave, frente] of Object.entries(mapa.frentes ?? {}))
    if (casa(frente.arquivos ?? [], rel)) return { tipo: "frente", chave };
  return { tipo: "livre" };
}

function acharRaiz(inicio) {
  for (let p = path.resolve(inicio); ; p = path.dirname(p)) {
    if (existsSync(path.join(p, ".claude", "frentes.json"))) return p;
    if (path.dirname(p) === p) return null;
  }
}

function branchDe(raiz) {
  return execFileSync("git", ["-C", raiz, "branch", "--show-current"], {
    encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], timeout: 5000,
  }).trim();
}

// uma pergunta por (sessão, chave): guarda no temp do sistema, fora do repo
function jaPerguntou(sessao, chave) {
  const pasta = path.join(tmpdir(), "claude-guarda-da-frente");
  const arquivo = path.join(pasta, `${(sessao || "sem-sessao").replace(/[^\w-]/g, "_")}.json`);
  let vistos = [];
  try { vistos = JSON.parse(readFileSync(arquivo, "utf8")); } catch { /* primeira vez */ }
  if (vistos.includes(chave)) return true;
  vistos.push(chave);
  try { mkdirSync(pasta, { recursive: true }); writeFileSync(arquivo, JSON.stringify(vistos)); }
  catch (e) { log("não gravou o estado da sessão", { arquivo, erro: String(e) }); }
  return false;
}

function guardarBash(entrada, raiz, branch) {
  const cmd = String(entrada.tool_input?.command ?? "");
  if (/\bgit\b[^;&|]*\badd\s+(-A\b|--all\b|\.(\s|$))/.test(cmd) || /\bgit\b[^;&|]*\bcommit\b[^;&|]*\s-[a-zA-Z]*a/.test(cmd))
    perguntar("Comando git que varre a árvore inteira. Há outra sessão no mesmo repositório: " +
      "adicione nomeando cada arquivo seu");
  if (/\bgit\b[^;&|]*\bpush\b[^;&|]*(\bmain\b|:main\b)/.test(cmd) && !/integrar\.sh/.test(cmd))
    perguntar("Push direto na main. A integração passa por scripts/integrar.sh, que traz a main, " +
      "roda os testes e sobe a versão");
  if (branch === "main" && /\bgit\b[^;&|]*\bcommit\b/.test(cmd))
    perguntar("Commit na main. O trabalho de cada frente é na branch dela (frente/piscofins, frente/icms)");
}

function guardarArquivo(entrada, raiz, branch, mapa) {
  const alvo = entrada.tool_input?.file_path ?? entrada.tool_input?.notebook_path;
  if (!alvo) return;
  const abs = path.resolve(entrada.cwd ?? process.cwd(), alvo);
  const rel = path.relative(raiz, abs).split(path.sep).join("/");
  if (rel.startsWith("..") || path.isAbsolute(rel)) return;

  const frentes = Object.entries(mapa.frentes ?? {});
  if (branch === "main" || branch === "master") {
    if (!jaPerguntou(entrada.session_id, `main|${raiz}`))
      perguntar(`Esta pasta está na ${branch}. Ninguém desenvolve na main: cada frente trabalha ` +
        `na sua branch (${frentes.map(([, f]) => `${f.branch} em ../${f.pasta}`).join(", ")})`);
    return;
  }
  const minha = frentes.find(([, f]) => f.branch === branch);
  if (!minha) return; // branch fora do esquema das frentes: não é assunto deste hook
  const [minhaChave, minhaFrente] = minha;

  const dono = classificar(mapa, rel);
  let motivo = null;
  if (dono.tipo === "integracao")
    motivo = `${rel} só muda no commit de integração, feito por scripts/integrar.sh`;
  else if (dono.tipo === "compartilhado")
    motivo = `${rel} é da zona compartilhada: mudança pequena, commit separado, e avisar a outra sessão`;
  else if (dono.tipo === "frente" && dono.chave !== minhaChave)
    motivo = `${rel} é da frente de ${mapa.frentes[dono.chave].rotulo}, e esta sessão é de ` +
      `${minhaFrente.rotulo}. Se for mesmo preciso, avise a outra sessão antes`;
  if (motivo && !jaPerguntou(entrada.session_id, `${raiz}|${rel}`)) perguntar(motivo);
}

// Consulta à mão: de quem é cada arquivo versionado (ou só os passados).
//   node .claude/hooks/guarda-da-frente.mjs --classificar [arquivo...]
if (process.argv[2] === "--classificar") {
  const raiz = acharRaiz(process.cwd());
  const mapa = JSON.parse(readFileSync(path.join(raiz, ".claude", "frentes.json"), "utf8"));
  const arquivos = process.argv.length > 3
    ? process.argv.slice(3).map((a) => path.relative(raiz, path.resolve(a)).split(path.sep).join("/"))
    : execFileSync("git", ["-C", raiz, "ls-files"], { encoding: "utf8" }).trim().split("\n");
  for (const rel of arquivos) {
    const d = classificar(mapa, rel);
    process.stdout.write(`${d.tipo === "frente" ? d.chave : d.tipo}\t${rel}\n`);
  }
  process.exit(0);
}

try {
  const entrada = JSON.parse(readFileSync(0, "utf8"));
  const cwd = entrada.cwd ?? process.cwd();
  // arquivo: a raiz é a do worktree do ARQUIVO, não a de onde a sessão abriu
  const alvo = entrada.tool_input?.file_path ?? entrada.tool_input?.notebook_path;
  const raiz = acharRaiz(alvo ? path.dirname(path.resolve(cwd, alvo)) : cwd);
  if (!raiz) process.exit(0);
  const mapa = JSON.parse(readFileSync(path.join(raiz, ".claude", "frentes.json"), "utf8"));
  const branch = branchDe(raiz);
  if (entrada.tool_name === "Bash" || entrada.tool_name === "PowerShell") guardarBash(entrada, raiz, branch);
  else guardarArquivo(entrada, raiz, branch, mapa);
} catch (e) {
  log("falhou e deixou passar", { erro: String(e?.stack ?? e) });
}
process.exit(0);

#!/usr/bin/env node
/**
 * Levanta do próprio código tudo que um handoff de design precisa descrever.
 *
 *     npm run handoff              # escreve docs/HANDOFF-FRONT.md
 *     npm run handoff -- --stdout  # joga na tela
 *
 * O ponto: um handoff escrito à mão envelhece no dia seguinte. Este sai do
 * código-fonte, então ou está certo ou o código mudou — e rodar de novo custa
 * dois segundos. O que ele levanta:
 *
 *   1. **Rotas** — o endereço, a tela que atende e se exige papel;
 *   2. **Telas** — o resumo que cada arquivo já escreve no próprio topo;
 *   3. **Componentes** — o inventário do que existe, com as propriedades;
 *   4. **Tokens** — as cores, raios e sombras, com o valor de cada uma;
 *   5. **Endpoints** — o que a tela pede ao servidor, agrupado por assunto;
 *   6. **Papéis e menu** — quem vê o quê;
 *   7. **Buracos** — rota sem tela, tela sem rota, rota órfã sem link.
 *
 * O item 7 existe por um motivo específico: em 22/09/2026 três telas ficaram
 * prontas, testadas e inalcançáveis, porque registrar a rota não cria caminho
 * nenhum. Um relatório que não responde "dá para chegar lá?" não serve.
 *
 * **Não lê dado de cliente.** Só fontes em `src/`.
 */

import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = dirname(fileURLToPath(import.meta.url));
const FRONT = resolve(AQUI, "..");
const SRC = join(FRONT, "src");
const RAIZ = resolve(FRONT, "..");

const ler = (caminho) => readFileSync(caminho, "utf8");
const existe = (caminho) => existsSync(caminho);

/** Os arquivos .ts/.tsx de uma pasta, em ordem. */
function arquivos(pasta, extensoes = [".ts", ".tsx"]) {
  const alvo = join(SRC, pasta);
  if (!existe(alvo)) return [];
  return readdirSync(alvo)
    .filter((n) => extensoes.some((e) => n.endsWith(e)))
    .sort();
}

/**
 * O comentário de bloco do topo do arquivo, em uma frase.
 *
 * As telas desta casa começam com um `/** ... *\/` que diz para que servem. É
 * a melhor descrição que existe, e já está escrita — repetir isso à mão num
 * documento seria criar a segunda cópia que um dia divergiria.
 */
function resumoDoArquivo(texto) {
  const bloco = texto.match(/\/\*\*([\s\S]*?)\*\//);
  if (!bloco) return "";
  const linhas = bloco[1]
    .split("\n")
    .map((l) => l.replace(/^\s*\*ature?\s?/, "").replace(/^\s*\*\s?/, "").trim())
    .filter(Boolean);
  if (linhas.length === 0) return "";
  // a primeira frase: o título do comentário, sem o parágrafo inteiro
  const primeira = linhas[0];
  const segunda = linhas.slice(1).find((l) => l.length > 0 && !l.startsWith("@")) ?? "";
  return segunda && primeira.length < 60 ? `${primeira} ${segunda}` : primeira;
}

const tabela = (colunas, linhas) =>
  [
    `| ${colunas.join(" | ")} |`,
    `| ${colunas.map(() => "---").join(" | ")} |`,
    ...linhas.map((l) => `| ${l.join(" | ")} |`),
  ].join("\n");

const escapar = (t) => String(t).replace(/\|/g, "\\|");

/* ------------------------------------------------------------------ rotas */

function rotas() {
  const roteador = ler(join(SRC, "routers/index.tsx"));
  const encontradas = [];
  const re = /\{\s*path:\s*(?:"([^"]+)"|ROTAS\.(\w+))\s*,\s*element:\s*<(\w+)/g;
  let m;
  while ((m = re.exec(roteador)) !== null) {
    encontradas.push({ caminho: m[1] ?? `ROTAS.${m[2]}`, tela: m[3] });
  }
  // as que exigem papel vêm dentro de um <ExigePapel papeis={...}>
  const protegidas = new Set();
  const reProtegida = /<ExigePapel[\s\S]*?children:\s*\[([\s\S]*?)\]/g;
  let p;
  while ((p = reProtegida.exec(roteador)) !== null) {
    const dentro = p[1];
    for (const r of encontradas) {
      if (dentro.includes(`<${r.tela}`)) protegidas.add(r.tela);
    }
  }
  // o valor literal de cada ROTAS.x, para o documento mostrar o endereço
  const constantes = literaisDeRotas();
  return encontradas.map((r) => ({
    ...r,
    caminho: r.caminho.startsWith("ROTAS.")
      ? (constantes[r.caminho.slice(6)] ?? r.caminho)
      : r.caminho,
    exigePapel: protegidas.has(r.tela),
  }));
}

/** `routes.ts` → { inicio: "/", projeto: "/projetos/:id", ... } */
function literaisDeRotas() {
  const texto = ler(join(SRC, "constants/routes.ts"));
  const saida = {};
  const simples = /^\s{2}(\w+):\s*"([^"]+)"/gm;
  let m;
  while ((m = simples.exec(texto)) !== null) saida[m[1]] = m[2];
  const comParametro = /^\s{2}(\w+):\s*\([^)]*\)\s*=>\s*`([^`]+)`/gm;
  while ((m = comParametro.exec(texto)) !== null) {
    saida[m[1]] = m[2].replace(/\$\{[^}]+\}/g, ":id");
  }
  return saida;
}

/* ----------------------------------------------------------------- telas */

function telas() {
  return arquivos("pages").map((nome) => {
    const texto = ler(join(SRC, "pages", nome));
    return {
      nome: nome.replace(/\.tsx?$/, ""),
      arquivo: `src/pages/${nome}`,
      resumo: resumoDoArquivo(texto),
      linhas: texto.split("\n").length,
    };
  });
}

/* ----------------------------------------------------------- componentes */

function componentes() {
  const saida = [];
  for (const pasta of ["components/ui", "components/shared", "layout"]) {
    for (const nome of arquivos(pasta)) {
      const texto = ler(join(SRC, pasta, nome));
      const exportados = [...texto.matchAll(/export function (\w+)/g)].map((m) => m[1]);
      if (exportados.length === 0) continue;
      saida.push({
        pasta,
        arquivo: `src/${pasta}/${nome}`,
        exportados,
        resumo: resumoDoComponente(texto, exportados[0]),
        props: propsDe(texto, exportados[0]),
      });
    }
  }
  return saida;
}

/** Onde a função exportada começa. Aceita genérica: `Combobox<T extends …>(`. */
function ondeComeca(texto, nome) {
  const m = new RegExp(`export function ${nome}\\s*(?:<[^>]*>)?\\s*\\(`).exec(texto);
  return m ? m.index : -1;
}

/**
 * O comentário que descreve o componente — o que está **logo acima** dele.
 *
 * Não o primeiro do arquivo: lá em cima costuma estar o comentário de uma
 * propriedade de interface, e era ele que saía no relatório, descrevendo um
 * campo no lugar do componente.
 */
function resumoDoComponente(texto, nome) {
  const inicio = ondeComeca(texto, nome);
  if (inicio < 0) return resumoDoArquivo(texto);
  const antes = texto.slice(0, inicio);
  const fim = antes.lastIndexOf("*/");
  const comeco = antes.lastIndexOf("/**", fim);
  // só vale se o bloco estiver colado na função: entre um e outro pode haver
  // no máximo espaço em branco
  if (fim > 0 && comeco >= 0 && antes.slice(fim + 2).trim() === "") {
    return resumoDoArquivo(antes.slice(comeco));
  }
  return resumoDoArquivo(texto);
}


/** As propriedades do primeiro componente exportado, pelo destructuring. */
function propsDe(texto, nome) {
  const inicio = ondeComeca(texto, nome);
  if (inicio < 0) return [];
  const trecho = texto.slice(inicio, inicio + 900);
  const chaves = trecho.match(/\(\s*\{([\s\S]*?)\}\s*:/);
  if (!chaves) return [];
  return chaves[1]
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("//") && !l.startsWith("*") && !l.startsWith("/*"))
    .map((l) => l.replace(/[,:].*$/, "").replace(/\.\.\./, "…").trim())
    .filter(Boolean);
}

/* ---------------------------------------------------------------- tokens */

function tokens() {
  const texto = ler(join(SRC, "styles/tokens.css"));
  const grupos = [];
  let atual = null;
  for (const linha of texto.split("\n")) {
    // título de seção é o comentário que ocupa a linha inteira. Sem esta
    // exigência, o `/* linha divisória */` que explica a cor dourada virava
    // um grupo, e as cores da marca iam parar dentro dele
    const soComentario = linha.trim().startsWith("/*");
    const titulo = soComentario ? linha.match(/\/\*\s*-*\s*([^-*]+?)\s*-*\s*\*\//) : null;
    if (titulo && titulo[1].trim().length > 2) {
      atual = { titulo: titulo[1].trim(), itens: [] };
      grupos.push(atual);
      continue;
    }
    const variavel = linha.match(/^\s+(--[\w-]+):\s*([^;]+);(?:\s*\/\*\s*(.*?)\s*\*\/)?/);
    if (variavel && atual) {
      atual.itens.push({
        nome: variavel[1],
        valor: variavel[2].trim(),
        nota: variavel[3] ?? "",
      });
    }
  }
  return grupos.filter((g) => g.itens.length > 0);
}

/* ------------------------------------------------------------- endpoints */

// `api.ts` é o transporte (monta a URL, põe o token, trata o 401) e `sessao.ts`
// só guarda o token: nenhum dos dois é uma lista de endpoints, e incluí-los
// fazia aparecer uma rota `/api:id` que não existe
const NAO_SAO_SERVICOS = new Set(["api.ts", "sessao.ts"]);

function endpoints() {
  const saida = [];
  for (const nome of arquivos("services")) {
    if (NAO_SAO_SERVICOS.has(nome)) continue;
    const texto = ler(join(SRC, "services", nome));
    const achados = new Map();

    // Cada chamada é um pedaço: o método e a rota de um mesmo `chamar(...)`
    // têm de sair juntos. Procurar o próximo `method:` a partir da rota
    // atravessava para a função seguinte, e o relatório trocava os verbos —
    // dizia GET num cancelamento, que é POST.
    for (const pedaco of texto.split(/\bchamar</).slice(1)) {
      const rota = pedaco.match(/[`"](\/[^`"]*)/);
      if (!rota) continue;
      const metodo = pedaco.slice(0, 400).match(/method:\s*"(\w+)"/);
      guardar(achados, rota[1], metodo ? metodo[1] : "GET");
    }
    // o download não passa pelo `chamar`: monta a URL inteira e é sempre GET
    for (const m of texto.matchAll(/baixarArquivo\(\s*[`"]([^`"]+)/g)) {
      guardar(achados, m[1], "GET");
    }

    const rotas = [...achados.entries()]
      .map(([rota, metodo]) => ({ rota, metodo }))
      .sort((a, b) => a.rota.localeCompare(b.rota));
    if (rotas.length > 0) saida.push({ servico: nome.replace(/\.ts$/, ""), rotas });
  }
  return saida;
}

/**
 * Normaliza a rota e guarda.
 *
 * Três coisas: todo parâmetro vira `:id`; parâmetros colados viram um só
 * (`/planilhas/${qual}${filtro}` saía como `:id:id`); e o prefixo `/api` entra
 * onde falta, para que a lista inteira leia igual — `chamar` o acrescenta por
 * dentro, `baixarArquivo` já o traz escrito.
 */
function guardar(mapa, bruta, metodo) {
  const rota = ("/api" + bruta.replace(/^\/api/, ""))
    .replace(/\$\{[^}]*\}/g, ":id")
    .replace(/(:id)+/g, ":id")
    .replace(/\?.*$/, "")
    .replace(/\/$/, "");
  // o verbo explícito vence o padrão: a mesma rota aparece em POST e em GET
  if (!mapa.has(rota) || mapa.get(rota) === "GET") mapa.set(rota, metodo);
}

/* ------------------------------------------------------- papéis e o menu */

function papeis() {
  const texto = ler(join(SRC, "constants/roles.ts"));
  const listas = [...texto.matchAll(/export const (\w+): Papel\[\] = \[([^\]]+)\]/g)].map((m) => ({
    nome: m[1],
    papeis: m[2].replace(/\s+/g, " ").replace(/"/g, "").trim(),
  }));
  const menuTexto = ler(join(SRC, "constants/navigation.ts"));
  const menu = [...menuTexto.matchAll(/\{\s*para:\s*ROTAS\.(\w+)[^}]*rotulo:\s*"([^"]+)"[^}]*\}/gs)]
    .map((m) => ({ rota: m[1], rotulo: m[2] }));
  return { listas, menu };
}

/* --------------------------------------------------------------- buracos */

/**
 * O que existe sem caminho — a pergunta que um handoff tem de responder.
 *
 * Três formas de a tela ficar inalcançável, e todas já aconteceram aqui:
 * rota declarada em `routes.ts` e não registrada no roteador; tela em
 * `pages/` sem rota nenhuma; e rota registrada que nenhum link aponta.
 */
function buracos() {
  const roteador = ler(join(SRC, "routers/index.tsx"));
  const declaradas = literaisDeRotas();
  const registradas = rotas();
  const fonteInteira = arquivosDeTodaAFonte();

  // o NOME do parâmetro não pode decidir nada: `/segmentos/${chave}` chega
  // aqui como `/segmentos/:id` e está no roteador como `/segmentos/:chave`.
  // Comparar o texto cru dava dois falsos positivos — e uma seção que grita à
  // toa deixa de ser lida, que é o pior defeito possível num relatório assim
  const forma = (caminho) => caminho.replace(/:\w+/g, ":x").replace(/\/$/, "");
  const formasRegistradas = new Set(registradas.map((x) => forma(x.caminho)));
  const semRegistro = Object.entries(declaradas)
    .filter(([nome, caminho]) =>
      !new RegExp(`path:\\s*ROTAS\\.${nome}\\b`).test(roteador) &&
      !formasRegistradas.has(forma(caminho)))
    .map(([nome, caminho]) => ({ nome, caminho }));

  const usadasNoRoteador = new Set(registradas.map((r) => r.tela));
  const semRota = telas()
    .map((t) => t.nome)
    .filter((nome) => !usadasNoRoteador.has(nome));

  // rota registrada que nenhum arquivo aponta com <Link>, navigate() ou Voltar
  const semLink = registradas
    .filter((r) => {
      const nome = Object.entries(declaradas).find(([, v]) => v === r.caminho)?.[0];
      if (!nome) return false;
      const usos = fonteInteira.filter(
        ({ caminho, texto }) =>
          !caminho.endsWith("routers/index.tsx") &&
          !caminho.endsWith("constants/routes.ts") &&
          new RegExp(`ROTAS\\.${nome}\\b`).test(texto),
      );
      return usos.length === 0;
    })
    .map((r) => r.caminho);

  return { semRegistro, semRota, semLink };
}

function arquivosDeTodaAFonte() {
  const saida = [];
  const andar = (pasta) => {
    for (const item of readdirSync(pasta, { withFileTypes: true })) {
      const caminho = join(pasta, item.name);
      if (item.isDirectory()) andar(caminho);
      else if (/\.tsx?$/.test(item.name)) saida.push({ caminho, texto: ler(caminho) });
    }
  };
  andar(SRC);
  return saida;
}

/* ---------------------------------------------------------- o documento */

function versao() {
  const arquivo = join(RAIZ, "VERSAO");
  return existe(arquivo) ? ler(arquivo).trim() : "(sem VERSAO)";
}

function montar() {
  const hoje = new Date().toISOString().slice(0, 10);
  const partes = [];
  const P = (t) => partes.push(t);

  P(`# Handoff do front — CRM Fiscal`);
  P("");
  P(`> Gerado de \`frontend/tools/handoff.mjs\` em ${hoje}, sobre a versão **${versao()}**.`);
  P(`> Não editar à mão: rode \`npm run handoff\` de novo depois de mexer no front.`);
  P("");
  P(`Tudo aqui sai do código-fonte em \`frontend/src\`. Se divergir da tela, o`);
  P(`errado é o código — não este documento.`);
  P("");

  // ----------------------------------------------------------------- rotas
  const r = rotas();
  P(`## 1. Rotas (${r.length})`);
  P("");
  P(`O endereço, a tela que o atende e se exige papel específico.`);
  P("");
  P(tabela(
    ["Endereço", "Tela", "Exige papel"],
    r.map((x) => [`\`${escapar(x.caminho)}\``, x.tela, x.exigePapel ? "sim" : "—"]),
  ));
  P("");

  // ----------------------------------------------------------------- telas
  const t = telas();
  P(`## 2. Telas (${t.length})`);
  P("");
  P(`O resumo é o que o próprio arquivo diz de si no comentário do topo.`);
  P("");
  for (const tela of t) {
    P(`### ${tela.nome}`);
    P("");
    P(`\`${tela.arquivo}\` · ${tela.linhas} linhas`);
    P("");
    P(tela.resumo || "_(sem comentário de topo)_");
    P("");
  }

  // ----------------------------------------------------------- componentes
  const c = componentes();
  P(`## 3. Componentes (${c.length} arquivos)`);
  P("");
  P(`O que já existe e pode ser reaproveitado. Desenhar um componente que já`);
  P(`está aqui custa o dobro: o trabalho de desenhar e o de reconciliar depois.`);
  P("");
  for (const grupo of ["components/ui", "components/shared", "layout"]) {
    const doGrupo = c.filter((x) => x.pasta === grupo);
    if (doGrupo.length === 0) continue;
    P(`### \`src/${grupo}\``);
    P("");
    P(tabela(
      ["Componente", "Exporta", "Propriedades", "Para que serve"],
      doGrupo.map((x) => [
        `\`${x.arquivo.split("/").pop()}\``,
        x.exportados.join(", "),
        x.props.length ? `\`${escapar(x.props.join(", "))}\`` : "—",
        escapar(x.resumo || "—"),
      ]),
    ));
    P("");
  }

  // --------------------------------------------------------------- tokens
  const grupos = tokens();
  const quantos = grupos.reduce((n, g) => n + g.itens.length, 0);
  P(`## 4. Tokens de design (${quantos})`);
  P("");
  P(`Em \`src/styles/tokens.css\`. Toda cor, raio e sombra da tela sai daqui —`);
  P(`nenhum valor literal no componente. Um desenho que precise de uma cor nova`);
  P(`precisa de um token novo, e o token tem de valer nos dois temas.`);
  P("");
  for (const g of grupos) {
    P(`### ${g.titulo}`);
    P("");
    P(tabela(
      ["Token", "Valor", "Nota"],
      g.itens.map((i) => [`\`${i.nome}\``, `\`${escapar(i.valor)}\``, escapar(i.nota || "—")]),
    ));
    P("");
  }

  // ------------------------------------------------------------ endpoints
  const e = endpoints();
  const totalRotas = e.reduce((n, s) => n + s.rotas.length, 0);
  P(`## 5. O que a tela pede ao servidor (${totalRotas} chamadas)`);
  P("");
  P(`Agrupado pelo serviço que faz a chamada. Os parâmetros da URL aparecem como`);
  P(`\`:id\`, qualquer que seja o nome no código.`);
  P("");
  for (const servico of e) {
    P(`### \`${servico.servico}\``);
    P("");
    P(tabela(
      ["Método", "Rota"],
      servico.rotas.map((x) => [x.metodo, `\`${escapar(x.rota)}\``]),
    ));
    P("");
  }

  // -------------------------------------------------------- papéis e menu
  const { listas, menu } = papeis();
  P(`## 6. Papéis e menu`);
  P("");
  P(`### Listas de papel usadas pela tela`);
  P("");
  P(tabela(["Lista", "Papéis"], listas.map((l) => [`\`${l.nome}\``, escapar(l.papeis)])));
  P("");
  P(`### Menu lateral`);
  P("");
  P(tabela(["Rótulo", "Rota"], menu.map((m) => [m.rotulo, `\`ROTAS.${m.rota}\``])));
  P("");

  // -------------------------------------------------------------- buracos
  const b = buracos();
  P(`## 7. Buracos de navegação`);
  P("");
  P(`A pergunta que um handoff tem de responder: **partindo da tela inicial, dá`);
  P(`para chegar lá?** Registrar a rota não cria caminho nenhum — em 22/09/2026`);
  P(`três telas ficaram prontas, testadas e inalcançáveis por causa disso.`);
  P("");
  P(`#### Rotas declaradas em \`routes.ts\` e não registradas no roteador`);
  P("");
  P(b.semRegistro.length
    ? b.semRegistro.map((x) => `- \`ROTAS.${x.nome}\` → \`${x.caminho}\``).join("\n")
    : "_Nenhuma._");
  P("");
  P(`#### Telas em \`pages/\` sem rota`);
  P("");
  P(b.semRota.length ? b.semRota.map((x) => `- \`${x}\``).join("\n") : "_Nenhuma._");
  P("");
  P(`#### Rotas que nenhum link aponta`);
  P("");
  P(`Alcançáveis só digitando o endereço. Nem toda é defeito — algumas são`);
  P(`destino de redirecionamento do servidor —, mas cada uma merece uma resposta.`);
  P("");
  P(b.semLink.length ? b.semLink.map((x) => `- \`${x}\``).join("\n") : "_Nenhuma._");
  P("");

  return partes.join("\n");
}

/* --------------------------------------------------------------- entrada */

const documento = montar();
if (process.argv.includes("--stdout")) {
  process.stdout.write(documento);
} else {
  const destino = join(RAIZ, "docs", "HANDOFF-FRONT.md");
  mkdirSync(dirname(destino), { recursive: true });
  writeFileSync(destino, documento + "\n", "utf8");
  const linhas = documento.split("\n").length;
  process.stdout.write(`docs/HANDOFF-FRONT.md — ${linhas} linhas, versão ${versao()}\n`);
}

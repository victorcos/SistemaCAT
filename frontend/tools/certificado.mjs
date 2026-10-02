/**
 * Gera o certificado que põe o dev server em HTTPS — e por que isso importa.
 *
 * O front é aberto de outras máquinas, pelo IP (`host: CAT_HOST ?? true` no
 * `vite.config.ts`). E `http://<ip>:5173` **não é contexto seguro**, o que tem
 * uma consequência que custou uma investigação em 02/10/2026: a
 * `File System Access API` não existe fora de contexto seguro, o download cai
 * no caminho antigo, e o caminho antigo põe o arquivo **inteiro na memória da
 * aba** antes de gravar. Num 037 de 2,93 milhões de linhas isso não passa.
 *
 * Com HTTPS a origem vira segura, o seletor de pasta volta, e com ele o
 * `pipeTo` — que liga a resposta da rede direto ao arquivo, em blocos, sem
 * teto de tamanho. Ver `src/lib/download.ts`.
 *
 * ## O que este script faz, e o que ele não resolve
 *
 * Gera um par chave/certificado **autoassinado**, com o `subjectAltName`
 * cobrindo `localhost`, `127.0.0.1` e **todos os IPv4 da máquina** — sem o SAN
 * do endereço que a pessoa digita, o navegador nem oferece o "prosseguir".
 *
 * Autoassinado significa aviso do navegador na primeira visita. Quem prosseguir
 * ganha contexto seguro de verdade (`isSecureContext === true`), que é tudo o
 * que o download precisa. Para não ter aviso, o caminho é instalar a autoridade
 * em cada máquina (`mkcert -install`) ou servir o build atrás da API com
 * certificado próprio — que é a solução estrutural, e outra conversa.
 *
 * **A chave privada não é versionada.** O `.gitignore` da raiz já exclui
 * `*.pem` e `*.key`; este script grava em `frontend/certificado/`, e cada
 * máquina gera a sua.
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { hostname, networkInterfaces } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
export const PASTA = join(RAIZ, "certificado");
export const CHAVE = join(PASTA, "dev.key");
export const CERTIFICADO = join(PASTA, "dev.pem");

/** O navegador recusa confiar em certificado com validade longa demais. */
const DIAS = 825;

/** Onde este dev server pode ser alcançado. Sem isto no SAN, o navegador barra. */
function enderecos() {
  const ips = Object.values(networkInterfaces())
    .flatMap((interfaces) => interfaces ?? [])
    .filter((i) => i.family === "IPv4" && !i.internal)
    .map((i) => i.address);

  const nomes = ["localhost", hostname()];
  return {
    ips: [...new Set(["127.0.0.1", ...ips])],
    nomes: [...new Set(nomes.filter(Boolean))],
  };
}

function gerar() {
  const { ips, nomes } = enderecos();
  const san = [
    ...nomes.map((n) => `DNS:${n}`),
    ...ips.map((ip) => `IP:${ip}`),
    "IP:::1",
  ].join(",");

  mkdirSync(PASTA, { recursive: true });
  execFileSync(
    "openssl",
    [
      "req", "-x509",
      "-newkey", "rsa:2048",
      "-nodes",
      "-keyout", CHAVE,
      "-out", CERTIFICADO,
      "-days", String(DIAS),
      "-subj", `/CN=${hostname()}`,
      "-addext", `subjectAltName=${san}`,
      // sem isto o Chrome recusa o certificado como "não é uma autoridade"
      "-addext", "basicConstraints=critical,CA:FALSE",
      "-addext", "keyUsage=critical,digitalSignature,keyEncipherment",
      "-addext", "extendedKeyUsage=serverAuth",
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
  );

  console.log(`certificado gerado em ${PASTA}`);
  console.log(`  válido por ${DIAS} dias, cobrindo:`);
  for (const n of nomes) console.log(`    https://${n}:5173`);
  for (const ip of ips) console.log(`    https://${ip}:5173`);
  console.log(
    "\nO `npm run dev` já o encontra sozinho. Na primeira visita o navegador\n" +
      "avisa que o certificado é autoassinado — prosseguir dá contexto seguro,\n" +
      "que é o que o download em fluxo precisa.",
  );
}

if (existsSync(CERTIFICADO) && !process.argv.includes("--refazer")) {
  console.log(
    `já existe ${CERTIFICADO}\n` +
      "Os endereços da máquina podem ter mudado (IP novo não está no certificado\n" +
      "antigo, e aí o navegador barra). Para refazer: npm run certificado -- --refazer",
  );
} else {
  try {
    gerar();
  } catch (erro) {
    const saida = erro.stderr?.toString().trim();
    console.error(
      "não deu para gerar o certificado.\n" +
        (saida ? `openssl: ${saida}\n` : "") +
        "\nÉ o `openssl` que falta no PATH? Ele vem com o Git para Windows, em\n" +
        "C:\\Program Files\\Git\\usr\\bin. Sem certificado o dev server sobe em\n" +
        "HTTP normalmente — só não há seletor de pasta fora de localhost.",
    );
    process.exitCode = 1;
  }
}

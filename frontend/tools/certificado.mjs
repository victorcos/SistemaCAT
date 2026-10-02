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
 * cobrindo `localhost`, `127.0.0.1`, todos os IPv4 da máquina e **a sub-rede
 * /24 de cada um deles** — sem o SAN do endereço que a pessoa digita, o
 * navegador nem oferece o "prosseguir".
 *
 * ## Por que a sub-rede inteira, e não só o IP de agora
 *
 * O endereço muda. Em 02/10/2026 ele mudou duas vezes em quinze minutos — cabo
 * para Wi-Fi e de volta —, e o certificado ficou obsoleto nas duas. Usar o nome
 * da máquina resolveria, mas depender do DNS interno da empresa é depender da
 * equipe de infra, e isso foi recusado com razão.
 *
 * Então cobre-se o /24: `192.168.88.1` a `.254`. Qualquer endereço que o DHCP
 * entregue já está no certificado, e não há o que refazer. São ~254 entradas
 * por adaptador, o que um certificado aguenta sem reclamar.
 *
 * **Não é frouxidão de segurança.** O certificado continua autoassinado e a
 * chave privada continua só aqui: cobrir um endereço não permite a ninguém se
 * passar por ele. O que a sub-rede compra é o navegador parar de reclamar de
 * nome quando o IP troca.
 *
 * Os adaptadores virtuais do Hyper-V (`vEthernet ...`) entram só com o próprio
 * endereço, sem expansão: ninguém acessa o sistema por eles.
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

/** Todo endereço da /24 de um IP. `192.168.88.185` -> `.1` até `.254`. */
function subRede(ip) {
  const partes = ip.split(".");
  if (partes.length !== 4) return [ip];
  const prefixo = partes.slice(0, 3).join(".");
  return Array.from({ length: 254 }, (_, i) => `${prefixo}.${i + 1}`);
}

/** Onde este dev server pode ser alcançado. Sem isto no SAN, o navegador barra. */
function enderecos() {
  const reais = [];
  const virtuais = [];
  for (const [nome, interfaces] of Object.entries(networkInterfaces())) {
    for (const i of interfaces ?? []) {
      if (i.family !== "IPv4" || i.internal) continue;
      // o switch virtual do Hyper-V não é por onde ninguém acessa o sistema
      (nome.startsWith("vEthernet") ? virtuais : reais).push(i.address);
    }
  }

  const ips = ["127.0.0.1", ...virtuais, ...reais.flatMap(subRede)];
  return {
    ips: [...new Set(ips)],
    nomes: [...new Set(["localhost", hostname()].filter(Boolean))],
    // o que se imprime: a sub-rede inteira poluiria a saída
    destaque: [...new Set(reais)],
  };
}

function gerar() {
  const { ips, nomes, destaque } = enderecos();
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
  console.log(`  válido por ${DIAS} dias, cobrindo ${ips.length} endereços.`);
  console.log("  Os desta máquina agora:");
  for (const n of nomes) console.log(`    https://${n}`);
  for (const ip of destaque) console.log(`    https://${ip}`);
  if (destaque.length) {
    const r = destaque.map((ip) => ip.split(".").slice(0, 3).join(".") + ".1-254");
    console.log(`  E a sub-rede inteira (${r.join(", ")}), para o IP poder mudar`);
    console.log("  sem o certificado ficar obsoleto.");
  }
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

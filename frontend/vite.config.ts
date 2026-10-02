import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/**
 * HTTPS quando houver certificado, HTTP quando nao houver.
 *
 * **Nao e firula: e o que decide se o download funciona de outra maquina.**
 * `http://<ip>:5173` nao e contexto seguro, e fora de contexto seguro a
 * `File System Access API` nao existe — o download cai no caminho antigo, que
 * poe o arquivo inteiro na memoria da aba antes de gravar. Num 037 de 2,93
 * milhoes de linhas isso nao passa (investigado em 02/10/2026).
 *
 * Opt-in pela existencia do arquivo, e nao por variavel de ambiente: quem nao
 * gerou certificado continua em HTTP sem configurar nada, e quem gerou nao
 * precisa lembrar de ligar. `npm run certificado` gera.
 */
/**
 * A API esta em HTTPS? Quem decide e o `backend/.env`, o mesmo arquivo que ela le.
 *
 * **Sem isto o desenvolvimento quebra quando o modo de rede e ligado.** O proxy
 * apontava para `http://localhost:8010` fixo; no dia em que a API passou a servir
 * o front em HTTPS (02/10/2026), `localhost:5173` continuou carregando a pagina e
 * passou a dar 500 em toda chamada de API — pagina que abre e nao funciona, que e
 * pior que pagina que nao abre.
 *
 * Ler o `.env` da API e nao uma variavel propria: uma fonte de verdade. Ligar o
 * modo em um lugar nao pode exigir lembrar de um segundo.
 */
function apiEmHttps() {
  const env = join(dirname(fileURLToPath(import.meta.url)), "..", "backend", ".env");
  if (!existsSync(env)) return false;
  return readFileSync(env, "utf8")
    .split(/\r?\n/)
    .some((l) => /^\s*CAT_TLS_CERTIFICADO\s*=\s*\S/.test(l));
}

function certificado() {
  const pasta = join(dirname(fileURLToPath(import.meta.url)), "certificado");
  const chave = join(pasta, "dev.key");
  const cert = join(pasta, "dev.pem");
  if (!existsSync(chave) || !existsSync(cert)) return undefined;
  return { key: readFileSync(chave), cert: readFileSync(cert) };
}

export default defineConfig({
  plugins: [react(), tailwindcss()],

  // lucide-react exporta um icone por modulo; sem o pre-bundle o dev server
  // abre centenas de requisicoes na primeira carga e demora a subir
  optimizeDeps: { include: ["lucide-react"] },

  // '@/' espelha o paths do tsconfig. fileURLToPath e nao .pathname: no
  // Windows o .pathname devolve '/C:/projetos/...' e o resolve quebra.
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },

  // Os testes de tela rodam em jsdom. O nome do arquivo segue o resto da casa
  // (`.teste.tsx`, como `test_*.py` no motor) para que procurar por "teste"
  // ache tudo, nas duas linguagens.
  test: {
    environment: "jsdom",
    include: ["src/**/*.teste.{ts,tsx}"],
    setupFiles: ["src/testes/ambiente.ts"],
    restoreMocks: true,
  },

  server: {
    port: 5173,
    https: certificado(),

    // Escutar em todas as interfaces, e nao so em ::1.
    //
    // A tela roda no micro de quem desenvolve, mas quem confere a apuracao abre
    // de outra maquina. Fechado, o Vite atende `localhost` e recusa a conexao
    // vinda da rede — de fora parece servidor fora do ar, sem pista nenhuma.
    // `CAT_HOST=localhost npm run dev` fecha de novo.
    host: process.env.CAT_HOST ?? true,

    // Por IP (http://192.168.x.x:5173) o Vite libera sozinho; por NOME de
    // maquina ele responde "Blocked request" desde a 6.0.9, que e protecao
    // contra rebind de DNS. CAT_HOSTS aceita a lista, separada por virgula.
    allowedHosts: (process.env.CAT_HOSTS ?? "")
      .split(",")
      .map((h) => h.trim())
      .filter(Boolean),
    // O front fala com a API por caminho relativo; o proxy evita CORS no dev.
    //
    // Porta 8010 e nao 8000: a 8000 costuma estar ocupada por outro projeto
    // (o Reenquadrador roda nela). Apontar para uma API alheia faz todo login
    // falhar com 404 e nenhuma pista na tela.
    //
    // Para mudar sem editar codigo: CAT_API_PORT=8011 npm run dev. O motor (8020)
    // nao serve: ele nao tem rota /api desde a fatia 7.
    proxy: {
      "/api": {
        target: `${apiEmHttps() ? "https" : "http"}://localhost:${process.env.CAT_API_PORT ?? 8010}`,
        changeOrigin: true,
        // o certificado da API e autoassinado: validar aqui recusaria a propria
        // maquina. O proxy nao sai do host, e quem valida de verdade e o
        // navegador, na ponta
        secure: false,
      },
    },
  },
});

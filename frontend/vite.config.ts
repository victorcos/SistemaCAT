import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

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
        target: `http://localhost:${process.env.CAT_API_PORT ?? 8010}`,
        changeOrigin: true,
      },
    },
  },
});

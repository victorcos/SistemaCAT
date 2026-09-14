import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
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

  server: {
    port: 5173,
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

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // O front fala com a API por caminho relativo; o proxy evita CORS no dev.
    //
    // Porta 8010 e nao 8000: a 8000 costuma estar ocupada por outro projeto
    // (o Reenquadrador roda nela). Apontar para uma API alheia faz todo login
    // falhar com 404 e nenhuma pista na tela.
    //
    // Para mudar sem editar codigo: CAT_API_PORT=8020 npm run dev
    proxy: {
      "/api": {
        target: `http://localhost:${process.env.CAT_API_PORT ?? 8010}`,
        changeOrigin: true,
      },
    },
  },
});

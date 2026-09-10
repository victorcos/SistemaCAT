import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // o front fala com a API por caminho relativo; o proxy evita CORS no dev
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
});

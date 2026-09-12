import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ThemeProvider } from "@/providers/ThemeProvider";
// as fontes viajam com o app. Sem isto cada máquina renderizava com o que
// tivesse instalado: "Inter" não existia em nenhuma, o navegador caía no
// Segoe UI, e o peso 650 dos rótulos (que só uma fonte variável tem)
// virava o negrito que houvesse — o rótulo da ficha saía "bugado".
import "@fontsource-variable/inter";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@/styles/tokens.css";
// ponte tokens -> Tailwind. Depois de tokens.css porque le as variaveis dele.
import "@/styles/tema.css";

const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("Elemento #raiz não encontrado no index.html");

createRoot(raiz).render(
  <StrictMode>
    {/* fora do roteador de proposito: tema nao depende de rota, e precisa
        valer ja na primeira pintura */}
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
);

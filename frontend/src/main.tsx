import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// as fontes viajam com o app. Sem isto cada máquina renderizava com o que
// tivesse instalado: "Inter" não existia em nenhuma, o navegador caía no
// Segoe UI, e o peso 650 dos rótulos (que só uma fonte variável tem)
// virava o negrito que houvesse — o rótulo da ficha saía "bugado".
import "@fontsource-variable/inter";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./estilos/tokens.css";

const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("Elemento #raiz não encontrado no index.html");

createRoot(raiz).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

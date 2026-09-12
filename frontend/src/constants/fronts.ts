/** As frentes de trabalho que o sistema atende. Saiu de services/importacao.ts
 *  porque é vocabulário do domínio, não detalhe de transporte HTTP. */
export const FRENTES = {
  cat42: "CAT 42 — ressarcimento de ICMS-ST",
  depara: "De-para de produto",
  sped: "Quebra de SPED",
  notafiscal: "Nota fiscal",
} as const;

export type Frente = keyof typeof FRENTES;

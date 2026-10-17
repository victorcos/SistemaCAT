/**
 * Que tributo um trabalho novo recebe — e por que a frente vem antes dos arquivos.
 *
 * Em 17/10/2026 abriu-se um trabalho de **CAT 42** e ele nasceu com módulo
 * `irpj_csll`. A remessa tinha uma ECD, que atende PIS/COFINS e IRPJ/CSLL, e o
 * primeiro da lista virou o padrão sem ninguém olhar a frente escolhida ao
 * lado.
 *
 * Não era cosmético: o módulo decide as **etapas** (`Etapas.TrilhasDo`). Aquele
 * trabalho nasceu sem razão dos itens, sem ST suportado e sem arquivo digital —
 * a CAT 42 inteira. E não foi o primeiro: os trabalhos 19 e 25 também estão
 * gravados como `frente=cat42` com módulo de PIS/COFINS.
 */

import { describe, expect, it } from "vitest";

import { MODULO_FIXO_DA_FRENTE, moduloPadrao } from "./Importar";
import type { Segmento } from "@/services/segmentos";

const TUDO: Segmento[] = [
  {
    chave: "icms",
    rotulo: "ICMS",
    descricao: "",
    modulos: [
      { chave: "icms", rotulo: "ICMS", descricao: "" },
      { chave: "ibs", rotulo: "IBS", descricao: "" },
    ],
  },
  {
    chave: "piscofins",
    rotulo: "PIS/COFINS",
    descricao: "",
    modulos: [{ chave: "piscofins", rotulo: "PIS/COFINS", descricao: "" }],
  },
  {
    chave: "irpj_csll",
    rotulo: "IRPJ/CSLL",
    descricao: "",
    modulos: [{ chave: "irpj_csll", rotulo: "IRPJ/CSLL", descricao: "" }],
  },
] as unknown as Segmento[];

describe("o tributo de um trabalho novo", () => {
  it("a CAT 42 é de ICMS mesmo com uma ECD na remessa", () => {
    // o caso exato de 17/10/2026: a ECD atende irpj_csll e piscofins
    expect(moduloPadrao(TUDO, ["irpj_csll", "piscofins"], "cat42")).toBe("icms");
  });

  it("e continua de ICMS quando os arquivos não sugerem nada", () => {
    expect(moduloPadrao(TUDO, [], "cat42")).toBe("icms");
  });

  it("nas outras frentes, os arquivos é que sugerem", () => {
    expect(moduloPadrao(TUDO, ["piscofins"], "sped")).toBe("piscofins");
    expect(moduloPadrao(TUDO, ["irpj_csll"], "sped")).toBe("irpj_csll");
  });

  it("sem indicação utilizável, o ICMS continua sendo o padrão", () => {
    expect(moduloPadrao(TUDO, ["tributo_que_nao_existe"], "sped")).toBe("icms");
  });

  it("quem não enxerga o ICMS recebe o primeiro que enxerga", () => {
    const soContribuicoes = [TUDO[1]];
    expect(moduloPadrao(soContribuicoes, [], "sped")).toBe("piscofins");
  });

  it("a CAT 42 não impõe ICMS a quem não enxerga ICMS", () => {
    // impor um tributo que a pessoa não vê criaria trabalho invisível para ela
    const soContribuicoes = [TUDO[1]];
    expect(moduloPadrao(soContribuicoes, ["piscofins"], "cat42")).toBe("piscofins");
  });

  it("só a CAT 42 fixa o tributo; as demais frentes atravessam tributos", () => {
    expect(MODULO_FIXO_DA_FRENTE.cat42).toBe("icms");
    expect(MODULO_FIXO_DA_FRENTE.sped).toBeUndefined();
    expect(MODULO_FIXO_DA_FRENTE.depara).toBeUndefined();
    expect(MODULO_FIXO_DA_FRENTE.notafiscal).toBeUndefined();
  });
});

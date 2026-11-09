/**
 * Para onde a seta "voltar" leva, saindo de uma etapa.
 *
 * Até 09/11/2026 ela levava sempre ao trabalho — a lista de FRENTES (CAT 42,
 * Quebra de XML, Crédito outorgado). Quem estava na etapa 3 da CAT 42 e
 * clicava em voltar subia dois níveis de uma vez e tinha de entrar na frente
 * de novo para seguir para a etapa 4.
 *
 * O que estes testes guardam é a exceção que não se adivinha: frente de uma
 * etapa só **não** tem painel, porque o card dela vai direto para a tela da
 * etapa. Voltar para esse painel levaria a uma tela que ninguém viu.
 */

import { describe, expect, it } from "vitest";

import { rotuloDoVoltar, voltarDaEtapa } from "./voltar";
import type { ProjetoDetalhe, Trilha } from "@/services/importacao";

function trilha(chave: string, rotulo: string, etapas: string[]): Trilha {
  return {
    chave,
    rotulo,
    sigla: chave.slice(0, 3).toUpperCase(),
    descricao: "",
    etapas,
    feitas: 0,
    totais: etapas.length,
    construida: true,
  };
}

/** como o servidor descreve o módulo de ICMS hoje */
const ICMS = {
  projeto: {} as ProjetoDetalhe["projeto"],
  etapas: [],
  trilhas: [
    trilha("importar", "Importar arquivos", ["importar"]),
    trilha("cat42", "CAT 42", [
      "conferencia",
      "movimentos",
      "st_suportado",
      "razao",
      "apuracao",
      "arquivo_digital",
      "entrega",
    ]),
    trilha("credito_outorgado", "Crédito outorgado", ["credito_outorgado"]),
    trilha("quebra_xml", "Quebra de XML", ["quebra_xml"]),
  ],
} satisfies ProjetoDetalhe;

describe("voltarDaEtapa", () => {
  it("volta ao painel da frente, e não à lista de frentes", () => {
    expect(voltarDaEtapa(32, "movimentos", ICMS)).toBe("/projetos/32/frente/cat42");
  });

  it("vale para toda etapa da CAT 42", () => {
    for (const etapa of ICMS.trilhas[1].etapas) {
      expect(voltarDaEtapa(7, etapa, ICMS)).toBe("/projetos/7/frente/cat42");
    }
  });

  it("frente de uma etapa só volta ao trabalho: o painel dela nunca é mostrado", () => {
    expect(voltarDaEtapa(32, "credito_outorgado", ICMS)).toBe("/projetos/32");
    expect(voltarDaEtapa(32, "quebra_xml", ICMS)).toBe("/projetos/32");
    expect(voltarDaEtapa(32, "importar", ICMS)).toBe("/projetos/32");
  });

  it("sem o detalhe carregado ainda, volta ao trabalho em vez de ficar sem link", () => {
    expect(voltarDaEtapa(32, "movimentos", null)).toBe("/projetos/32");
    expect(voltarDaEtapa(32, "movimentos", undefined)).toBe("/projetos/32");
  });

  it("etapa que nenhuma frente reivindica volta ao trabalho", () => {
    expect(voltarDaEtapa(32, "etapa_que_nao_existe", ICMS)).toBe("/projetos/32");
    expect(voltarDaEtapa(32, "movimentos", { ...ICMS, trilhas: undefined })).toBe("/projetos/32");
  });
});

describe("rotuloDoVoltar", () => {
  it("nomeia a frente quando é para lá que o clique leva", () => {
    expect(rotuloDoVoltar("razao", ICMS)).toBe("Voltar a CAT 42");
  });

  it("continua dizendo trabalho quando é para o trabalho que leva", () => {
    expect(rotuloDoVoltar("quebra_xml", ICMS)).toBe("Voltar ao trabalho");
    expect(rotuloDoVoltar("razao", null)).toBe("Voltar ao trabalho");
  });
});

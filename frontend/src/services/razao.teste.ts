/**
 * A frase que diz de onde veio a alíquota do confronto.
 *
 * Ela existe porque o número do razão muda conforme a prova: 2.228 saídas da
 * empresa 26 não tinham alíquota no 0200 e passaram a ter uma lida na entrada
 * da mercadoria. Quem revisa precisa ver **por onde** se procurou (o código ou
 * o NCM) e **o que** disse a alíquota (destaque, ST retido, efetiva do CST 60),
 * porque a confiança em cada uma é diferente.
 */

import { describe, expect, it } from "vitest";

import { ondeAAliquotaFoiBuscada } from "./razao";

describe("ondeAAliquotaFoiBuscada", () => {
  it("põe a fonte mais usada na frente e escreve o número em pt-BR", () => {
    expect(ondeAAliquotaFoiBuscada({ ncm_st: 949, ncm_interna: 7555, ncm_efetiva: 83 })).toBe(
      "7.555 pelo NCM, ICMS destacado na entrada; " +
        "949 pelo NCM, ST retido na entrada; " +
        "83 pelo NCM, alíquota efetiva do CST 60",
    );
  });

  it("distingue o que veio pelo código do que veio pelo NCM", () => {
    expect(ondeAAliquotaFoiBuscada({ item_st: 2 })).toBe("2 pelo código, ST retido na entrada");
  });

  it("não inventa frase quando nada foi lido na entrada", () => {
    expect(ondeAAliquotaFoiBuscada(undefined)).toBe("");
    expect(ondeAAliquotaFoiBuscada({})).toBe("");
    expect(ondeAAliquotaFoiBuscada({ ncm_st: 0 })).toBe("");
  });

  it("mostra a chave crua da fonte que ainda não tem rótulo, em vez de sumir com ela", () => {
    expect(ondeAAliquotaFoiBuscada({ ncm_futura: 3 })).toBe("3 ncm_futura");
  });
});

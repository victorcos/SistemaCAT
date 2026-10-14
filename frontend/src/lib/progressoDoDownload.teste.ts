/**
 * O andamento que aparece ao lado do botão de baixar.
 *
 * Montar a Consulta de Entradas da empresa 24 levou 39 minutos em 14/10/2026,
 * com um girador e nada mais na tela. Houve quem concluísse que tinha travado
 * e clicasse de novo, pondo dois pedidos a disputar o mesmo disco.
 *
 * O que estes testes guardam é o que faz esse enfeite ser inofensivo: consulta
 * que falha não derruba o download, e o que sobrou de um pedido não vaza para
 * o seguinte.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { acompanhar, agora, assinar, nada, publicar } from "./progressoDoDownload";

const ANDANDO = { passo: "Montando a planilha", feito: 50, total: 200, fracao: 0.25, terminado: false };

afterEach(() => {
  nada();
  vi.useRealTimers();
});

describe("o canal", () => {
  it("entrega a quem assina o que já estava em curso", () => {
    publicar(ANDANDO);
    const visto: unknown[] = [];
    assinar((a) => visto.push(a));
    expect(visto).toEqual([ANDANDO]);
  });

  it("para de entregar a quem cancelou a assinatura", () => {
    const visto: unknown[] = [];
    const cancelar = assinar((a) => visto.push(a));
    cancelar();
    publicar(ANDANDO);
    expect(visto).toEqual([null]);
  });

  it("limpar apaga o que estava em curso, para não vazar no pedido seguinte", () => {
    publicar(ANDANDO);
    nada();
    expect(agora()).toBeNull();
  });
});

describe("acompanhar", () => {
  it("pergunta de segundo em segundo e publica o que vem", async () => {
    vi.useFakeTimers();
    const buscar = vi.fn().mockResolvedValue(ANDANDO);
    const parar = acompanhar("k1", buscar);

    await vi.advanceTimersByTimeAsync(1000);
    expect(buscar).toHaveBeenCalledWith("k1");
    expect(agora()).toEqual(ANDANDO);

    await vi.advanceTimersByTimeAsync(1000);
    expect(buscar).toHaveBeenCalledTimes(2);
    parar();
  });

  it("consulta que falha não derruba o download", async () => {
    vi.useFakeTimers();
    const buscar = vi.fn().mockRejectedValue(new Error("rede caiu"));
    const parar = acompanhar("k2", buscar);

    await vi.advanceTimersByTimeAsync(3000);

    expect(buscar).toHaveBeenCalledTimes(3);   // continuou perguntando
    expect(agora()).toBeNull();                 // e não publicou lixo
    parar();
  });

  it("parar limpa o andamento e não pergunta mais", async () => {
    vi.useFakeTimers();
    const buscar = vi.fn().mockResolvedValue(ANDANDO);
    const parar = acompanhar("k3", buscar);
    await vi.advanceTimersByTimeAsync(1000);
    parar();

    await vi.advanceTimersByTimeAsync(5000);
    expect(buscar).toHaveBeenCalledTimes(1);
    expect(agora()).toBeNull();
  });
});

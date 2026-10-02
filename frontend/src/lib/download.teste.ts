/**
 * Por que não há seletor de pasta — e por que a resposta não pode ser o silêncio.
 *
 * Dois relatos, nove dias e uma causa diferente cada:
 *
 * * **01/10/2026** — o seletor existia e falhava, e o `AbortError` dele era
 *   tratado como desistência. Nenhuma requisição saía, nenhum arquivo aparecia,
 *   nenhum erro na tela. Resolvido medindo o tempo: abortar em menos de 150 ms
 *   não é alguém lendo a janela e desistindo;
 * * **02/10/2026** — o seletor **não existia**, e esse ramo saía calado. Um 037
 *   de 2,93 milhões de linhas foi pedido de outra máquina, pelo IP do dev
 *   server; `http` num IP de rede não é contexto seguro, a API não está lá, e o
 *   relato foi "nem gerou a opção de escolher o caminho". O comportamento
 *   estava certo — faltava dizer.
 *
 * Estes testes fecham o segundo. `motivoSemSeletor` separa os dois motivos
 * porque **as soluções são diferentes**: contexto inseguro se resolve abrindo
 * por `localhost`; navegador sem suporte não se resolve.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DownloadCancelado,
  escolherOndeSalvar,
  foiAbortado,
  motivoSemSeletor,
} from "./download";

type Janela = typeof window & {
  showSaveFilePicker?: unknown;
  isSecureContext: boolean;
};

const janela = window as Janela;
const seguroOriginal = janela.isSecureContext;

function semApi(seguro: boolean) {
  delete janela.showSaveFilePicker;
  Object.defineProperty(janela, "isSecureContext", {
    value: seguro, configurable: true, writable: true,
  });
}

function comApi(seletor: () => Promise<unknown>) {
  janela.showSaveFilePicker = seletor;
  Object.defineProperty(janela, "isSecureContext", {
    value: true, configurable: true, writable: true,
  });
}

afterEach(() => {
  delete janela.showSaveFilePicker;
  Object.defineProperty(janela, "isSecureContext", {
    value: seguroOriginal, configurable: true, writable: true,
  });
});

describe("motivoSemSeletor", () => {
  it("não acusa nada quando a API existe", () => {
    comApi(async () => ({}));

    expect(motivoSemSeletor()).toBe("");
  });

  it("culpa o contexto quando a página não é segura", () => {
    semApi(false);

    expect(motivoSemSeletor()).toBe("contexto-inseguro");
  });

  it("culpa o navegador quando o contexto é seguro e a API falta", () => {
    // Firefox e Safari em https: não há o que fazer além da pasta de downloads
    semApi(true);

    expect(motivoSemSeletor()).toBe("sem-suporte");
  });
});

describe("escolherOndeSalvar sem seletor", () => {
  it("cai no caminho antigo e **avisa** no console", async () => {
    semApi(false);
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});

    const destino = await escolherOndeSalvar("consulta_de_entradas.xlsx");

    expect(destino).toBeNull();
    expect(aviso).toHaveBeenCalledOnce();
    // a mensagem tem de dizer o que fazer, não só que faltou
    expect(aviso.mock.calls[0][0]).toContain("localhost");
  });

  it("diz outra coisa quando a culpa é do navegador", async () => {
    semApi(true);
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});

    await escolherOndeSalvar("consulta_de_entradas.csv");

    expect(aviso.mock.calls[0][0]).toContain("showSaveFilePicker");
    expect(aviso.mock.calls[0][0]).not.toContain("localhost");
  });
});

describe("escolherOndeSalvar com seletor", () => {
  const abortar = () => {
    const e = new DOMException("abortado", "AbortError");
    return Promise.reject(e);
  };

  it("devolve o destino quando a pessoa escolhe", async () => {
    const alvo = { nome: "destino" };
    comApi(async () => alvo);

    await expect(escolherOndeSalvar("x.xlsx")).resolves.toBe(alvo);
  });

  it("aborto imediato é seletor que não apareceu, não desistência", async () => {
    comApi(abortar);
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});

    // sem o relógio, isto virava `DownloadCancelado` e o download sumia calado
    await expect(escolherOndeSalvar("x.xlsx")).resolves.toBeNull();
    expect(aviso).toHaveBeenCalled();
  });

  it("aborto depois de uma pausa é decisão de quem clicou", async () => {
    comApi(async () => {
      // mais que os 150 ms que ninguém leva para ler uma janela e desistir
      await new Promise((pronto) => setTimeout(pronto, 180));
      return abortar();
    });

    await expect(escolherOndeSalvar("x.xlsx")).rejects.toBeInstanceOf(
      DownloadCancelado,
    );
  });
});

describe("foiAbortado", () => {
  it("reconhece o aborto e ignora o resto", () => {
    expect(foiAbortado(new DOMException("x", "AbortError"))).toBe(true);
    expect(foiAbortado(new Error("rede caiu"))).toBe(false);
    expect(foiAbortado(new DownloadCancelado())).toBe(false);
  });
});

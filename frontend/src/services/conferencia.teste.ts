/**
 * Quem baixa: o navegador ou a aba.
 *
 * **A aba perde.** O caminho antigo busca com `fetch` e, sem o seletor de pasta
 * — que não existe fora de contexto seguro, e `http://<ip>:5173` não é —, segura
 * a resposta inteira na memória antes de gravar. Num 037 de 2,93 milhões de
 * linhas isso não passa. Investigado em 02/10/2026, depois de um "está
 * carregando há um tempo, não sei se travou".
 *
 * O caminho novo pede um tíquete (um `POST` barato, que **não** gera a planilha)
 * e entrega a URL ao navegador. O gerenciador dele grava em fluxo, mostra
 * progresso, e a aba não toca nos bytes.
 *
 * Só a rota de planilha tem tíquete. A extração da quebra e a planilha da 047
 * têm rota própria, com corpo, e seguem pelo caminho antigo — é esse desvio que
 * estes testes guardam, porque errá-lo manda um `POST` para uma rota que não
 * existe e o download morre com 404.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { baixarArquivo } from "./conferencia";

const TIQUETE = { tiquete: "abc123", vale_por_segundos: 120 };

function resposta(corpo: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => corpo,
    blob: async () => new Blob(["x"]),
    body: null,
  } as unknown as Response;
}

let cliques: HTMLAnchorElement[];

beforeEach(() => {
  cliques = [];
  // jsdom não baixa nada; o que interessa é o que o link pedia
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    cliques.push(this);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("rota de planilha", () => {
  it("pede tíquete e entrega a URL ao navegador", async () => {
    const buscar = vi.fn().mockResolvedValue(resposta(TIQUETE));
    vi.stubGlobal("fetch", buscar);

    await baixarArquivo(
      "/api/apuracao-piscofins/12/planilhas/entradas?formato=csv",
      "consulta_de_entradas.csv",
    );

    // o POST vai para o tíquete, levando o recorte
    expect(buscar).toHaveBeenCalledOnce();
    const [url, opcoes] = buscar.mock.calls[0];
    expect(url).toBe("/api/apuracao-piscofins/12/planilhas/entradas/tiquete?formato=csv");
    expect(opcoes.method).toBe("POST");

    // e o download é do navegador, com o tíquete na URL
    expect(cliques).toHaveLength(1);
    expect(cliques[0].getAttribute("href")).toBe(
      "/api/apuracao-piscofins/12/planilhas/entradas?formato=csv&t=abc123",
    );
    expect(cliques[0].getAttribute("download")).toBe("consulta_de_entradas.csv");
  });

  it("não deixa o tíquete viajar no Referer", async () => {
    // ele anda na URL; sem `noreferrer` iria no cabeçalho de toda requisição
    // que a página fizesse depois
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(resposta(TIQUETE)));

    await baixarArquivo("/api/exclusoes/9/planilhas/pacote", "pacote.zip");

    expect(cliques[0].rel).toBe("noreferrer");
  });

  it("o `?` só aparece uma vez quando não havia recorte", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(resposta(TIQUETE)));

    await baixarArquivo("/api/exclusoes/9/planilhas/pacote", "pacote.zip");

    expect(cliques[0].getAttribute("href")).toBe(
      "/api/exclusoes/9/planilhas/pacote?t=abc123",
    );
  });

  it("recusa do tíquete vira erro na tela, antes de qualquer espera", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      resposta({ detail: "A apuração das exclusões ainda não terminou." }, 409),
    ));

    await expect(
      baixarArquivo("/api/exclusoes/9/planilhas/pacote", "pacote.zip"),
    ).rejects.toThrow("ainda não terminou");
    expect(cliques).toHaveLength(0);
  });
});

describe("rota que não é de planilha", () => {
  it("segue pelo caminho antigo, sem pedir tíquete", async () => {
    // a extração da quebra tem rota própria: um POST para `/tiquete` ali
    // bateria em 404 e o download morreria sem explicação
    const buscar = vi.fn().mockResolvedValue(resposta({}, 200));
    vi.stubGlobal("fetch", buscar);

    await baixarArquivo("/api/quebra-de-sped/3/extracoes", "sped.zip");

    const [url, opcoes] = buscar.mock.calls[0];
    expect(url).toBe("/api/quebra-de-sped/3/extracoes");
    expect(opcoes?.method).toBeUndefined();
    expect(url).not.toContain("tiquete");
  });

  it("a própria rota do tíquete não pede outro tíquete", async () => {
    const buscar = vi.fn().mockResolvedValue(resposta({}, 200));
    vi.stubGlobal("fetch", buscar);

    await baixarArquivo(
      "/api/exclusoes/9/planilhas/pacote/tiquete", "pacote.zip",
    );

    expect(buscar.mock.calls[0][0]).not.toContain("tiquete/tiquete");
  });
});

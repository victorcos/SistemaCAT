/**
 * Quem baixa é a aba, e a pessoa escolhe a pasta.
 *
 * Entre 02/10 e 14/10/2026 a planilha saía por outro caminho: um tíquete e um
 * `<a download>`, com o navegador gravando onde quisesse. Tirava o teto de
 * memória, mas tirava junto a escolha da pasta — e trouxe um defeito próprio:
 * o clique no link acontecia **depois** da ida à rede, e Chrome e Edge
 * bloqueiam download que perdeu o gesto de quem clicou. O que se via era
 * "verifique a conexão com a Internet", sem requisição nenhuma sair.
 *
 * Voltou a ser como era (decisão do Victor, 14/10/2026). O que estes testes
 * guardam é a ordem que faz isso funcionar, e que já custou duas investigações:
 *
 * * **o seletor vem antes da busca** — ele só abre enquanto a ativação do
 *   clique vale, e ela não sobrevive a uma ida à rede;
 * * **o arquivo criado é descartado quando a resposta não presta** — o seletor
 *   cria o arquivo ao confirmar o nome, e sem o descarte fica um arquivo de
 *   0 byte com cara de planilha;
 * * **cancelar não é erro**, e falha de gravação não é cancelamento.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { baixarArquivo } from "./conferencia";
import * as disco from "../lib/download";

const PLANILHA = "/api/apuracao-piscofins/12/planilhas/entradas?formato=csv";

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

/** O que `showSaveFilePicker` devolveria, sem tocar em disco. */
function arquivoFalso() {
  return { nome: "escolhido" } as unknown as FileSystemFileHandle;
}

let ordem: string[];

beforeEach(() => {
  ordem = [];
  vi.spyOn(disco, "escolherOndeSalvar").mockImplementation(async () => {
    ordem.push("seletor");
    return arquivoFalso();
  });
  vi.spyOn(disco, "gravarNoArquivo").mockImplementation(async () => {
    ordem.push("gravou");
  });
  vi.spyOn(disco, "descartar").mockImplementation(async () => {
    ordem.push("descartou");
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("baixar planilha", () => {
  it("pergunta a pasta antes de ir à rede, e grava em fluxo", async () => {
    const buscar = vi.fn().mockImplementation(async () => {
      ordem.push("rede");
      return resposta(null);
    });
    vi.stubGlobal("fetch", buscar);

    await baixarArquivo(PLANILHA, "consulta_de_entradas.csv");

    // a ordem é o que faz o seletor abrir: depois da rede ele seria recusado
    expect(ordem).toEqual(["seletor", "rede", "gravou"]);
    expect(buscar).toHaveBeenCalledOnce();

    // a URL é a mesma de sempre, mais a chave com que o motor conta o
    // andamento enquanto monta — ela entra como `&` porque já havia `?formato`
    const pedida = buscar.mock.calls[0][0] as string;
    expect(pedida.startsWith(`${PLANILHA}&progresso=`)).toBe(true);
    expect(pedida.length).toBeGreaterThan(`${PLANILHA}&progresso=`.length);
  });

  it("leva o token no cabeçalho, que é o motivo de a aba buscar", async () => {
    localStorage.setItem("cat.token", "jwt-de-teste");
    const buscar = vi.fn().mockResolvedValue(resposta(null));
    vi.stubGlobal("fetch", buscar);

    await baixarArquivo(PLANILHA, "consulta_de_entradas.csv");

    const cabecalhos = buscar.mock.calls[0][1].headers as Headers;
    expect(cabecalhos.get("Authorization")).toBe("Bearer jwt-de-teste");
    localStorage.clear();
  });

  it("recusa do servidor vira erro na tela e não deixa arquivo de 0 byte", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      resposta({ detail: "A apuração das exclusões ainda não terminou." }, 409),
    ));

    await expect(
      baixarArquivo("/api/exclusoes/9/planilhas/pacote", "pacote.zip"),
    ).rejects.toThrow("ainda não terminou");

    expect(ordem).toEqual(["seletor", "descartou"]);
  });

  it("sem espaço em disco, a frase do motor chega inteira à tela", async () => {
    // é o 422 que `exigir_espaco` devolve desde a v0.162.0
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(resposta(
      { detail: "Sem espaço em disco para montar esta planilha: ela precisa de "
                + "cerca de 15,2 GB e restam 0,5 GB em D:." }, 422)));

    await expect(baixarArquivo(PLANILHA, "entradas.xlsx"))
      .rejects.toThrow("Sem espaço em disco");
  });

  it("queda de rede não deixa o arquivo escolhido para trás", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(baixarArquivo(PLANILHA, "entradas.csv"))
      .rejects.toThrow("Não foi possível baixar");

    expect(ordem).toEqual(["seletor", "descartou"]);
  });
});

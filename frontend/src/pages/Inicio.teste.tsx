/**
 * "Novo trabalho" numa tela que já é de um tributo.
 *
 * O modal abria com um seletor de **Tributo** listando os cinco — e marcado em
 * ICMS — numa tela chamada "Trabalhos de PIS/COFINS". Além de perguntar o que a
 * tela já sabia, ele convidava ao erro: a frente vinha "CAT 42" e o trabalho
 * nasceria de ICMS dentro da lista de PIS/COFINS, onde ninguém o encontraria
 * depois.
 *
 * O que estes testes cobram é a **ligação**: que a tela diga ao modal em que
 * tributo ela está, e que o modal pare de perguntar.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Inicio from "./Inicio";

vi.mock("@/services/importacao", async (original) => ({
  ...(await original<typeof import("@/services/importacao")>()),
  listarProjetos: vi.fn(),
  listarEmpresas: vi.fn(),
  criarProjeto: vi.fn(),
}));

vi.mock("@/services/segmentos", async (original) => ({
  ...(await original<typeof import("@/services/segmentos")>()),
  meusSegmentos: vi.fn(),
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ usuario: { id: 1, nome_exibicao: "Victor", papel: "dev" } }),
}));

const importacao = await import("@/services/importacao");
const segmentos = await import("@/services/segmentos");
const listarProjetos = vi.mocked(importacao.listarProjetos);
const listarEmpresas = vi.mocked(importacao.listarEmpresas);
const criarProjeto = vi.mocked(importacao.criarProjeto);
const meusSegmentos = vi.mocked(segmentos.meusSegmentos);

const CATALOGO = [
  {
    chave: "piscofins",
    rotulo: "PIS/COFINS",
    descricao: "",
    modulos: [
      { chave: "piscofins", rotulo: "PIS/COFINS", descricao: "" },
      { chave: "cbs", rotulo: "CBS", descricao: "" },
    ],
  },
  {
    chave: "icms",
    rotulo: "ICMS",
    descricao: "",
    modulos: [{ chave: "icms", rotulo: "ICMS", descricao: "" }],
  },
];

function abrirEm(modulo: string) {
  listarProjetos.mockResolvedValue([] as never);
  listarEmpresas.mockResolvedValue([
    { id: 7, cnpj_raiz: "03083231", cnpj_matriz: null, cnpj_matriz_formatado: null,
      razao_social: "CEMA", uf: "MG", inscricao_estadual: null, pre_cadastro: false, projetos: 0 },
  ] as never);
  meusSegmentos.mockResolvedValue(CATALOGO as never);
  criarProjeto.mockResolvedValue({ id: 99 } as never);

  render(
    <MemoryRouter initialEntries={[`/modulos/${modulo}`]}>
      <Routes>
        <Route path="/modulos/:chave" element={<Inicio />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  criarProjeto.mockClear();
});

describe("numa tela de um tributo só", () => {
  it("o modal não pergunta o tributo: mostra o da tela", async () => {
    abrirEm("piscofins");
    await screen.findByText("Trabalhos de PIS/COFINS");

    fireEvent.click(screen.getByRole("button", { name: /Novo trabalho/ }));

    // o campo existe, com o valor; o que sumiu foi a pergunta
    await screen.findByText("Definido pela tela em que você está.");
    expect(screen.getAllByText("PIS/COFINS").length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("combobox", { name: /ICMS|IRPJ|CBS/ }),
    ).toBeNull();
  });

  it("a frente nasce coerente com o tributo, e não em CAT 42", async () => {
    abrirEm("piscofins");
    await screen.findByText("Trabalhos de PIS/COFINS");

    fireEvent.click(screen.getByRole("button", { name: /Novo trabalho/ }));
    await screen.findByText("Definido pela tela em que você está.");

    expect(screen.getByText("Quebra de SPED")).toBeTruthy();
    expect(screen.queryByText("CAT 42 — ressarcimento de ICMS-ST")).toBeNull();
  });

  it("o trabalho é criado no tributo da tela", async () => {
    abrirEm("piscofins");
    await screen.findByText("Trabalhos de PIS/COFINS");
    fireEvent.click(screen.getByRole("button", { name: /Novo trabalho/ }));
    await screen.findByText("Definido pela tela em que você está.");

    fireEvent.change(screen.getByPlaceholderText("Apuração PIS/COFINS 2025"), {
      target: { value: "Apuração 2025" },
    });
    fireEvent.change(screen.getByPlaceholderText("01/2021"), { target: { value: "01/2021" } });
    fireEvent.change(screen.getByPlaceholderText("12/2025"), { target: { value: "12/2025" } });
    // a empresa é o único combobox que sobrou no formulário
    fireEvent.click(screen.getAllByRole("combobox")[0]);
    fireEvent.click(await screen.findByRole("option", { name: /CEMA/ }));
    fireEvent.click(screen.getByRole("button", { name: "Criar trabalho" }));

    await waitFor(() => expect(criarProjeto).toHaveBeenCalled());
    const pedido = criarProjeto.mock.calls[0][0];
    expect(pedido.modulo).toBe("piscofins");
    expect(pedido.frente).toBe("sped");
  });

  it("no ICMS, a frente nasce CAT 42", async () => {
    abrirEm("icms");
    await screen.findByText("Trabalhos de ICMS");

    fireEvent.click(screen.getByRole("button", { name: /Novo trabalho/ }));
    await screen.findByText("Definido pela tela em que você está.");

    expect(screen.getByText("CAT 42 — ressarcimento de ICMS-ST")).toBeTruthy();
  });
});

/**
 * O seletor do razão: o que a marcação tem de aguentar.
 *
 * Existe por uma pergunta feita em 23/09/2026, na revisão da tela: *"filtrar,
 * marcar, trocar de filtro, marcar outra — a primeira continua marcada?"*. A
 * resposta estava certa no código e **não estava testada**, que é o mesmo que
 * não ter resposta: a próxima mudança no seletor poderia mover o estado da
 * seleção para dentro da lista sem ninguém perceber, e quem só descobre isso
 * é quem perde meia hora de marcação na frente do cliente.
 *
 * O que estes testes cobram: a seleção sobrevive a busca, a recorte, a
 * estabelecimento e a navegar pela árvore; e o que se extrai é exatamente o
 * que está marcado, inclusive o que saiu da tela por causa do filtro.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SeletorDeConta } from "./RazaoContabil";
import type { ContaContabil, PaginaDeContas } from "@/services/apuracaoPisCofins";

vi.mock("@/services/apuracaoPisCofins", async (original) => ({
  ...(await original<typeof import("@/services/apuracaoPisCofins")>()),
  contasDoRazaoContabil: vi.fn(),
  estabelecimentosDoRazaoContabil: vi.fn(),
  baixarPlanilhaDaApuracao: vi.fn(),
}));

const servicos = await import("@/services/apuracaoPisCofins");
const pedirContas = vi.mocked(servicos.contasDoRazaoContabil);
const pedirEstabelecimentos = vi.mocked(servicos.estabelecimentosDoRazaoContabil);
const baixar = vi.mocked(servicos.baixarPlanilhaDaApuracao);

const CNPJ = "44000007002122";

function conta(codigo: string, descricao: string, referencial = "1.01.01.01"): ContaContabil {
  return {
    cnpj: CNPJ,
    conta: codigo,
    descricao,
    conta_referencial: referencial,
    lancamentos: 10,
    debitos: "100.00",
    creditos: "40.00",
    saldo: "60.00",
    de: "2025-01-01",
    ate: "2025-12-31",
    arquivos: 1,
  };
}

function pagina(linhas: ContaContabil[], nos: PaginaDeContas["nos"] = [], pai = ""): PaginaDeContas {
  return { pagina: 1, por_pagina: 100, total: linhas.length, linhas, nos, pai };
}

function galho(codigo: string, contas: number) {
  return { codigo, contas, lancamentos: contas * 10, debitos: "0.00", creditos: "0.00", saldo: "0.00" };
}

/** A conta marcada na tela, do jeito que a pessoa vê: a caixinha ligada. */
const caixaDa = (codigo: string) =>
  screen.getByRole("checkbox", { name: `Marcar a conta ${codigo}` }) as HTMLInputElement;

const marcadas = () => Number(screen.getByTestId("quantas-marcadas").textContent);

beforeEach(() => {
  pedirEstabelecimentos.mockResolvedValue({ linhas: [] });
  baixar.mockResolvedValue(undefined);
});

describe("a marcação atravessa os filtros", () => {
  it("trocar a busca não desmarca o que já foi marcado", async () => {
    // primeira busca traz o CAIXA; a segunda, os FORNECEDORES
    pedirContas.mockImplementation(async (_execucao, filtro) =>
      filtro.busca.includes("FORNEC")
        ? pagina([conta("21010500001", "Fornecedores", "2.01.01.03.01")])
        : pagina([conta("11010100001", "Caixa")]),
    );

    render(<SeletorDeConta execucaoId={115} />);

    const busca = screen.getByLabelText("Conta, nome ou conta referencial");
    fireEvent.change(busca, { target: { value: "CAIXA" } });
    await screen.findByText("Caixa");

    fireEvent.click(caixaDa("11010100001"));
    expect(marcadas()).toBe(1);

    // troca o filtro: a primeira conta sai da tela
    fireEvent.change(busca, { target: { value: "FORNEC" } });
    await screen.findByText("Fornecedores");
    expect(screen.queryByText("Caixa")).toBeNull();

    // a segunda marcação não pode apagar a primeira
    fireEvent.click(caixaDa("21010500001"));
    expect(marcadas()).toBe(2);

    // e voltar à primeira busca mostra a caixinha ainda ligada
    fireEvent.change(busca, { target: { value: "CAIXA" } });
    await screen.findByText("Caixa");
    expect(caixaDa("11010100001").checked).toBe(true);
  });

  it("extrai as duas, inclusive a que o filtro tirou da tela", async () => {
    pedirContas.mockImplementation(async (_execucao, filtro) =>
      filtro.busca.includes("FORNEC")
        ? pagina([conta("21010500001", "Fornecedores", "2.01.01.03.01")])
        : pagina([conta("11010100001", "Caixa")]),
    );

    render(<SeletorDeConta execucaoId={115} />);
    const busca = screen.getByLabelText("Conta, nome ou conta referencial");

    fireEvent.change(busca, { target: { value: "CAIXA" } });
    await screen.findByText("Caixa");
    fireEvent.click(caixaDa("11010100001"));

    fireEvent.change(busca, { target: { value: "FORNEC" } });
    await screen.findByText("Fornecedores");
    fireEvent.click(caixaDa("21010500001"));

    fireEvent.click(screen.getByRole("button", { name: /Extrair as contas marcadas/ }));

    await waitFor(() => expect(baixar).toHaveBeenCalled());
    const [, qual, formato, contas] = baixar.mock.calls[0];
    expect(qual).toBe("razao-contabil");
    expect(formato).toBe("xlsx");
    expect([...(contas ?? [])].sort()).toEqual(["11010100001", "21010500001"]);
  });

  it("trocar o recorte pelo saldo não desmarca", async () => {
    pedirContas.mockImplementation(async (_execucao, filtro) =>
      filtro.recorte === "credoras"
        ? pagina([conta("21010500001", "Fornecedores", "2.01.01.03.01")])
        : pagina([conta("11010100001", "Caixa")]),
    );

    render(<SeletorDeConta execucaoId={115} />);
    await screen.findByText("Caixa");
    fireEvent.click(caixaDa("11010100001"));

    fireEvent.click(screen.getByRole("radio", { name: "Credoras" }));
    await screen.findByText("Fornecedores");
    fireEvent.click(caixaDa("21010500001"));

    expect(marcadas()).toBe(2);
  });

  it("trocar de estabelecimento não desmarca", async () => {
    pedirEstabelecimentos.mockResolvedValue({
      linhas: [
        { cnpj: CNPJ, contas: 2, lancamentos: 20, de: "2025-01-01", ate: "2025-12-31" },
        { cnpj: "44000007000189", contas: 1, lancamentos: 10, de: "2025-01-01", ate: "2025-12-31" },
      ],
    });
    pedirContas.mockImplementation(async (_execucao, filtro) =>
      filtro.cnpj === "44000007000189"
        ? pagina([conta("21010500001", "Fornecedores", "2.01.01.03.01")])
        : pagina([conta("11010100001", "Caixa")]),
    );

    render(<SeletorDeConta execucaoId={115} />);
    await screen.findByText("Caixa");
    fireEvent.click(caixaDa("11010100001"));

    fireEvent.change(await screen.findByLabelText("Estabelecimento"), {
      target: { value: "44000007000189" },
    });
    await screen.findByText("Fornecedores");
    fireEvent.click(caixaDa("21010500001"));

    expect(marcadas()).toBe(2);
  });
});

describe("a marcação atravessa a árvore", () => {
  it("marcar num galho, fechar, marcar noutro: as duas ficam", async () => {
    pedirContas.mockImplementation(async (_execucao, filtro) => {
      if (filtro.busca.trim()) return pagina([]);
      if (filtro.pai === "1.01.01.01") return pagina([conta("11010100001", "Caixa")]);
      if (filtro.pai === "2.01.01.03.01")
        return pagina([conta("21010500001", "Fornecedores", "2.01.01.03.01")]);
      if (filtro.pai === "1") return pagina([], [galho("1.01.01.01", 1)], "1");
      if (filtro.pai === "2") return pagina([], [galho("2.01.01.03.01", 1)], "2");
      return pagina([], [galho("1", 1), galho("2", 1)]);
    });

    render(<SeletorDeConta execucaoId={115} />);

    // desce pelo Ativo até a conta e marca
    fireEvent.click(await screen.findByRole("button", { name: "Conta referencial 1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Conta referencial 1.01.01.01" }));
    await screen.findByText("Caixa");
    fireEvent.click(caixaDa("11010100001"));
    expect(marcadas()).toBe(1);

    // fecha o galho inteiro — a conta some da tela
    fireEvent.click(screen.getByRole("button", { name: "Conta referencial 1" }));
    expect(screen.queryByText("Caixa")).toBeNull();

    // desce pelo Passivo e marca a segunda
    fireEvent.click(await screen.findByRole("button", { name: "Conta referencial 2" }));
    fireEvent.click(await screen.findByRole("button", { name: "Conta referencial 2.01.01.03.01" }));
    await screen.findByText("Fornecedores");
    fireEvent.click(caixaDa("21010500001"));

    expect(marcadas()).toBe(2);

    // e reabrir o primeiro galho mostra a caixinha ainda ligada
    fireEvent.click(screen.getByRole("button", { name: "Conta referencial 1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Conta referencial 1.01.01.01" }));
    await waitFor(() => expect(caixaDa("11010100001").checked).toBe(true));
  });

  it("Limpar desmarca tudo, e só quando se pede", async () => {
    pedirContas.mockResolvedValue(pagina([conta("11010100001", "Caixa")]));

    render(<SeletorDeConta execucaoId={115} />);
    fireEvent.change(screen.getByLabelText("Conta, nome ou conta referencial"), {
      target: { value: "CAIXA" },
    });
    await screen.findByText("Caixa");
    fireEvent.click(caixaDa("11010100001"));
    expect(marcadas()).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: "Limpar" }));
    expect(marcadas()).toBe(0);
    expect(caixaDa("11010100001").checked).toBe(false);
  });

  it("sem nada marcado, não há o que extrair", async () => {
    pedirContas.mockResolvedValue(pagina([conta("11010100001", "Caixa")]));

    render(<SeletorDeConta execucaoId={115} />);
    const botao = screen.getByRole("button", {
      name: /Extrair as contas marcadas/,
    }) as HTMLButtonElement;

    expect(botao.disabled).toBe(true);
    fireEvent.click(botao);
    expect(baixar).not.toHaveBeenCalled();
  });
});

describe("a mesma conta em dois estabelecimentos", () => {
  it("marca nos dois, porque é a mesma conta do plano", async () => {
    const naFilial = { ...conta("11010100001", "Caixa"), cnpj: "44000007000189" };
    pedirContas.mockResolvedValue(pagina([conta("11010100001", "Caixa"), naFilial]));

    render(<SeletorDeConta execucaoId={115} />);
    await waitFor(() => expect(screen.getAllByText("Caixa")).toHaveLength(2));

    const caixinhas = screen.getAllByRole("checkbox", {
      name: "Marcar a conta 11010100001",
    }) as HTMLInputElement[];
    fireEvent.click(caixinhas[0]);

    // uma marcação só: o que se extrai é o código da conta, e ele é um só
    expect(marcadas()).toBe(1);
    expect(caixinhas.every((c) => c.checked)).toBe(true);
  });
});

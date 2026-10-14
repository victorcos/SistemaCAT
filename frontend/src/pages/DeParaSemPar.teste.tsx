/**
 * A seção "Códigos sem par": quantos são, e como alcançar os que não cabem.
 *
 * A tabela corta em `POR_PAGINA` linhas. Numa base real da empresa JK são
 * **1.591 códigos sem par para 200 linhas** — 1.391 ficavam inalcançáveis, sem
 * busca que chegasse neles e sem nada na tela dizendo que havia mais.
 *
 * O número importa tanto quanto a busca: código sem par é ficha que vai ficar
 * negativa e sair do total. Quem não sabe que são 1.591 acha que resolveu o
 * problema depois de olhar 200.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DePara from "./DePara";
import type { DeParaDoTrabalho } from "@/services/depara";

vi.mock("@/services/depara", async (original) => ({
  ...(await original<typeof import("@/services/depara")>()),
  deparaDoTrabalho: vi.fn(),
  decidirDePara: vi.fn(),
}));

vi.mock("@/hooks/useAuth", () => ({ useAuth: () => ({ podeEscrever: true }) }));

const servico = await import("@/services/depara");
const pedir = vi.mocked(servico.deparaDoTrabalho);

function semPar(quantos: number) {
  return Array.from({ length: quantos }, (_, i) => ({
    cnpj: "65100026000157",
    codigo: `${1000 + i}`,
    descricao: i === 0 ? "PREGO COM CABECA 17X21 01KG GERDAU" : `ITEM GENERICO ${i}`,
    ncm: i === 0 ? "73170090" : "39174090",
    saidas: "3",
  }));
}

function resposta(quantos: number): DeParaDoTrabalho {
  return {
    movimentos_execucao_id: 195,
    resumo: { pares: 0, pendentes: 0, aprovados: 0, automaticos: 0, recusados: 0,
              sem_par: quantos, precisavam_de_par: quantos, resolvidos: 0,
              estabelecimentos: 1 },
    pares: [],
    sem_par: semPar(quantos),
  } as DeParaDoTrabalho;
}

function montar() {
  render(
    <MemoryRouter initialEntries={["/projetos/26/depara"]}>
      <Routes>
        <Route path="/projetos/:id/depara" element={<DePara />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  pedir.mockReset();
});

describe("quantos são", () => {
  it("diz o total ao lado do título", async () => {
    pedir.mockResolvedValue(resposta(1591));
    montar();

    const titulo = await screen.findByRole("heading", { name: /Códigos sem par/ }, { timeout: 4000 });
    expect(titulo.textContent).toMatch(/1\.591/);
  });

  it("avisa que a tabela está cortada", async () => {
    // 1.591 para 200 linhas: sem isto, 1.391 somem sem que ninguém perceba
    pedir.mockResolvedValue(resposta(1591));
    montar();

    expect(await screen.findByText(/mostrando 200 de 1\.591/, undefined, { timeout: 4000 })).toBeTruthy();
  });

  it("quando tudo cabe, o aviso não assusta", async () => {
    pedir.mockResolvedValue(resposta(12));
    montar();

    expect(await screen.findByText(/mostrando 12 de 12/, undefined, { timeout: 4000 })).toBeTruthy();
  });
});

describe("a busca alcança o que a página corta", () => {
  it("acha pela descrição um código que está fora das 200 primeiras", async () => {
    pedir.mockResolvedValue(resposta(1591));
    montar();
    await screen.findByText(/mostrando 200 de 1\.591/, undefined, { timeout: 4000 });

    const campo = screen.getByPlaceholderText(/Buscar por código, descrição ou NCM/i);
    fireEvent.change(campo, { target: { value: "ITEM GENERICO 900" } });

    await waitFor(() => expect(screen.getByText("ITEM GENERICO 900")).toBeTruthy());
  });

  it("acha por pedaço do código", async () => {
    pedir.mockResolvedValue(resposta(1591));
    montar();
    await screen.findByText(/mostrando 200 de 1\.591/, undefined, { timeout: 4000 });

    fireEvent.change(screen.getByPlaceholderText(/Buscar por código/i), {
      target: { value: "2500" },
    });

    await waitFor(() => expect(screen.getByText("2500")).toBeTruthy());
  });

  it("diz quantos casaram com o filtro, contra o total", async () => {
    pedir.mockResolvedValue(resposta(1591));
    montar();
    await screen.findByText(/mostrando 200 de 1\.591/, undefined, { timeout: 4000 });

    fireEvent.change(screen.getByPlaceholderText(/Buscar por código/i), {
      target: { value: "PREGO" },
    });

    expect(await screen.findByText(/1 de 1\.591 com o filtro/, undefined, { timeout: 4000 })).toBeTruthy();
  });

  it("acha pelo NCM, que é como se procura família de produto", async () => {
    pedir.mockResolvedValue(resposta(30));
    montar();
    await screen.findByText(/mostrando 30 de 30/, undefined, { timeout: 4000 });

    fireEvent.change(screen.getByPlaceholderText(/Buscar por código/i), {
      target: { value: "73170090" },
    });

    expect(await screen.findByText(/1 de 30 com o filtro/, undefined, { timeout: 4000 })).toBeTruthy();
  });
});

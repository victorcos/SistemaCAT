/**
 * O seletor de colunas da quebra de XML segue o tributo do trabalho.
 *
 * Existe por um erro que passou na primeira versão: numa tela de PIS/COFINS, o
 * seletor abria marcado no atalho de **ICMS** e mostrava ICMS-ST, IPI e ISSQN
 * com o mesmo peso dos blocos que interessam. Quem foi baixar a planilha teria
 * levado as colunas erradas sem perceber — o download não avisa.
 *
 * O que estes testes cobram: o padrão é o do módulo; o que é do outro tributo
 * fica guardado, mas **não some** (cruzar com o ICMS destacado é trabalho
 * legítimo); e o atalho do outro tributo sai da barra, onde convidava ao clique
 * errado.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import QuebraXml from "./QuebraXml";

vi.mock("@/services/quebraXml", async (original) => ({
  ...(await original<typeof import("@/services/quebraXml")>()),
  camposDoXml: vi.fn(),
  listarQuebrasDeXml: vi.fn(),
  detalharQuebraDeXml: vi.fn(),
  iniciarQuebraDeXml: vi.fn(),
  baixarItensDoXml: vi.fn(),
}));

vi.mock("@/services/importacao", async (original) => ({
  ...(await original<typeof import("@/services/importacao")>()),
  detalharProjeto: vi.fn(),
}));

const xml = await import("@/services/quebraXml");
const importacao = await import("@/services/importacao");
const pedirCampos = vi.mocked(xml.camposDoXml);
const listar = vi.mocked(xml.listarQuebrasDeXml);
const baixar = vi.mocked(xml.baixarItensDoXml);
const detalhar = vi.mocked(importacao.detalharProjeto);

const CATALOGO = {
  blocos: ["Identificação", "Produto", "ICMS", "ICMS-ST e efetivo", "PIS e COFINS", "IPI e ISSQN"],
  campos: [
    { campo: "chave", titulo: "Chave de Acesso", bloco: "Identificação" },
    { campo: "descricao", titulo: "Descrição", bloco: "Produto" },
    { campo: "valor_icms", titulo: "Valor", bloco: "ICMS" },
    { campo: "valor_st", titulo: "Valor da ST", bloco: "ICMS-ST e efetivo" },
    { campo: "valor_pis", titulo: "Valor do PIS", bloco: "PIS e COFINS" },
    { campo: "valor_ipi", titulo: "Valor do IPI", bloco: "IPI e ISSQN" },
  ],
  atalhos: {
    icms: ["chave", "descricao", "valor_icms", "valor_st"],
    piscofins: ["chave", "descricao", "valor_pis"],
    descontos: ["chave", "descricao"],
    tudo: ["chave", "descricao", "valor_icms", "valor_st", "valor_pis", "valor_ipi"],
  },
};

const CONCLUIDA = {
  id: 9,
  projeto_id: 6,
  etapa: "quebra_xml",
  situacao: "concluida",
  passo: "Concluída",
  fracao: 1,
  arquivos_totais: 3,
  arquivos_lidos: 3,
  bytes_lidos: 10,
  documentos: 2,
  erro: null,
  iniciada_em: "2026-09-24T10:00:00-03:00",
  terminada_em: "2026-09-24T10:01:00-03:00",
  resumo: { versao: 1, arquivos: 3, notas: 2, itens: 7 },
};

function montar(modulo: string, resumo: object = CONCLUIDA.resumo) {
  detalhar.mockResolvedValue({
    projeto: { id: 6, modulo, modulo_rotulo: modulo, empresa: "CEMA", status: "em_andamento" },
    etapas: [],
  } as never);
  listar.mockResolvedValue([{ ...CONCLUIDA, resumo }] as never);
  pedirCampos.mockResolvedValue(CATALOGO as never);

  return render(
    <MemoryRouter initialEntries={["/projetos/6/quebra-xml"]}>
      <Routes>
        <Route path="/projetos/:id/quebra-xml" element={<QuebraXml />} />
      </Routes>
    </MemoryRouter>,
  );
}

const marcados = () => screen.getByText(/de 6 campos/).textContent ?? "";

beforeEach(() => {
  baixar.mockResolvedValue(undefined);
});

describe("o que ficou de fora", () => {
  /**
   * O zip do portal entra fechado na importação: é a quebra que abre a nota e
   * vê de quem ela é. Descarte sem nome de CNPJ na tela é descarte que ninguém
   * confere — e aqui o que sai é dado de outro cliente.
   */
  it("mostra as notas de outra empresa e de quem são", async () => {
    montar("piscofins", {
      versao: 1, arquivos: 3, notas: 2, itens: 7,
      de_outra_empresa: 1243, cnpjs_de_fora: { "22333444": 1200, "77666555": 43 },
    });

    expect(await screen.findByText("notas de outra empresa")).toBeTruthy();
    expect(screen.getByText("1.243")).toBeTruthy();
    expect(screen.getByText("22333444")).toBeTruthy();
    expect(screen.getByText("77666555")).toBeTruthy();
  });

  it("sem nota de fora, o assunto não aparece", async () => {
    montar("piscofins");
    await screen.findByText("PIS e COFINS");
    expect(screen.queryByText("notas de outra empresa")).toBeNull();
  });
});

describe("num trabalho de PIS/COFINS", () => {
  it("abre marcado no atalho do próprio tributo, e não no do ICMS", async () => {
    montar("piscofins");

    // o atalho de PIS/COFINS tem 3 campos; o de ICMS teria 4
    await waitFor(() => expect(marcados()).toContain("3"));
    expect(
      (screen.getByRole("checkbox", { name: "Marcar Valor do PIS" }) as HTMLInputElement).checked,
    ).toBe(true);
  });

  it("não mostra ICMS, ST e IPI até pedirem", async () => {
    montar("piscofins");
    await screen.findByText("PIS e COFINS");

    expect(screen.queryByRole("checkbox", { name: "Marcar o bloco ICMS" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Mostrar os outros tributos/ }));

    expect(screen.getByRole("checkbox", { name: "Marcar o bloco ICMS" })).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: "Marcar o bloco IPI e ISSQN" })).toBeTruthy();
  });

  it("o atalho do outro tributo sai da barra", async () => {
    montar("piscofins");
    await screen.findByText("PIS e COFINS");

    expect(screen.getByRole("button", { name: "PIS/COFINS" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "ICMS" })).toBeNull();
  });

  it("marcar uma coluna do outro tributo continua possível, e vai no download", async () => {
    montar("piscofins");
    await screen.findByText("PIS e COFINS");

    fireEvent.click(screen.getByRole("button", { name: /Mostrar os outros tributos/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Marcar Valor" }));
    fireEvent.click(screen.getByRole("button", { name: /Baixar a planilha/ }));

    await waitFor(() => expect(baixar).toHaveBeenCalled());
    const [, , campos] = baixar.mock.calls[0];
    expect(campos).toContain("valor_icms");
    expect(campos).toContain("valor_pis");
  });
});

describe("num trabalho de ICMS", () => {
  it("abre no atalho de ICMS e guarda PIS/COFINS", async () => {
    montar("icms");

    await waitFor(() => expect(marcados()).toContain("4"));
    expect(screen.queryByRole("checkbox", { name: "Marcar o bloco PIS e COFINS" })).toBeNull();
    expect(screen.getByRole("button", { name: "ICMS" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "PIS/COFINS" })).toBeNull();
  });
});

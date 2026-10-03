/**
 * O descarte por empresa, na tela da importação.
 *
 * O sistema não pergunta se pode deixar de fora o arquivo de outra empresa —
 * misturar cliente contamina a apuração dos dois, e essa é a regra dura do
 * lote. Mas descarte que ninguém vê é boato: a pasta de rede guarda o grupo
 * inteiro, e quem importa precisa conferir, antes de gravar, que o que saiu
 * não era seu.
 *
 * O que estes testes cobram: o painel aparece com a conta, abre com o CNPJ e o
 * nome dos arquivos, e some quando não houve descarte nenhum.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ConfirmProvider } from "@/providers/ConfirmProvider";
import Lote from "./Lote";

vi.mock("@/services/lote", async (original) => ({
  ...(await original<typeof import("@/services/lote")>()),
  inspecionarPasta: vi.fn(),
  listarLotes: vi.fn(),
  registrarLote: vi.fn(),
  removerLote: vi.fn(),
}));

vi.mock("@/services/importacao", async (original) => ({
  ...(await original<typeof import("@/services/importacao")>()),
  detalharProjeto: vi.fn(),
}));

const lote = await import("@/services/lote");
const importacao = await import("@/services/importacao");
const inspecionar = vi.mocked(lote.inspecionarPasta);
const listar = vi.mocked(lote.listarLotes);
const detalhar = vi.mocked(importacao.detalharProjeto);

const ARQUIVO = {
  nome: "efd_2025_01.txt", caminho: "Z:/base/efd_2025_01.txt", tamanho: 100,
  tipo: "sped_contribuicoes", tipo_rotulo: "EFD-Contribuições", grupo: "sped",
  alimenta: true, cnpj: "77665544000105", competencia: "2025-01-01", uf: "MG",
  detalhe: "", motivo: "",
};

const INTRUSO = {
  ...ARQUIVO, nome: "intruso.txt", caminho: "Z:/base/intruso.txt",
  alimenta: false, cnpj: "11222333000181", motivo: "de outra empresa",
};

const RESUMO = {
  pasta: "Z:/base", total_arquivos: 1, arquivos_uteis: 1, bytes_totais: 100,
  de_outra_empresa: 0, serve: true, competencia_ini: "2025-01-01",
  competencia_fim: "2025-01-01", cnpjs: ["77665544000105"], contagens: [],
  avisos: [], amostra: [ARQUIVO], ja_no_trabalho: 0, reclassificados: 0,
  empresas_de_fora: [], fora_por_empresa: [],
};

async function conferir(resumo: object) {
  detalhar.mockResolvedValue({
    projeto: { id: 6, modulo: "piscofins", modulo_rotulo: "PIS/COFINS", empresa: "empresa S",
               status: "em_andamento" },
    etapas: [],
  } as never);
  listar.mockResolvedValue([] as never);
  inspecionar.mockResolvedValue(resumo as never);

  render(
    <ConfirmProvider>
      <MemoryRouter initialEntries={["/projetos/6/lote"]}>
        <Routes>
          <Route path="/projetos/:id/lote" element={<Lote />} />
        </Routes>
      </MemoryRouter>
    </ConfirmProvider>,
  );

  fireEvent.change(await screen.findByLabelText(/Pasta/), { target: { value: "Z:/base" } });
  fireEvent.click(screen.getByRole("button", { name: /Conferir/ }));
  await waitFor(() => expect(inspecionar).toHaveBeenCalled());
}

describe("arquivos de outra empresa", () => {
  it("diz quantos saíram e abre com o CNPJ e o nome de cada um", async () => {
    await conferir({
      ...RESUMO,
      de_outra_empresa: 39,
      empresas_de_fora: [{ cnpj: "11222333000181", arquivos: 39, bytes_totais: 4096 }],
      fora_por_empresa: [INTRUSO],
    });

    expect(await screen.findByText(/39 arquivo\(s\) de outra empresa/)).toBeTruthy();
    // fechado, o nome do arquivo não ocupa a tela
    expect(screen.queryByText("intruso.txt")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Ver o que saiu" }));

    // o CNPJ aparece na conta por empresa e na linha do arquivo
    expect(screen.getAllByText("11222333000181")).toHaveLength(2);
    expect(screen.getByText("intruso.txt")).toBeTruthy();
    // a amostra tem 1 de 39: a tela diz isso em vez de fingir a lista inteira
    expect(screen.getByText(/Mostrando 1 de 39/)).toBeTruthy();
  });

  it("sem nada de outra empresa, o painel não aparece", async () => {
    await conferir(RESUMO);
    expect(await screen.findByText(/O que há nesta pasta/)).toBeTruthy();
    expect(screen.queryByText(/de outra empresa/)).toBeNull();
  });
});

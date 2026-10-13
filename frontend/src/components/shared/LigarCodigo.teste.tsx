/**
 * Ligar um código a outro: o que a tela precisa mostrar antes de alguém decidir.
 *
 * Isto substitui um campo de texto onde se digitava o código de destino **de
 * cabeça** — sem busca, sem a descrição do outro lado, e sem alcançar o código
 * que só tem entrada, que é justamente o par que falta.
 *
 * O que estes testes cobram é o que separa um seletor de um palpite:
 *
 * * **o porquê aparece em cada candidato.** Lista ordenada sem explicação é a
 *   pessoa confiando no palpite da máquina, e esta casa não faz isso;
 * * **a descrição dos dois lados fica visível** — ligar por código é o erro que
 *   a tela antiga convidava a cometer;
 * * **nada é gravado sem escolha explícita.** O primeiro da lista é o mais
 *   provável, não o escolhido;
 * * **o fator sobrevive à escolha**, porque kit de 3 ligado com fator 1 tria
 *   a quantidade por três e ninguém vê.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LigarCodigo } from "./LigarCodigo";
import type { ParaLigar } from "@/services/depara";

vi.mock("@/services/depara", async (original) => ({
  ...(await original<typeof import("@/services/depara")>()),
  candidatosParaLigar: vi.fn(),
}));

const servico = await import("@/services/depara");
const pedir = vi.mocked(servico.candidatosParaLigar);

function resposta(parcial: Partial<ParaLigar> = {}): ParaLigar {
  return {
    origem: {
      codigo: "X00450IETL", descricao: "CASTANHA ESCURA 500G",
      ncm: "08013200", entradas: "0", saidas: "120",
    },
    candidatos: [
      {
        codigo: "X00450IETL  08", descricao: "CASTANHA ESCURA 500G", ncm: "08013200",
        entradas: "20", saidas: "0", pontos: 155,
        porques: ["mesmo NCM", "descrição 100% parecida", "tem entrada e não tem saída"],
      },
      {
        codigo: "4450", descricao: "CAST. ESCURO 500G", ncm: "08013200",
        entradas: "300", saidas: "0", pontos: 82,
        porques: ["mesmo NCM", "descrição 20% parecida"],
      },
    ],
    no_estabelecimento: 87,
    ...parcial,
  };
}

function montar(sobre: Partial<Parameters<typeof LigarCodigo>[0]> = {}) {
  const aoLigar = vi.fn();
  render(
    <LigarCodigo
      projetoId={5}
      cnpj="43112531000421"
      origem="X00450IETL"
      descricao="CASTANHA ESCURA 500G"
      fator="1"
      aoMudarFator={vi.fn()}
      aoLigar={aoLigar}
      gravando={false}
      aoFechar={vi.fn()}
      {...sobre}
    />,
  );
  return { aoLigar };
}

beforeEach(() => {
  pedir.mockReset();
  pedir.mockResolvedValue(resposta());
});

describe("o que a tela mostra antes da decisão", () => {
  it("mostra a descrição do código que está sendo ligado", async () => {
    montar();

    expect(await screen.findAllByText("CASTANHA ESCURA 500G")).not.toHaveLength(0);
  });

  it("mostra o porquê de cada candidato ter subido", async () => {
    // sem isto, a ordem é um palpite que ninguém pode conferir
    montar();

    expect(
      await screen.findByText(/mesmo NCM; descrição 100% parecida; tem entrada e não tem saída/),
    ).toBeTruthy();
  });

  it("mostra entradas e saídas de cada candidato", async () => {
    // é o que distingue o par que conserta a ficha do que só se parece
    montar();

    expect(await screen.findByText(/20 entradas · 0 saídas/)).toBeTruthy();
    expect(screen.getByText(/300 entradas · 0 saídas/)).toBeTruthy();
  });

  it("diz quantos códigos o estabelecimento tem quando a busca não acha nada", async () => {
    pedir.mockResolvedValue(resposta({ candidatos: [] }));
    montar();

    fireEvent.change(await screen.findByRole("searchbox"), { target: { value: "parafuso" } });

    expect(await screen.findByText(/nos 87 do estabelecimento/i)).toBeTruthy();
  });
});

describe("nada é gravado sem escolha", () => {
  it("não oferece o botão de ligar antes de escolher um candidato", async () => {
    montar();
    await screen.findByText(/X00450IETL\s+08/);

    expect(screen.queryByRole("button", { name: "Ligar" })).toBeNull();
  });

  it("liga com o código escolhido, e não com o primeiro da lista", async () => {
    const { aoLigar } = montar();

    fireEvent.click(await screen.findByText("CAST. ESCURO 500G"));
    fireEvent.click(screen.getByRole("button", { name: "Ligar" }));

    expect(aoLigar).toHaveBeenCalledWith("4450", "1");
  });

  it("leva o fator informado, e não um 1 fixo", async () => {
    // kit de 3 ligado com fator 1 divide a quantidade por três sem ninguém ver
    const { aoLigar } = montar({ fator: "3" });

    fireEvent.click(await screen.findByText("CAST. ESCURO 500G"));
    fireEvent.click(screen.getByRole("button", { name: "Ligar" }));

    expect(aoLigar).toHaveBeenCalledWith("4450", "3");
  });
});

describe("a busca", () => {
  it("vai ao servidor com o termo digitado", async () => {
    montar();
    await screen.findByText(/X00450IETL\s+08/);

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "cast esc" } });

    await waitFor(() =>
      expect(pedir).toHaveBeenCalledWith(5, "43112531000421", "X00450IETL", "cast esc", expect.anything()),
    );
  });

  it("não dispara uma busca por tecla", async () => {
    montar();
    await screen.findByText(/X00450IETL\s+08/);
    const antes = pedir.mock.calls.length;

    const campo = screen.getByRole("searchbox");
    fireEvent.change(campo, { target: { value: "c" } });
    fireEvent.change(campo, { target: { value: "ca" } });
    fireEvent.change(campo, { target: { value: "cas" } });

    await waitFor(() => expect(pedir.mock.calls.length).toBeGreaterThan(antes));
    expect(pedir.mock.calls.length - antes).toBeLessThan(3);
  });
});

/**
 * O que a tela diz sobre o registro que ela **não** oferece.
 *
 * Um registro pode ficar de fora da lista de extração por dois motivos
 * diferentes, e eles pedem respostas opostas:
 *
 * * a quebra é anterior à entrada dele no índice — **rodar a quebra de novo
 *   resolve**;
 * * o sistema não tem leiaute para ele — rodar de novo **não** resolve, é
 *   código a escrever.
 *
 * O caso que estes testes guardam é o segundo, porque ele era invisível. Em
 * 11/10/2026 alguém notou a olho que faltava o M205: ele existia nos arquivos,
 * estava contado no índice, e não aparecia em lista nenhuma. Quem confere lê
 * ausência como "não existe no SPED" — e nesse dia eram dez registros do
 * bloco M escondidos, um deles com 64.183 linhas.
 *
 * Dar o mesmo aviso aos dois seria pior que não avisar: mandaria rodar a
 * quebra de novo, meia hora de leitura, para o registro continuar faltando.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExtrairDoSped } from "./ExtrairDoSped";
import type { AlvosDaQuebra } from "@/services/quebraDeSped";

vi.mock("@/services/quebraDeSped", async (original) => ({
  ...(await original<typeof import("@/services/quebraDeSped")>()),
  alvosDaQuebra: vi.fn(),
}));

const servico = await import("@/services/quebraDeSped");
const pedirAlvos = vi.mocked(servico.alvosDaQuebra);

function alvos(parcial: Partial<AlvosDaQuebra> = {}): AlvosDaQuebra {
  return {
    linhas: [
      { alvo: "M200", rotulo: "M200", bloco: "M", quantidade: 46, colunas: 13, hierarquia: false },
    ],
    blocos: ["M"],
    rotulos_dos_blocos: { M: "Apuração" },
    estabelecimentos: [],
    sem_indice: 0,
    nao_extraiveis: [],
    ...parcial,
  } as AlvosDaQuebra;
}

beforeEach(() => {
  pedirAlvos.mockReset();
});

describe("o registro que o sistema não sabe ler", () => {
  it("aparece com a contagem, em vez de sumir da tela", async () => {
    pedirAlvos.mockResolvedValue(
      alvos({ sem_leiaute: [{ alvo: "M115", quantidade: 64183, bloco: "M" }] }),
    );

    render(<ExtrairDoSped execucaoId={181} />);

    expect(await screen.findByText(/M115 \(64\.183\)/)).toBeTruthy();
  });

  it("diz que rodar a quebra de novo NÃO resolve", async () => {
    // o aviso dos não indexados manda rodar de novo; aqui isso custaria meia
    // hora de leitura para o registro continuar faltando
    pedirAlvos.mockResolvedValue(
      alvos({ sem_leiaute: [{ alvo: "M115", quantidade: 2, bloco: "M" }] }),
    );

    render(<ExtrairDoSped execucaoId={181} />);

    const faixa = await screen.findByText(/não há leiaute para eles aqui/i);
    expect(faixa.textContent).toMatch(/não.{0,10}resolve/i);
  });

  it("não inventa a faixa quando todos os registros têm leiaute", async () => {
    pedirAlvos.mockResolvedValue(alvos({ sem_leiaute: [] }));

    render(<ExtrairDoSped execucaoId={181} />);

    await waitFor(() => expect(screen.getByText("M200")).toBeTruthy());
    expect(screen.queryByText(/ainda não sabe ler/i)).toBeNull();
  });

  it("aguenta a resposta antiga, sem o campo", async () => {
    // a API pode estar numa versão anterior enquanto o front já subiu
    pedirAlvos.mockResolvedValue(alvos());

    render(<ExtrairDoSped execucaoId={181} />);

    await waitFor(() => expect(screen.getByText("M200")).toBeTruthy());
    expect(screen.queryByText(/ainda não sabe ler/i)).toBeNull();
  });
});

describe("os dois avisos não se confundem", () => {
  it("cada um sai com a sua saída", async () => {
    pedirAlvos.mockResolvedValue(
      alvos({
        nao_extraiveis: [{ alvo: "C870", quantidade: 10, bloco: "C" }],
        sem_leiaute: [{ alvo: "M115", quantidade: 20, bloco: "M" }],
      }),
    );

    render(<ExtrairDoSped execucaoId={181} />);

    expect(await screen.findByText(/esta quebra não indexou/i)).toBeTruthy();
    expect(screen.getByText(/ainda não sabe ler/i)).toBeTruthy();
  });
});

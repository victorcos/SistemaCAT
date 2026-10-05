/**
 * O resultado do crédito de combustível: o que a tela não pode deixar de dizer.
 *
 * Esta etapa **audita** além de apurar, e por isso o número grande sozinho é
 * uma resposta incompleta. Três coisas acompanham o total porque sem elas
 * alguém soma errado — e nenhuma delas se defende sozinha no código:
 *
 * * **quanto do total é estimativa**, porque na era da substituição tributária
 *   a base vem do valor do item (o arquivo do destinatário não traz a do ST);
 * * **o que ficou de fora, e por quê**, com o motivo visível — competência sem
 *   ad rem conferida não vira zero, vira linha com explicação;
 * * **o intervalo de emissão**, que é o que diz se prescrição é assunto, no dia
 *   em que estiver escrito **igual ao arquivo**, sem fuso pelo meio.
 *
 * O caso que estes testes guardam de verdade é o do **motivo desconhecido**. O
 * motor inventa código novo de recusa quando uma tabela nova entra, e a
 * tradução dele mora no front. Um `?? ""` descuidado na tradução faria a linha
 * desaparecer: o total não fecharia, e ninguém saberia por quê.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Concluida } from "./Combustivel";
import { dia } from "@/lib/format";
import { rotuloDoMotivo, type ResumoDoCombustivel } from "@/services/combustivel";

function resumo(parcial: Partial<ResumoDoCombustivel> = {}): ResumoDoCombustivel {
  return {
    arquivos_no_lote: 198,
    arquivos_lidos: 150,
    ignorados_por_duplicidade: 48,
    linhas: 14_654,
    linhas_de_monofasico: 4_233,
    estabelecimentos: 3,
    competencias: 25,
    credito: "1566349.35",
    credito_estimado: "0",
    linhas_recusadas: 0,
    a_revisar: 0,
    recusas_com_exemplo: {},
    ...parcial,
  };
}

describe("o que ficou fora do total", () => {
  it("mostra o motivo que o front sabe traduzir, em português", () => {
    render(
      <Concluida
        resumo={resumo({
          linhas_recusadas: 9,
          recusas_com_exemplo: {
            ad_rem_nao_conferida: { linhas: 9, exemplo: "2023-07: a ad rem do mês não está conferida." },
          },
        })}
      />,
    );

    expect(screen.getByText(/ad rem daquele mês não está conferida/i)).toBeTruthy();
    expect(screen.getByText(/a ad rem do mês não está conferida\./)).toBeTruthy();
  });

  it("mostra pela chave o motivo que ainda não tem tradução", () => {
    // o motor ganha código novo quando entra tabela nova. Sumir seria pior que
    // aparecer feio: o total não fecharia e ninguém saberia por quê.
    render(
      <Concluida
        resumo={resumo({
          linhas_recusadas: 4,
          recusas_com_exemplo: {
            motivo_que_ninguem_traduziu: { linhas: 4, exemplo: "2026-01: motivo novo do motor." },
          },
        })}
      />,
    );

    expect(screen.getByText("motivo_que_ninguem_traduziu")).toBeTruthy();
    // a contagem do item, e não a frase do cabeçalho: as duas dizem "4 linha(s)"
    expect(screen.getByText("4 linha(s)")).toBeTruthy();
  });

  it("não inventa bloco de recusa quando não houve recusa", () => {
    render(<Concluida resumo={resumo()} />);

    expect(screen.queryByText(/Fora do total, e por quê/i)).toBeNull();
  });
});

describe("a estimativa", () => {
  it("é dita com o valor quando existe", () => {
    render(<Concluida resumo={resumo({ credito_estimado: "237658.21" })} />);

    expect(screen.getByText(/237\.658,21 do total são estimativa/)).toBeTruthy();
  });

  it("não aparece quando o total inteiro é apurado", () => {
    render(<Concluida resumo={resumo({ credito_estimado: "0" })} />);

    expect(screen.queryByText(/estimativa/i)).toBeNull();
  });
});

describe("o intervalo de emissão", () => {
  it("sai como está no arquivo, sem fuso pelo meio", () => {
    // `new Date("2024-02-15")` é meia-noite UTC: em Brasília isso imprime
    // 14/02. Data de emissão não tem fuso — é o dia escrito no arquivo.
    render(
      <Concluida
        resumo={resumo({ primeira_emissao: "2024-02-15", ultima_emissao: "2026-01-31" })}
      />,
    );

    expect(screen.getByText("15/02/2024")).toBeTruthy();
    expect(screen.getByText("31/01/2026")).toBeTruthy();
  });

  it("o formatador não volta um dia em nenhuma borda do mês", () => {
    expect(dia("2024-01-01")).toBe("01/01/2024");
    expect(dia("2024-12-31")).toBe("31/12/2024");
    expect(dia("2024-03-01")).toBe("01/03/2024");
    expect(dia(null)).toBe("—");
  });
});

describe("a tradução dos motivos", () => {
  it("devolve a chave quando não conhece o motivo", () => {
    expect(rotuloDoMotivo("inventado_agora")).toBe("inventado_agora");
  });

  it("nunca devolve vazio", () => {
    for (const motivo of ["sem_classificacao", "mes_partido", "o_que_vier"]) {
      expect(rotuloDoMotivo(motivo).length).toBeGreaterThan(0);
    }
  });
});

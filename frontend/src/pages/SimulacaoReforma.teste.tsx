/**
 * O resultado da simulação da reforma: o que a tela não pode deixar de dizer.
 *
 * Três coisas são marcação, e marcação só se cobra renderizando:
 *
 * * **as premissas vêm antes dos números** — quem lê 4,8% em 2027 precisa ter
 *   lido antes que o preço é constante e que o IS é hipótese;
 * * **a pendência de cadastro não some**: item sem classificação fica fora da
 *   conta com a receita dita, e a tela diz que deveria ser zero;
 * * **margem negativa fica vermelha**: é o SKU ou a categoria que passa a dar
 *   prejuízo, e um número preto no meio dos outros esconde justamente isso.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Concluida } from "./SimulacaoReforma";
import type { AnoDaSimulacao, LinhaDaVisao, ResumoDaSimulacao } from "@/services/simulacaoReforma";

function ano(a: number, lucro: number, margem: number): AnoDaSimulacao {
  return {
    ano: a,
    receita_bruta: 615_865_187.3,
    icms: 114_218_026.33,
    pis_cofins: 15_874_275.06,
    ipi: 0,
    cbs: 0,
    ibs: 0,
    receita_liquida: 485_772_885.9,
    custo_de_compra: 425_775_979.46,
    ipi_custo: 3_229_459.69,
    seletivo: 0,
    cmv: 429_005_439.15,
    lucro_bruto: lucro,
    margem,
    creditos: 81_549_703.96,
    valor_bruto_das_compras: 510_555_143.11,
    a_recolher: 48_542_597.43,
    carga: 0.0788,
    carga_com_seletivo: 0.0788,
    teste_destacado: 0,
    variacao_teorica: 0,
  };
}

function linha(chave: string, rotulo: string, margem2027: number): LinhaDaVisao {
  return {
    chave,
    rotulo,
    linhas: 100,
    skus: 10,
    receita_bruta: 1_000_000,
    seletivo_pleno: 0,
    anos: {
      "2025": { lucro_bruto: 90_000, margem: 0.09, carga: 0.1, variacao_teorica: 0 },
      "2027": { lucro_bruto: margem2027 * 1_000_000, margem: margem2027, carga: 0.1, variacao_teorica: 0.05 },
      "2033": { lucro_bruto: 150_000, margem: 0.15, carga: 0.05, variacao_teorica: -0.06 },
    },
  };
}

function resumo(parcial: Partial<ResumoDaSimulacao> = {}): ResumoDaSimulacao {
  return {
    cenario: { nome: "Base — LC 214/2025", fator_seletivo: 1, anos: [], grupos: [], seletivo: [] },
    base: {
      arquivos: 3,
      arquivos_de_classificacao: 1,
      linhas_lidas: 522_934,
      linhas_consideradas: 474_289,
      skus: 14_197,
      itens_classificados: 20_307,
      lojas: 51,
      competencias: ["2025-12"],
      receita_bruta: 615_865_187.3,
      conflitos_de_cadastro: 0,
    },
    exclusoes: [],
    pendencias: [],
    por_ano: [ano(2025, 56_767_446.75, 0.0922), ano(2027, 29_833_883.19, 0.0484), ano(2033, 93_506_142.43, 0.1518)],
    por_grupo: [linha("padrao", "Alíquota padrão", 0.0125)],
    por_uf: [],
    por_seletivo: [],
    por_capitulo: [],
    segundos: 184,
    ...parcial,
  };
}

describe("as premissas vêm antes dos números", () => {
  it("diz que é preliminar, com preço constante e IS hipotético, antes da trajetória", () => {
    render(<Concluida execucaoId={1} resumo={resumo()} />);

    const premissas = screen.getByText(/Simulação preliminar, sujeita à validação de premissas/i);
    const trajetoria = screen.getByText(/Trajetória, ano a ano/i);
    // o que vem antes no DOM vem antes na leitura
    expect(premissas.compareDocumentPosition(trajetoria) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/Preço e volume constantes/i)).toBeTruthy();
    expect(screen.getByText(/são hipóteses/i)).toBeTruthy();
  });

  it("avisa quando a base tem um mês só, porque a sazonalidade impede extrapolar", () => {
    render(<Concluida execucaoId={1} resumo={resumo()} />);
    expect(screen.getByText(/Base de um mês só \(12\/2025\)/)).toBeTruthy();
  });

  it("não avisa de mês só quando o ano inteiro está na base", () => {
    const base = resumo().base!;
    render(
      <Concluida
        execucaoId={1}
        resumo={resumo({ base: { ...base, competencias: ["2025-01", "2025-02", "2025-03"] } })}
      />,
    );
    expect(screen.queryByText(/Base de um mês só/)).toBeNull();
  });
});

describe("o que ficou fora da conta", () => {
  it("a pendência de cadastro aparece com a receita, os exemplos e o aviso de que deveria ser zero", () => {
    render(
      <Concluida
        execucaoId={1}
        resumo={resumo({
          pendencias: [
            {
              motivo: "Item sem cadastro de classificação",
              linhas: 37,
              skus: 4,
              receita_bruta: 2_500_000,
              exemplos: ["1234 EQUIPAMENTO LOCADO", "5678 ITEM NOVO"],
            },
          ],
        })}
      />,
    );

    expect(screen.getByText(/R\$ 2,5 mi de receita ficaram fora por falta de cadastro/)).toBeTruthy();
    expect(screen.getByText(/Deveria ser zero antes de apresentar/)).toBeTruthy();
    expect(screen.getByText("Item sem cadastro de classificação")).toBeTruthy();
    expect(screen.getByText(/1234 EQUIPAMENTO LOCADO/)).toBeTruthy();
  });

  it("a exclusão por falta de custo aparece como método, com a receita líquida", () => {
    render(
      <Concluida
        execucaoId={1}
        resumo={resumo({
          exclusoes: [{ motivo: "Sem compra Abr-Dez", linhas: 40_633, skus: 2_485, receita_liquida: 64_869_226.86 }],
        })}
      />,
    );

    expect(screen.getByText(/Sem custo de compra: Sem compra Abr-Dez/)).toBeTruthy();
    expect(screen.getByText(/64\.869\.226,86 de receita líquida/)).toBeTruthy();
    // exclusão é método, não pendência: o aviso amarelo de cadastro não aparece
    expect(screen.queryByText(/por falta de cadastro/)).toBeNull();
  });

  it("não inventa o bloco quando nada ficou de fora", () => {
    render(<Concluida execucaoId={1} resumo={resumo()} />);
    expect(screen.queryByText(/Fora da conta, e por quê/i)).toBeNull();
  });
});

describe("a margem", () => {
  it("negativa fica vermelha na visão, e positiva não", () => {
    render(
      <Concluida
        execucaoId={1}
        resumo={resumo({
          por_seletivo: [linha("alcool", "Bebidas alcoólicas", -0.3), linha("", "Sem Imposto Seletivo", 0.097)],
        })}
      />,
    );

    const negativa = screen.getByText("-30,0%");
    expect(negativa.className).toContain("text-erro");
    const positiva = screen.getByText("9,7%");
    expect(positiva.className).not.toContain("text-erro");
  });

  it("os três anos em destaque saem com o lucro e a margem", () => {
    render(<Concluida execucaoId={1} resumo={resumo()} />);
    expect(screen.getByText("Lucro bruto 2025")).toBeTruthy();
    expect(screen.getByText("Lucro bruto 2027")).toBeTruthy();
    expect(screen.getByText("Lucro bruto 2033")).toBeTruthy();
    expect(screen.getByText("margem 4,8%")).toBeTruthy();
  });
});

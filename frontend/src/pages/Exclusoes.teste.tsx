/**
 * O número grande das exclusões diz qual dos dois ele é.
 *
 * A tese das contribuições tem **duas frentes**: o consolidado, que arredonda
 * uma vez por grupo com a alíquota efetiva do grupo, e o detalhe item a item,
 * que arredonda por linha como o relatório 680 do escritório anterior. Os dois
 * não batem, de propósito — cerca de 0,06% na base em que a regra foi medida.
 *
 * A explicação existia desde sempre, **no bloco do 680, a uma rolagem do número
 * grande**. Quem lê o número e vai conferir contra o relatório do escritório não
 * passa por ela: encontra uma diferença de alguns milhares de reais e vai
 * procurar defeito onde não há. Estes testes prendem a frase no lugar onde o
 * número é lido.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Concluido, QualDosDois } from "./Exclusoes";
import type { ExecucaoDasExclusoes, ResumoDasExclusoes } from "@/services/exclusoes";

function resumo(parcial: Partial<ResumoDasExclusoes> = {}): ResumoDasExclusoes {
  return { total_atualizado: "100000.00", ...parcial } as ResumoDasExclusoes;
}

describe("qual dos dois números é este", () => {
  it("diz que é o consolidado mesmo sem o detalhe para comparar", () => {
    render(<QualDosDois resumo={resumo()} />);

    expect(screen.getByText(/consolidado/)).toBeTruthy();
    expect(screen.queryByText(/680/)).toBeNull();
  });

  it("não inventa comparação quando o detalhe não foi apurado", () => {
    // `receita_por_item` vazio é rodada em que a tese por item não correu.
    // Comparar com zero diria "100% de diferença", que é falso e alarmante
    render(
      <QualDosDois resumo={resumo({ receita_por_item: {} as never })} />,
    );

    expect(screen.queryByText(/a mais|a menos/)).toBeNull();
  });

  it("mostra o total do 680 e a diferença quando os dois existem", () => {
    render(
      <QualDosDois
        resumo={resumo({
          total_atualizado: "2700000.00",
          receita_por_item: { total_atualizado: "2701620.00" } as never,
        })}
      />,
    );

    expect(screen.getByText(/^R\$\s*2\.701\.620,00$/)).toBeTruthy();
    // ancorado: "1.620,00" sem âncora casa também com "2.701.620,00"
    expect(screen.getByText(/^R\$\s*1\.620,00$/)).toBeTruthy();
    expect(screen.getByText(/a mais/)).toBeTruthy();
    // 1.620 / 2.700.000 = 0,06% — a diferença medida em 24/09/2026
    expect(screen.getByText(/0,06/)).toBeTruthy();
  });

  it("diz 'a menos' quando o detalhe fica abaixo do consolidado", () => {
    render(
      <QualDosDois
        resumo={resumo({
          total_atualizado: "2700000.00",
          receita_por_item: { total_atualizado: "2698000.00" } as never,
        })}
      />,
    );

    expect(screen.getByText(/a menos/)).toBeTruthy();
  });

  it("não fala em diferença quando os dois batem", () => {
    render(
      <QualDosDois
        resumo={resumo({
          total_atualizado: "500000.00",
          receita_por_item: { total_atualizado: "500000.00" } as never,
        })}
      />,
    );

    expect(screen.getByText(/os dois batem nesta base/)).toBeTruthy();
    expect(screen.queryByText(/a mais|a menos/)).toBeNull();
  });
});

describe("a frase está no cartão, e não só no componente", () => {
  /**
   * **O teste que faltava.** Arrancar `<QualDosDois>` do cartão passou por
   * todos os testes acima: eles renderizam o componente isolado, e componente
   * que existe não é componente que aparece. É a mesma classe de defeito dos
   * "dois registros" de uma etapa — o código certo no lugar errado.
   */
  const execucao = { id: 1, situacao: "concluida" } as ExecucaoDasExclusoes;

  it("o número grande se identifica como consolidado", () => {
    render(
      <Concluido
        execucao={execucao}
        resumo={resumo({
          total_atualizado: "2700000.00",
          receita_por_item: { total_atualizado: "2701620.00" } as never,
        })}
      />,
    );

    // a frase é única do `QualDosDois`: o rótulo acima também diz "consolidado"
    expect(screen.getByText(/arredonda uma vez por grupo/)).toBeTruthy();
    expect(screen.getByText(/^R\$\s*1\.620,00$/)).toBeTruthy();
  });
});

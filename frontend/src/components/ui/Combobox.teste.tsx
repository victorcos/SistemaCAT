/**
 * O painel do combobox não escapa do modal.
 *
 * Dois defeitos em sequência, os dois vistos em tela: primeiro a lista abria
 * **atrás** do diálogo (resolvido portando o painel para dentro do `<dialog>`);
 * depois passou a abrir **para fora** dele — num campo perto do rodapé, a lista
 * descia além da borda do card e ficava sobre o fundo escurecido da página.
 *
 * A causa do segundo era a medida: o espaço disponível vinha da janela, e a
 * janela é maior que o modal. Quem está dentro de um diálogo tem o diálogo por
 * mundo — é a borda dele que decide se a lista cabe embaixo, se cabe em cima e
 * onde ela para.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Combobox } from "./Combobox";

const OPCOES = [
  { valor: "piscofins", rotulo: "PIS/COFINS" },
  { valor: "icms", rotulo: "ICMS" },
  { valor: "irpj_csll", rotulo: "IRPJ/CSLL" },
];

/** jsdom não faz layout: todo retângulo é zero até alguém dizer o contrário. */
function retangulo(el: Element, r: { top: number; bottom: number }) {
  el.getBoundingClientRect = () =>
    ({
      top: r.top, bottom: r.bottom, left: 40, right: 340,
      width: 300, height: r.bottom - r.top, x: 40, y: r.top,
      toJSON: () => ({}),
    }) as DOMRect;
}

function montarNoModal(campo: { top: number; bottom: number }) {
  const { container } = render(
    // `open` porque o jsdom não implementa showModal(), e diálogo fechado é
    // `display: none` — invisível também para as queries por papel
    <dialog data-testid="modal" open>
      <Combobox valor="icms" opcoes={OPCOES} aoMudar={() => {}} />
    </dialog>,
  );
  const modal = screen.getByTestId("modal");
  // um modal de 520 px de altura, como o "Novo trabalho"
  retangulo(modal, { top: 8, bottom: 528 });
  retangulo(container.querySelector("[role='combobox']")!.parentElement!, campo);
  return modal;
}

function painelDe(modal: HTMLElement): HTMLElement {
  // o painel é portado para dentro do diálogo; é o filho com posição fixa
  const alvo = modal.querySelector<HTMLElement>("div[style*='position: fixed']");
  if (!alvo) throw new Error("o painel não foi montado dentro do modal");
  return alvo;
}

describe("dentro de um modal", () => {
  it("abre para cima quando não cabe embaixo, ainda que caiba na janela", () => {
    // campo a 38 px do rodapé do modal — e a 278 px do rodapé da janela
    const modal = montarNoModal({ top: 460, bottom: 490 });

    fireEvent.click(screen.getByRole("combobox"));
    const estilo = painelDe(modal).style;

    expect(estilo.bottom).not.toBe("");
    expect(estilo.top).toBe("");
  });

  it("abre para baixo quando cabe, e para antes da borda do modal", () => {
    const modal = montarNoModal({ top: 120, bottom: 150 });

    fireEvent.click(screen.getByRole("combobox"));
    const estilo = painelDe(modal).style;

    expect(estilo.top).toBe("156px");
    // 528 - 8 (margem) - 150 (rodapé do campo) - 14 = 356
    expect(estilo.maxHeight).toBe("356px");
  });

  it("o painel é montado dentro do diálogo, e não no corpo da página", () => {
    const modal = montarNoModal({ top: 120, bottom: 150 });

    fireEvent.click(screen.getByRole("combobox"));

    expect(modal.contains(painelDe(modal))).toBe(true);
    expect(screen.getByRole("listbox")).toBeTruthy();
  });
});

describe("fora de modal", () => {
  it("o limite volta a ser a janela", () => {
    const { container } = render(
      <Combobox valor="icms" opcoes={OPCOES} aoMudar={() => {}} />,
    );
    retangulo(container.querySelector("[role='combobox']")!.parentElement!, {
      top: 100, bottom: 130,
    });

    fireEvent.click(screen.getByRole("combobox"));
    const painel = document.body.querySelector<HTMLElement>("div[style*='position: fixed']")!;

    expect(painel.style.top).toBe("136px");
    // a janela do jsdom tem 768 px: 768 - 130 - 14
    expect(painel.style.maxHeight).toBe("624px");
  });
});

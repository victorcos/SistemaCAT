/**
 * O que todo teste de tela precisa antes de rodar.
 *
 * `cleanup` desmonta o que o teste anterior montou. Sem isso, o segundo teste
 * de um arquivo encontra dois seletores na tela e `getByRole` falha dizendo
 * que achou dois — erro que parece do componente e é do ambiente.
 */
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

/**
 * O jsdom não faz layout, e por isso não tem `scrollIntoView`.
 *
 * Quem o chama é código de teclado — a lista do combobox rolando até a opção
 * ativa. Sem este remendo, o efeito estoura e o teste falha por um motivo que
 * não tem nada a ver com o que ele está medindo.
 */
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

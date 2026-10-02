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

/**
 * O jsdom também não tem `showModal()` nem `close()` no `<dialog>`.
 *
 * O `open` que o remendo põe e tira é o que decide se o conteúdo existe para as
 * queries por papel: diálogo fechado é `display: none`, e nem `getByRole` o
 * enxerga. O evento `close` vai junto porque é por ele que a tela sabe que o
 * usuário fechou pelo Esc.
 */
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function abrir(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.show = HTMLDialogElement.prototype.showModal;
  HTMLDialogElement.prototype.close = function fechar(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}

/**
 * O jsdom não cria endereço de objeto, e o caminho antigo de download precisa.
 *
 * `baixarPelaPastaPadrao` monta um `blob:` para o link apontar. No jsdom a
 * função ou falta ou tropeça nas entranhas do `Blob`, e o teste falha com
 * `Cannot read properties of undefined (reading '_buffer')` — erro que parece
 * do download e é do ambiente. O remendo devolve um endereço de mentira, que é
 * tudo o que o teste precisa: o que se mede é o link, não o blob.
 */
URL.createObjectURL = () => "blob:de-mentira";
URL.revokeObjectURL = () => {};

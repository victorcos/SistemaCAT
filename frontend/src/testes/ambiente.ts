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

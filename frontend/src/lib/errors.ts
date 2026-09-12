import { ErroApi } from "@/types/erro";

/**
 * Garante um ErroApi a partir de qualquer coisa que tenha sido lançada.
 *
 * Existia copiado em seis páginas, com TRÊS mensagens diferentes. A do
 * Movimentos dizia "Não foi possível falar com o servidor", o que era falso:
 * falha de rede de verdade já sai de services/api.ts como ErroApi e passa
 * direto por aqui sem tocar no texto padrão. Este fallback só alcança erro de
 * programação, e para esse a mensagem honesta é a de baixo.
 */
export function comoErro(
  e: unknown,
  padrao = "Erro inesperado. Tente novamente.",
): ErroApi {
  return e instanceof ErroApi ? e : new ErroApi(padrao, 0);
}

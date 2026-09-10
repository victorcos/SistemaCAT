import { ErroApi } from "../tipos/auth";

const CHAVE_TOKEN = "cat.token";

export const guardarToken = (t: string) => localStorage.setItem(CHAVE_TOKEN, t);
export const lerToken = () => localStorage.getItem(CHAVE_TOKEN);
export const limparToken = () => localStorage.removeItem(CHAVE_TOKEN);

/**
 * Chamada à API.
 *
 * Todo erro sai como ErroApi carregando o identificador da requisição, que o
 * servidor devolve no cabeçalho. É o que permite mostrar um código na tela e
 * achar a linha exata no log sem ficar caçando por horário.
 */
export async function chamar<T>(
  caminho: string,
  opcoes: RequestInit = {},
): Promise<T> {
  const token = lerToken();
  const cabecalhos = new Headers(opcoes.headers);
  if (token) cabecalhos.set("Authorization", `Bearer ${token}`);

  let resposta: Response;
  try {
    resposta = await fetch(`/api${caminho}`, { ...opcoes, headers: cabecalhos });
  } catch {
    throw new ErroApi(
      "Não foi possível falar com o servidor. Verifique sua conexão.",
      0,
    );
  }

  const requisicaoId = resposta.headers.get("X-Request-Id") ?? undefined;

  if (!resposta.ok) {
    let detalhe = "Não foi possível concluir a operação.";
    try {
      const corpo = await resposta.json();
      if (typeof corpo?.detail === "string") detalhe = corpo.detail;
    } catch {
      /* resposta sem JSON: fica a mensagem padrão */
    }
    if (resposta.status === 401 && token) {
      limparToken(); // sessão expirada durante o uso
    }
    throw new ErroApi(detalhe, resposta.status, requisicaoId);
  }

  return resposta.status === 204 ? (undefined as T) : await resposta.json();
}

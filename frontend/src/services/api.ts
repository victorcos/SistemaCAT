import { ErroApi } from "@/types/erro";
import { emitirSessaoExpirada, lerToken, limparToken } from "./sessao";

// reexportados para nao quebrar quem ja importava daqui; a fonte e sessao.ts
export { guardarToken, lerToken, limparToken } from "./sessao";

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
    // 401 COM token e sessão que expirou durante o uso. 401 SEM token é só
    // login com senha errada — não é expiração e não deve avisar ninguém.
    if (resposta.status === 401 && token) {
      limparToken();
      emitirSessaoExpirada();
    }
    throw new ErroApi(detalhe, resposta.status, requisicaoId);
  }

  return resposta.status === 204 ? (undefined as T) : await resposta.json();
}

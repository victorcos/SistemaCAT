import { chamar } from "./api";

/**
 * Segmentos tributários: a primeira coisa que a pessoa vê depois de entrar.
 *
 * O catálogo vem do servidor, não daqui. Repetir a lista em TypeScript faria
 * duas fontes para a mesma verdade, e um dia elas divergiriam — e a que a tela
 * mostrasse não seria a que a API deixa abrir.
 *
 * São dois níveis: o segmento (PIS/COFINS, ICMS, IRPJ/CSLL) e, dentro dele, os
 * módulos. A reforma mora ao lado do tributo que sucede — CBS com PIS/COFINS,
 * IBS com ICMS —, porque de 2027 a 2033 é a mesma equipe apurando os dois lado
 * a lado.
 */

export interface Modulo {
  chave: string;
  rotulo: string;
  descricao: string;
}

export interface Segmento {
  chave: string;
  rotulo: string;
  descricao: string;
  modulos: Modulo[];
}

/** Só os que a pessoa enxerga. A tela nunca recebe card que não pode abrir. */
export const meusSegmentos = () =>
  chamar<{ segmentos: Segmento[] }>("/segmentos").then((r) => r.segmentos);

/** O catálogo inteiro, para o gestor liberar segmento a quem está abaixo. */
export const catalogoDeSegmentos = () =>
  chamar<{ segmentos: Segmento[] }>("/segmentos/todos").then((r) => r.segmentos);

/**
 * Troca a lista inteira de um usuário: o que não vem, sai. Substituir em vez de
 * somar é o que permite tirar acesso — e tirar tem de ser tão barato quanto dar.
 */
export const definirSegmentos = (usuarioId: number, segmentos: string[]) =>
  chamar<unknown>(`/usuarios/${usuarioId}/segmentos`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segmentos }),
  });

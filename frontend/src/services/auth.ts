import { chamar, guardarToken, limparToken } from "./api";
import type { RespostaToken, Usuario } from "@/types/auth";

export async function entrar(
  usuario: string,
  senha: string,
): Promise<RespostaToken> {
  // o endpoint segue o padrão OAuth2, que exige formulário e não JSON
  const corpo = new URLSearchParams({ username: usuario, password: senha });
  const r = await chamar<RespostaToken>("/auth/token", {
    method: "POST",
    body: corpo,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  guardarToken(r.access_token);
  return r;
}

export const quemSouEu = () => chamar<Usuario>("/auth/eu");

export const sair = () => limparToken();

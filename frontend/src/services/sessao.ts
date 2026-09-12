import { CHAVE_TOKEN } from "@/constants/storage";

export const guardarToken = (t: string) => localStorage.setItem(CHAVE_TOKEN, t);
export const lerToken = () => localStorage.getItem(CHAVE_TOKEN);
export const limparToken = () => localStorage.removeItem(CHAVE_TOKEN);

/**
 * Aviso de sessão expirada.
 *
 * O problema que isto resolve: `chamar()` apagava o token no 401, mas o React
 * não ficava sabendo. O componente continuava montado mostrando a mensagem de
 * erro, e a única saída era recarregar a página na mão — a tela ficava presa.
 *
 * `chamar()` não pode navegar sozinho (é um módulo, não um componente, e não
 * tem `useNavigate`). Então ele avisa por aqui e quem sabe navegar escuta: o
 * AuthProvider assina no mount, zera o usuário e manda para o login.
 */
type Ouvinte = () => void;
const ouvintes = new Set<Ouvinte>();

export function aoExpirarSessao(ouvinte: Ouvinte): () => void {
  ouvintes.add(ouvinte);
  return () => ouvintes.delete(ouvinte);
}

export function emitirSessaoExpirada() {
  for (const ouvinte of ouvintes) ouvinte();
}

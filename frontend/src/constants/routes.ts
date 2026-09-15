/**
 * Os caminhos do sistema num lugar só.
 *
 * Sem isto, mudar "/projetos/:id/arquivos" obriga a caçar template string
 * espalhada por cinco telas — e o TypeScript não ajuda, porque string sempre
 * compila.
 */
export const ROTAS = {
  login: "/login",
  trocarSenha: "/trocar-senha",
  inicio: "/",
  importar: "/importar",
  usuarios: "/usuarios",

  projeto: (id: number | string) => `/projetos/${id}`,
  arquivos: (id: number | string) => `/projetos/${id}/arquivos`,
  conferencia: (id: number | string) => `/projetos/${id}/conferencia`,
  movimentos: (id: number | string) => `/projetos/${id}/movimentos`,
  suportado: (id: number | string) => `/projetos/${id}/suportado`,
  razao: (id: number | string) => `/projetos/${id}/razao`,
  historico: (id: number | string) => `/projetos/${id}/historico`,
} as const;

/** Rotas que existem para entrar no sistema. Nunca servem como destino de
 *  volta depois do login — mandar alguem de volta para /login ou para
 *  /trocar-senha e um laco. */
const ROTAS_DE_ACESSO: string[] = [ROTAS.login, ROTAS.trocarSenha];

/**
 * Para onde voltar depois de entrar.
 *
 * O `de` vem do state da navegacao, que o navegador guarda no history e
 * devolve inclusive depois de um F5 — entao um `de` ruim gravado uma vez
 * sobrevive a sessao inteira. Filtrar aqui e o que impede isso.
 */
export function destinoDeVolta(de: unknown): string {
  return typeof de === "string" && de.startsWith("/") && !ROTAS_DE_ACESSO.includes(de)
    ? de
    : ROTAS.inicio;
}

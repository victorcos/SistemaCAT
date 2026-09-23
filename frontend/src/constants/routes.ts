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
  /** os cards do primeiro nível: os segmentos tributários que a pessoa enxerga */
  segmentos: "/segmentos",
  /** os cards do segundo nível: os módulos de um segmento */
  segmento: (chave: string) => `/segmentos/${chave}`,
  /** a lista de trabalhos de um módulo — a tela de demanda */
  modulo: (chave: string) => `/modulos/${chave}`,
  importar: "/importar",
  usuarios: "/usuarios",

  projeto: (id: number | string) => `/projetos/${id}`,
  arquivos: (id: number | string) => `/projetos/${id}/arquivos`,
  conferencia: (id: number | string) => `/projetos/${id}/conferencia`,
  movimentos: (id: number | string) => `/projetos/${id}/movimentos`,
  suportado: (id: number | string) => `/projetos/${id}/suportado`,
  razao: (id: number | string) => `/projetos/${id}/razao`,
  depara: (id: number | string) => `/projetos/${id}/depara`,
  apuracao: (id: number | string) => `/projetos/${id}/apuracao`,
  arquivoDigital: (id: number | string) => `/projetos/${id}/arquivo-digital`,
  preValidacao: (id: number | string) => `/projetos/${id}/pre-validacao`,
  quebraDeSped: (id: number | string) => `/projetos/${id}/quebra-de-sped`,
  /** o razão da ECD, com seletor de conta — sai da quebra de SPED */
  razaoContabil: (id: number | string) => `/projetos/${id}/razao-contabil`,
  entrega: (id: number | string) => `/projetos/${id}/entrega`,
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
function paraOndeIa(de: unknown): string | null {
  return typeof de === "string" && de.startsWith("/") && !ROTAS_DE_ACESSO.includes(de)
    ? de
    : null;
}

/**
 * Para onde mandar quem acabou de entrar.
 *
 * Quem foi barrado a caminho de alguma tela volta para ela. Quem entrou pela
 * porta da frente vai para onde o **servidor** disse: o hub, um segmento, ou
 * direto o módulo, conforme o que a pessoa enxerga (`usuario.entrada`,
 * resolvido em `Segmentos.Entrada`).
 *
 * A regra fica no servidor e não aqui porque é a mesma que decide o que cada
 * rota aceita. Duas cópias divergiriam, e a tela mandaria alguém para uma
 * página que a API recusa.
 */
export function destinoDaEntrada(usuario: { entrada: string | null }, de?: unknown): string {
  return paraOndeIa(de) ?? usuario.entrada ?? ROTAS.inicio;
}

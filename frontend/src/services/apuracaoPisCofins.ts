import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Apuração de PIS/COFINS: o par que se confronta.
 *
 * A **Consulta de Entradas (037)**, tirada da EFD-Contribuições, e o **razão
 * contábil**, tirado da ECD. Onde os dois discordam é onde está o trabalho.
 *
 * Saiu de dentro da quebra de SPED em 23/09/2026. A quebra abre os arquivos;
 * esta confronta o fiscal com o contábil — e quem quer olhar um registro não
 * precisa esperar a 037 de um ano inteiro.
 *
 * As três últimas chamadas são a leitura do razão na tela, e ficam aqui porque
 * é desta execução que o `razao.parquet` sai.
 */

export interface ResumoDaApuracao {
  versao?: number;
  arquivos?: number;
  /** quantas EFD-Contribuições e quantas ECD entraram */
  contribuicoes?: number;
  ecd?: number;
  ilegiveis?: number;
  /** linhas da Consulta de Entradas e do razão contábil */
  entradas?: number;
  linhas_do_razao?: number;
  /** quantas entradas vieram de cada ramo de documento */
  por_ramo?: Record<string, number>;
  estabelecimentos?: string[];
  competencias?: string[];
  avisos?: string[];
  iniciada_por?: string;
  segundos?: number;
  andamento?: { arquivos: number; entradas: number; razao: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDaApuracao extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaApuracao | null;
}

/** As duas planilhas: o par que se confronta. */
export type PlanilhaDaApuracao = "entradas" | "razao-contabil";

const NOME: Record<PlanilhaDaApuracao, string> = {
  entradas: "consulta_de_entradas",
  "razao-contabil": "razao_contabil",
};

export const iniciarApuracao = (projetoId: number) =>
  chamar<ExecucaoDaApuracao>(`/projetos/${projetoId}/apuracao-piscofins`, { method: "POST" });

export const listarApuracoes = (projetoId: number) =>
  chamar<ExecucaoDaApuracao[]>(`/projetos/${projetoId}/apuracao-piscofins`);

export const detalharApuracao = (execucaoId: number) =>
  chamar<ExecucaoDaApuracao>(`/apuracao-piscofins/${execucaoId}`);

export const cancelarApuracao = (execucaoId: number) =>
  chamar<ExecucaoDaApuracao>(`/apuracao-piscofins/${execucaoId}/cancelar`, { method: "POST" });

/**
 * Baixa a planilha da apuração.
 *
 * `contas` só vale para o razão, e é o recorte que a tela do razão monta: as
 * contas marcadas. Vazio, vem o razão inteiro — que numa ECD de rede passa de
 * milhão de partidas. O servidor as recebe como `classificacoes`, que é o
 * canal genérico de recorte das planilhas (na conferência são as situações do
 * documento; no suportado, as fontes da cascata).
 */
export function baixarPlanilhaDaApuracao(
  execucaoId: number,
  qual: PlanilhaDaApuracao,
  formato: Formato,
  contas: string[] = [],
  sinal?: AbortSignal,
): Promise<void> {
  const p = new URLSearchParams();
  if (formato !== "xlsx") p.set("formato", formato);
  if (contas.length) p.set("classificacoes", contas.join(","));
  const filtro = p.toString() ? `?${p}` : "";
  // o nome diz que é recorte: dois arquivos na pasta de Downloads com o mesmo
  // nome e conteúdos diferentes é como se confere a conta errada
  const recorte = contas.length ? `_${contas.length}_contas` : "";
  return baixarArquivo(
    `/api/apuracao-piscofins/${execucaoId}/planilhas/${qual}${filtro}`,
    `${NOME[qual]}${recorte}.${formato}`,
    sinal,
  );
}

/* -------------------------------------------------------------------------
 * O razão contábil da ECD: escolher a conta, depois ver os lançamentos.
 *
 * Sai desta mesma execução — é o `razao.parquet` que ela deixou em disco —, mas não é download: a tela lê página a página, porque uma ECD de
 * rede passa de milhão de partidas e nenhuma delas cabe numa resposta.
 * ------------------------------------------------------------------------- */

export interface Pagina<T> {
  pagina: number;
  por_pagina: number;
  total: number;
  linhas: T[];
}

/** Uma conta no seletor: o que ela movimentou e o que sobrou. */
export interface ContaContabil {
  cnpj: string;
  conta: string;
  descricao: string;
  conta_referencial: string;
  lancamentos: number;
  /** em reais, como texto — Decimal não atravessa JSON sem perder casa */
  debitos: string;
  creditos: string;
  saldo: string;
  de: string;
  ate: string;
  /** em quantos arquivos de ECD esta conta aparece; > 1 quebra o saldo corrente */
  arquivos: number;
}

/** Uma partida do razão, com o lançamento que a contém e o saldo até ela. */
export interface LancamentoContabil {
  cnpj: string;
  conta: string;
  descricao: string;
  conta_referencial: string;
  competencia: string;
  data: string;
  numero: string;
  valor_do_lancamento: string;
  centro_de_custo: string;
  valor: string;
  /** "D" ou "C" */
  debito_ou_credito: string;
  historico: string;
  codigo_do_historico: string;
  participante: string;
  tipo: string;
  saldo: string;
  arquivo: string;
}

export interface PaginaDeLancamentos extends Pagina<LancamentoContabil> {
  cnpj: string;
  conta: string;
  descricao: string;
  conta_referencial: string;
  /** houve recorte de data ou busca: os totais são os do recorte, não os da conta */
  recortado: boolean;
  totais: { debitos: string; creditos: string; saldo: string };
}

export interface EstabelecimentoDoRazao {
  cnpj: string;
  contas: number;
  lancamentos: number;
  de: string;
  ate: string;
}

/** O recorte do seletor é sobre o saldo da conta. */
export type RecorteDeConta = "todas" | "devedoras" | "credoras" | "zeradas" | "com_movimento";

export function contasDoRazaoContabil(
  execucaoId: number,
  filtro: { busca: string; cnpj: string; recorte: RecorteDeConta; pagina: number; porPagina: number },
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({ pagina: String(filtro.pagina), por_pagina: String(filtro.porPagina) });
  if (filtro.busca.trim()) p.set("busca", filtro.busca.trim());
  if (filtro.cnpj) p.set("cnpj", filtro.cnpj);
  if (filtro.recorte !== "todas") p.set("so", filtro.recorte);
  return chamar<Pagina<ContaContabil>>(`/apuracao-piscofins/${execucaoId}/contas?${p}`, { signal: sinal });
}

export function lancamentosDaConta(
  execucaoId: number,
  conta: { cnpj: string; conta: string },
  filtro: { busca: string; de: string; ate: string; pagina: number },
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({
    cnpj: conta.cnpj,
    conta: conta.conta,
    pagina: String(filtro.pagina),
    por_pagina: "100",
  });
  if (filtro.busca.trim()) p.set("busca", filtro.busca.trim());
  if (filtro.de) p.set("de", filtro.de);
  if (filtro.ate) p.set("ate", filtro.ate);
  return chamar<PaginaDeLancamentos>(`/apuracao-piscofins/${execucaoId}/lancamentos?${p}`, { signal: sinal });
}

export const estabelecimentosDoRazaoContabil = (execucaoId: number, sinal?: AbortSignal) =>
  chamar<{ linhas: EstabelecimentoDoRazao[] }>(`/apuracao-piscofins/${execucaoId}/estabelecimentos`, { signal: sinal });

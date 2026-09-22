import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Quebra de SPED — primeira etapa do módulo de PIS/COFINS.
 *
 * Lê a EFD-Contribuições e a ECD que o lote trouxe e deixa em disco o par que
 * se confronta: a **Consulta de Entradas (037)**, do lado fiscal, e o **razão
 * contábil**, do lado da contabilidade. Onde os dois discordam é onde está o
 * trabalho.
 *
 * Não depende de conferência nem de movimentos — aquelas são do rito da CAT 42,
 * no módulo de ICMS. Aqui o caminho é importar e quebrar.
 */

export interface ResumoDaQuebra {
  versao?: number;
  arquivos?: number;
  /** quantas EFD-Contribuições e quantas ECD entraram */
  contribuicoes?: number;
  ecd?: number;
  ilegiveis?: number;
  bytes?: number;
  linhas?: number;
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

export interface ExecucaoDaQuebra extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaQuebra | null;
}

/** As quatro planilhas da etapa. As duas primeiras são o par que se confronta. */
export type PlanilhaDaQuebra = "entradas" | "razao-contabil" | "arquivos" | "contagens";

const NOME: Record<PlanilhaDaQuebra, string> = {
  entradas: "consulta_de_entradas",
  "razao-contabil": "razao_contabil",
  arquivos: "sped_quebrados",
  contagens: "registros_por_arquivo",
};

export const iniciarQuebra = (projetoId: number) =>
  chamar<ExecucaoDaQuebra>(`/projetos/${projetoId}/quebra-de-sped`, { method: "POST" });

export const listarQuebras = (projetoId: number) =>
  chamar<ExecucaoDaQuebra[]>(`/projetos/${projetoId}/quebra-de-sped`);

export const detalharQuebra = (execucaoId: number) =>
  chamar<ExecucaoDaQuebra>(`/quebra-de-sped/${execucaoId}`);

export const cancelarQuebra = (execucaoId: number) =>
  chamar<ExecucaoDaQuebra>(`/quebra-de-sped/${execucaoId}/cancelar`, { method: "POST" });

export function baixarPlanilhaDaQuebra(
  execucaoId: number,
  qual: PlanilhaDaQuebra,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(
    `/api/quebra-de-sped/${execucaoId}/planilhas/${qual}${filtro}`,
    `${NOME[qual]}.${formato}`,
    sinal,
  );
}

/* -------------------------------------------------------------------------
 * O razão contábil da ECD: escolher a conta, depois ver os lançamentos.
 *
 * Sai da mesma execução da quebra — é o `razao.parquet` que ela deixou em
 * disco —, mas não é download: a tela lê página a página, porque uma ECD de
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
  return chamar<Pagina<ContaContabil>>(`/quebra-de-sped/${execucaoId}/contas?${p}`, { signal: sinal });
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
  return chamar<PaginaDeLancamentos>(`/quebra-de-sped/${execucaoId}/lancamentos?${p}`, { signal: sinal });
}

export const estabelecimentosDoRazaoContabil = (execucaoId: number, sinal?: AbortSignal) =>
  chamar<{ linhas: EstabelecimentoDoRazao[] }>(`/quebra-de-sped/${execucaoId}/estabelecimentos`, { signal: sinal });

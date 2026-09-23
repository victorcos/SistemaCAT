import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Apuração das contribuições — a Gestão Fiscal no padrão do MA.
 *
 * Segunda etapa do módulo de PIS/COFINS. Lê a EFD-Contribuições e a ECF do lote
 * e monta os quadros: da EFD saem **PIS e COFINS**, nos 36 quadros; da ECF saem
 * **IRPJ e CSLL** do Lucro Real.
 *
 * As duas fontes são independentes — a etapa roda com uma só, e diz qual
 * faltou. Um trabalho que tem só a ECF ainda tem IRPJ/CSLL para mostrar.
 */

export interface ResumoDaGestao {
  versao?: number;
  arquivos?: number;
  /** quantas EFD-Contribuições e quantas ECF foram lidas */
  contribuicoes?: number;
  ecf?: number;
  ilegiveis?: number;
  /** quantos quadros e quantas linhas de quadro saíram */
  quadros?: number;
  linhas?: number;
  /** os tributos que houve fonte para montar, na ordem em que saem */
  tributos?: string[];
  competencias?: string[];
  cnpj?: string;
  razao_social?: string;
  avisos?: string[];
  iniciada_por?: string;
  segundos?: number;
  andamento?: { arquivos: number; linhas: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDaGestao extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaGestao | null;
}

/** Uma planilha só: os quatro tributos, uma aba cada, no formato largo do MA. */
export type PlanilhaDaGestao = "quadros";

export const iniciarGestao = (projetoId: number) =>
  chamar<ExecucaoDaGestao>(`/projetos/${projetoId}/apuracao-contribuicoes`, { method: "POST" });

export const listarGestoes = (projetoId: number) =>
  chamar<ExecucaoDaGestao[]>(`/projetos/${projetoId}/apuracao-contribuicoes`);

export const detalharGestao = (execucaoId: number) =>
  chamar<ExecucaoDaGestao>(`/apuracao-contribuicoes/${execucaoId}`);

export const cancelarGestao = (execucaoId: number) =>
  chamar<ExecucaoDaGestao>(`/apuracao-contribuicoes/${execucaoId}/cancelar`, { method: "POST" });

export function baixarPlanilhaDaGestao(
  execucaoId: number,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(
    `/api/apuracao-contribuicoes/${execucaoId}/planilhas/quadros${filtro}`,
    `gestao_fiscal.${formato}`,
    sinal,
  );
}

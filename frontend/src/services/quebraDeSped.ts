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

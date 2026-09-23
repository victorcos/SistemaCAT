import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Quebrar os SPED: abrir os arquivos e dizer o que há dentro.
 *
 * Duas planilhas — o que foi lido e quantos de cada registro cada arquivo tem —
 * e um índice em disco com a posição de cada registro, que é o que permite
 * extrair qualquer bloco depois sem reler o arquivo.
 *
 * A Consulta de Entradas e o razão contábil saíram daqui em 23/09/2026 e viraram
 * a apuração de PIS/COFINS (`services/apuracaoPisCofins.ts`).
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
  /** quantos registros distintos apareceram em todos os arquivos somados */
  registros?: number;
  estabelecimentos?: string[];
  competencias?: string[];
  avisos?: string[];
  iniciada_por?: string;
  segundos?: number;
  andamento?: { arquivos: number; registros: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDaQuebra extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaQuebra | null;
}

/** As duas planilhas da etapa: o que foi lido e o que há dentro. */
export type PlanilhaDaQuebra = "arquivos" | "contagens";

const NOME: Record<PlanilhaDaQuebra, string> = {
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

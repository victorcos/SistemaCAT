import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Exclusões da base do PIS/COFINS.
 *
 * Hoje uma tese: as próprias contribuições fora da base. A receita embute PIS e
 * COFINS, e a base de cada uma perde as duas — decidido em 24/09/2026 entre as
 * três leituras possíveis. Vale só no débito: o crédito das aquisições fica
 * como está.
 *
 * A do ICMS destacado (Tema 69) vem depois, no mesmo parquet, porque precisa de
 * outra fonte: a EFD ICMS/IPI do mesmo CNPJ e competência.
 */

/** O total de uma competência — soma dos grupos, já arredondados. */
export interface LinhaDaCompetencia {
  competencia: string;
  grupos: number;
  /** em reais, como texto: Decimal não atravessa JSON sem perder casa */
  base: string;
  excluido: string;
  pis: string;
  cofins: string;
  pis_novo: string;
  cofins_novo: string;
  diferenca_pis: string;
  diferenca_cofins: string;
  diferenca: string;
}

export interface ResumoDasExclusoes {
  versao?: number;
  /** "agregados" (a Gestão já tinha lido) ou "sped" (leu agora) */
  fonte?: string;
  arquivos?: number;
  ilegiveis?: number;
  /** registro × CST × CFOP na competência: a unidade em que a conta arredonda */
  grupos?: number;
  base?: string;
  excluido?: string;
  diferenca_pis?: string;
  diferenca_cofins?: string;
  diferenca?: string;
  competencias?: string[];
  por_competencia?: LinhaDaCompetencia[];
  /** motivo -> quantas chaves não entraram na tese. Nada sai em silêncio */
  fora?: Record<string, number>;
  avisos?: string[];
  iniciada_por?: string;
  segundos?: number;
  andamento?: { arquivos: number; grupos: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDasExclusoes extends Omit<Execucao, "resumo"> {
  resumo: ResumoDasExclusoes | null;
}

export const iniciarExclusoes = (projetoId: number) =>
  chamar<ExecucaoDasExclusoes>(`/projetos/${projetoId}/exclusoes`, { method: "POST" });

export const listarExclusoes = (projetoId: number) =>
  chamar<ExecucaoDasExclusoes[]>(`/projetos/${projetoId}/exclusoes`);

export const detalharExclusoes = (execucaoId: number) =>
  chamar<ExecucaoDasExclusoes>(`/exclusoes/${execucaoId}`);

export const cancelarExclusoes = (execucaoId: number) =>
  chamar<ExecucaoDasExclusoes>(`/exclusoes/${execucaoId}/cancelar`, { method: "POST" });

/** Uma linha por grupo: somar a coluna da diferença dá o total da tela. */
export function baixarPlanilhaDasExclusoes(
  execucaoId: number,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(
    `/api/exclusoes/${execucaoId}/planilhas/exclusoes${filtro}`,
    `exclusoes_piscofins.${formato}`,
    sinal,
  );
}

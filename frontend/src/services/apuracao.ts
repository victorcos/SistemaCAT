import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Apuração do período: o fechamento por estabelecimento e mês.
 *
 * Ressarcimento e complemento nunca somados — um se pede, o outro se recolhe.
 * E a competência só é "apta" quando não há pendência: é ela que segue para o
 * arquivo digital.
 */

export interface MotivoDeBloqueio {
  codigo: string;
  rotulo: string;
  o_que_fazer: string;
}

export interface Competencia {
  cnpj: string;
  uf: string;
  competencia: string;
  ressarcimento: string;
  complemento: string;
  credito_operacao_propria: string;
  itens: number;
  linhas: number;
  saldo_inicial_quantidade: string;
  saldo_inicial_icms: string;
  saldo_final_quantidade: string;
  saldo_final_icms: string;
  fichas_retiradas: number;
  fichas_negativas?: number;
  confronto_pendente: number;
  sem_aliquota: number;
  indefinidas: number;
  inventarios_conferidos: number;
  inventarios_divergentes: number;
  apta: boolean;
  motivos: MotivoDeBloqueio[];
}

export interface ResumoDaApuracao {
  versao?: number;
  competencias?: number;
  aptas?: number;
  estabelecimentos?: number;
  estabelecimentos_aptos?: number;
  itens?: number;
  linhas?: number;
  saldos?: number;
  ressarcimento?: string;
  complemento?: string;
  credito_operacao_propria?: string;
  /** o que dá para pedir hoje: só das competências sem pendência */
  ressarcimento_apto?: string;
  complemento_apto?: string;
  por_competencia?: {
    competencia: string;
    competencias: number;
    aptas: number;
    ressarcimento: string;
    complemento: string;
  }[];
  por_motivo?: (MotivoDeBloqueio & { competencias: number })[];
  razao_execucao_id?: number;
  iniciada_por?: string;
  segundos?: number;
  andamento?: { competencias: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDaApuracao extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaApuracao | null;
}

export interface Pagina<T> {
  pagina: number;
  por_pagina: number;
  total: number;
  linhas: T[];
}

/** "todas", "aptas", "bloqueadas" ou o código de um motivo de bloqueio. */
export type RecorteDeCompetencia = string;
export type PlanilhaDaApuracao = "apuracao" | "saldos";

export const VERSAO_DO_RESUMO_DA_APURACAO = 1;

export const iniciarApuracao = (projetoId: number) =>
  chamar<ExecucaoDaApuracao>(`/projetos/${projetoId}/apuracao`, { method: "POST" });

export const listarApuracao = (projetoId: number) =>
  chamar<ExecucaoDaApuracao[]>(`/projetos/${projetoId}/apuracao`);

export const detalharApuracao = (execucaoId: number) =>
  chamar<ExecucaoDaApuracao>(`/apuracao/${execucaoId}`);

export const cancelarApuracao = (execucaoId: number) =>
  chamar<ExecucaoDaApuracao>(`/apuracao/${execucaoId}/cancelar`, { method: "POST" });

export function competenciasApuradas(
  execucaoId: number,
  filtro: { recorte: RecorteDeCompetencia; busca: string; pagina: number; porPagina: number },
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({ pagina: String(filtro.pagina), por_pagina: String(filtro.porPagina) });
  if (filtro.recorte !== "todas") p.set("so", filtro.recorte);
  if (filtro.busca.trim()) p.set("busca", filtro.busca.trim());
  return chamar<Pagina<Competencia>>(`/apuracao/${execucaoId}/competencias?${p}`, { signal: sinal });
}

const NOME: Record<PlanilhaDaApuracao, string> = {
  apuracao: "apuracao_do_periodo",
  saldos: "saldos_1050",
};

export function baixarPlanilhaDaApuracao(
  execucaoId: number,
  qual: PlanilhaDaApuracao,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(`/api/apuracao/${execucaoId}/planilhas/${qual}${filtro}`, `${NOME[qual]}.${formato}`, sinal);
}

import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Razão dos itens: a Ficha 3 de cada estabelecimento e mercadoria com ST.
 *
 * Mesmo desenho da etapa 4 — rodada no servidor, cancelável, com a lista de
 * fichas e as linhas de cada uma paginadas no servidor.
 */

export interface PorEnquadramento {
  /** "1", "2", "3", "4", "0" ou "indefinido" */
  codigo: string;
  rotulo: string;
  linhas: number;
  quantidade: string;
  suportado: string;
  confronto: string;
  ressarcimento: string;
  complemento: string;
}

export interface PendenciasDoRazao {
  saidas_sem_aliquota: number;
  saidas_indefinidas: number;
  confronto_pendente: number;
  fichas_negativas: number;
  fichas_abertura_sem_valor: number;
  fichas_fora_de_sp: number;
  relatorio_sem_estabelecimento: number;
  relatorio_trocado_pela_efd: number;
  quantidade_negativa: number;
}

export interface ResumoDoRazao {
  versao?: number;
  periodo_inicio?: string;
  periodo_fim?: string;
  abertura_em?: string | null;
  codigos_com_st?: number;
  fichas?: number;
  estabelecimentos?: number;
  linhas?: number;
  ressarcimento?: string;
  complemento?: string;
  por_enquadramento?: PorEnquadramento[];
  por_competencia?: { competencia: string; linhas: number; ressarcimento: string; complemento: string }[];
  saidas_por_origem?: Record<string, number>;
  pendencias?: PendenciasDoRazao;
  relatorios?: { arquivos: number; so_de_entradas: number; recusados: number; linhas: number };
  iniciada_por?: string;
  segundos?: number;
  andamento?: { linhas: number; total: number; fichas: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDoRazao extends Omit<Execucao, "resumo"> {
  resumo: ResumoDoRazao | null;
}

export interface Ficha {
  cnpj: string;
  uf: string;
  codigo: string;
  descricao: string;
  linhas: number;
  abertura_quantidade: string;
  abertura_sem_valor: boolean;
  entradas: string;
  saidas: string;
  saldo_quantidade: string;
  saldo_valor: string;
  ressarcimento: string;
  complemento: string;
  ficou_negativo: boolean;
  saidas_sem_aliquota: number;
  saidas_indefinidas: number;
}

export interface LinhaDaFicha {
  numero: number;
  data: string;
  especie: "entrada" | "saida";
  devolucao: boolean;
  cfop: string;
  documento: string;
  origem: string;
  enquadramento: number | null;
  enquadramento_indefinido: boolean;
  quantidade: string;
  icms_suportado: string;
  valor_unitario_usado: string;
  icms_efetivo: string | null;
  saldo_quantidade: string;
  saldo_unitario: string;
  saldo_valor: string;
  ressarcimento: string;
  complemento: string;
}

export interface Pagina<T> {
  pagina: number;
  por_pagina: number;
  total: number;
  linhas: T[];
}

export type Recorte = "todas" | "negativas" | "sem_aliquota" | "indefinidas";
export type PlanilhaDoRazao = "ficha3" | "fichas";

export const VERSAO_DO_RESUMO_DO_RAZAO = 1;

export const iniciarRazao = (projetoId: number) =>
  chamar<ExecucaoDoRazao>(`/projetos/${projetoId}/razao`, { method: "POST" });

export const listarRazao = (projetoId: number) =>
  chamar<ExecucaoDoRazao[]>(`/projetos/${projetoId}/razao`);

export const detalharRazao = (execucaoId: number) =>
  chamar<ExecucaoDoRazao>(`/razao/${execucaoId}`);

export const cancelarRazao = (execucaoId: number) =>
  chamar<ExecucaoDoRazao>(`/razao/${execucaoId}/cancelar`, { method: "POST" });

export function fichasDoRazao(
  execucaoId: number,
  filtro: { busca: string; recorte: Recorte; pagina: number; porPagina: number },
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({ pagina: String(filtro.pagina), por_pagina: String(filtro.porPagina) });
  if (filtro.busca.trim()) p.set("busca", filtro.busca.trim());
  if (filtro.recorte !== "todas") p.set("so", filtro.recorte);
  return chamar<Pagina<Ficha>>(`/razao/${execucaoId}/fichas?${p}`, { signal: sinal });
}

export function linhasDaFicha(
  execucaoId: number,
  ficha: { cnpj: string; codigo: string },
  pagina: number,
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({ cnpj: ficha.cnpj, codigo: ficha.codigo, pagina: String(pagina), por_pagina: "50" });
  return chamar<Pagina<LinhaDaFicha>>(`/razao/${execucaoId}/ficha?${p}`, { signal: sinal });
}

const NOME: Record<PlanilhaDoRazao, string> = { ficha3: "ficha3", fichas: "fichas_do_razao" };

export function baixarPlanilhaDoRazao(
  execucaoId: number,
  qual: PlanilhaDoRazao,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(`/api/razao/${execucaoId}/planilhas/${qual}${filtro}`, `${NOME[qual]}.${formato}`, sinal);
}

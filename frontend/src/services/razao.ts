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
  /** art. 271, só no enquadramento 4 (v0.53) */
  credito?: string;
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
  linhas_unidade_sem_fator?: number;
  abertura_sem_fator?: number;
  fichas_abertura_parcial?: number;
}

/** O saldo da ficha em cada data de bloco H contra o que a empresa declarou. */
export interface ConferenciaComInventario {
  datas: number;
  comparacoes: number;
  com_estoque: number;
  batem: number;
  proximas: number;
  divergentes: number;
  suspeita_unidade: number;
  fichas_divergentes: number;
  fichas_suspeita_unidade: number;
}

export interface ResumoDoRazao {
  versao?: number;
  /** a escolha do trabalho com que este razão foi montado; ausente nos de antes dela */
  venda_a_consumidor?: string;
  periodo_inicio?: string;
  periodo_fim?: string;
  abertura_em?: string | null;
  codigos_com_st?: number;
  fichas?: number;
  estabelecimentos?: number;
  linhas?: number;
  ressarcimento?: string;
  complemento?: string;
  /** crédito da operação própria do art. 271 nas saídas para outro estado (v0.53) */
  credito_operacao_propria?: string;
  /** saídas de enquadramento 2 e 4 confrontadas com o ICMS próprio das entradas (v0.53) */
  confronto_pela_entrada?: number;
  /** fora do total até os dados chegarem: o valor delas não é confiável */
  retiradas?: { fichas: number; linhas: number; ressarcimento: string; complemento: string };
  /** v0.56: fichas que abriram com o que faltava para o estoque não ficar negativo. */
  abertas_por_saldo_negativo?: { fichas: number; quantidade: string };
  /** v0.57: saídas de enquadramento 1 que confrontaram com base reduzida, e quanto ela tirou do confronto. */
  reducao_de_base?: { saidas: number; efetivo_reduzido: string };
  /** v0.58: saídas cuja alíquota veio da nota de entrada, por falta de 0200. */
  aliquota_da_entrada?: number;
  por_enquadramento?: PorEnquadramento[];
  por_competencia?: { competencia: string; linhas: number; ressarcimento: string; complemento: string }[];
  saidas_por_origem?: Record<string, number>;
  pendencias?: PendenciasDoRazao;
  conversao?: { linhas_convertidas: number; linhas_sem_fator: number };
  conferencia_inventario?: ConferenciaComInventario | Record<string, never>;
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
  /** o ICMS da abertura pelas entradas anteriores ao inventário (item 3.3.8) */
  abertura_valor?: string;
  abertura_sem_valor: boolean;
  abertura_parcial?: boolean;
  entradas: string;
  saidas: string;
  saldo_quantidade: string;
  saldo_valor: string;
  ressarcimento: string;
  complemento: string;
  ficou_negativo: boolean;
  retirada?: boolean;
  saidas_sem_aliquota: number;
  saidas_com_reducao?: number;
  saidas_indefinidas: number;
  linhas_sem_fator?: number;
  inventarios_conferidos?: number;
  inventarios_divergentes?: number;
  maior_diferenca_inventario?: string;
  suspeita_de_unidade?: boolean;
}

export interface LinhaDaFicha {
  numero: number;
  data: string;
  especie: "entrada" | "saida";
  devolucao: boolean;
  cfop: string;
  /** v0.58: o CST do documento, da EFD ou do XML */
  cst_icms?: string;
  documento: string;
  origem: string;
  enquadramento: number | null;
  enquadramento_indefinido: boolean;
  ficha_retirada?: boolean;
  abertura_por_saldo_negativo?: string;
  /** a quantidade vai na unidade do inventário; estas dizem como chegou lá */
  unidade_origem?: string;
  fator_conversao?: string;
  unidade_sem_fator?: boolean;
  quantidade: string;
  icms_suportado: string;
  valor_unitario_usado: string;
  icms_efetivo: string | null;
  /** v0.57: a alíquota do confronto e a redução de base, em %, que entraram nele */
  aliquota?: string | null;
  reducao_base?: string | null;
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

export type Recorte =
  | "validas"
  | "retiradas"
  | "todas"
  | "negativas"
  | "sem_aliquota"
  | "indefinidas"
  | "divergentes"
  | "suspeita_unidade"
  | "sem_fator";
export type PlanilhaDoRazao = "ficha3" | "fichas" | "conferencia";

/** 2: fichas com estoque negativo saem do total */
export const VERSAO_DO_RESUMO_DO_RAZAO = 2;

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

const NOME: Record<PlanilhaDoRazao, string> = {
  ficha3: "ficha3",
  fichas: "fichas_do_razao",
  conferencia: "conferencia_com_inventario",
};

export function baixarPlanilhaDoRazao(
  execucaoId: number,
  qual: PlanilhaDoRazao,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(`/api/razao/${execucaoId}/planilhas/${qual}${filtro}`, `${NOME[qual]}.${formato}`, sinal);
}

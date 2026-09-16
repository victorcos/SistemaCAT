import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import type { Pagina } from "./apuracao";
import type { Trava } from "./arquivoDigital";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Pré-validar o arquivo digital que o cliente já transmitiu.
 *
 * Fora do roteiro do trabalho: não depende de nenhuma etapa, e serve à
 * auditoria de quem já entrega a CAT 42 com outra ferramenta. Lê o TXT solto
 * no lote e o que estiver dentro de zip.
 */

export interface ArquivoDoCliente {
  nome: string;
  origem: string;
  cnpj: string;
  competencia: string;
  linhas: number;
  bytes: number;
  sha256: string;
  participantes: number;
  itens: number;
  saldos: number;
  eletronicos: number;
  nao_eletronicos: number;
  erros: number;
  avisos: number;
  itens_recompostos: number;
  itens_que_fecham: number;
  maior_diferenca_de_valor: string;
  repetido: boolean;
}

export interface ResumoDaPreValidacao {
  versao?: number;
  fontes?: number;
  arquivos?: number;
  sem_ocorrencia?: number;
  com_erro?: number;
  com_aviso?: number;
  repetidos?: number;
  de_outra_empresa?: number;
  linhas?: number;
  bytes?: number;
  erros?: number;
  avisos?: number;
  itens_recompostos?: number;
  itens_que_fecham?: number;
  estabelecimentos?: number;
  competencia_inicial?: string | null;
  competencia_final?: string | null;
  por_regra?: (Trava & { severidade: "erro" | "aviso"; arquivos: number; ocorrencias: number })[];
  iniciada_por?: string;
  segundos?: number;
  andamento?: { arquivos: number; bytes: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDaPreValidacao extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaPreValidacao | null;
}

/** "todos", "com_erro", "com_aviso", "sem_ocorrencia" ou "repetidos". */
export type RecorteDoCliente = string;
export type PlanilhaDaPreValidacao = "arquivos" | "ocorrencias";

export const VERSAO_DO_RESUMO_DA_PRE_VALIDACAO = 1;

export const iniciarPreValidacao = (projetoId: number) =>
  chamar<ExecucaoDaPreValidacao>(`/projetos/${projetoId}/pre-validacao`, { method: "POST" });

export const listarPreValidacao = (projetoId: number) =>
  chamar<ExecucaoDaPreValidacao[]>(`/projetos/${projetoId}/pre-validacao`);

export const detalharPreValidacao = (execucaoId: number) =>
  chamar<ExecucaoDaPreValidacao>(`/pre-validacao/${execucaoId}`);

export const cancelarPreValidacao = (execucaoId: number) =>
  chamar<ExecucaoDaPreValidacao>(`/pre-validacao/${execucaoId}/cancelar`, { method: "POST" });

export function arquivosDoCliente(
  execucaoId: number,
  filtro: { recorte: RecorteDoCliente; busca: string; pagina: number; porPagina: number },
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({ pagina: String(filtro.pagina), por_pagina: String(filtro.porPagina) });
  if (filtro.recorte !== "todos") p.set("so", filtro.recorte);
  if (filtro.busca.trim()) p.set("busca", filtro.busca.trim());
  return chamar<Pagina<ArquivoDoCliente>>(`/pre-validacao/${execucaoId}/arquivos?${p}`, { signal: sinal });
}

const NOME: Record<PlanilhaDaPreValidacao, string> = {
  arquivos: "arquivos_do_cliente",
  ocorrencias: "pre_validacao_do_cliente",
};

export function baixarPlanilhaDaPreValidacao(
  execucaoId: number,
  qual: PlanilhaDaPreValidacao,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(`/api/pre-validacao/${execucaoId}/planilhas/${qual}${filtro}`, `${NOME[qual]}.${formato}`, sinal);
}

import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import type { MotivoDeBloqueio, Pagina } from "./apuracao";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Etapa 7: o arquivo digital da CAT 42, um por estabelecimento de SP e mês.
 *
 * Vai para o envio só a competência apta, sem trava e sem erro na
 * pré-validação; as outras de SP saem como prévia, com PREVIA no nome.
 */

export interface Trava {
  codigo: string;
  rotulo: string;
  o_que_fazer: string;
}

export interface ArquivoGerado {
  cnpj: string;
  competencia: string;
  nome: string;
  destino: "envio" | "previa";
  apta: boolean;
  motivos: MotivoDeBloqueio[];
  travas: Trava[];
  ressarcimento: string;
  complemento: string;
  linhas: number;
  bytes: number;
  sha256: string;
  participantes: number;
  itens: number;
  saldos: number;
  eletronicos: number;
  nao_eletronicos: number;
  linhas_sem_documento: number;
  erros: number;
  avisos: number;
  itens_recompostos: number;
  itens_que_fecham: number;
}

export interface Ocorrencia {
  nome: string;
  regra: string;
  severidade: "erro" | "aviso";
  rotulo: string;
  o_que_fazer: string;
  vezes_no_arquivo: number;
  linha: number | null;
  registro: string;
  campo: string;
  item: string;
  mensagem: string;
}

export interface ResumoDoArquivoDigital {
  versao?: number;
  venda_a_consumidor?: string;
  competencias?: number;
  competencias_fora_de_sp?: number;
  arquivos?: number;
  para_envio?: number;
  previas?: number;
  linhas?: number;
  bytes?: number;
  por_registro?: Record<string, number>;
  linhas_sem_documento?: number;
  erros?: number;
  avisos?: number;
  itens_recompostos?: number;
  itens_que_fecham?: number;
  ressarcimento_para_envio?: string;
  complemento_para_envio?: string;
  por_trava?: (Trava & { arquivos: number })[];
  por_regra?: (Trava & { severidade: "erro" | "aviso"; arquivos: number; ocorrencias: number })[];
  apuracao_execucao_id?: number;
  razao_execucao_id?: number;
  iniciada_por?: string;
  segundos?: number;
  andamento?: { arquivos: number; total: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDoArquivoDigital extends Omit<Execucao, "resumo"> {
  resumo: ResumoDoArquivoDigital | null;
}

/** "todos", "envio", "previa" ou o código de uma trava. */
export type RecorteDeArquivo = string;
export type PlanilhaDoArquivoDigital = "arquivos" | "ocorrencias";
export type PacoteDoArquivoDigital = "envio" | "previas";

export const VERSAO_DO_RESUMO_DO_ARQUIVO_DIGITAL = 1;

export const iniciarArquivoDigital = (projetoId: number) =>
  chamar<ExecucaoDoArquivoDigital>(`/projetos/${projetoId}/arquivo-digital`, { method: "POST" });

export const listarArquivoDigital = (projetoId: number) =>
  chamar<ExecucaoDoArquivoDigital[]>(`/projetos/${projetoId}/arquivo-digital`);

export const detalharArquivoDigital = (execucaoId: number) =>
  chamar<ExecucaoDoArquivoDigital>(`/arquivo-digital/${execucaoId}`);

export const cancelarArquivoDigital = (execucaoId: number) =>
  chamar<ExecucaoDoArquivoDigital>(`/arquivo-digital/${execucaoId}/cancelar`, { method: "POST" });

export function arquivosGerados(
  execucaoId: number,
  filtro: { recorte: RecorteDeArquivo; busca: string; pagina: number; porPagina: number },
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({ pagina: String(filtro.pagina), por_pagina: String(filtro.porPagina) });
  if (filtro.recorte !== "todos") p.set("so", filtro.recorte);
  if (filtro.busca.trim()) p.set("busca", filtro.busca.trim());
  return chamar<Pagina<ArquivoGerado>>(`/arquivo-digital/${execucaoId}/arquivos?${p}`, { signal: sinal });
}

export function ocorrenciasDoArquivo(execucaoId: number, nome: string, pagina: number, sinal?: AbortSignal) {
  const p = new URLSearchParams({ arquivo: nome, pagina: String(pagina), por_pagina: "50" });
  return chamar<Pagina<Ocorrencia>>(`/arquivo-digital/${execucaoId}/ocorrencias?${p}`, { signal: sinal });
}

const NOME: Record<PlanilhaDoArquivoDigital, string> = {
  arquivos: "arquivos_digitais",
  ocorrencias: "pre_validacao",
};

export function baixarPlanilhaDoArquivoDigital(
  execucaoId: number,
  qual: PlanilhaDoArquivoDigital,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(`/api/arquivo-digital/${execucaoId}/planilhas/${qual}${filtro}`, `${NOME[qual]}.${formato}`, sinal);
}

/** Os TXT num zip: o de envio e o de prévias nunca se misturam. */
export function baixarPacote(execucaoId: number, qual: PacoteDoArquivoDigital, sinal?: AbortSignal): Promise<void> {
  const nome = qual === "envio" ? "arquivos_para_envio.zip" : "previas.zip";
  return baixarArquivo(`/api/arquivo-digital/${execucaoId}/planilhas/${qual}?formato=zip`, nome, sinal);
}

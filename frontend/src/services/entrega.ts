import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import type { Pagina } from "./apuracao";
import { baixarArquivo, type Execucao } from "./conferencia";

/**
 * Etapa 8: relatórios e entrega.
 *
 * O relatório mostra toda competência, pronta ou não; o dossiê leva só o que
 * vai à SEFAZ. Montar não conclui: um revisor ou gestor aprova, e é a
 * aprovação que fecha a etapa.
 */

export type Gravidade = "trava" | "atencao" | "informacao";

export interface PendenciaDaEntrega {
  etapa: string;
  nome_da_etapa: string;
  codigo: string;
  rotulo: string;
  quantidade: number;
  unidade: string;
  gravidade: Gravidade;
  gravidade_rotulo: string;
  o_que_fazer: string;
  /** o mesmo problema como cada etapa o viu, na unidade dela; a primeira é onde se resolve */
  medidas?: { quantidade: number; unidade: string; etapa: string; nome_da_etapa: string }[];
}

export interface EstabelecimentoDaEntrega {
  cnpj: string;
  uf: string;
  competencias: number;
  para_envio: number;
  previas: number;
  fora_de_sp: boolean;
  ressarcimento: string;
  complemento: string;
  ressarcimento_para_envio: string;
  complemento_para_envio: string;
  no_dossie: boolean;
  arquivos_no_dossie: number;
  bytes_no_dossie: number;
}

export interface ResumoDaEntrega {
  versao?: number;
  competencias?: number;
  competencias_de_sp?: number;
  para_envio?: number;
  previas?: number;
  fora_de_sp?: number;
  sem_arquivo?: number;
  estabelecimentos?: number;
  estabelecimentos_no_dossie?: number;
  ressarcimento?: string;
  complemento?: string;
  ressarcimento_para_envio?: string;
  complemento_para_envio?: string;
  arquivos_no_dossie?: number;
  arquivos_no_pacote?: number;
  bytes_do_pacote?: number;
  sha256_do_pacote?: string;
  por_gravidade?: Partial<Record<Gravidade, number>>;
  pendencias?: PendenciaDaEntrega[];
  arquivo_digital_execucao_id?: number;
  apuracao_execucao_id?: number;
  razao_execucao_id?: number;
  iniciada_por?: string;
  segundos?: number;
  andamento?: { estabelecimentos: number; total: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDaEntrega extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaEntrega | null;
  /** nome de quem aprovou; nulo enquanto ninguém aprovou */
  aprovada_por: string | null;
  aprovada_em: string | null;
}

export type RecorteDeEstabelecimento = "todos" | "no_dossie" | "fora_do_dossie" | "com_previa" | "fora_de_sp";

export const VERSAO_DO_RESUMO_DA_ENTREGA = 1;

export const iniciarEntrega = (projetoId: number) =>
  chamar<ExecucaoDaEntrega>(`/projetos/${projetoId}/entrega`, { method: "POST" });

export const listarEntrega = (projetoId: number) => chamar<ExecucaoDaEntrega[]>(`/projetos/${projetoId}/entrega`);

export const detalharEntrega = (execucaoId: number) => chamar<ExecucaoDaEntrega>(`/entrega/${execucaoId}`);

export const cancelarEntrega = (execucaoId: number) =>
  chamar<ExecucaoDaEntrega>(`/entrega/${execucaoId}/cancelar`, { method: "POST" });

export const aprovarEntrega = (execucaoId: number, observacao: string) =>
  chamar<ExecucaoDaEntrega>(`/entrega/${execucaoId}/aprovar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ observacao: observacao.trim() || null }),
  });

export function estabelecimentosDaEntrega(
  execucaoId: number,
  filtro: { recorte: RecorteDeEstabelecimento; busca: string; pagina: number; porPagina: number },
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({ pagina: String(filtro.pagina), por_pagina: String(filtro.porPagina) });
  if (filtro.recorte !== "todos") p.set("so", filtro.recorte);
  if (filtro.busca.trim()) p.set("busca", filtro.busca.trim());
  return chamar<Pagina<EstabelecimentoDaEntrega>>(`/entrega/${execucaoId}/estabelecimentos?${p}`, { signal: sinal });
}

export const baixarPacoteDaEntrega = (execucaoId: number, sinal?: AbortSignal) =>
  baixarArquivo(`/api/entrega/${execucaoId}/planilhas/pacote?formato=zip`, "pacote_de_entrega.zip", sinal);

export const baixarRelatorioDaEntrega = (execucaoId: number, sinal?: AbortSignal) =>
  baixarArquivo(`/api/entrega/${execucaoId}/planilhas/relatorio`, "relatorio_da_entrega.xlsx", sinal);

import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Apuração do ICMS suportado: a cascata de quatro fontes sobre cada item de
 * entrada.
 *
 * Mesmo desenho das etapas anteriores — a rodada não cabe numa requisição,
 * a API devolve um identificador e a tela acompanha. Duas coisas novas: a
 * rodada aceita cancelar, e o analítico vem paginado do servidor (numa base
 * real são 8,7 milhões de itens).
 */

/** As fontes, na ordem da cascata. A ordem desta lista É a ordem da tela. */
export const FONTES = [
  "documento",
  "informado_pelo_fornecedor",
  "base_e_aliquota",
  "nao_apuravel",
] as const;
export type Fonte = (typeof FONTES)[number];

export interface FatiaDeFonte {
  codigo: Fonte;
  rotulo: string;
  itens: number;
  valor: string;
  /** `null` no não apurável: não é documento nem reconstrução */
  documental: boolean | null;
}

export interface QuebraPorCst {
  cst: string;
  itens: number;
  valor: string;
  apurados: number;
}

export interface QuebraPorCompetencia {
  /** "2021-05" */
  competencia: string;
  itens: number;
  valor: string;
  cobertura: number;
}

export interface EntradaDoLog {
  em: string;
  nivel: "info" | "aviso" | "erro";
  texto: string;
}

export interface AndamentoDoSuportado {
  itens: number;
  apurados: number;
  estabelecimentos: number;
  total: number;
}

/**
 * O resumo de uma apuração.
 *
 * Quase tudo opcional porque o mesmo campo `resumo` carrega três momentos:
 * rodando (só andamento e log), concluída (tudo) e de versão anterior (sem
 * `versao` e sem a lista por fonte).
 */
export interface ResumoDoSuportado {
  versao?: number;
  itens?: number;
  apurados?: number;
  cobertura?: number;
  valor_total?: string;
  valor_documental?: string;
  fracao_documental?: number;
  por_fonte?: FatiaDeFonte[];
  por_pendencia?: { sem_o_que_apurar: number; falta_dado: number };
  por_cst?: QuebraPorCst[];
  por_competencia?: QuebraPorCompetencia[];
  estabelecimentos?: number;
  cst_sem_o_que_apurar?: { cst: string; itens: number } | null;
  iniciada_por?: string;
  relatorios?: { arquivos: number; recusados: number; itens: number; sem_chave: number };
  movimentos_execucao_id?: number;
  segundos?: number;
  andamento?: AndamentoDoSuportado;
  log?: EntradaDoLog[];
}

/** A versão do resumo que esta tela sabe ler. Abaixo disso, "rode de novo". */
export const VERSAO_DO_RESUMO = 2;

export interface ExecucaoDoSuportado extends Omit<Execucao, "resumo"> {
  resumo: ResumoDoSuportado | null;
}

export type Escopo = "documento" | "item";

export interface ItemDoAnalitico {
  /** o que identifica a nota: a chave, ou estabelecimento+número quando não há chave */
  documento: string;
  /** vazia na nota sem chave de acesso (modelo 1) */
  chave: string;
  numero_documento: string | null;
  modelo: string;
  competencia: string;
  participante: string | null;
  codigo: string | null;
  descricao: string | null;
  cst: string;
  fonte: Fonte;
  bc_st: string;
  suportado: string;
  motivo: string;
}

export interface DocumentoDoAnalitico {
  documento: string;
  chave: string;
  numero_documento: string | null;
  modelo: string;
  competencia: string;
  participante: string | null;
  cst: string;
  fonte: Fonte;
  itens: number;
  bc_st: string;
  suportado: string;
  filhos: ItemDoAnalitico[];
}

export interface PaginaDoAnalitico<T> {
  escopo: Escopo;
  pagina: number;
  por_pagina: number;
  total: number;
  linhas: T[];
}

export const iniciarSuportado = (projetoId: number) =>
  chamar<ExecucaoDoSuportado>(`/projetos/${projetoId}/suportado`, { method: "POST" });

export const listarSuportado = (projetoId: number) =>
  chamar<ExecucaoDoSuportado[]>(`/projetos/${projetoId}/suportado`);

export const detalharSuportado = (execucaoId: number) =>
  chamar<ExecucaoDoSuportado>(`/suportado/${execucaoId}`);

/**
 * Pede para a rodada parar. Na fila, cancela na hora; rodando, ela para no
 * próximo ponto seguro — a tela continua acompanhando até virar "cancelada".
 */
export const cancelarSuportado = (execucaoId: number) =>
  chamar<ExecucaoDoSuportado>(`/suportado/${execucaoId}/cancelar`, { method: "POST" });

export function linhasDoSuportado(
  execucaoId: number,
  filtro: { escopo: Escopo; fonte: Fonte | null; busca: string; pagina: number; porPagina: number },
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({
    escopo: filtro.escopo,
    pagina: String(filtro.pagina),
    por_pagina: String(filtro.porPagina),
  });
  if (filtro.fonte) p.set("fonte", filtro.fonte);
  if (filtro.busca.trim()) p.set("busca", filtro.busca.trim());
  return chamar<PaginaDoAnalitico<DocumentoDoAnalitico | ItemDoAnalitico>>(
    `/suportado/${execucaoId}/linhas?${p}`,
    { signal: sinal },
  );
}

/** O nome que a janela de salvar sugere: a fonte entra quando filtra. */
export function nomeDaPlanilha(fonte: Fonte | null, formato: Formato): string {
  return `icms_suportado${fonte ? `-${fonte}` : ""}.${formato}`;
}

export function baixarPlanilhaDoSuportado(
  execucaoId: number,
  fonte: Fonte | null,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const p = new URLSearchParams();
  // `classificacoes`, nesta etapa, são as fontes da cascata
  if (fonte) p.set("classificacoes", fonte);
  if (formato !== "xlsx") p.set("formato", formato);
  const filtro = p.toString() ? `?${p}` : "";
  return baixarArquivo(
    `/api/suportado/${execucaoId}/planilhas/suportado${filtro}`,
    nomeDaPlanilha(fonte, formato),
    sinal,
  );
}

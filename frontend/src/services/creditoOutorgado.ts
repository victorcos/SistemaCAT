import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Crédito outorgado: quais itens vendidos são produto beneficiado.
 *
 * Duas coisas que as outras etapas não têm:
 *
 * * **um filtro que é do trabalho**, e existe antes da primeira rodada — por
 *   isso ele pende do projeto (`/projetos/:id/credito-outorgado/filtro`) e não
 *   da execução;
 * * **uma leitura por produto**, que é como se revisa esse filtro depois:
 *   ninguém confere um benefício lendo três milhões de linhas de venda.
 *
 * A regra vive no motor (`dominio/icms/credito_outorgado`): a descrição manda,
 * a NCM confirma. Nada disso é decidido aqui.
 */

export interface FiltroDoOutorgado {
  /** NCM só com dígitos, como o motor normaliza */
  ncms: string[];
  /** termos de descrição em maiúsculas */
  termos: string[];
  /** rodar sem julgar nada: tudo sai elegível, marcado "SEM FILTRO" */
  sem_filtro: boolean;
  /** guardar também o que ficou de fora, para revisar o filtro */
  guardar_descartados: boolean;
  atualizado_em?: string | null;
  atualizado_por?: number | null;
}

export interface ResumoDoOutorgado {
  versao?: number;
  arquivos?: number;
  bytes?: number;
  documentos?: number;
  itens?: number;
  elegiveis?: number;
  descartados?: number;
  /** o que os itens elegíveis somam, em centavos */
  centavos_elegiveis?: number;
  repetidos?: number;
  nao_autorizados?: number;
  nao_sao_documento?: number;
  ilegiveis?: number;
  exemplos_ilegiveis?: string[];
  recusados?: string[];
  /** o retrato do filtro no momento da rodada — não o filtro de hoje */
  filtro?: { ncms: string[]; termos: string[]; sem_filtro: boolean };
  guardou_descartados?: boolean;
  iniciada_por?: string;
  segundos?: number;
  andamento?: { arquivos: number; elegiveis: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDoOutorgado extends Omit<Execucao, "resumo"> {
  resumo: ResumoDoOutorgado | null;
}

/** Um produto capturado pelo filtro: é por aqui que se revisa a triagem. */
export interface ProdutoDoOutorgado {
  codigo: string;
  descricao: string;
  ncm: string;
  motivo: string;
  itens: number;
  quantidade: string;
  valor: string;
}

/** Uma linha de item, com a nota de onde veio. */
export interface ItemDoOutorgado {
  chave: string;
  modelo: string;
  numero_documento: string;
  serie: string;
  emissao: string | null;
  emitente: string;
  emitente_nome: string;
  destinatario: string;
  destinatario_nome: string;
  numero_item: number;
  codigo: string;
  descricao: string;
  ncm: string;
  cest: string;
  cfop: string;
  unidade: string;
  quantidade: string;
  valor_unitario: string;
  valor: string;
  cst_icms: string;
  bc_icms: string;
  aliq_icms: string;
  valor_icms: string;
  cst_pis: string;
  cst_cofins: string;
  motivo: string;
  arquivo: string;
}

export interface PaginaDeProdutos {
  pagina: number;
  por_pagina: number;
  total: number;
  linhas: ProdutoDoOutorgado[];
  itens: number;
  valor: string;
  descartados: boolean;
  buscou: boolean;
}

export interface PaginaDeItens {
  pagina: number;
  por_pagina: number;
  total: number;
  linhas: ItemDoOutorgado[];
  valor: string;
  descartados: boolean;
  buscou: boolean;
}

/** As duas listas: o que entra no benefício e o que ficou de fora. */
export type PlanilhaDoOutorgado = "elegiveis" | "descartados";

const NOME: Record<PlanilhaDoOutorgado, string> = {
  elegiveis: "credito_outorgado",
  descartados: "credito_outorgado_descartados",
};

export const lerFiltroDoOutorgado = (projetoId: number) =>
  chamar<FiltroDoOutorgado>(`/projetos/${projetoId}/credito-outorgado/filtro`);

export const gravarFiltroDoOutorgado = (
  projetoId: number,
  filtro: Pick<FiltroDoOutorgado, "ncms" | "termos" | "sem_filtro" | "guardar_descartados">,
) =>
  chamar<FiltroDoOutorgado>(`/projetos/${projetoId}/credito-outorgado/filtro`, {
    method: "PUT",
    body: JSON.stringify(filtro),
  });

export const iniciarOutorgado = (projetoId: number) =>
  chamar<ExecucaoDoOutorgado>(`/projetos/${projetoId}/credito-outorgado`, { method: "POST" });

export const listarOutorgados = (projetoId: number) =>
  chamar<ExecucaoDoOutorgado[]>(`/projetos/${projetoId}/credito-outorgado`);

export const detalharOutorgado = (execucaoId: number) =>
  chamar<ExecucaoDoOutorgado>(`/credito-outorgado/${execucaoId}`);

export const cancelarOutorgado = (execucaoId: number) =>
  chamar<ExecucaoDoOutorgado>(`/credito-outorgado/${execucaoId}/cancelar`, { method: "POST" });

function consulta(p: { descartados?: boolean; busca?: string; codigo?: string; pagina?: number }) {
  const q = new URLSearchParams();
  if (p.descartados) q.set("descartados", "true");
  if (p.busca?.trim()) q.set("busca", p.busca.trim());
  if (p.codigo) q.set("codigo", p.codigo);
  if (p.pagina && p.pagina > 1) q.set("pagina", String(p.pagina));
  const texto = q.toString();
  return texto ? `?${texto}` : "";
}

export const produtosDoOutorgado = (
  execucaoId: number,
  p: { descartados?: boolean; busca?: string; pagina?: number },
  sinal?: AbortSignal,
) =>
  chamar<PaginaDeProdutos>(`/credito-outorgado/${execucaoId}/produtos${consulta(p)}`, { signal: sinal });

export const itensDoOutorgado = (
  execucaoId: number,
  p: { descartados?: boolean; busca?: string; codigo?: string; pagina?: number },
  sinal?: AbortSignal,
) =>
  chamar<PaginaDeItens>(`/credito-outorgado/${execucaoId}/itens${consulta(p)}`, { signal: sinal });

export function baixarPlanilhaDoOutorgado(
  execucaoId: number,
  qual: PlanilhaDoOutorgado,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(
    `/api/credito-outorgado/${execucaoId}/planilhas/${qual}${filtro}`,
    `${NOME[qual]}.${formato}`,
    sinal,
  );
}

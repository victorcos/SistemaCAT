import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Fatia, type Formato } from "./conferencia";

/**
 * Histórico de movimentação: os itens da EFD, marcados pela conferência.
 *
 * Mesmo desenho da conferência — a rodada não cabe numa requisição, a API
 * devolve um identificador e a tela acompanha.
 */

export interface ResumoDaMovimentacao {
  arquivos: number;
  estabelecimentos: string[];
  documentos: number;
  documentos_com_item: number;
  entradas_sem_item: number;
  saidas_sem_item: number;
  valor_saidas_sem_item: string;
  valor_saidas_sem_item_st: string;
  saidas_sem_item_por_modelo: Fatia[];
  movimentos: number;
  movimentos_entrada: number;
  movimentos_saida: number;
  valor_entradas: string;
  valor_saidas: string;
  st_nas_entradas: string;
  por_cst: Fatia[];
  por_classificacao: Fatia[];
  itens_cadastrados: number;
  itens_movimentados: number;
  itens_sem_cadastro: number;
  inventarios: number;
  itens_em_estoque: number;
  valor_em_estoque: string;
  conferencia_usada: boolean;
  cobertura_de_item: number;
  avisos: string[];
  recusados: string[];
  /** Fora do confronto de propósito, e não por defeito. Opcional porque
   *  execução antiga não gravou o campo. */
  observacoes?: string[];
  efd_originais_substituidas: number;
  analiticos: number;
}

export interface ExecucaoDeMovimentos extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaMovimentacao | null;
}

/** As quatro listas que a etapa exporta. */
export type PlanilhaDeMovimentos = "movimentos" | "itens" | "inventario" | "analitico";

export const iniciarMovimentos = (projetoId: number) =>
  chamar<ExecucaoDeMovimentos>(`/projetos/${projetoId}/movimentos`, {
    method: "POST",
  });

export const listarMovimentos = (projetoId: number) =>
  chamar<ExecucaoDeMovimentos[]>(`/projetos/${projetoId}/movimentos`);

export const detalharMovimentos = (execucaoId: number) =>
  chamar<ExecucaoDeMovimentos>(`/movimentos/${execucaoId}`);

export function baixarPlanilhaDeMovimentos(
  execucaoId: number,
  qual: PlanilhaDeMovimentos,
  modelos: string[] = [],
  classificacoes: string[] = [],
  formato: Formato = "xlsx",
): Promise<void> {
  const parametros = new URLSearchParams();
  if (modelos.length) parametros.set("modelos", modelos.join(","));
  if (classificacoes.length)
    parametros.set("classificacoes", classificacoes.join(","));
  if (formato !== "xlsx") parametros.set("formato", formato);
  const filtro = parametros.toString() ? `?${parametros}` : "";
  return baixarArquivo(
    `/api/movimentos/${execucaoId}/planilhas/${qual}${filtro}`,
    `${qual}.${formato}`,
  );
}

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
  /** O item do XML (v0.53). Opcionais: execução antiga não leu XML. */
  xml_arquivos?: number;
  xml_documentos?: number;
  xml_itens?: number;
  xml_repetidos?: number;
  xml_nao_sao_documento?: number;
  xml_ilegiveis?: number;
  /** v0.55: uso denegado fora; cópia autorizada no lugar da sem protocolo. */
  xml_nao_autorizados?: number;
  xml_copias_trocadas?: number;
  saidas_completadas_pelo_xml?: number;
  entradas_completadas_pelo_xml?: number;
  movimentos_do_xml?: number;
  itens_pareados_com_xml?: number;
  itens_sem_par_no_xml?: number;
  /** Canceladas na SEFAZ (v0.54.0): evento de cancelamento ou lista de chaves. */
  chaves_canceladas?: number;
  documentos_cancelados_na_sefaz?: number;
  movimentos_cancelados?: number;
  /** Não escrituradas e a multa do art. 527, sem SELIC (v0.54.0). */
  nao_escrituradas_entradas?: number;
  nao_escrituradas_saidas?: number;
  valor_nao_escriturado_entradas?: string;
  icms_nao_escriturado_saidas?: string;
  multa_nao_escrituradas_entradas?: string;
  multa_nao_escrituradas_saidas?: string;
  contingencia_por_ano?: Fatia[];
}

export interface ExecucaoDeMovimentos extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaMovimentacao | null;
}

/** As listas que a etapa exporta. */
export type PlanilhaDeMovimentos =
  | "movimentos"
  | "itens"
  | "inventario"
  | "analitico"
  | "contingencia";

/** O nome que a janela de salvar sugere. */
const NOME_SUGERIDO: Record<PlanilhaDeMovimentos, string> = {
  movimentos: "movimentos",
  itens: "cadastro_de_itens",
  inventario: "inventario",
  analitico: "analitico_por_documento",
  contingencia: "contingencia_nao_escrituradas",
};

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
  sinal?: AbortSignal,
): Promise<void> {
  const parametros = new URLSearchParams();
  if (modelos.length) parametros.set("modelos", modelos.join(","));
  if (classificacoes.length)
    parametros.set("classificacoes", classificacoes.join(","));
  if (formato !== "xlsx") parametros.set("formato", formato);
  const filtro = parametros.toString() ? `?${parametros}` : "";
  return baixarArquivo(
    `/api/movimentos/${execucaoId}/planilhas/${qual}${filtro}`,
    `${NOME_SUGERIDO[qual]}.${formato}`,
    sinal,
  );
}

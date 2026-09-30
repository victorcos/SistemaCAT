import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Exclusões da base do PIS/COFINS. Duas teses, uma rodada.
 *
 * **As próprias contribuições fora da base**: a receita embute PIS e COFINS, e
 * a base de cada uma perde as duas — decidido em 24/09/2026 entre as três
 * leituras possíveis. Vale só no débito: o crédito das aquisições fica como
 * está.
 *
 * **O ICMS destacado fora da base**, o Tema 69: apurado item a item, no formato
 * do relatório 903, e corrigido pela Selic até o mês em que se roda. Esperava-se
 * precisar da EFD ICMS/IPI para achá-lo; não precisa — o C170 da própria
 * EFD-Contribuições traz o `VL_ICMS`.
 *
 * **O número do Tema 69 só existe com a data ao lado.** A Selic acumulada cresce
 * a cada mês, então a tela mostra sempre até quando a rodada corrigiu. Rodar de
 * novo no mês que vem dá outro número — maior, e certo.
 */

/** O total de uma competência — soma dos grupos, já arredondados. */
export interface LinhaDaCompetencia {
  competencia: string;
  /** fora dos cinco anos: aparece em vermelho e não entra no crédito */
  prescrita: boolean;
  grupos: number;
  /** em reais, como texto: Decimal não atravessa JSON sem perder casa */
  base: string;
  excluido: string;
  pis: string;
  cofins: string;
  pis_novo: string;
  cofins_novo: string;
  diferenca_pis: string;
  diferenca_cofins: string;
  diferenca: string;
}

/** O total de uma competência no Tema 69 — em reais, como texto. */
export interface CompetenciaDoIcms {
  competencia: string;
  prescrita: boolean;
  /** itens de nota que entraram */
  linhas: number;
  /** a acumulada aplicada nesta competência, em por cento */
  selic_acumulada: string;
  base: string;
  icms_excluido: string;
  diferenca_pis: string;
  diferenca_cofins: string;
  selic: string;
  total_atualizado: string;
}

/** O ICMS fora da base — o Tema 69. Vazio quando a tese não pôde ser apurada. */
export interface ResumoDoIcms {
  versao?: number;
  /** "aaaa-mm": o mês da restituição até onde a Selic acumulou */
  ate?: string;
  arquivos?: number;
  ilegiveis?: number;
  /** itens de nota fiscal no relatório */
  linhas?: number;
  estabelecimentos?: string[];
  competencias?: string[];
  base?: string;
  icms_excluido?: string;
  diferenca_pis?: string;
  diferenca_cofins?: string;
  /** só a correção, separada do principal: é o que mais cresce com o tempo */
  selic?: string;
  total_atualizado?: string;
  prescrito?: string;
  competencias_prescritas?: number;
  data_de_referencia?: string;
  por_competencia?: CompetenciaDoIcms[];
  avisos?: string[];
  segundos?: number;
}

export interface ResumoDasExclusoes {
  versao?: number;
  /** "agregados" (a Gestão já tinha lido) ou "sped" (leu agora) */
  fonte?: string;
  arquivos?: number;
  ilegiveis?: number;
  /** registro × CST × CFOP na competência: a unidade em que a conta arredonda */
  grupos?: number;
  base?: string;
  excluido?: string;
  diferenca_pis?: string;
  diferenca_cofins?: string;
  diferenca?: string;
  competencias?: string[];
  /** o que os cinco anos levaram — mostrado, nunca somado ao crédito */
  prescrito?: string;
  competencias_prescritas?: number;
  /** a data do pedido que decidiu o corte, em aaaa-mm-dd */
  data_de_referencia?: string;
  por_competencia?: LinhaDaCompetencia[];
  /** motivo -> quantas chaves não entraram na tese. Nada sai em silêncio */
  fora?: Record<string, number>;
  /** a segunda tese. Ausente ou vazia quando não deu para apurá-la */
  icms?: ResumoDoIcms;
  avisos?: string[];
  iniciada_por?: string;
  segundos?: number;
  /** `fase` diz qual das duas leituras está andando: "receita" ou "icms" */
  andamento?: { arquivos: number; grupos: number; fase?: string };
  log?: EntradaDoLog[];
}

export interface ExecucaoDasExclusoes extends Omit<Execucao, "resumo"> {
  resumo: ResumoDasExclusoes | null;
}

export const iniciarExclusoes = (projetoId: number) =>
  chamar<ExecucaoDasExclusoes>(`/projetos/${projetoId}/exclusoes`, { method: "POST" });

export const listarExclusoes = (projetoId: number) =>
  chamar<ExecucaoDasExclusoes[]>(`/projetos/${projetoId}/exclusoes`);

export const detalharExclusoes = (execucaoId: number) =>
  chamar<ExecucaoDasExclusoes>(`/exclusoes/${execucaoId}`);

export const cancelarExclusoes = (execucaoId: number) =>
  chamar<ExecucaoDasExclusoes>(`/exclusoes/${execucaoId}/cancelar`, { method: "POST" });

/**
 * O Tema 69 item a item: as quarenta colunas do relatório 903, na ordem em que
 * o MA exporta — para que o cliente ponha as duas lado a lado e confira.
 */
export function baixarPlanilhaDoIcms(
  execucaoId: number,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(
    `/api/exclusoes/${execucaoId}/planilhas/icms${filtro}`,
    `exclusao_do_icms.${formato}`,
    sinal,
  );
}

/** Uma linha por grupo: somar a coluna da diferença dá o total da tela. */
export function baixarPlanilhaDasExclusoes(
  execucaoId: number,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(
    `/api/exclusoes/${execucaoId}/planilhas/exclusoes${filtro}`,
    `exclusoes_piscofins.${formato}`,
    sinal,
  );
}

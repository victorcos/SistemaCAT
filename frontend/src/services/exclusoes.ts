import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Exclusões da base do PIS/COFINS. Quatro teses, uma rodada.
 *
 * **As próprias contribuições fora da base**: a receita embute PIS e COFINS, e
 * a base de cada uma perde as duas — decidido em 24/09/2026 entre as três
 * leituras possíveis. Vale só no débito: o crédito das aquisições fica como
 * está.
 *
 * **A tese das contribuições tem duas frentes.** A consolidada soma por grupo e
 * arredonda uma vez por grupo — é o número que se pede, e é o que está nos
 * campos do topo deste resumo. A detalhada (`receita_por_item`) é o relatório
 * 680 do MA, uma linha por item. Os dois totais **não batem**, e é de propósito:
 * arredondar milhões de itens um a um move o total, e na base em que a regra foi
 * medida a diferença ficou em 0,06%. Ver a decisão de 24/09/2026.
 *
 * **Três exclusões de imposto da receita**, apuradas item a item e corrigidas
 * pela Selic até o mês em que se roda: o **ICMS** (Tema 69, relatório 903), o
 * **ICMS-ST** (839) e o **ISS** (933). Cada uma tem o seu total, o seu detalhe e
 * a sua planilha, e elas nunca se somam num número só — são pedidos diferentes,
 * com fundamentos diferentes.
 *
 * As três têm a mesma forma de resumo (`ResumoDaTese`), porque a rodada é a
 * mesma; o que muda é a conta, e essa mora no motor de cada uma.
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
  selic: string;
  total_atualizado: string;
  /** a acumulada aplicada nesta competência, em por cento */
  selic_acumulada: string;
}

/** O total de uma competência numa tese por item — em reais, como texto. */
export interface CompetenciaDaTese {
  competencia: string;
  prescrita: boolean;
  /** itens de nota que entraram */
  linhas: number;
  /** a acumulada aplicada nesta competência, em por cento */
  selic_acumulada: string;
  base: string;
  excluido: string;
  diferenca_pis: string;
  diferenca_cofins: string;
  selic: string;
  total_atualizado: string;
}

/** Uma tese por item. Vazia quando ela não pôde ser apurada. */
export interface ResumoDaTese {
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
  /** o imposto que sai da base: ICMS, ICMS-ST ou ISS, conforme a tese */
  excluido?: string;
  diferenca_pis?: string;
  diferenca_cofins?: string;
  /** só a correção, separada do principal: é o que mais cresce com o tempo */
  selic?: string;
  total_atualizado?: string;
  prescrito?: string;
  competencias_prescritas?: number;
  data_de_referencia?: string;
  por_competencia?: CompetenciaDaTese[];
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
  /** o principal que volta, sem a Selic */
  diferenca?: string;
  /** a correção, e o total com ela. Esta tese não corrigia até 01/10/2026 */
  selic?: string;
  total_atualizado?: string;
  /** o mês até onde a Selic acumulou, em aaaa-mm */
  ate?: string;
  competencias?: string[];
  /** o que os cinco anos levaram — mostrado, nunca somado ao crédito */
  prescrito?: string;
  competencias_prescritas?: number;
  /** a data do pedido que decidiu o corte, em aaaa-mm-dd */
  data_de_referencia?: string;
  por_competencia?: LinhaDaCompetencia[];
  /** motivo -> quantas chaves não entraram na tese. Nada sai em silêncio */
  fora?: Record<string, number>;
  /** as quatro teses por item. Ausentes ou vazias quando não deu para apurá-las.
   *  `receita_por_item` não é um quinto pedido: é a mesma tese dos campos acima
   *  vista item a item, no leiaute do 680. Somá-la ao resto pede a tese 1 duas
   *  vezes */
  receita_por_item?: ResumoDaTese;
  icms?: ResumoDaTese;
  icms_st?: ResumoDaTese;
  iss?: ResumoDaTese;
  avisos?: string[];
  iniciada_por?: string;
  segundos?: number;
  /** `fase` diz qual das cinco leituras anda: receita, receita_por_item, icms,
   *  icms_st ou iss */
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
 * O detalhe de uma tese por item, nas colunas e na ordem em que o MA exporta —
 * para que o cliente ponha os dois relatórios lado a lado e confira.
 *
 * `alvo` é o nome da planilha na API: `receita-por-item`, `icms`, `icms-st` ou
 * `iss`.
 */
/** Como o arquivo baixado se chama, por tese. Derivar do `alvo` dava
 *  `exclusao_do_receita_por_item`, que ninguém reconhece na pasta de downloads */
const ARQUIVO_DA_TESE: Record<string, string> = {
  "receita-por-item": "exclusao_piscofins_na_propria_base",
  icms: "exclusao_do_icms",
  "icms-st": "exclusao_do_icms_st",
  iss: "exclusao_do_iss",
};

export function baixarPlanilhaDaTese(
  execucaoId: number,
  alvo: string,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  const nome = ARQUIVO_DA_TESE[alvo] ?? `exclusao_${alvo.replace(/-/g, "_")}`;
  return baixarArquivo(
    `/api/exclusoes/${execucaoId}/planilhas/${alvo}${filtro}`,
    `${nome}.${formato}`,
    sinal,
  );
}

/**
 * **Tudo de uma vez**: o consolidado e as quatro teses por item, num zip.
 *
 * Quem confere põe os arquivos lado a lado com os do escritório anterior, e isso
 * só funciona se os cinco saírem do **mesmo instante** — cinco downloads em
 * cinco cliques são cinco chances de misturar rodadas. Vai com um `LEIA-ME.txt`
 * que diz o que é cada arquivo e avisa da diferença de arredondamento entre as
 * duas frentes da tese das contribuições.
 */
export const baixarPacoteDasExclusoes = (execucaoId: number, sinal?: AbortSignal) =>
  baixarArquivo(
    `/api/exclusoes/${execucaoId}/planilhas/pacote?formato=zip`,
    "exclusoes_da_base.zip",
    sinal,
  );

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

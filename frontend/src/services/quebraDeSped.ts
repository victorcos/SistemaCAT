import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Quebrar os SPED: abrir os arquivos e dizer o que há dentro.
 *
 * Duas planilhas — o que foi lido e quantos de cada registro cada arquivo tem —
 * e um índice em disco com a posição de cada registro, que é o que permite
 * extrair qualquer bloco depois sem reler o arquivo.
 *
 * A Consulta de Entradas e o razão contábil saíram daqui em 23/09/2026 e viraram
 * a apuração de PIS/COFINS (`services/apuracaoPisCofins.ts`).
 */

export interface ResumoDaQuebra {
  versao?: number;
  arquivos?: number;
  /** quantas EFD-Contribuições e quantas ECD entraram */
  contribuicoes?: number;
  ecd?: number;
  ilegiveis?: number;
  bytes?: number;
  linhas?: number;
  /** quantos registros distintos apareceram em todos os arquivos somados */
  registros?: number;
  estabelecimentos?: string[];
  competencias?: string[];
  avisos?: string[];
  iniciada_por?: string;
  segundos?: number;
  andamento?: { arquivos: number; registros: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDaQuebra extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaQuebra | null;
}

/** As duas planilhas da etapa: o que foi lido e o que há dentro. */
export type PlanilhaDaQuebra = "arquivos" | "contagens";

const NOME: Record<PlanilhaDaQuebra, string> = {
  arquivos: "sped_quebrados",
  contagens: "registros_por_arquivo",
};

export const iniciarQuebra = (projetoId: number) =>
  chamar<ExecucaoDaQuebra>(`/projetos/${projetoId}/quebra-de-sped`, { method: "POST" });

export const listarQuebras = (projetoId: number) =>
  chamar<ExecucaoDaQuebra[]>(`/projetos/${projetoId}/quebra-de-sped`);

export const detalharQuebra = (execucaoId: number) =>
  chamar<ExecucaoDaQuebra>(`/quebra-de-sped/${execucaoId}`);

export const cancelarQuebra = (execucaoId: number) =>
  chamar<ExecucaoDaQuebra>(`/quebra-de-sped/${execucaoId}/cancelar`, { method: "POST" });

/**
 * Um alvo de extração: um registro do SPED ou uma hierarquia dele.
 *
 * Quem diz quais existem é o servidor, a partir do índice da própria quebra —
 * só aparece o que **está nos arquivos**. Oferecer o C870 a quem não emite
 * cupom seria oferecer planilha vazia.
 */
export interface AlvoDaQuebra {
  /** "C170" ou "C100+C170" */
  alvo: string;
  rotulo: string;
  /** a primeira letra do registro: é como o leiaute do SPED se organiza */
  bloco: string;
  quantidade: number;
  colunas: number;
  hierarquia: boolean;
}

export interface AlvosDaQuebra {
  linhas: AlvoDaQuebra[];
  blocos: string[];
  rotulos_dos_blocos: Record<string, string>;
  /** quem aparece nos arquivos: a tela oferece em vez de pedir digitado */
  estabelecimentos: { cnpj: string; empresa: string }[];
  /** arquivos cujo índice não serve mais: a extração sai sem eles */
  sem_indice: number;
}

/**
 * O que entra na extração. Tudo vazio: sai inteira.
 *
 * Dois níveis, como no motor: `cnpjs`, `de` e `ate` pulam o arquivo sem
 * abri-lo; o resto filtra linha a linha, procurando o campo pelo sufixo do
 * nome — `cst_pis` acha o do C170, o do C870 e o do C491.
 */
export interface RecorteDaExtracao {
  cnpjs: string[];
  de: string;
  ate: string;
  cst_pis: string[];
  cst_cofins: string[];
  cfop: string[];
  cod_item: string[];
  cod_nat: string[];
  num_doc: string[];
  ind_aj: string[];
  cod_aj: string[];
  ind_oper: string;
  descricao: string[];
  doc_de: string;
  doc_ate: string;
  vl_pis_min: string;
  vl_pis_max: string;
  vl_item_min: string;
  vl_item_max: string;
}

export const RECORTE_INTEIRO: RecorteDaExtracao = {
  cnpjs: [], de: "", ate: "",
  cst_pis: [], cst_cofins: [], cfop: [], cod_item: [], cod_nat: [], num_doc: [],
  ind_aj: [], cod_aj: [], ind_oper: "", descricao: [],
  doc_de: "", doc_ate: "", vl_pis_min: "", vl_pis_max: "", vl_item_min: "", vl_item_max: "",
};

/** Quantos filtros estão em uso. Zero quer dizer extração inteira. */
export function quantosFiltros(r: RecorteDaExtracao): number {
  return Object.values(r).filter((v) => (Array.isArray(v) ? v.length > 0 : v !== "")).length;
}

export const alvosDaQuebra = (execucaoId: number, sinal?: AbortSignal) =>
  chamar<AlvosDaQuebra>(`/quebra-de-sped/${execucaoId}/alvos`, { signal: sinal });

/** Extrai o alvo e baixa a planilha. O nome do arquivo é o do servidor. */
export function baixarExtracao(
  execucaoId: number,
  alvo: string,
  formato: Formato,
  recorte: RecorteDaExtracao = RECORTE_INTEIRO,
  sinal?: AbortSignal,
): Promise<void> {
  const q = new URLSearchParams({ alvo });
  if (formato !== "xlsx") q.set("formato", formato);
  // campo ausente é ausência de filtro: mandar vazio faria o servidor
  // interpretar "nenhum valor passa"
  for (const [nome, valor] of Object.entries(recorte)) {
    const texto = Array.isArray(valor) ? valor.join(",") : valor;
    if (texto) q.set(nome, texto);
  }
  return baixarArquivo(
    `/api/quebra-de-sped/${execucaoId}/extracao?${q}`,
    `sped_${alvo.replace(/\+/g, "_")}.${formato}`,
    sinal,
  );
}

export function baixarPlanilhaDaQuebra(
  execucaoId: number,
  qual: PlanilhaDaQuebra,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const filtro = formato !== "xlsx" ? `?formato=${formato}` : "";
  return baixarArquivo(
    `/api/quebra-de-sped/${execucaoId}/planilhas/${qual}${filtro}`,
    `${NOME[qual]}.${formato}`,
    sinal,
  );
}

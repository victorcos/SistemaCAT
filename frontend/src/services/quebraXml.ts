import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Quebra de XML — as notas do lote, item a item.
 *
 * A mesma leitura que a extração de movimentos já usava no ICMS: NF-e, NFC-e e
 * CF-e SAT, soltos ou em zip, com CT-e e evento de cancelamento recusados e a
 * cópia autorizada vencendo a sem protocolo. O que muda é o propósito — aqui o
 * XML é o produto, e a planilha sai com as colunas que a pessoa escolher.
 *
 * Serve ao ICMS e ao PIS/COFINS: no primeiro é o item que a EFD não traz na
 * saída própria; no segundo, o CST e a alíquota que o C170 consolidado esconde.
 */

export interface ResumoDaQuebraDeXml {
  versao?: number;
  arquivos?: number;
  notas?: number;
  itens?: number;
  /** o que não entrou, cada um com a sua conta */
  repetidos?: number;
  nao_sao_documento?: number;
  ilegiveis?: number;
  sem_item?: number;
  nao_autorizados?: number;
  copias_trocadas?: number;
  cancelamentos?: number;
  iniciada_por?: string;
  segundos?: number;
  andamento?: { arquivos: number; notas: number; itens: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDaQuebraDeXml extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaQuebraDeXml | null;
}

/** Uma coluna possível da planilha. O catálogo vem do servidor. */
export interface CampoDoXml {
  campo: string;
  titulo: string;
  bloco: string;
}

export interface CatalogoDoXml {
  blocos: string[];
  campos: CampoDoXml[];
  /** atalho -> campos que ele marca ("icms", "piscofins", "descontos", "tudo") */
  atalhos: Record<string, string[]>;
}

/**
 * O catálogo de colunas.
 *
 * Vem do servidor de propósito: a tela não pode oferecer coluna que a planilha
 * não sabe produzir. Uma segunda lista escrita aqui divergiria na primeira vez
 * que alguém acrescentasse um campo do outro lado.
 */
export const camposDoXml = (sinal?: AbortSignal) =>
  chamar<CatalogoDoXml>("/quebra-xml/campos", { signal: sinal });

export const iniciarQuebraDeXml = (projetoId: number) =>
  chamar<ExecucaoDaQuebraDeXml>(`/projetos/${projetoId}/quebra-xml`, { method: "POST" });

export const listarQuebrasDeXml = (projetoId: number) =>
  chamar<ExecucaoDaQuebraDeXml[]>(`/projetos/${projetoId}/quebra-xml`);

export const detalharQuebraDeXml = (execucaoId: number) =>
  chamar<ExecucaoDaQuebraDeXml>(`/quebra-xml/${execucaoId}`);

export const cancelarQuebraDeXml = (execucaoId: number) =>
  chamar<ExecucaoDaQuebraDeXml>(`/quebra-xml/${execucaoId}/cancelar`, { method: "POST" });

/**
 * A planilha dos itens, com as colunas escolhidas.
 *
 * Os campos viajam em `classificacoes`, que é o canal genérico de recorte das
 * planilhas — aqui recortando **coluna** em vez de linha. Vazio, vem o
 * catálogo inteiro.
 */
export function baixarItensDoXml(
  execucaoId: number,
  formato: Formato,
  campos: string[] = [],
  sinal?: AbortSignal,
): Promise<void> {
  const p = new URLSearchParams();
  if (formato !== "xlsx") p.set("formato", formato);
  if (campos.length) p.set("classificacoes", campos.join(","));
  const filtro = p.toString() ? `?${p}` : "";
  const recorte = campos.length ? `_${campos.length}_campos` : "";
  return baixarArquivo(
    `/api/quebra-xml/${execucaoId}/planilhas/itens${filtro}`,
    `itens_do_xml${recorte}.${formato}`,
    sinal,
  );
}

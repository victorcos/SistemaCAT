import { chamar } from "./api";

/**
 * Lote de arquivos: a base de trabalho de um projeto que já existe.
 *
 * Não confundir com `importacao.ts`, que é o cadastro — aquele cria empresa e
 * projeto a partir de uma amostra do SPED, e acontece uma vez. Este alimenta
 * um trabalho já cadastrado, tem gigabytes e volta quantas vezes a empresa
 * mandar arquivo.
 *
 * Por isso aqui não se envia arquivo: envia-se o caminho da pasta. A maior
 * base que medimos tem 7.036 arquivos e um relatório sozinho tem 194 MB.
 */

export interface ArquivoDoLote {
  nome: string;
  caminho: string;
  tamanho: number;
  tipo: string;
  tipo_rotulo: string;
  grupo: string;
  alimenta_a_cat: boolean;
  cnpj: string | null;
  competencia: string | null;
  uf: string;
  detalhe: string;
  motivo: string;
}

export interface Contagem {
  tipo: string;
  rotulo: string;
  grupo: string;
  alimenta_a_cat: boolean;
  quantidade: number;
}

export interface ResumoDoLote {
  pasta: string;
  total_arquivos: number;
  arquivos_uteis: number;
  bytes_totais: number;
  de_outra_empresa: number;
  serve: boolean;
  competencia_ini: string | null;
  competencia_fim: string | null;
  cnpjs: string[];
  contagens: Contagem[];
  avisos: string[];
  amostra: ArquivoDoLote[];
  ja_no_trabalho: number;
}

export interface Lote {
  id: number;
  projeto_id: number;
  pasta: string;
  total_arquivos: number;
  arquivos_uteis: number;
  bytes_totais: number;
  competencia_ini: string | null;
  competencia_fim: string | null;
  observacao: string | null;
  criado_em: string;
  contagens: Contagem[];
}

export const inspecionarPasta = (projetoId: number, pasta: string) =>
  chamar<ResumoDoLote>(`/projetos/${projetoId}/lotes/inspecionar`, {
    method: "POST",
    body: JSON.stringify({ pasta }),
    headers: { "Content-Type": "application/json" },
  });

export const registrarLote = (
  projetoId: number,
  pasta: string,
  observacao: string | null,
) =>
  chamar<Lote>(`/projetos/${projetoId}/lotes`, {
    method: "POST",
    body: JSON.stringify({ pasta, observacao }),
    headers: { "Content-Type": "application/json" },
  });

export const listarLotes = (projetoId: number) =>
  chamar<Lote[]>(`/projetos/${projetoId}/lotes`);

export interface LoteApagado {
  pasta: string;
  arquivos: number;
  conferencias_invalidadas: number;
}

/** Desfaz a importação. O arquivo do cliente em disco não é tocado. */
export const removerLote = (projetoId: number, loteId: number) =>
  chamar<LoteApagado>(`/projetos/${projetoId}/lotes/${loteId}`, {
    method: "DELETE",
  });

import { chamar } from "./api";

/**
 * Histórico do trabalho: linha do tempo, comentários, situação e sucessão.
 *
 * O contrato está em docs/CONTRATOS.md §6. Duas coisas que valem repetir
 * aqui, porque mudam como a tela é escrita:
 *
 * * a paginação é **por cursor** (`antes_de`), não por página: com evento
 *   entrando enquanto se lê, offset repetiria e pularia linha;
 * * `rotulo_do_tipo` já vem traduzido do servidor. A tela não reescreve
 *   rótulo de evento — se o backend ganhar um tipo novo, ele aparece certo
 *   sem release do front.
 */

/** Os tipos que o servidor grava. Agrupados para o filtro em `FAMILIA`. */
export type TipoDeEvento =
  | "criado"
  | "comentario"
  | "status"
  | "sucessao"
  | "lote_importado"
  | "lote_removido"
  | "etapa_iniciada"
  | "etapa_concluida"
  | "etapa_falhou"
  | "planilha_baixada";

export interface EventoDoProjeto {
  id: number;
  tipo: TipoDeEvento;
  rotulo_do_tipo: string;
  texto: string;
  dados: {
    de?: string | null;
    para?: string | null;
    frase?: string;
    etapa?: string;
    pasta?: string;
    arquivos?: number;
    uteis?: number;
    bytes?: number;
    execucao_id?: number;
    [k: string]: unknown;
  };
  autor: string;
  autor_id: number | null;
  quando: string;
  e_comentario: boolean;
}

export interface PaginaDeHistorico {
  eventos: EventoDoProjeto[];
  tem_mais: boolean;
  proximo_cursor: number | null;
}

export interface StatusDisponivel {
  valor: string;
  rotulo: string;
  explicacao: string;
  exige_motivo: boolean;
}

export interface Sucessor {
  id: number;
  nome_exibicao: string;
  usuario: string;
  papel: string;
  cargo: string;
  /** receber o trabalho vai dar a esta pessoa acesso à empresa */
  precisa_de_acesso: boolean;
}

/** As quatro famílias do filtro da tela, sobre os dez tipos do servidor. */
export type Familia = "tudo" | "comentarios" | "situacao" | "arquivos" | "etapas";

export const FAMILIA: Record<Exclude<Familia, "tudo">, TipoDeEvento[]> = {
  comentarios: ["comentario"],
  situacao: ["status", "sucessao", "criado"],
  arquivos: ["lote_importado", "lote_removido"],
  etapas: ["etapa_iniciada", "etapa_concluida", "etapa_falhou", "planilha_baixada"],
};

export const daFamilia = (e: EventoDoProjeto, f: Familia) =>
  f === "tudo" || FAMILIA[f].includes(e.tipo);

export function lerHistorico(
  projetoId: number,
  opcoes: { antes_de?: number | null; quantos?: number } = {},
) {
  const p = new URLSearchParams();
  if (opcoes.antes_de) p.set("antes_de", String(opcoes.antes_de));
  if (opcoes.quantos) p.set("quantos", String(opcoes.quantos));
  const q = p.toString();
  return chamar<PaginaDeHistorico>(
    `/projetos/${projetoId}/historico${q ? `?${q}` : ""}`,
  );
}

export const comentar = (projetoId: number, texto: string) =>
  chamar<EventoDoProjeto>(`/projetos/${projetoId}/historico/comentarios`, {
    method: "POST",
    body: JSON.stringify({ texto }),
    headers: { "Content-Type": "application/json" },
  });

export const listarStatus = () => chamar<StatusDisponivel[]>("/status-de-projeto");

export const mudarStatus = (projetoId: number, status: string, motivo: string) =>
  chamar<{ status: string; rotulo: string }>(`/projetos/${projetoId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, motivo }),
    headers: { "Content-Type": "application/json" },
  });

export const listarSucessores = (projetoId: number) =>
  chamar<Sucessor[]>(`/projetos/${projetoId}/sucessores`);

export const passarTrabalho = (
  projetoId: number,
  responsavel_id: number,
  motivo: string,
) =>
  chamar<{ responsavel_id: number; responsavel: string | null }>(
    `/projetos/${projetoId}/responsavel`,
    {
      method: "PATCH",
      body: JSON.stringify({ responsavel_id, motivo }),
      headers: { "Content-Type": "application/json" },
    },
  );

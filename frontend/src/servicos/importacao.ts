import { chamar, lerToken } from "./api";
import { ErroApi } from "../tipos/auth";

export const FRENTES = {
  cat42: "CAT 42 — ressarcimento de ICMS-ST",
  depara: "De-para de produto",
  sped: "Quebra de SPED",
  notafiscal: "Nota fiscal",
} as const;

export type Frente = keyof typeof FRENTES;

export interface Remessa {
  razao_social: string;
  cnpj_raiz: string;
  cnpj_matriz: string | null;
  cnpj_matriz_formatado: string | null;
  matriz_encontrada: boolean;
  uf: string;
  inscricao_estadual: string;
  filiais: number;
  total_arquivos: number;
  lidos: number;
  recusados: number;
  tipos: Record<string, number>;
  arquivos_para_cat: number;
  primeira_competencia: string | null;
  ultima_competencia: string | null;
  avisos: string[];
  ja_cadastrada: boolean;
  empresa_id: number | null;
}

export interface Empresa {
  id: number;
  cnpj_raiz: string;
  cnpj_matriz: string | null;
  cnpj_matriz_formatado: string | null;
  razao_social: string;
  uf: string | null;
  inscricao_estadual: string | null;
  pre_cadastro: boolean;
  projetos: number;
}

export interface Projeto {
  id: number;
  empresa_id: number;
  empresa: string;
  cnpj_matriz: string | null;
  cnpj_matriz_formatado: string | null;
  uf: string | null;
  frente: string;
  frente_rotulo: string;
  nome: string;
  competencia_ini: string;
  competencia_fim: string;
  status: string;
  pre_cadastro: boolean;
  etapas_feitas: number;
  etapas_totais: number;
}

export interface Etapa {
  chave: string;
  nome: string;
  descricao: string;
  situacao: string;
  situacao_rotulo: string;
  implementada: boolean;
  acessivel: boolean;
}

export interface ProjetoDetalhe {
  projeto: Projeto;
  etapas: Etapa[];
}

/**
 * Envia a remessa.
 *
 * Não usa `chamar` porque este é o único ponto com multipart: definir
 * Content-Type à mão quebraria o limite que o navegador gera sozinho.
 */
export async function analisarRemessa(arquivo: File): Promise<Remessa> {
  const corpo = new FormData();
  corpo.append("arquivo", arquivo);

  const cabecalhos = new Headers();
  const token = lerToken();
  if (token) cabecalhos.set("Authorization", `Bearer ${token}`);

  let r: Response;
  try {
    r = await fetch("/api/importacoes/analisar", {
      method: "POST",
      body: corpo,
      headers: cabecalhos,
    });
  } catch {
    throw new ErroApi("Não foi possível enviar o arquivo.", 0);
  }

  const requisicaoId = r.headers.get("X-Request-Id") ?? undefined;
  if (!r.ok) {
    let detalhe = "Não foi possível ler a remessa.";
    try {
      const c = await r.json();
      if (typeof c?.detail === "string") detalhe = c.detail;
    } catch {
      /* resposta sem JSON */
    }
    throw new ErroApi(detalhe, r.status, requisicaoId);
  }
  return r.json();
}

export const criarEmpresa = (dados: {
  cnpj_raiz: string;
  cnpj_matriz: string;
  razao_social: string;
  uf: string;
  inscricao_estadual: string;
}) =>
  chamar<Empresa>("/empresas", {
    method: "POST",
    body: JSON.stringify(dados),
    headers: { "Content-Type": "application/json" },
  });

export const listarEmpresas = () => chamar<Empresa[]>("/empresas");

export const criarProjeto = (dados: {
  empresa_id: number;
  frente: Frente;
  nome: string;
  competencia_ini: string;
  competencia_fim: string;
  observacao: string | null;
}) =>
  chamar<Projeto>("/projetos", {
    method: "POST",
    body: JSON.stringify(dados),
    headers: { "Content-Type": "application/json" },
  });

export const listarProjetos = () => chamar<Projeto[]>("/projetos");

export const detalharProjeto = (id: number) =>
  chamar<ProjetoDetalhe>(`/projetos/${id}`);

export interface OQueSeraApagado {
  projeto: string;
  empresa: string;
  lotes: number;
  arquivos: number;
  execucoes: number;
}

/** O que some se confirmar. A confirmação precisa ser informada. */
export const previaDaExclusao = (id: number) =>
  chamar<OQueSeraApagado>(`/projetos/${id}/exclusao`);

/**
 * Apaga o trabalho. Pede a senha de novo de propósito: a sessão fica aberta a
 * jornada inteira, e uma tela deixada em máquina destravada não pode bastar
 * para desfazer meses de apuração.
 */
export const excluirProjeto = (id: number, senha: string) =>
  chamar<OQueSeraApagado>(`/projetos/${id}`, {
    method: "DELETE",
    body: JSON.stringify({ senha }),
    headers: { "Content-Type": "application/json" },
  });

import type { Frente } from "@/constants/fronts";
import { chamar, lerToken } from "./api";
import { ErroApi } from "@/types/erro";

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
  /** a que trabalho cada tipo de arquivo serve — informação, não alerta */
  observacoes: string[];
  /** chaves dos módulos que têm o que ler nesta remessa */
  modulos_atendidos: string[];
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
  /** o tributo do trabalho: decide as etapas e o que a base precisa trazer */
  modulo: string;
  modulo_rotulo: string;
  nome: string;
  competencia_ini: string;
  competencia_fim: string;
  status: string;
  status_rotulo: string;
  pre_cadastro: boolean;
  etapas_feitas: number;
  etapas_totais: number;
  /** quem criou não muda nunca; quem responde muda a cada sucessão */
  criado_por: string | null;
  criado_por_id: number | null;
  responsavel: string | null;
  responsavel_id: number | null;
  comentarios: number;
  /** como o cupom entra no razão: "enquadramento_1" (o manual) ou "demais_saidas" (como a empresa 17) */
  venda_a_consumidor: string;
  venda_a_consumidor_rotulo: string;
}

export interface Etapa {
  chave: string;
  nome: string;
  /** o rótulo da barra do trabalho: "Arquivos", "Quebras", "Apuração" */
  nome_curto: string;
  descricao: string;
  situacao: string;
  situacao_rotulo: string;
  implementada: boolean;
  acessivel: boolean;
}

/** De quando é a base importada; `fora_do_periodo` são as EFD fora do período do cadastro. */
export interface BaseDoTrabalho {
  efds: number;
  primeira: string | null;
  ultima: string | null;
  fora_do_periodo: number;
}

/**
 * Uma frente de trabalho do módulo — a CAT 42, o crédito outorgado, a quebra
 * de XML —, com as chaves das etapas que cabem dentro dela.
 *
 * É o card que a tela do trabalho abre. Quem diz quais são, e em que ordem, é
 * o servidor (`Etapas.TrilhasPorModulo`): repetir a lista aqui daria duas
 * fontes para a mesma verdade, e um dia a tela ofereceria uma frente que o
 * servidor não conhece.
 */
export interface Trilha {
  chave: string;
  rotulo: string;
  /** o quadrado do card, como no hub: "C42", "OUT" */
  sigla: string;
  descricao: string;
  /** chaves de `Etapa`, na ordem da frente */
  etapas: string[];
  feitas: number;
  totais: number;
  /** falso quando nenhuma etapa própria da frente foi construída ainda */
  construida: boolean;
}

export interface ProjetoDetalhe {
  projeto: Projeto;
  etapas: Etapa[];
  base?: BaseDoTrabalho;
  /** vazio no módulo que ainda não tem frente construída */
  trilhas?: Trilha[];
}

/**
 * Envia a remessa.
 *
 * Não usa `chamar` porque este é o único ponto com multipart: definir
 * Content-Type à mão quebraria o limite que o navegador gera sozinho.
 *
 * Aceita `sinal` porque é envio longo — SPED de uma empresa grande passa de
 * um GB — e cancelar aqui desfaz mesmo: a análise não grava nada, então
 * abortar não deixa meia empresa cadastrada.
 */
export async function analisarRemessa(
  arquivo: File,
  sinal?: AbortSignal,
): Promise<Remessa> {
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
      signal: sinal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
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
  /**
   * O tributo — `icms`, `piscofins`, `irpj_csll`.
   *
   * Não se confunde com a frente: frente é o TIPO de trabalho (razão, de-para,
   * quebra de SPED), módulo é o TRIBUTO. É o módulo que decide o **roteiro de
   * etapas**: um trabalho de ICMS percorre as oito da CAT 42; um de PIS/COFINS,
   * a quebra de SPED e a apuração das contribuições.
   *
   * Omitir cai em `icms` no servidor, que é o que todo trabalho anterior a esta
   * coluna é. Foi o que aconteceu até aqui — e por isso nenhum trabalho chegava
   * às telas de PIS/COFINS.
   */
  modulo: string;
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

/** Os trabalhos que a pessoa enxerga. `modulo` recorta pela frente tributária;
 *  sem ele a lista sai inteira, como sempre saiu. */
export const listarProjetos = (modulo?: string) =>
  chamar<Projeto[]>(modulo ? `/projetos?modulo=${encodeURIComponent(modulo)}` : "/projetos");

export const detalharProjeto = (id: number) =>
  chamar<ProjetoDetalhe>(`/projetos/${id}`);

export interface OpcaoDeVendaAConsumidor {
  valor: string;
  rotulo: string;
  explicacao: string;
}

export const opcoesDeVendaAConsumidor = () =>
  chamar<OpcaoDeVendaAConsumidor[]>("/venda-a-consumidor");

/** Devolve o cartão do trabalho já com a escolha nova. */
/** Nome e período; o que não vier fica como está. A API grava o evento com o de e o para. */
export const alterarCadastro = (
  projetoId: number,
  cadastro: { nome?: string; competencia_ini?: string; competencia_fim?: string },
) =>
  chamar<Projeto>(`/projetos/${projetoId}/cadastro`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cadastro),
  });

export const definirVendaAConsumidor = (projetoId: number, valor: string) =>
  chamar<Projeto>(`/projetos/${projetoId}/venda-a-consumidor`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ valor }),
  });

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

import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao } from "./conferencia";

/**
 * A simulação da reforma tributária do consumo: IBS, CBS e Imposto Seletivo.
 *
 * A mesma etapa nos módulos CBS e IBS. Ela não apura um tributo: põe os cinco
 * — ICMS, PIS/COFINS, CBS, IBS e IS — sobre a mesma linha de venda, de 2025 a
 * 2033, com preço e volume constantes, e mede o que acontece com a margem.
 *
 * O motor manda os números já somados por ano e por visão. Os percentuais vêm
 * calculados sobre a soma — a tela nunca tira média de margem.
 */

export interface AnoDaSimulacao {
  ano: number;
  receita_bruta: number;
  icms: number;
  pis_cofins: number;
  ipi: number;
  cbs: number;
  ibs: number;
  receita_liquida: number;
  custo_de_compra: number;
  ipi_custo: number;
  seletivo: number;
  cmv: number;
  lucro_bruto: number;
  margem: number | null;
  creditos: number;
  valor_bruto_das_compras: number;
  a_recolher: number;
  carga: number | null;
  carga_com_seletivo: number | null;
  teste_destacado: number;
  /** quanto a receita teria de variar para preservar o lucro bruto do ano-base */
  variacao_teorica: number | null;
}

/** Uma chave de uma visão (grupo, UF, categoria do IS...) nos anos em destaque. */
export interface LinhaDaVisao {
  chave: string;
  rotulo: string;
  linhas: number;
  skus: number;
  receita_bruta: number;
  seletivo_pleno: number;
  anos: Record<
    string,
    { lucro_bruto: number; margem: number | null; carga: number | null; variacao_teorica: number | null }
  >;
}

export interface ResumoDaSimulacao {
  versao?: number;
  iniciada_por?: string;
  andamento?: { arquivos: number; linhas: number };
  cenario?: {
    nome: string;
    fator_seletivo: number;
    anos: { ano: number; cbs: number; ibs: number; fator_icms: number; observacao: string }[];
    grupos: { chave: string; rotulo: string; reducao: number; cclasstribs: string[] }[];
    seletivo: { chave: string; rotulo: string; aliquota: number; prefixos: string[] }[];
  };
  base?: {
    arquivos: number;
    arquivos_de_classificacao: number;
    linhas_lidas: number;
    linhas_consideradas: number;
    skus: number;
    itens_classificados: number;
    lojas: number;
    competencias: string[];
    receita_bruta: number;
    conflitos_de_cadastro: number;
  };
  /** linhas sem custo de compra: decisão de método */
  exclusoes?: { motivo: string; linhas: number; skus: number; receita_liquida: number }[];
  /** itens sem cadastro ou com cClassTrib sem grupo: deveria ser zero */
  pendencias?: { motivo: string; linhas: number; skus: number; receita_bruta: number; exemplos: string[] }[];
  por_ano?: AnoDaSimulacao[];
  por_grupo?: LinhaDaVisao[];
  por_uf?: LinhaDaVisao[];
  por_seletivo?: LinhaDaVisao[];
  por_capitulo?: LinhaDaVisao[];
  segundos?: number;
  log?: EntradaDoLog[];
}

export interface ExecucaoDaSimulacao extends Omit<Execucao, "resumo"> {
  resumo?: ResumoDaSimulacao | null;
}

export const iniciarSimulacao = (projetoId: number) =>
  chamar<ExecucaoDaSimulacao>(`/projetos/${projetoId}/simulacao-reforma`, { method: "POST" });

export const listarSimulacoes = (projetoId: number) =>
  chamar<ExecucaoDaSimulacao[]>(`/projetos/${projetoId}/simulacao-reforma`);

export const detalharSimulacao = (execucaoId: number) =>
  chamar<ExecucaoDaSimulacao>(`/simulacao-reforma/${execucaoId}`);

export const cancelarSimulacao = (execucaoId: number) =>
  chamar<ExecucaoDaSimulacao>(`/simulacao-reforma/${execucaoId}/cancelar`, { method: "POST" });

/** A planilha montada na rodada: premissas, DRE, trajetória e as visões. */
export const baixarSimulacao = (execucaoId: number, sinal?: AbortSignal) =>
  baixarArquivo(
    `/api/simulacao-reforma/${execucaoId}/planilhas/simulacao`,
    "simulacao_reforma.xlsx",
    sinal,
  );

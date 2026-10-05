import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import type { Execucao } from "./conferencia";

/**
 * Crédito de ICMS sobre o combustível queimado como insumo.
 *
 * Lê a EFD ICMS/IPI do lote direto: não depende da CAT 42 nem de etapa nenhuma
 * dela. A regra inteira vive no motor — o leitor acha as compras, o
 * classificador diz o que cada item é (a NCM manda, a descrição confirma) e a
 * apuração consulta as tabelas de ad rem, FCV e alíquota.
 *
 * ## O que esta tela mostra e as outras não
 *
 * **Quanto do total é estimativa.** A era da substituição tributária sai com a
 * base no valor do item, porque o arquivo do destinatário não traz a base do
 * ST — medido: zero em 5.234 linhas de CST 60/61. Um total com estimativa
 * dentro não se apresenta sem dizer quanto, e por isso `credito_estimado` vem
 * separado e não somado por dentro.
 *
 * **O que foi recusado, por motivo.** Competência sem ad rem conferida, mês em
 * que a alíquota virou no dia 15, compra que já veio com ICMS destacado. Nada
 * disso vira zero: vira linha fora do total, com o porquê. O motor manda a
 * contagem por motivo e **uma** frase de exemplo de cada — a frase completa
 * traz a competência dentro e não serve de agrupamento.
 *
 * **Quantas linhas pedem olho humano.** O classificador nunca recusa: emite
 * tudo com a confiança e o motivo, e marca o que precisa de revisão. Esse
 * número é o tamanho do trabalho que sobra para o analista.
 */

/** Uma recusa agrupada: quantas linhas caíram por um motivo, e um exemplo. */
export interface RecusaDoCombustivel {
  linhas: number;
  /** a frase inteira de uma das linhas, com competência e valores dentro */
  exemplo: string;
}

export interface ResumoDoCombustivel {
  versao?: number;
  iniciada_por?: string;
  arquivos_no_lote?: number;
  arquivos_lidos?: number;
  /** arquivos que repetiam estabelecimento e competência; o esperado num lote
   *  que aponta a pasta-mãe */
  ignorados_por_duplicidade?: number;
  ilegiveis?: number;
  /** itens de compra lidos — todos, não só os de combustível */
  linhas?: number;
  /** linhas de CST 61: a dimensão da tese, antes de qualquer conta */
  linhas_de_monofasico?: number;
  estabelecimentos?: number;
  competencias?: number;
  grupos?: number;
  /** Decimal em texto: o motor não manda número de dinheiro como float */
  credito?: string;
  credito_estimado?: string;
  linhas_recusadas?: number;
  a_revisar?: number;
  /** motivo curto -> quantas linhas */
  recusas?: Record<string, number>;
  /** motivo curto -> contagem e frase de exemplo */
  recusas_com_exemplo?: Record<string, RecusaDoCombustivel>;
  /** o intervalo das emissões: é ele que diz se prescrição é assunto */
  primeira_emissao?: string;
  ultima_emissao?: string;
  avisos?: number;
  segundos?: number;
  log?: EntradaDoLog[];
}

export interface ExecucaoDoCombustivel extends Omit<Execucao, "resumo"> {
  resumo?: ResumoDoCombustivel | null;
}

export const iniciarCombustivel = (projetoId: number) =>
  chamar<ExecucaoDoCombustivel>(`/projetos/${projetoId}/combustivel`, { method: "POST" });

export const listarCombustiveis = (projetoId: number) =>
  chamar<ExecucaoDoCombustivel[]>(`/projetos/${projetoId}/combustivel`);

export const detalharCombustivel = (execucaoId: number) =>
  chamar<ExecucaoDoCombustivel>(`/combustivel/${execucaoId}`);

export const cancelarCombustivel = (execucaoId: number) =>
  chamar<ExecucaoDoCombustivel>(`/combustivel/${execucaoId}/cancelar`, { method: "POST" });

/**
 * O rótulo de cada motivo de recusa, para a tela não mostrar a chave crua.
 *
 * O motor manda código curto porque a frase traz valores dentro e não serve de
 * agrupamento. A tradução é aqui, e **motivo que não estiver nesta tabela
 * aparece pela chave** — some seria pior: o total não fecharia e ninguém saberia
 * por quê.
 */
export const MOTIVOS_DE_RECUSA: Record<string, string> = {
  sem_classificacao: "Não deu para dizer o que o item é",
  fora_da_tese: "É de outra tese (lubrificante, etanol hidratado)",
  sem_competencia: "O arquivo não trouxe competência",
  sem_quantidade: "O item veio sem quantidade",
  sem_fator: "Falta o fator de conversão da embalagem",
  sem_valor_do_item: "O item veio sem valor",
  ad_rem_nao_conferida: "A ad rem daquele mês não está conferida no convênio",
  fcv_desconhecido: "Não há fator de correção de volume para a UF",
  aliquota_nao_conferida: "A alíquota interna daquele estado não está conferida",
  mes_partido: "A alíquota mudou no meio do mês",
  regime_incoerente: "O regime e a tabela discordam",
  cst_nao_e_do_regime: "O CST não é de monofásico nem de imposto retido",
  icms_ja_destacado: "O documento já destacou o ICMS: o crédito já foi tomado",
};

export const rotuloDoMotivo = (motivo: string) =>
  MOTIVOS_DE_RECUSA[motivo] ?? motivo;

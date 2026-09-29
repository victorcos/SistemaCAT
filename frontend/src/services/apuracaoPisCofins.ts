import type { EntradaDoLog } from "@/components/shared/Rodada";
import { chamar } from "./api";
import { baixarArquivo, type Execucao, type Formato } from "./conferencia";

/**
 * Apuração de PIS/COFINS: o par que se confronta.
 *
 * A **Consulta de Entradas (037)** e a **Consulta de Saídas (047)**, tiradas da
 * EFD-Contribuições, e o **razão contábil**, tirado da ECD. Onde o fiscal e o
 * contábil discordam é onde está o trabalho.
 *
 * Saiu de dentro da quebra de SPED em 23/09/2026. A quebra abre os arquivos;
 * esta confronta o fiscal com o contábil — e quem quer olhar um registro não
 * precisa esperar a 037 de um ano inteiro.
 *
 * As três últimas chamadas são a leitura do razão na tela, e ficam aqui porque
 * é desta execução que o `razao.parquet` sai.
 */

export interface ResumoDaApuracao {
  versao?: number;
  arquivos?: number;
  /** quantas EFD-Contribuições e quantas ECD entraram */
  contribuicoes?: number;
  ecd?: number;
  ilegiveis?: number;
  /** linhas das duas consultas e do razão contábil */
  entradas?: number;
  saidas?: number;
  linhas_do_razao?: number;
  /** quantas entradas vieram de cada ramo de documento */
  por_ramo?: Record<string, number>;
  /** e o mesmo do lado das saídas */
  por_ramo_das_saidas?: Record<string, number>;
  /** registros de saída que a 047 ainda não monta, e quantos apareceram */
  nao_cobertos?: Record<string, number>;
  estabelecimentos?: string[];
  competencias?: string[];
  avisos?: string[];
  iniciada_por?: string;
  segundos?: number;
  andamento?: { arquivos: number; entradas: number; saidas: number; razao: number };
  log?: EntradaDoLog[];
}

export interface ExecucaoDaApuracao extends Omit<Execucao, "resumo"> {
  resumo: ResumoDaApuracao | null;
}

/** As três planilhas: os dois lados do fiscal e o contábil. */
export type PlanilhaDaApuracao = "entradas" | "saidas" | "razao-contabil";

const NOME: Record<PlanilhaDaApuracao, string> = {
  entradas: "consulta_de_entradas",
  saidas: "consulta_de_saidas",
  "razao-contabil": "razao_contabil",
};

export const iniciarApuracao = (projetoId: number) =>
  chamar<ExecucaoDaApuracao>(`/projetos/${projetoId}/apuracao-piscofins`, { method: "POST" });

export const listarApuracoes = (projetoId: number) =>
  chamar<ExecucaoDaApuracao[]>(`/projetos/${projetoId}/apuracao-piscofins`);

export const detalharApuracao = (execucaoId: number) =>
  chamar<ExecucaoDaApuracao>(`/apuracao-piscofins/${execucaoId}`);

export const cancelarApuracao = (execucaoId: number) =>
  chamar<ExecucaoDaApuracao>(`/apuracao-piscofins/${execucaoId}/cancelar`, { method: "POST" });

/**
 * Baixa a planilha da apuração.
 *
 * `contas` só vale para o razão, e é o recorte que a tela do razão monta: as
 * contas marcadas. Vazio, vem o razão inteiro — que numa ECD de rede passa de
 * milhão de partidas. O servidor as recebe como `classificacoes`, que é o
 * canal genérico de recorte das planilhas (na conferência são as situações do
 * documento; no suportado, as fontes da cascata).
 */
export function baixarPlanilhaDaApuracao(
  execucaoId: number,
  qual: PlanilhaDaApuracao,
  formato: Formato,
  contas: string[] = [],
  sinal?: AbortSignal,
): Promise<void> {
  const p = new URLSearchParams();
  if (formato !== "xlsx") p.set("formato", formato);
  if (contas.length) p.set("classificacoes", contas.join(","));
  const filtro = p.toString() ? `?${p}` : "";
  // o nome diz que é recorte: dois arquivos na pasta de Downloads com o mesmo
  // nome e conteúdos diferentes é como se confere a conta errada
  const recorte = contas.length ? `_${contas.length}_contas` : "";
  return baixarArquivo(
    `/api/apuracao-piscofins/${execucaoId}/planilhas/${qual}${filtro}`,
    `${NOME[qual]}${recorte}.${formato}`,
    sinal,
  );
}

/* -------------------------------------------------------------------------
 * O razão contábil da ECD: escolher a conta, depois ver os lançamentos.
 *
 * Sai desta mesma execução — é o `razao.parquet` que ela deixou em disco —, mas não é download: a tela lê página a página, porque uma ECD de
 * rede passa de milhão de partidas e nenhuma delas cabe numa resposta.
 * ------------------------------------------------------------------------- */

export interface Pagina<T> {
  pagina: number;
  por_pagina: number;
  total: number;
  linhas: T[];
}

/** Uma conta no seletor: o que ela movimentou e o que sobrou. */
export interface ContaContabil {
  cnpj: string;
  conta: string;
  descricao: string;
  conta_referencial: string;
  lancamentos: number;
  /** em reais, como texto — Decimal não atravessa JSON sem perder casa */
  debitos: string;
  creditos: string;
  saldo: string;
  de: string;
  ate: string;
  /** em quantos arquivos de ECD esta conta aparece; > 1 quebra o saldo corrente */
  arquivos: number;
}

/** Uma partida do razão, com o lançamento que a contém e o saldo até ela. */
export interface LancamentoContabil {
  cnpj: string;
  conta: string;
  descricao: string;
  conta_referencial: string;
  competencia: string;
  data: string;
  numero: string;
  valor_do_lancamento: string;
  centro_de_custo: string;
  valor: string;
  /** "D" ou "C" */
  debito_ou_credito: string;
  historico: string;
  codigo_do_historico: string;
  participante: string;
  tipo: string;
  saldo: string;
  arquivo: string;
}

export interface PaginaDeLancamentos extends Pagina<LancamentoContabil> {
  cnpj: string;
  conta: string;
  descricao: string;
  conta_referencial: string;
  /** houve recorte de data ou busca: os totais são os do recorte, não os da conta */
  recortado: boolean;
  totais: { debitos: string; creditos: string; saldo: string };
}

export interface EstabelecimentoDoRazao {
  cnpj: string;
  contas: number;
  lancamentos: number;
  de: string;
  ate: string;
}

/** O recorte do seletor é sobre o saldo da conta. */
export type RecorteDeConta = "todas" | "devedoras" | "credoras" | "zeradas" | "com_movimento";

/** Um galho do plano referencial, com tudo que está pendurado abaixo dele. */
export interface GalhoDoPlano {
  /** o código da conta referencial, ou "sem-referencial" para as não mapeadas */
  codigo: string;
  contas: number;
  lancamentos: number;
  debitos: string;
  creditos: string;
  saldo: string;
}

export interface PaginaDeContas extends Pagina<ContaContabil> {
  /** os galhos filhos; vazio na busca e na lista chapada */
  nos: GalhoDoPlano[];
  pai: string;
}

/** O galho das contas que a ECD não mapeou a referencial nenhuma. */
export const SEM_REFERENCIAL = "sem-referencial";

/**
 * As contas do razão — chapadas, ou o galho da árvore do plano referencial.
 *
 * Com `arvore`, vêm os galhos filhos de `pai` e só as contas que param nele:
 * dez mil contas numa lista são cem páginas, e ninguém acha nada virando cem
 * páginas. Com `busca`, a árvore se desfaz — quem digita o nome quer a conta,
 * não o caminho até ela.
 */
export function contasDoRazaoContabil(
  execucaoId: number,
  filtro: {
    busca: string;
    cnpj: string;
    recorte: RecorteDeConta;
    pagina: number;
    porPagina: number;
    pai?: string | null;
    arvore?: boolean;
  },
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({ pagina: String(filtro.pagina), por_pagina: String(filtro.porPagina) });
  if (filtro.busca.trim()) p.set("busca", filtro.busca.trim());
  if (filtro.cnpj) p.set("cnpj", filtro.cnpj);
  if (filtro.recorte !== "todas") p.set("so", filtro.recorte);
  if (filtro.arvore) p.set("arvore", "true");
  if (filtro.pai) p.set("pai", filtro.pai);
  return chamar<PaginaDeContas>(`/apuracao-piscofins/${execucaoId}/contas?${p}`, { signal: sinal });
}

export function lancamentosDaConta(
  execucaoId: number,
  conta: { cnpj: string; conta: string },
  filtro: { busca: string; de: string; ate: string; pagina: number },
  sinal?: AbortSignal,
) {
  const p = new URLSearchParams({
    cnpj: conta.cnpj,
    conta: conta.conta,
    pagina: String(filtro.pagina),
    por_pagina: "100",
  });
  if (filtro.busca.trim()) p.set("busca", filtro.busca.trim());
  if (filtro.de) p.set("de", filtro.de);
  if (filtro.ate) p.set("ate", filtro.ate);
  return chamar<PaginaDeLancamentos>(`/apuracao-piscofins/${execucaoId}/lancamentos?${p}`, { signal: sinal });
}

export const estabelecimentosDoRazaoContabil = (execucaoId: number, sinal?: AbortSignal) =>
  chamar<{ linhas: EstabelecimentoDoRazao[] }>(`/apuracao-piscofins/${execucaoId}/estabelecimentos`, { signal: sinal });

/* -------------------------------------------------------------------------
 * A Consulta de Saídas (047) na tela: recortar primeiro, olhar depois.
 *
 * Mesma forma do razão contábil acima, e pela mesma razão: a 047 de cinco anos
 * de uma rede passa de sete milhões de linhas. Não cabe numa resposta, não abre
 * no Excel, e ninguém lê. A tela recorta antes de mostrar, e o download sai
 * recortado do mesmo jeito — quem está olhando uma competência quer aquela
 * competência no arquivo.
 * ------------------------------------------------------------------------- */

/** O recorte da tela. Tudo vazio é a 047 inteira. */
export interface RecorteDasSaidas {
  cnpjs: string[];
  competencias: string[];
  ramos: string[];
  cfops: string[];
  cst_pis: string[];
  busca: string;
}

export const RECORTE_DAS_SAIDAS_INTEIRO: RecorteDasSaidas = {
  cnpjs: [],
  competencias: [],
  ramos: [],
  cfops: [],
  cst_pis: [],
  busca: "",
};

export const quantosFiltrosNasSaidas = (r: RecorteDasSaidas) =>
  [r.cnpjs, r.competencias, r.ramos, r.cfops, r.cst_pis].filter((l) => l.length).length +
  (r.busca.trim() ? 1 : 0);

/** Um valor possível num filtro, com quantas linhas ele traz. */
export interface EscolhaDoFiltro {
  valor: string;
  linhas: number;
  /** o texto ao lado do código, quando há: a descrição do CFOP */
  rotulo?: string;
}

export interface FiltrosDasSaidas {
  cnpjs: EscolhaDoFiltro[];
  competencias: EscolhaDoFiltro[];
  ramos: EscolhaDoFiltro[];
  cfops: EscolhaDoFiltro[];
  cst_pis: EscolhaDoFiltro[];
  linhas_no_recorte: number;
  linhas_no_total: number;
  /** false quando há busca livre: o número acima ignora a busca, e a tela diz isso */
  busca_conta_no_resumo: boolean;
  totais: { valor: string; pis: string; cofins: string };
}

/** Uma linha da 047: as 53 colunas, todas como texto, como no relatório. */
export interface LinhaDaSaida {
  cnpj: string;
  periodo: string;
  registros: string;
  modelo: string;
  situacao: string;
  codigo_do_participante: string;
  cnpj_do_participante: string;
  cpf_do_participante: string;
  nome_do_participante: string;
  uf_origem_destino: string;
  numero_do_documento: string;
  serie: string;
  chave: string;
  data_do_documento: string;
  data_de_saida: string;
  valor_do_documento: string;
  desconto_do_documento: string;
  valor_da_mercadoria: string;
  frete: string;
  seguro: string;
  outras_despesas: string;
  numero_do_item: string;
  codigo_do_item: string;
  descricao_complementar: string;
  descricao_do_item: string;
  ncm: string;
  codigo_do_servico: string;
  codigo_de_barra: string;
  tipo_do_item: string;
  valor_do_item: string;
  quantidade: string;
  unidade: string;
  desconto_do_item: string;
  cfop: string;
  descricao_do_cfop: string;
  faturamento: string;
  natureza: string;
  icms: string;
  icms_st: string;
  ipi: string;
  cst_pis: string;
  base_do_pis: string;
  quantidade_base_do_pis: string;
  aliquota_do_pis: string;
  quantidade_aliquota_do_pis: string;
  pis: string;
  cst_cofins: string;
  base_da_cofins: string;
  quantidade_base_da_cofins: string;
  aliquota_da_cofins: string;
  quantidade_aliquota_da_cofins: string;
  cofins: string;
  conta_contabil: string;
}

export interface PaginaDasSaidas extends Pagina<LinhaDaSaida> {
  recortado: boolean;
  /** os totais são do recorte inteiro, não da página: total que muda ao virar
   *  a página não serve para conferir nada */
  totais: { valor: string; pis: string; cofins: string };
}

/** O recorte vira query: as listas separadas por vírgula. */
function comoQuery(recorte: RecorteDasSaidas): URLSearchParams {
  const p = new URLSearchParams();
  const listas: [string, string[]][] = [
    ["cnpjs", recorte.cnpjs],
    ["competencias", recorte.competencias],
    ["ramos", recorte.ramos],
    ["cfops", recorte.cfops],
    ["cst_pis", recorte.cst_pis],
  ];
  for (const [nome, valores] of listas) if (valores.length) p.set(nome, valores.join(","));
  if (recorte.busca.trim()) p.set("busca", recorte.busca.trim());
  return p;
}

export const filtrosDasSaidas = (
  execucaoId: number,
  recorte: RecorteDasSaidas,
  sinal?: AbortSignal,
) =>
  chamar<FiltrosDasSaidas>(
    `/apuracao-piscofins/${execucaoId}/saidas/filtros?${comoQuery(recorte)}`,
    { signal: sinal },
  );

export function linhasDasSaidas(
  execucaoId: number,
  recorte: RecorteDasSaidas,
  pagina: number,
  porPagina = 100,
  sinal?: AbortSignal,
) {
  const p = comoQuery(recorte);
  p.set("pagina", String(pagina));
  p.set("por_pagina", String(porPagina));
  return chamar<PaginaDasSaidas>(`/apuracao-piscofins/${execucaoId}/saidas?${p}`, { signal: sinal });
}

/**
 * Baixa a 047 recortada como a tela está mostrando.
 *
 * O nome carrega a marca do recorte para que dois downloads diferentes não se
 * confundam na pasta de Downloads — é o mesmo cuidado do razão.
 */
export function baixarSaidas(
  execucaoId: number,
  recorte: RecorteDasSaidas,
  formato: Formato,
  sinal?: AbortSignal,
): Promise<void> {
  const p = comoQuery(recorte);
  if (formato !== "xlsx") p.set("formato", formato);
  const quantos = quantosFiltrosNasSaidas(recorte);
  const marca = quantos ? `_${quantos}_filtro${quantos === 1 ? "" : "s"}` : "";
  return baixarArquivo(
    `/api/apuracao-piscofins/${execucaoId}/saidas/planilha?${p}`,
    `consulta_de_saidas${marca}.${formato}`,
    sinal,
  );
}

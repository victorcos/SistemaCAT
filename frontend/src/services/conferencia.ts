import { chamar, lerToken } from "./api";
import { ErroApi } from "@/types/erro";

/**
 * Conferência de documentos: EFD contra XML e relatório do cliente.
 *
 * A rodada não cabe numa requisição — são milhares de arquivos e dezenas de
 * gigabytes —, então a API devolve um identificador e a tela acompanha.
 */

export interface Fatia {
  rotulo: string;
  documentos: number;
  valor: string;
  codigo: string;
}

export interface ResumoDaConferencia {
  escriturados: number;
  conferidos: number;
  nao_escrituradas: number;
  sem_documento: number;
  sem_documento_cobravel: number;
  documentos_na_pasta: number;
  valor_conferido: string;
  valor_sem_documento: string;
  sem_chave_na_efd: number;
  cobertura: number;
  origens: string[];
  por_modelo: Fatia[];
  por_operacao: Fatia[];
  por_classificacao: Fatia[];
  avisos: string[];
  recusados: string[];
  /** O que andou desde a rodada anterior. Vazio na primeira. */
  comparou: boolean;
  pendencias_resolvidas: number;
  pendencias_que_permanecem: number;
  pendencias_novas: number;
  andou: string;
}

export interface Execucao {
  id: number;
  projeto_id: number;
  etapa: string;
  situacao: "na_fila" | "rodando" | "concluida" | "falhou";
  passo: string | null;
  fracao: number;
  arquivos_totais: number;
  arquivos_lidos: number;
  bytes_lidos: number;
  documentos: number;
  erro: string | null;
  iniciada_em: string;
  terminada_em: string | null;
  resumo: ResumoDaConferencia | null;
}

export const EM_CURSO = ["na_fila", "rodando"];

/** As três listas que a conferência exporta. */
export type Planilha = "nao-escrituradas" | "a-cobrar" | "conferidas";

export const iniciarConferencia = (projetoId: number) =>
  chamar<Execucao>(`/projetos/${projetoId}/conferencias`, { method: "POST" });

export const listarConferencias = (projetoId: number) =>
  chamar<Execucao[]>(`/projetos/${projetoId}/conferencias`);

export const detalharConferencia = (execucaoId: number) =>
  chamar<Execucao>(`/conferencias/${execucaoId}`);

/**
 * Baixa uma das três planilhas.
 *
 * Não dá para usar um link simples: a rota exige o token no cabeçalho, e
 * `<a href>` não manda cabeçalho. Então busca-se o conteúdo e monta-se o
 * download a partir dele.
 */
export async function baixarPlanilha(
  execucaoId: number,
  qual: Planilha,
  modelos: string[] = [],
  classificacoes: string[] = [],
): Promise<void> {
  const parametros = new URLSearchParams();
  if (modelos.length) parametros.set("modelos", modelos.join(","));
  if (classificacoes.length)
    parametros.set("classificacoes", classificacoes.join(","));
  const filtro = parametros.toString() ? `?${parametros}` : "";
  await baixarArquivo(
    `/api/conferencias/${execucaoId}/planilhas/${qual}${filtro}`,
    `${qual}.xlsx`,
  );
}

/**
 * Busca um arquivo autenticado e dispara o download no navegador.
 *
 * Serve a qualquer etapa que exporte planilha: a rota exige o token no
 * cabeçalho, e `<a href>` não manda cabeçalho.
 */
export async function baixarArquivo(
  endereco: string,
  nomePadrao: string,
): Promise<void> {
  const cabecalhos = new Headers();
  const token = lerToken();
  if (token) cabecalhos.set("Authorization", `Bearer ${token}`);

  let r: Response;
  try {
    r = await fetch(endereco, { headers: cabecalhos });
  } catch {
    throw new ErroApi("Não foi possível baixar a planilha.", 0);
  }

  const requisicaoId = r.headers.get("X-Request-Id") ?? undefined;
  if (!r.ok) {
    let detalhe = "Não foi possível gerar a planilha.";
    try {
      const corpo = await r.json();
      if (typeof corpo?.detail === "string") detalhe = corpo.detail;
    } catch {
      /* resposta sem JSON */
    }
    throw new ErroApi(detalhe, r.status, requisicaoId);
  }

  const conteudo = await r.blob();
  const url = URL.createObjectURL(conteudo);
  const link = document.createElement("a");
  link.href = url;
  link.download = nomeDoArquivo(r) ?? nomePadrao;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // o navegador precisa do endereço enquanto o download começa
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

function nomeDoArquivo(r: Response): string | null {
  const cabecalho = r.headers.get("Content-Disposition");
  const achado = cabecalho?.match(/filename="?([^";]+)"?/);
  return achado ? achado[1] : null;
}

/** Milhar com ponto, como se escreve em português. */

import {
  baixarPelaPastaPadrao,
  descartar,
  DownloadCancelado,
  escolherOndeSalvar,
  foiAbortado,
  gravarNoArquivo,
} from "@/lib/download";
import { ErroApi } from "@/types/erro";
import { chamar, lerToken } from "./api";

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
  /** Fora do confronto de propósito, e não por defeito: linha que não é
   *  documento. Opcional porque execução antiga não gravou o campo. */
  observacoes?: string[];
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

/** O nome que a janela de salvar sugere. Antes era a chave da rota
 *  ("a-cobrar.xlsx"), que não diz nada na pasta de quem baixou. */
const NOME_SUGERIDO: Record<Planilha, string> = {
  "nao-escrituradas": "notas_nao_escrituradas",
  "a-cobrar": "notas_a_cobrar",
  conferidas: "notas_conferidas",
};

export const iniciarConferencia = (projetoId: number) =>
  chamar<Execucao>(`/projetos/${projetoId}/conferencias`, { method: "POST" });

export const listarConferencias = (projetoId: number) =>
  chamar<Execucao[]>(`/projetos/${projetoId}/conferencias`);

export const detalharConferencia = (execucaoId: number) =>
  chamar<Execucao>(`/conferencias/${execucaoId}`);

/**
/**
 * Em que formato a lista sai.
 *
 * `xlsx` é para abrir e ler. `csv` é para carregar em outra ferramenta, e
 * para quando a lista passa do que o Excel aguenta — CSV não tem limite de
 * linha nem quebra em aba.
 */
export type Formato = "xlsx" | "csv";

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
  formato: Formato = "xlsx",
  sinal?: AbortSignal,
): Promise<void> {
  const parametros = new URLSearchParams();
  if (modelos.length) parametros.set("modelos", modelos.join(","));
  if (classificacoes.length)
    parametros.set("classificacoes", classificacoes.join(","));
  if (formato !== "xlsx") parametros.set("formato", formato);
  const filtro = parametros.toString() ? `?${parametros}` : "";
  await baixarArquivo(
    `/api/conferencias/${execucaoId}/planilhas/${qual}${filtro}`,
    `${NOME_SUGERIDO[qual]}.${formato}`,
    sinal,
  );
}

/**
 * Busca um arquivo autenticado e salva onde a pessoa escolher.
 *
 * Serve a qualquer etapa que exporte planilha: a rota exige o token no
 * cabeçalho, e `<a href>` não manda cabeçalho.
 *
 * **O seletor de pasta vem antes da busca.** O navegador só abre "salvar
 * como" enquanto a ativação do gesto do clique vale, e ela não sobrevive a
 * uma ida à rede. Perguntar depois de buscar faz o seletor ser recusado —
 * além de obrigar a segurar o arquivo em algum lugar enquanto se pergunta.
 *
 * Com o seletor, a resposta é canalizada da rede direto para o arquivo: a
 * memória usada não depende do tamanho do download, e um CSV de vários GB
 * passa a caber. Sem ele, cai no caminho antigo, que carrega tudo em memória
 * e entrega à pasta de downloads do navegador.
 */
export async function baixarArquivo(
  endereco: string,
  nomePadrao: string,
  sinal?: AbortSignal,
): Promise<void> {
  const destino = await escolherOndeSalvar(nomePadrao);

  const cabecalhos = new Headers();
  const token = lerToken();
  if (token) cabecalhos.set("Authorization", `Bearer ${token}`);

  let r: Response;
  try {
    r = await fetch(endereco, { headers: cabecalhos, signal: sinal });
  } catch (e) {
    if (destino) await descartar(destino);
    // cancelar no meio da busca não é falha de rede
    if (foiAbortado(e)) throw new DownloadCancelado();
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
    // o seletor já criou o arquivo ao confirmar o nome; sem isto ficaria um
    // arquivo de 0 byte com cara de planilha, que alguém tentaria abrir
    if (destino) await descartar(destino);
    throw new ErroApi(detalhe, r.status, requisicaoId);
  }

  if (destino) {
    try {
      await gravarNoArquivo(destino, r, sinal);
    } catch (e) {
      // cancelou no meio da gravação: o arquivo pela metade não serve a
      // ninguém, e deixá-lo no disco é o mesmo que entregar dado truncado
      if (e instanceof DownloadCancelado) await descartar(destino);
      throw e;
    }
    return;
  }
  baixarPelaPastaPadrao(await r.blob(), nomeDoArquivo(r) ?? nomePadrao);
}

function nomeDoArquivo(r: Response): string | null {
  const cabecalho = r.headers.get("Content-Disposition");
  const achado = cabecalho?.match(/filename="?([^";]+)"?/);
  return achado ? achado[1] : null;
}

/** Milhar com ponto, como se escreve em português. */

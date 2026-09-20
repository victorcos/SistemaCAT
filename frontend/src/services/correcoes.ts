import { chamar } from "./api";

/**
 * Correção à mão: o que uma pessoa muda no que o sistema calculou.
 *
 * O sistema lê documento fiscal, e documento fiscal vem errado — alíquota que o
 * 0200 não traz, enquadramento que nenhum CFOP decide, nota cancelada fora da
 * lista de canceladas, quantidade digitada errada no ERP. A correção destrava
 * esses casos **sem mexer no dado de origem**: o parquet do documento continua
 * como o documento é, e a correção fica ao lado, com autor, data e motivo.
 *
 * São duas portas e um só caminho de gravação: corrigir na tela, linha a linha,
 * ou subir a Ficha 3 editada no Excel. A planilha passa por
 * {@link conferirPlanilha}, que só **compara e devolve o antes e o depois**;
 * gravar é sempre {@link gravarCorrecoes}, depois de a pessoa ver o que muda.
 */

export type CampoDaCorrecao =
  | "aliquota"
  | "reducao_base"
  | "enquadramento"
  | "quantidade"
  | "valor_item"
  | "icms_suportado"
  | "excluida";

export type AlvoDaCorrecao = "mercadoria" | "linha";

/** Uma correção pedida: o que gravar. */
export interface Correcao {
  campo: CampoDaCorrecao;
  valor: string;
  motivo: string;
  cnpj?: string;
  codigo?: string;
  documento?: string;
  numero_item?: number | null;
  /** o que estava na tela quando a pessoa corrigiu: é o "antes" do histórico */
  valor_anterior?: string;
}

/** Uma correção já gravada, como a tela a lê. */
export interface CorrecaoGravada {
  id: number;
  campo: CampoDaCorrecao;
  rotulo: string;
  onde: string;
  cnpj: string;
  codigo: string;
  documento: string;
  numero_item: number | null;
  valor: string;
  valor_anterior: string;
  motivo: string;
  situacao: "ativa" | "desfeita";
  autor: string;
  criada_em: string;
  /** "Alíquota interna (mercadoria 4002): 18,0000 → 25,0000" */
  frase: string;
}

export interface CampoCorrigivel {
  campo: CampoDaCorrecao;
  rotulo: string;
  alvo: AlvoDaCorrecao;
}

/** Uma mudança que a planilha propõe. Ainda não gravada. */
export interface MudancaDaPlanilha {
  campo: CampoDaCorrecao;
  rotulo: string;
  alvo: AlvoDaCorrecao;
  onde: string;
  cnpj: string;
  codigo: string;
  documento: string;
  numero_item: number | null;
  de: string;
  para: string;
  motivo: string;
  frase: string;
  /** a coluna do leiaute que a pessoa editou */
  coluna: string;
  aba: string;
  linha_na_planilha: number;
  /** quantas linhas da ficha esta correção alcança — na mercadoria, todas as dela */
  linhas_atingidas: number;
}

export interface ProblemaDaPlanilha {
  aba: string;
  linha: number;
  campo?: string;
  rotulo?: string;
  mensagem: string;
}

export interface PlanilhaConferida {
  execucao_id: number;
  projeto_id: number;
  arquivo: string;
  correcoes: MudancaDaPlanilha[];
  erros: ProblemaDaPlanilha[];
  avisos: ProblemaDaPlanilha[];
  linhas_lidas: number;
  abas: string[];
  /** linhas com motivo escrito que não casaram com nenhuma linha da ficha */
  nao_achadas: number;
  total: number;
  total_de_erros: number;
  limite: number;
  truncado: boolean;
}

export const ROTULO_DO_CAMPO: Record<CampoDaCorrecao, string> = {
  aliquota: "Alíquota interna",
  reducao_base: "Redução de base (%)",
  enquadramento: "Enquadramento legal",
  quantidade: "Quantidade",
  valor_item: "Valor do item (base do ICMS)",
  icms_suportado: "ICMS suportado",
  excluida: "Fora da ficha",
};

export async function listarCorrecoes(
  projetoId: number,
  opcoes: { todas?: boolean } = {},
): Promise<{ correcoes: CorrecaoGravada[]; campos: CampoCorrigivel[] }> {
  const p = opcoes.todas ? "?todas=true" : "";
  return chamar<{ correcoes: CorrecaoGravada[]; campos: CampoCorrigivel[] }>(
    `/projetos/${projetoId}/correcoes${p}`,
  );
}

export async function gravarCorrecoes(projetoId: number, correcoes: Correcao[]): Promise<number> {
  const r = await chamar<{ gravadas: number }>(`/projetos/${projetoId}/correcoes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ correcoes }),
  });
  return r.gravadas;
}

export const desfazerCorrecao = (projetoId: number, correcaoId: number) =>
  chamar<CorrecaoGravada>(`/projetos/${projetoId}/correcoes/${correcaoId}`, { method: "DELETE" });

/**
 * Sobe a Ficha 3 editada e devolve o que ela muda. **Não grava nada.**
 *
 * O `Content-Type` não vai à mão de propósito: quem monta o multipart é o
 * navegador, e a fronteira tem de ser a que ele escolheu — escrevê-la aqui é
 * como o corpo chega truncado do outro lado.
 */
export function conferirPlanilha(
  execucaoId: number,
  arquivo: File,
  sinal?: AbortSignal,
): Promise<PlanilhaConferida> {
  const corpo = new FormData();
  corpo.append("arquivo", arquivo, arquivo.name);
  return chamar<PlanilhaConferida>(`/razao/${execucaoId}/correcoes/planilha`, {
    method: "POST",
    body: corpo,
    signal: sinal,
  });
}

/** A mudança da planilha como o POST de gravação a espera. */
export const comoCorrecao = (m: MudancaDaPlanilha): Correcao => ({
  campo: m.campo,
  valor: m.para,
  motivo: m.motivo,
  cnpj: m.cnpj,
  codigo: m.codigo,
  documento: m.documento,
  numero_item: m.numero_item,
  valor_anterior: m.de,
});

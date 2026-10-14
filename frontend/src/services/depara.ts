import { chamar } from "./api";

/**
 * De-para de códigos: o mesmo produto escriturado com outro código na compra,
 * no kit ou no marketplace. O sistema propõe a partir da movimentação; quem
 * escreve aprova ou recusa, e a decisão vale para a empresa.
 */

export type SituacaoDoPar = "pendente" | "aprovado" | "recusado";
export type MotivoDoPar = "gtin" | "sufixo" | "kit" | "descricao" | "cliente" | "analista";

export interface ParDoDePara {
  cnpj: string;
  origem: string;
  destino: string;
  /** quantidade na origem × fator = quantidade no destino */
  fator: string;
  motivos: MotivoDoPar[];
  confianca: "alta" | "media" | null;
  explicacao: string;
  /** falso quando o par veio de decisão (cliente, analista) e não de proposta */
  proposto: boolean;
  /**
   * v0.161: vale aprovado **pela prova** (GTIN ou sufixo), sem ninguém decidir.
   * Recusar grava a discordância, e a discordância vence.
   */
  automatico: boolean;
  situacao: SituacaoDoPar;
  decidido_por: string | null;
  decidido_em: string | null;
  destino_decidido: string | null;
  fator_decidido: string | null;
}

export interface CodigoSemPar {
  cnpj: string;
  codigo: string;
  descricao: string;
  ncm: string;
  saidas: string;
}

export interface DeParaDoTrabalho {
  movimentos_execucao_id: number;
  resumo: {
    pares: number;
    pendentes: number;
    aprovados: number;
    /** destes, os que valeram pela prova, sem ninguém decidir */
    automaticos: number;
    recusados: number;
    sem_par: number;
    /** códigos com saída e sem entrada: os que virariam ficha negativa */
    precisavam_de_par: number;
    /** destes, quantos já têm par — por proposta ou por decisão */
    resolvidos: number;
    estabelecimentos: number;
  };
  pares: ParDoDePara[];
  sem_par: CodigoSemPar[];
}

export interface Decisao {
  cnpj: string;
  origem: string;
  destino: string;
  fator: string;
  motivo: MotivoDoPar;
  situacao: "aprovado" | "recusado";
  confianca?: string | null;
  explicacao?: string | null;
}

export const ROTULO_DO_MOTIVO: Record<MotivoDoPar, string> = {
  gtin: "mesmo GTIN",
  sufixo: "código + sufixo",
  kit: "kit",
  descricao: "descrição e NCM",
  cliente: "informado pelo cliente",
  analista: "informado pelo analista",
};

export async function deparaDoTrabalho(projetoId: number): Promise<DeParaDoTrabalho> {
  return chamar<DeParaDoTrabalho>(`/projetos/${projetoId}/depara`);
}

/** Um código com que o sem par pode ser ligado, e por que ele subiu na lista. */
export interface CandidatoParaLigar {
  codigo: string;
  descricao: string;
  ncm: string;
  entradas: string;
  saidas: string;
  pontos: number;
  porques: string[];
}

export interface ParaLigar {
  origem: { codigo: string; descricao: string; ncm: string; entradas: string; saidas: string };
  candidatos: CandidatoParaLigar[];
  no_estabelecimento: number;
}

/**
 * Com que códigos este pode ser ligado — ordenados pelo provável.
 *
 * O motor **não propõe** aqui: `propor` só devolve o que prova, e esta lista
 * existe justamente para o que ficou de fora dela. Quem decide é quem olha, e
 * por isso cada candidato traz o porquê de ter subido.
 */
export async function candidatosParaLigar(
  projetoId: number,
  cnpj: string,
  origem: string,
  busca: string,
  sinal?: AbortSignal,
): Promise<ParaLigar> {
  const q = new URLSearchParams({ origem, cnpj, busca });
  return chamar<ParaLigar>(`/projetos/${projetoId}/depara/para-ligar?${q}`, { signal: sinal });
}

export async function decidirDePara(projetoId: number, decisoes: Decisao[]): Promise<number> {
  const r = await chamar<{ gravadas: number }>(`/projetos/${projetoId}/depara`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decisoes }),
  });
  return r.gravadas;
}

/** A decisão que aprova ou recusa um par como foi proposto. */
export function decisaoDoPar(p: ParDoDePara, situacao: "aprovado" | "recusado"): Decisao {
  return {
    cnpj: p.cnpj,
    origem: p.origem,
    destino: p.destino,
    fator: p.fator,
    motivo: p.motivos[0] ?? "analista",
    situacao,
    confianca: p.confianca,
    explicacao: p.explicacao,
  };
}

const SEPARADOR = ";";

/**
 * A planilha que vai ao cliente: os códigos com saída e sem origem, e duas
 * colunas para ele preencher — o código do mesmo produto e, se for kit, quantas
 * unidades. É o que a RVZ fez na empresa 04, com os códigos de marketplace.
 */
export function planilhaParaOCliente(semPar: CodigoSemPar[]): string {
  const cabecalho = ["CNPJ", "Código sem origem", "Descrição", "NCM", "Quantidade saída",
    "Código do mesmo produto (preencher)", "Unidades por item (se kit)"];
  const escapar = (v: string) => (/[;"\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const linhas = semPar.map((s) => [s.cnpj, s.codigo, s.descricao, s.ncm, s.saidas.replace(".", ","), "", ""]);
  return "﻿" + [cabecalho, ...linhas].map((l) => l.map(escapar).join(SEPARADOR)).join("\r\n") + "\r\n";
}

/** Lê a planilha preenchida (CSV com ;) e devolve as decisões do cliente. */
export function lerPlanilhaDoCliente(texto: string): { decisoes: Decisao[]; ignoradas: number } {
  const linhas = texto.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim());
  const decisoes: Decisao[] = [];
  let ignoradas = 0;
  for (const bruta of linhas.slice(1)) {
    const c = dividir(bruta);
    const [cnpj, origem, , , , destino, unidades] = c.map((x) => (x ?? "").trim());
    if (!origem || !destino || origem === destino) {
      ignoradas += 1;
      continue;
    }
    const fator = (unidades || "1").replace(",", ".");
    decisoes.push({ cnpj: cnpj ?? "", origem, destino, fator, motivo: "cliente", situacao: "aprovado" });
  }
  return { decisoes, ignoradas };
}

function dividir(linha: string): string[] {
  const campos: string[] = [];
  let atual = "";
  let aspas = false;
  for (let i = 0; i < linha.length; i++) {
    const ch = linha[i];
    if (aspas) {
      if (ch === '"' && linha[i + 1] === '"') {
        atual += '"';
        i++;
      } else if (ch === '"') aspas = false;
      else atual += ch;
    } else if (ch === '"') aspas = true;
    else if (ch === SEPARADOR) {
      campos.push(atual);
      atual = "";
    } else atual += ch;
  }
  campos.push(atual);
  return campos;
}

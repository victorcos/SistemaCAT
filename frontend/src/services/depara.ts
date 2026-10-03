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
    recusados: number;
    sem_par: number;
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
 * unidades. É o que a RVZ fez na empresa D, com os códigos de marketplace.
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

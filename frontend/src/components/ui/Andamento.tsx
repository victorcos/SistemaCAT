import { Barra, Secao } from "@/components/ui/Pagina";
import { numero, tamanho } from "@/lib/format";

/**
 * O andamento de uma execução longa.
 *
 * Só o que toda execução tem — passo, fração, arquivos, documentos, bytes.
 * Não recebe `Execucao` inteira de propósito: a da conferência e a dos
 * movimentos carregam resumos de tipos diferentes, e exigir um deles faria a
 * outra tela não compilar por um componente que nem olha o resumo.
 */
export interface EmAndamento {
  passo: string | null;
  fracao: number;
  arquivos_totais: number;
  arquivos_lidos: number;
  bytes_lidos: number;
  documentos: number;
}

export function Andamento({ e }: { e: EmAndamento }) {
  const pct = Math.round(e.fracao * 100);
  return (
    <Secao titulo={e.passo ?? "Processando"}>
      <p className="m-0 mt-1 text-[13px] text-texto-suave">
        {numero(e.arquivos_lidos)} de {numero(e.arquivos_totais)} arquivos ·{" "}
        {numero(e.documentos)} documentos · {tamanho(e.bytes_lidos)}
      </p>
      <Barra de={pct} para={100} className="mt-4" />
      <p className="m-0 mt-3 text-xs text-texto-fraco">
        Pode fechar esta tela. O processamento continua no servidor.
      </p>
    </Secao>
  );
}

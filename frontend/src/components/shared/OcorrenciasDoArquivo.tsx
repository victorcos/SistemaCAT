import { useEffect, useState, type ReactNode } from "react";
import { Aviso } from "@/components/ui/Aviso";
import { useAcao } from "@/hooks/useAcao";
import { cn } from "@/lib/cn";
import { numero } from "@/lib/format";
import type { Pagina } from "@/services/apuracao";
import type { Ocorrencia } from "@/services/arquivoDigital";

/**
 * O que a pré-validação achou num arquivo digital.
 *
 * Serve às duas telas que pré-validam — a do arquivo que o sistema gerou e a
 * do que o cliente já transmitiu. A leitura é a mesma, e duas cópias
 * divergiriam na primeira correção.
 */
export function OcorrenciasDoArquivo({
  chave,
  carregar,
  cabecalho,
}: {
  /** muda quando é outro arquivo: é o que refaz a leitura */
  chave: string;
  carregar: (sinal: AbortSignal) => Promise<Pagina<Ocorrencia>>;
  cabecalho?: ReactNode;
}) {
  const [dados, setDados] = useState<Pagina<Ocorrencia> | null>(null);
  const leitura = useAcao();
  const { executar } = leitura;

  useEffect(() => {
    let vivo = true;
    executar(carregar).then((r) => {
      if (vivo && r) setDados(r);
    });
    return () => {
      vivo = false;
    };
    // `carregar` é recriada a cada render de quem chama; a chave é o que importa
  }, [chave, executar]);

  return (
    <div className="border-t border-borda-sutil bg-superficie-alt px-5.5 py-4">
      {cabecalho}
      {leitura.erro && <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />}
      {dados && dados.total === 0 && (
        <p className="m-0 mt-3 text-xs text-sucesso">A pré-validação não achou nada neste arquivo.</p>
      )}
      {dados && dados.total > 0 && (
        <div className="mt-3 flex flex-col">
          {dados.linhas.map((o, i) => (
            <div key={`${o.regra}-${o.linha}-${i}`} className="flex flex-wrap gap-3 border-t border-borda-sutil py-2 text-xs">
              <span className={cn("w-[48px] font-bold", o.severidade === "erro" ? "text-erro" : "text-atencao")}>
                {o.severidade}
              </span>
              <code className="w-[90px] font-mono text-texto-fraco">
                {o.linha ? `linha ${numero(o.linha)}` : "arquivo"}
              </code>
              <span className="min-w-[260px] flex-1 text-texto [text-wrap:pretty]">{o.mensagem}</span>
              <span className="text-texto-fraco">{o.rotulo}</span>
            </div>
          ))}
          {dados.total > dados.linhas.length && (
            <p className="m-0 mt-2 text-[11px] text-texto-fraco">
              Mostrando {numero(dados.linhas.length)} de {numero(dados.total)} exemplos guardados. A planilha de
              ocorrências traz todos.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Ligar um código sem par a outro, olhando para os dois.
 *
 * **O que isto substitui.** A tela pedia o código de destino num campo de
 * texto: sem busca, sem a descrição do outro lado, e sem alcançar o código que
 * só tem entrada — que é justamente o par que falta. Quem ligava precisava
 * saber o código de cor, e a RVZ fez isso na mão numa planilha à parte.
 *
 * O motor ordena os prováveis e diz **por que** cada um subiu. Ele não propõe:
 * `propor` só devolve o que prova, e esta lista existe para o que ficou de
 * fora dela. A decisão continua sendo de quem olha — por isso o porquê aparece
 * em cada linha, e não um palpite sem explicação.
 */

import { useEffect, useRef, useState } from "react";

import { Botao } from "@/components/ui/Botao";
import { Busca } from "@/components/ui/Filtros";
import { comoErro } from "@/lib/errors";
import { numero } from "@/lib/format";
import { candidatosParaLigar, type CandidatoParaLigar, type ParaLigar } from "@/services/depara";

interface Props {
  projetoId: number;
  cnpj: string;
  origem: string;
  descricao: string;
  /** o fator que o pai mantém: quantas unidades do destino cabem numa da origem */
  fator: string;
  aoMudarFator: (fator: string) => void;
  aoLigar: (destino: string, fator: string) => void;
  gravando: boolean;
  aoFechar: () => void;
}

export function LigarCodigo({
  projetoId, cnpj, origem, descricao, fator, aoMudarFator, aoLigar, gravando, aoFechar,
}: Props) {
  const [busca, setBusca] = useState("");
  const [dados, setDados] = useState<ParaLigar | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [escolhido, setEscolhido] = useState<CandidatoParaLigar | null>(null);
  const ultima = useRef<AbortController | null>(null);

  useEffect(() => {
    // cada tecla cancela a busca anterior: sem isso, a resposta lenta de uma
    // busca antiga chega depois e sobrescreve a nova
    ultima.current?.abort();
    const controle = new AbortController();
    ultima.current = controle;
    const esperar = setTimeout(() => {
      setCarregando(true);
      candidatosParaLigar(projetoId, cnpj, origem, busca, controle.signal)
        .then((d) => {
          setDados(d);
          setErro(null);
        })
        .catch((e) => {
          if (controle.signal.aborted) return;
          setErro(comoErro(e).message);
        })
        .finally(() => {
          if (!controle.signal.aborted) setCarregando(false);
        });
    }, 250);
    return () => {
      clearTimeout(esperar);
      controle.abort();
    };
  }, [projetoId, cnpj, origem, busca]);

  return (
    <div className="rounded-lg border border-borda bg-superficie p-3">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-suave">Ligando este código</p>
          <p className="font-mono text-sm">{origem}</p>
          <p className="truncate text-xs text-suave">{descricao}</p>
        </div>
        <Botao tamanho="sm" variante="fantasma" onClick={aoFechar}>
          Fechar
        </Botao>
      </div>

      <Busca
        valor={busca}
        aoMudar={setBusca}
        placeholder="Buscar por descrição ou código (ex.: cast esc, 4450)"
      />

      {erro && <p className="mt-2 text-xs text-erro">{erro}</p>}

      {!erro && (
        <div className="mt-3 max-h-72 overflow-y-auto">
          {carregando && !dados && <p className="text-xs text-suave">Procurando…</p>}
          {dados && dados.candidatos.length === 0 && (
            <p className="text-xs text-suave">
              {busca
                ? `Nenhum código casa com "${busca}" nos ${numero(dados.no_estabelecimento)} do estabelecimento.`
                : "Nenhum código parecido. Busque pelo nome ou pelo código."}
            </p>
          )}
          {dados?.candidatos.map((c) => {
            const marcado = escolhido?.codigo === c.codigo;
            return (
              <button
                key={c.codigo}
                type="button"
                onClick={() => setEscolhido(c)}
                aria-pressed={marcado}
                className={`mb-1 w-full rounded border px-2 py-1.5 text-left ${
                  marcado ? "border-acento bg-acento/10" : "border-transparent hover:border-borda"
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-xs">{c.codigo}</span>
                  <span className="shrink-0 text-xs text-suave">
                    {numero(Number(c.entradas))} entradas · {numero(Number(c.saidas))} saídas
                  </span>
                </div>
                <div className="truncate text-xs">{c.descricao || "(sem descrição)"}</div>
                <div className="truncate text-xs text-suave">{c.porques.join("; ")}</div>
              </button>
            );
          })}
        </div>
      )}

      {escolhido && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-borda pt-3">
          <span className="text-xs text-suave">É o mesmo produto que</span>
          <span className="font-mono text-xs">{escolhido.codigo}</span>
          <label className="text-xs text-suave">
            unidades por item
            <input
              aria-label="Unidades por item"
              title="Unidades por item, se for kit"
              className="ml-1 w-14 rounded border border-borda px-2 py-1 font-mono text-xs"
              value={fator}
              onChange={(e) => aoMudarFator(e.target.value)}
            />
          </label>
          <Botao
            tamanho="sm"
            disabled={gravando}
            onClick={() => aoLigar(escolhido.codigo, fator)}
          >
            Ligar
          </Botao>
        </div>
      )}
    </div>
  );
}

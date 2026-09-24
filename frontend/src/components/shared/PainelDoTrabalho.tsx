import { useEffect, useState } from "react";
import { CardDeFuncionalidade } from "@/components/shared/CardDeFuncionalidade";
import { numero } from "@/lib/format";
import type { Etapa } from "@/services/importacao";
import { listarLotes, type Contagem } from "@/services/lote";

/**
 * O painel do trabalho: o que há para ler, e o que dá para fazer.
 *
 * Duas faixas. Em cima, **os leiautes da base** — EFD-Contribuições, ECD, ECF,
 * cada um com quantos arquivos o trabalho tem. Embaixo, **as funcionalidades**,
 * em cards, na mesma linguagem do hub de tributos.
 *
 * Substituiu a lista numerada de etapas em PIS/COFINS (23/09/2026) e **em todo
 * módulo** desde 24/09/2026. A lista dizia que o trabalho é uma fila — "1.
 * Importar, 2. Quebrar, 3. Apurar" — e isso deixou de valer também no ICMS: o
 * crédito outorgado lê os XML do lote direto e não espera etapa nenhuma, como
 * o resto do módulo um dia também não esperará.
 *
 * **A ordem não se perdeu com a numeração.** Ela é a ordem dos cards, que é a
 * do servidor (`Etapas.Roteiros`), e a dependência real — sem movimentos não há
 * razão — continua dita em cada descrição e cobrada por quem pode cobrá-la: o
 * servidor, com a frase que explica o que falta.
 *
 * **Os leiautes vêm do servidor.** Rótulo, tipo e se aquilo alimenta este
 * trabalho são decisão do motor (`TipoDeArquivo.modulos`), que a API espelha.
 * Repetir a regra aqui daria duas fontes para a mesma verdade — e um dia a tela
 * anunciaria uma ECF que o trabalho não lê.
 */

export function PainelDoTrabalho({
  projetoId,
  etapas,
  rota,
  bloqueio,
}: {
  projetoId: number;
  etapas: Etapa[];
  /** para onde cada chave leva; sem destino, o card fica morto com o motivo */
  rota: (chave: string) => string | null;
  /** trabalho parado: o motivo, que apaga todos os caminhos */
  bloqueio?: string;
}) {
  return (
    <div className="flex flex-col gap-4">
      <FaixaDeLeiautes projetoId={projetoId} />

      <section className="grid grid-cols-[repeat(auto-fit,minmax(288px,1fr))] gap-4">
        {etapas.map((e) => (
          <CardDeFuncionalidade
            key={e.chave}
            etapa={e}
            destino={destinoDe(e, rota, bloqueio)}
            motivo={motivoDe(e, bloqueio)}
          />
        ))}
      </section>
    </div>
  );
}

function destinoDe(e: Etapa, rota: (c: string) => string | null, bloqueio?: string): string | null {
  if (bloqueio || !e.implementada || !e.acessivel) return null;
  return rota(e.chave);
}

function motivoDe(e: Etapa, bloqueio?: string): string | undefined {
  if (!e.implementada) return "Ainda não construída";
  if (bloqueio) return bloqueio;
  if (!e.acessivel) return "Indisponível neste trabalho";
  return undefined;
}

/* ------------------------------------------------------------------ */

/**
 * Os leiautes da base, um chip cada.
 *
 * É enfeite no sentido estrito: se a chamada falhar, a faixa não aparece e o
 * painel continua inteiro. O que não pode falhar é conseguir abrir a
 * funcionalidade — e isso não depende daqui.
 */
function FaixaDeLeiautes({ projetoId }: { projetoId: number }) {
  const [leiautes, setLeiautes] = useState<Contagem[] | null>(null);

  useEffect(() => {
    let vivo = true;
    listarLotes(projetoId)
      .then((lotes) => vivo && setLeiautes(somar(lotes.flatMap((l) => l.contagens))))
      .catch(() => vivo && setLeiautes([]));
    return () => {
      vivo = false;
    };
  }, [projetoId]);

  if (leiautes === null || leiautes.length === 0) return null;

  const total = leiautes.reduce((s, c) => s + c.quantidade, 0);

  return (
    <section className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-cartao border border-borda bg-superficie-vidro px-5 py-4">
      <div className="min-w-[132px]">
        <p className="m-0 text-[10px] font-extrabold uppercase tracking-[0.14em] text-texto-fraco">
          A base do trabalho
        </p>
        <p className="m-0 mt-0.5 text-[13px] font-semibold text-texto-suave">
          {numero(total)} arquivo{total === 1 ? "" : "s"} que este trabalho lê
        </p>
      </div>

      <ul className="m-0 flex flex-1 list-none flex-wrap gap-2 p-0">
        {leiautes.map((c) => (
          <li
            key={c.tipo}
            className="flex items-baseline gap-2 rounded-full border border-borda px-3 py-1.5"
          >
            <span className="font-mono text-[15px] font-extrabold leading-none text-texto">
              {numero(c.quantidade)}
            </span>
            <span className="text-[12px] font-semibold text-texto-fraco">{c.rotulo}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Soma por tipo entre os lotes e fica só com o que alimenta este trabalho. */
function somar(contagens: Contagem[]): Contagem[] {
  const por_tipo = new Map<string, Contagem>();
  for (const c of contagens) {
    if (!c.alimenta) continue;
    const ja = por_tipo.get(c.tipo);
    if (ja) ja.quantidade += c.quantidade;
    else por_tipo.set(c.tipo, { ...c });
  }
  return [...por_tipo.values()].sort((a, b) => b.quantidade - a.quantidade);
}

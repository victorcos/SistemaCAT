import { useEffect, useState } from "react";
import { Chip } from "@/components/ui/Filtros";
import { corDoAssunto } from "@/constants/assuntos";
import { cn } from "@/lib/cn";
import { catalogoDeSegmentos, type Segmento } from "@/services/segmentos";
import { ENXERGA_TODOS_OS_SEGMENTOS } from "@/constants/roles";
import type { Papel } from "@/types/auth";

/**
 * Quais segmentos tributários cada pessoa enxerga — e quem decide isso.
 *
 * A API grava desde a v0.66.0 (`PUT /usuarios/:id/segmentos`) e nenhuma tela
 * chamava: o acesso existia e não havia como concedê-lo. Estas duas peças são
 * o que faltava.
 *
 * * **`PilulasDeSegmento`** — na lista, só para ver;
 * * **`ChipsDeSegmento`** — no formulário, para mudar.
 *
 * **O catálogo vem do servidor.** Repetir a lista em TypeScript daria duas
 * fontes para a mesma verdade, e um dia a tela ofereceria um segmento que a API
 * recusa.
 *
 * **Gestor e dev enxergam todos, sempre.** Não é uma escolha a fazer — é o que
 * o papel significa, e o servidor decide assim independentemente do que esteja
 * gravado. Os chips aparecem marcados e travados, com a razão no lugar em que
 * alguém procuraria: o próprio campo.
 */

/** O catálogo inteiro, buscado uma vez por montagem de tela. */
export function useCatalogoDeSegmentos(): Segmento[] {
  const [catalogo, setCatalogo] = useState<Segmento[]>([]);
  useEffect(() => {
    let vivo = true;
    catalogoDeSegmentos()
      .then((s) => vivo && setCatalogo(s))
      .catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, []);
  return catalogo;
}

export function PilulasDeSegmento({
  segmentos,
  catalogo,
  papel,
}: {
  segmentos: string[];
  catalogo: Segmento[];
  papel: Papel;
}) {
  // quem enxerga todos não tem lista que faça sentido: dizer "PIS/COFINS, ICMS,
  // IRPJ/CSLL" para um gestor é repetir o que o papel já diz
  if (ENXERGA_TODOS_OS_SEGMENTOS.includes(papel)) {
    return <span className="text-[12px] text-texto-fraco">todos</span>;
  }
  if (segmentos.length === 0) {
    return (
      <span
        className="rounded-full border border-atencao/40 bg-atencao-fundo px-2 py-0.5 text-[10px] font-extrabold text-atencao"
        title="Sem segmento liberado, esta pessoa entra e não vê trabalho nenhum."
      >
        nenhum
      </span>
    );
  }
  return (
    <span className="flex flex-wrap gap-1">
      {segmentos.map((chave) => (
        <span
          key={chave}
          className={cn(
            "whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-extrabold",
            corDoAssunto(chave).pilula,
          )}
        >
          {catalogo.find((s) => s.chave === chave)?.rotulo ?? chave}
        </span>
      ))}
    </span>
  );
}

export function ChipsDeSegmento({
  catalogo,
  escolhidos,
  aoMudar,
  papel,
}: {
  catalogo: Segmento[];
  escolhidos: string[];
  aoMudar: (chaves: string[]) => void;
  papel: Papel;
}) {
  const todos = ENXERGA_TODOS_OS_SEGMENTOS.includes(papel);

  return (
    <div className="flex flex-col gap-2">
      <div className={cn("flex flex-wrap gap-2", todos && "pointer-events-none opacity-70")}>
        {catalogo.map((s) => (
          <Chip
            key={s.chave}
            marcado={todos || escolhidos.includes(s.chave)}
            aoAlternar={() =>
              aoMudar(
                escolhidos.includes(s.chave)
                  ? escolhidos.filter((c) => c !== s.chave)
                  : [...escolhidos, s.chave],
              )
            }
          >
            {s.rotulo}
          </Chip>
        ))}
      </div>
      <p className="m-0 text-[11px] leading-relaxed text-texto-fraco">{dica(papel, escolhidos)}</p>
    </div>
  );
}

/**
 * O que a escolha faz, dito no momento de escolher.
 *
 * O efeito de liberar um segmento não é óbvio — ele decide **onde a pessoa cai
 * ao entrar**, e não só o que ela vê. Descobrir isso depois, porque alguém
 * reclamou que entrou numa tela inesperada, é caro.
 */
function dica(papel: Papel, escolhidos: string[]): string {
  if (ENXERGA_TODOS_OS_SEGMENTOS.includes(papel)) {
    return "Este papel enxerga todos os segmentos — não há o que liberar. Ao entrar, cai no painel com todos os cards.";
  }
  if (escolhidos.length === 0) {
    return "Sem nenhum segmento, a pessoa entra e não vê trabalho algum. Libere ao menos um.";
  }
  if (escolhidos.length === 1) {
    return "Com um segmento só, ela pula o painel e entra direto nele.";
  }
  return `Com ${escolhidos.length} segmentos, ela entra no painel e escolhe entre esses.`;
}

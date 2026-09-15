import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * As peças das telas de etapa que rodam no servidor e mostram o resultado em
 * cartões: faixa, rótulo, cartão, barra fina e o log da rodada.
 *
 * Nasceram na tela da etapa 4 e saíram dela quando a etapa 5 precisou das
 * mesmas. Duas cópias divergiriam na primeira correção.
 */

export interface EntradaDoLog {
  em: string;
  nivel: "info" | "aviso" | "erro";
  texto: string;
}

/* ------------------------------------------------------------------ */
/* formatação: número de tabela é monoespaçado e sem "R$"               */
/* ------------------------------------------------------------------ */

export const valor = (texto: string | number | undefined) =>
  Number(texto ?? 0).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export const pct = (fracao: number | undefined) =>
  `${((fracao ?? 0) * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`;

export const zero = (texto: string | undefined) => Number(texto ?? 0) === 0;

export const mesAno = (competencia: string) => {
  const [ano, mes] = competencia.split("-");
  return mes && ano ? `${mes}/${ano}` : competencia || "—";
};

export function quando(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("pt-BR")} às ${d.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

export function duracao(segundos: number): string {
  const m = Math.floor(segundos / 60);
  const s = Math.round(segundos % 60);
  return m ? `${m} min ${String(s).padStart(2, "0")} s` : `${s} s`;
}

/** Faixa neutra: informa sem acusar. */
export function Faixa({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="rounded-raio-g border border-borda-forte border-l-[3px] border-l-texto-fraco bg-superficie-alt px-4.5 py-3.5">
      <p className="m-0 text-[13px] font-extrabold text-texto">{titulo}</p>
      <p className="m-0 mt-1.5 text-[13px] leading-relaxed text-texto-suave">{children}</p>
    </section>
  );
}

export function Rotulo({ children }: { children: ReactNode }) {
  return (
    <p className="m-0 text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
      {children}
    </p>
  );
}

export function Cartao({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-cartao border border-borda bg-superficie p-6 shadow-cat", className)}>
      {children}
    </div>
  );
}

export function BarraFina({ fracao, classe, altura = "h-2" }: { fracao: number; classe: string; altura?: string }) {
  return (
    <div className={cn("overflow-hidden rounded-full bg-superficie-alt", altura)}>
      <div
        className={cn("h-full rounded-full transition-[width] duration-300", classe)}
        style={{ width: `${Math.max(0, Math.min(100, fracao * 100))}%` }}
      />
    </div>
  );
}

/** Nível que a tela mostra: início, fonte lida, aviso, fim. */
function nivelDoLog(e: EntradaDoLog, i: number, todos: EntradaDoLog[]): [string, string] {
  if (e.nivel === "erro") return ["erro", "text-erro"];
  if (e.nivel === "aviso") return ["aviso", "text-atencao"];
  if (i === 0) return ["início", "text-info"];
  if (i === todos.length - 1 && e.texto.startsWith("Concluída")) return ["fim", "text-texto-suave"];
  return ["info", "text-sucesso"];
}

export function ListaDoLog({ log, emCurso }: { log: EntradaDoLog[]; emCurso?: boolean }) {
  return (
    <div className="flex flex-col">
      {log.map((e, i) => {
        const [rotulo, classe] = nivelDoLog(e, i, log);
        return (
          <div key={`${e.em}-${i}`} className="flex gap-3.5 border-t border-borda-sutil py-2">
            <code className="w-[60px] shrink-0 font-mono text-xs text-texto-fraco">
              {new Date(e.em).toLocaleTimeString("pt-BR")}
            </code>
            <span className={cn("w-[90px] shrink-0 text-xs font-bold", classe)}>
              {emCurso && rotulo === "fim" ? "info" : rotulo}
            </span>
            <span className="flex-1 text-xs leading-relaxed text-texto-suave [text-wrap:pretty]">{e.texto}</span>
          </div>
        );
      })}
    </div>
  );
}


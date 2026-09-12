import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { IconeVoltar } from "@/constants/icons";
import { cn } from "@/lib/cn";
import { numero as formatarNumero } from "@/lib/format";

/**
 * As peças que todas as telas internas repetem.
 *
 * Estavam copiadas tela a tela: o cabeçalho com título e ação, a faixa de
 * métricas, o cartão de seção, o número grande. Cada cópia tinha uma medida
 * própria, e o resultado era um sistema que parecia sete sistemas.
 */

/** "← Trabalhos" no topo de uma tela de detalhe. */
export function Voltar({ para, children }: { para: string; children: ReactNode }) {
  return (
    <Link
      to={para}
      className="inline-flex w-fit items-center gap-1.5 text-[13px] font-semibold text-texto-suave no-underline hover:text-texto"
    >
      <IconeVoltar size={15} strokeWidth={2} aria-hidden />
      {children}
    </Link>
  );
}

interface PropsDeCabecalho {
  /** rótulo pequeno acima do título: "ADMINISTRAÇÃO", "ETAPA 2" */
  eyebrow?: string;
  titulo: ReactNode;
  sub?: ReactNode;
  /** botão à direita do título */
  acao?: ReactNode;
  /** aparece abaixo do texto: métricas, barra de progresso, meta */
  children?: ReactNode;
  className?: string;
}

/**
 * O cartão de cabeçalho de página.
 *
 * Traz os dois efeitos do redesenho: o brilho radial no canto e a faixa de
 * luz de 1px que atravessa o topo. Ambos em CSS puro e desligados por
 * `prefers-reduced-motion` (styles/animations.css).
 */
export function CabecalhoDePagina({
  eyebrow,
  titulo,
  sub,
  acao,
  children,
  className,
}: PropsDeCabecalho) {
  return (
    <section
      className={cn(
        "relative overflow-hidden rounded-cartao border border-borda bg-superficie p-6 shadow-cat",
        className,
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(420px_160px_at_8%_0%,color-mix(in_srgb,var(--marca-laranja)_16%,transparent),transparent_70%)]"
      />
      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-px overflow-hidden">
        <div className="h-full w-2/5 animate-brilho bg-[linear-gradient(90deg,transparent,var(--marca-laranja),transparent)]" />
      </div>

      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {eyebrow && (
            <p className="m-0 text-[11px] font-bold uppercase tracking-[0.18em] text-laranja-700 escuro:text-laranja-400">
              {eyebrow}
            </p>
          )}
          <h1 className="m-0 mt-1 text-[28px] font-extrabold leading-tight tracking-[-0.02em] text-texto">
            {titulo}
          </h1>
          {sub && (
            <p className="m-0 mt-2 max-w-[640px] text-sm leading-[1.55] text-texto-suave [text-wrap:pretty]">
              {sub}
            </p>
          )}
        </div>
        {acao}
      </div>

      {children && <div className="relative mt-5">{children}</div>}
    </section>
  );
}

export type TomDeMetrica = "neutro" | "info" | "sucesso" | "atencao" | "destaque";

const TONS_DE_METRICA: Record<TomDeMetrica, string> = {
  neutro: "",
  info: "border-info/20 bg-info-fundo [&>dt]:text-info",
  sucesso: "border-sucesso/20 bg-sucesso-fundo [&>dt]:text-sucesso",
  atencao: "border-atencao/20 bg-atencao-fundo [&>dt]:text-atencao",
  destaque:
    "border-laranja-500/25 bg-laranja-500/8 [&>dt]:text-laranja-700 escuro:[&>dt]:text-laranja-400",
};

/** A faixa de métricas. Sempre em <dl>: é rótulo e valor, não tabela. */
export function Metricas({ children }: { children: ReactNode }) {
  return (
    <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">{children}</dl>
  );
}

export function Metrica({
  rotulo,
  valor,
  nota,
  tom = "neutro",
}: {
  rotulo: string;
  valor: ReactNode;
  /** linha pequena sob o número: valor em reais, percentual, "de 8 etapas" */
  nota?: ReactNode;
  tom?: TomDeMetrica;
}) {
  return (
    <div
      className={cn(
        "rounded-raio-g border border-borda bg-superficie-vidro px-4 py-3.5",
        TONS_DE_METRICA[tom],
      )}
    >
      <dt className="text-[11px] font-bold uppercase tracking-[0.12em] text-texto-fraco">
        {rotulo}
      </dt>
      <dd className="m-0 mt-1 text-2xl font-extrabold tabular-nums text-texto">
        {typeof valor === "number" ? formatarNumero(valor) : valor}
      </dd>
      {nota && <dd className="m-0 mt-0.5 text-xs text-texto-fraco">{nota}</dd>}
    </div>
  );
}

/** Cartão de conteúdo com título e subtítulo. O corpo do sistema é feito destes. */
export function Secao({
  titulo,
  sub,
  acao,
  children,
  className,
  destaque,
}: {
  titulo?: ReactNode;
  sub?: ReactNode;
  acao?: ReactNode;
  children: ReactNode;
  className?: string;
  /** faixa laranja à esquerda: a seção que gera trabalho para o cliente */
  destaque?: boolean;
}) {
  return (
    <section
      className={cn(
        "rounded-cartao border border-borda bg-superficie p-6 shadow-cat",
        destaque && "border-l-[3px] border-l-marca-laranja",
        className,
      )}
    >
      {(titulo || acao) && (
        <div className="mb-1 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {titulo && <h2 className="m-0 text-lg font-extrabold text-texto">{titulo}</h2>}
            {sub && (
              <p className="m-0 mt-1.5 max-w-[680px] text-[13px] leading-[1.6] text-texto-suave [text-wrap:pretty]">
                {sub}
              </p>
            )}
          </div>
          {acao}
        </div>
      )}
      {children}
    </section>
  );
}

/** O número que responde à pergunta da seção, em tamanho de manchete. */
export function Numerao({
  children,
  tom,
  nota,
}: {
  children: ReactNode;
  tom?: "destaque";
  nota?: ReactNode;
}) {
  return (
    <div className="mt-4">
      <p
        className={cn(
          "m-0 text-[34px] font-extrabold leading-none tabular-nums",
          tom === "destaque" ? "text-laranja-700 escuro:text-laranja-400" : "text-texto",
        )}
      >
        {children}
      </p>
      {nota && <p className="m-0 mt-1.5 text-[13px] text-texto-fraco">{nota}</p>}
    </div>
  );
}

/** Barra de progresso. `de`/`para` em vez de percentual: o cálculo é sempre o
 *  mesmo e errá-lo dá barra passando de 100%. */
export function Barra({
  de,
  para,
  tom = "destaque",
  className,
}: {
  de: number;
  para: number;
  tom?: "destaque" | "sucesso";
  className?: string;
}) {
  const pct = para > 0 ? Math.min(100, Math.round((de / para) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-2 overflow-hidden rounded-full bg-superficie-alt", className)}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-500",
          tom === "sucesso" ? "bg-sucesso" : "bg-marca-laranja",
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/** Estado vazio: contorno tracejado, uma frase e, quando há, uma saída. */
export function Vazio({
  titulo,
  children,
  acao,
}: {
  titulo: ReactNode;
  children?: ReactNode;
  acao?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-cartao border border-dashed border-borda-forte px-6 py-14 text-center">
      <p className="m-0 text-[15px] font-bold text-texto-suave">{titulo}</p>
      {children && (
        <p className="m-0 max-w-[520px] text-[13px] leading-relaxed text-texto-fraco">{children}</p>
      )}
      {acao}
    </div>
  );
}

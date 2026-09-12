import type { ReactNode } from "react";
import { IconeBusca, IconeConfirma } from "@/constants/icons";
import { cn } from "@/lib/cn";
import { numero } from "@/lib/format";

/**
 * Busca, segmentado e chips — a barra que aparece sobre toda lista.
 *
 * Os três estavam reescritos em cada tela: `.modelo` na conferência, um
 * `<select>` no início, nada na de lotes. Aqui é um só, e o mesmo gesto
 * funciona em todas.
 */

export function Toolbar({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-borda px-4 py-4">
      {children}
    </div>
  );
}

export function Busca({
  valor,
  aoMudar,
  placeholder,
  className,
}: {
  valor: string;
  aoMudar: (v: string) => void;
  placeholder: string;
  className?: string;
}) {
  return (
    <div className={cn("relative min-w-[220px] max-w-[380px] flex-1", className)}>
      <IconeBusca
        size={13}
        strokeWidth={2}
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-texto-fraco"
        aria-hidden
      />
      <input
        type="search"
        value={valor}
        onChange={(e) => aoMudar(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className={cn(
          "w-full rounded-raio-g border border-borda-forte bg-superficie-vidro py-2.5 pl-8 pr-3.5",
          "text-[13px] text-texto placeholder:text-texto-fraco transition-colors",
          "focus:outline-none focus:border-laranja-500/55 focus:bg-laranja-500/6",
        )}
      />
    </div>
  );
}

/** Filtro de opção única. Um radiogroup de verdade: setas navegam. */
export function Segmentado<T extends string>({
  opcoes,
  valor,
  aoMudar,
  rotulo,
}: {
  opcoes: { chave: T; rotulo: string }[];
  valor: T;
  aoMudar: (v: T) => void;
  rotulo: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={rotulo}
      className="flex rounded-[11px] border border-borda bg-superficie-vidro p-1"
    >
      {opcoes.map((o) => {
        const ativo = o.chave === valor;
        return (
          <button
            key={o.chave}
            type="button"
            role="radio"
            aria-checked={ativo}
            onClick={() => aoMudar(o.chave)}
            className={cn(
              // sem preflight, o <button> vem com borda e fundo do navegador
              "cursor-pointer rounded-raio border-0 bg-transparent px-3.5 py-2 text-xs font-bold transition-colors",
              ativo
                ? "bg-laranja-500/16 text-laranja-800 escuro:text-laranja-300"
                : "text-texto-suave hover:text-texto",
            )}
          >
            {o.rotulo}
          </button>
        );
      })}
    </div>
  );
}

/** Contador à direita da toolbar: "1 usuário", "37 trabalhos". */
export function Contador({ quantos, singular, plural }: { quantos: number; singular: string; plural: string }) {
  return (
    <span className="ml-auto text-xs font-semibold text-texto-fraco">
      {quantos === 1 ? `1 ${singular}` : `${numero(quantos)} ${plural}`}
    </span>
  );
}

/** Grupo de chips com título e explicação. */
export function GrupoDeChips({
  titulo,
  explicacao,
  children,
}: {
  titulo: string;
  explicacao?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="mt-5">
      <p className="m-0 text-[11px] font-bold uppercase tracking-[0.12em] text-texto-fraco">
        {titulo}
      </p>
      {explicacao && (
        <p className="m-0 mt-1 max-w-[620px] text-xs leading-relaxed text-texto-fraco">
          {explicacao}
        </p>
      )}
      <div className="mt-2.5 flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

/**
 * Chip de filtro — caixa de seleção com cara de pílula.
 *
 * Um `<label>` com `<input type=checkbox>` escondido, e não uma div com
 * onClick: assim teclado, leitor de tela e o clique no rótulo funcionam de
 * graça.
 */
export function Chip({
  marcado,
  aoAlternar,
  children,
  contagem,
}: {
  marcado: boolean;
  aoAlternar: () => void;
  children: ReactNode;
  contagem?: ReactNode;
}) {
  return (
    <label
      className={cn(
        "inline-flex cursor-pointer select-none items-center gap-2.5 rounded-full border px-4 py-2.5",
        "text-[13px] transition-colors",
        marcado
          ? "border-laranja-500/45 bg-laranja-500/14 text-laranja-800 escuro:text-laranja-300 font-semibold"
          : "border-borda-forte bg-superficie-vidro text-texto hover:border-texto-fraco",
        "focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-borda-foco",
      )}
    >
      <input
        type="checkbox"
        checked={marcado}
        onChange={aoAlternar}
        className="sr-only"
      />
      <span
        aria-hidden
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border transition-colors",
          marcado ? "border-marca-laranja bg-marca-laranja text-acao-texto" : "border-texto-fraco",
        )}
      >
        {marcado && <IconeConfirma size={11} strokeWidth={3} />}
      </span>
      {children}
      {contagem !== undefined && (
        <span className="font-mono text-xs text-texto-fraco">{contagem}</span>
      )}
    </label>
  );
}

/** Pílula só de leitura: recorte que se mostra, não se filtra. */
export function Pilula({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-borda bg-superficie-vidro px-3.5 py-2 text-[13px] text-texto",
        className,
      )}
    >
      {children}
    </span>
  );
}

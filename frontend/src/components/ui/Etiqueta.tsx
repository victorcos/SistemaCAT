import type { ReactNode } from "react";
import { PAPEIS } from "@/constants/roles";
import { cn } from "@/lib/cn";
import type { Papel } from "@/types/auth";

export type TomDeEtiqueta =
  | "neutro"
  | "info"
  | "sucesso"
  | "atencao"
  | "erro"
  | "destaque";

const TONS: Record<TomDeEtiqueta, string> = {
  neutro: "text-cinza-700 bg-cinza-200",
  info: "text-azul-700 bg-azul-100",
  sucesso: "text-sucesso bg-sucesso-fundo",
  atencao: "text-atencao bg-atencao-fundo",
  erro: "text-erro bg-erro-fundo",
  destaque: "text-dourado-800 bg-dourado-200",
};

interface Props {
  tom?: TomDeEtiqueta;
  /** bolinha que pulsa à esquerda, para estado em curso */
  pulso?: boolean;
  children: ReactNode;
  className?: string;
  title?: string;
}

/** Pílula de estado. Substitui `.etiqueta--*` (Leiaute), `.pilula--*`
 *  (Usuarios) e `.selo--*` (Inicio), que faziam a mesma coisa três vezes. */
export function Etiqueta({
  tom = "neutro",
  pulso,
  children,
  className,
  title,
}: Props) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5",
        "text-[11px] font-bold tracking-[0.02em] whitespace-nowrap",
        TONS[tom],
        className,
      )}
    >
      {pulso && (
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current animate-pulso" />
      )}
      {children}
    </span>
  );
}

const TOM_DO_PAPEL: Record<Papel, TomDeEtiqueta> = {
  dev: "destaque",
  gestor: "info",
  analista: "sucesso",
  revisor: "atencao",
  leitura: "neutro",
};

/** A etiqueta de papel, com o rótulo e a ajuda vindos de constants/roles. */
export function EtiquetaDePapel({ papel }: { papel: Papel }) {
  return (
    <Etiqueta tom={TOM_DO_PAPEL[papel]} title={PAPEIS[papel].ajuda}>
      {PAPEIS[papel].rotulo}
    </Etiqueta>
  );
}

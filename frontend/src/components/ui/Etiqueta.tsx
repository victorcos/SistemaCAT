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

/** Cada tom é um par de tokens, e não uma cor da escala escrita à mão.
 *
 *  Três deles vinham da escala clara direto — `bg-cinza-200`, `bg-azul-100`,
 *  `bg-dourado-200` — e por isso não seguiam o tema: no escuro viravam chips
 *  claros, gritando no meio de uma tela preta. Os outros três já usavam token
 *  e sempre estiveram certos. */
const TONS: Record<TomDeEtiqueta, string> = {
  neutro: "text-etiqueta-neutra-texto bg-etiqueta-neutra-fundo",
  info: "text-info bg-info-fundo",
  sucesso: "text-sucesso bg-sucesso-fundo",
  atencao: "text-atencao bg-atencao-fundo",
  erro: "text-erro bg-erro-fundo",
  destaque: "text-etiqueta-destaque-texto bg-etiqueta-destaque-fundo",
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

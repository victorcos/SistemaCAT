import branco from "@/assets/bms-branco.png";
import marinho from "@/assets/bms-marinho.png";
import { cn } from "@/lib/cn";

/**
 * O logotipo, escolhendo a tinta pela superfície.
 *
 * Não existe SVG do logotipo no repositório — só PNG em alta (ver
 * docs/IDENTIDADE.md secao 7, que registra o vetor como pendência). Este
 * componente existe para que, no dia em que o vetor chegar, a troca seja num
 * arquivo e não em cinco telas.
 */
export function LogoBMS({
  sobre,
  className,
  alt = "BMS Consultoria Tributária",
}: {
  /** a cor da superfície onde o logotipo vai pousar */
  sobre: "escuro" | "claro";
  className?: string;
  alt?: string;
}) {
  return (
    <img
      src={sobre === "escuro" ? branco : marinho}
      alt={alt}
      className={cn("h-auto", className)}
    />
  );
}

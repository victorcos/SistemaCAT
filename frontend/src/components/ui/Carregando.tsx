import { IconeCarregando } from "@/constants/icons";
import { cn } from "@/lib/cn";

/** Estado de carregamento. Existe porque `.carregando` e `.pagina__carregando`
 *  eram usadas no JSX e nunca tiveram uma linha de CSS. */
export function Carregando({
  texto = "Carregando…",
  className,
}: {
  texto?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex items-center gap-2 p-6 text-sm text-texto-fraco",
        className,
      )}
    >
      <IconeCarregando size={16} className="animate-spin" aria-hidden />
      {texto}
    </div>
  );
}

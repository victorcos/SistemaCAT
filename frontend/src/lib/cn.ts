import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Junta classes e resolve conflito de utilitária do Tailwind.
 *
 * Sem o twMerge, `cn("p-2", "p-4")` deixa as duas no atributo e quem vence é
 * a ordem no CSS gerado, não a ordem aqui — o que torna impossível um
 * componente aceitar `className` de fora para ajustar o padrão. Com ele, a
 * última ganha, que é o que qualquer um espera.
 */
export const cn = (...classes: ClassValue[]) => twMerge(clsx(classes));

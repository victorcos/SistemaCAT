import type { ButtonHTMLAttributes } from "react";
import { IconeCarregando, type Icone } from "@/constants/icons";
import { cn } from "@/lib/cn";

export type TomDeBotaoIcone = "destaque" | "neutro" | "perigo" | "sucesso";

const TONS: Record<TomDeBotaoIcone, string> = {
  // laranja translúcido: a ação principal da linha (editar)
  destaque:
    "border-laranja-500/35 bg-laranja-500/12 text-laranja-700 escuro:text-laranja-300 " +
    "hover:not-disabled:border-laranja-500/65 hover:not-disabled:bg-laranja-500/22",
  // vidro: ação secundária (chave); ganha laranja no hover
  neutro:
    "border-borda-forte bg-superficie-vidro text-texto-suave " +
    "hover:not-disabled:border-laranja-500/45 hover:not-disabled:bg-laranja-500/14 " +
    "hover:not-disabled:text-laranja-700 escuro:hover:not-disabled:text-laranja-300",
  perigo:
    "border-erro/35 bg-transparent text-erro hover:not-disabled:bg-erro-fundo",
  sucesso:
    "border-sucesso/35 bg-transparent text-sucesso hover:not-disabled:bg-sucesso-fundo",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  icone: Icone;
  /** vira `title` e `aria-label`: botão só de ícone precisa de nome */
  rotulo: string;
  tom?: TomDeBotaoIcone;
  carregando?: boolean;
}

/**
 * Botão de 34×34 só com ícone, para ações de linha em tabela.
 *
 * Exige `rotulo` porque um ícone sozinho não tem nome para leitor de tela
 * nem dica para quem passa o mouse — e a spec pede os dois.
 */
export function BotaoIcone({
  icone: Ico,
  rotulo,
  tom = "neutro",
  carregando,
  className,
  disabled,
  ...resto
}: Props) {
  return (
    <button
      type="button"
      {...resto}
      title={rotulo}
      aria-label={rotulo}
      disabled={disabled || carregando}
      aria-busy={carregando || undefined}
      className={cn(
        "inline-flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[9px] border",
        "transition-all duration-150 hover:not-disabled:-translate-y-px",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-borda-foco",
        "disabled:cursor-not-allowed disabled:border-borda disabled:bg-transparent disabled:text-texto-fraco",
        TONS[tom],
        className,
      )}
    >
      {carregando ? (
        <IconeCarregando size={16} className="animate-spin" aria-hidden />
      ) : (
        <Ico size={16} strokeWidth={1.8} aria-hidden />
      )}
    </button>
  );
}

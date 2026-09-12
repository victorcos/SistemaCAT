import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { IconeCarregando, type Icone } from "@/constants/icons";
import { cn } from "@/lib/cn";

export type VarianteDeBotao = "principal" | "secundario" | "fantasma" | "perigo";

const VARIANTES: Record<VarianteDeBotao, string> = {
  // laranja da marca com texto marinho: 6,57:1. Branco sobre este laranja
  // daria 2,53:1 e reprovaria — ver docs/IDENTIDADE.md secao 2.
  principal:
    "bg-acao-fundo text-acao-texto hover:bg-acao-hover active:bg-acao-ativo " +
    "disabled:bg-acao-inativo-fundo disabled:text-acao-inativo-texto",
  secundario:
    "border border-acao2-borda text-acao2-texto hover:bg-acao2-hover " +
    "disabled:text-texto-fraco",
  fantasma: "text-acao2-texto hover:bg-acao2-hover disabled:text-texto-fraco",
  // Vermelho solido, nunca laranja da marca: a cor da marca e a de seguir em
  // frente, e apagar nao e seguir em frente.
  perigo:
    "bg-erro text-marca-branco hover:brightness-92 " +
    "disabled:bg-acao-inativo-fundo disabled:text-acao-inativo-texto",
};

const TAMANHOS = {
  sm: "px-3 py-1.5 text-xs gap-1.5",
  md: "px-4 py-2.5 text-[15px] gap-2",
} as const;

interface Base {
  variante?: VarianteDeBotao;
  tamanho?: keyof typeof TAMANHOS;
  carregando?: boolean;
  icone?: Icone;
  /** ocupa toda a largura disponível */
  largo?: boolean;
  children?: ReactNode;
  className?: string;
}

type PropsDeBotao = Base & ButtonHTMLAttributes<HTMLButtonElement>;
type PropsDeLink = Base & { para: string };

const base =
  "inline-flex items-center justify-center rounded-raio font-[650] " +
  "border border-transparent cursor-pointer transition-colors duration-150 " +
  "disabled:cursor-not-allowed " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-borda-foco";

function classes({
  variante = "principal",
  tamanho = "md",
  largo,
  className,
}: Base) {
  return cn(base, VARIANTES[variante], TAMANHOS[tamanho], largo && "w-full", className);
}

/**
 * O botão do sistema.
 *
 * Substitui `.botao` + `.botao--principal/--secundario/--perigo`, que estavam
 * definidos em pages/Login.css e pages/Usuarios.css e eram usados por 11 dos
 * 13 componentes.
 */
export function Botao({
  variante,
  tamanho = "md",
  carregando,
  icone: Ico,
  largo,
  className,
  children,
  disabled,
  ...resto
}: PropsDeBotao) {
  const tam = tamanho === "sm" ? 14 : 16;
  return (
    <button
      {...resto}
      disabled={disabled || carregando}
      aria-busy={carregando || undefined}
      className={classes({ variante, tamanho, largo, className })}
    >
      {carregando ? (
        <IconeCarregando size={tam} className="animate-spin" aria-hidden />
      ) : (
        Ico && <Ico size={tam} strokeWidth={2} aria-hidden />
      )}
      {children}
    </button>
  );
}

/** Mesma aparência, mas navega. Existe porque as telas usavam
 *  `<Link className="botao botao--principal">`, o que duplicava o estilo. */
export function BotaoLink({
  variante,
  tamanho = "md",
  icone: Ico,
  largo,
  className,
  children,
  para,
}: PropsDeLink) {
  return (
    <Link to={para} className={classes({ variante, tamanho, largo, className })}>
      {Ico && <Ico size={tamanho === "sm" ? 14 : 16} strokeWidth={2} aria-hidden />}
      {children}
    </Link>
  );
}

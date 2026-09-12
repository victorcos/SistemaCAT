import {
  forwardRef,
  useId,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import { IconeEsconder, IconeVer } from "@/constants/icons";
import { cn } from "@/lib/cn";

const entrada =
  "w-full rounded-raio border border-borda-forte bg-superficie px-3 py-2.5 " +
  "text-[15px] text-texto transition-[border-color,box-shadow] duration-150 " +
  "hover:not-disabled:border-texto-fraco " +
  "focus:outline-none focus:border-borda-foco " +
  "focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--borda-foco)_22%,transparent)] " +
  "disabled:bg-superficie-alt disabled:cursor-not-allowed";

interface PropsDeCampo {
  rotulo: string;
  /** texto de apoio sob o campo; vira aria-describedby */
  dica?: ReactNode;
  erro?: string;
  children: (props: { id: string; "aria-describedby"?: string }) => ReactNode;
}

/**
 * Rótulo + controle + dica, com os `id` e `aria-describedby` ligados.
 *
 * Substitui `.campo`, `.campo__rotulo` e `.campo__dica` — este último estava
 * definido duas vezes, em pages/Usuarios.css e pages/Lote.css, com
 * propriedades diferentes que se somavam na cascata.
 */
export function Campo({ rotulo, dica, erro, children }: PropsDeCampo) {
  const id = useId();
  const idApoio = dica || erro ? `${id}-apoio` : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-semibold text-texto-suave">
        {rotulo}
      </label>
      {children({ id, "aria-describedby": idApoio })}
      {(erro || dica) && (
        <p
          id={idApoio}
          className={cn(
            "text-xs leading-[1.45]",
            erro ? "text-erro" : "text-texto-fraco",
          )}
        >
          {erro || dica}
        </p>
      )}
    </div>
  );
}

// forwardRef porque o projeto e React 18: ali `ref` ainda nao passa como prop
// comum, e a tela de login precisa dar foco no primeiro campo ao abrir.
export const Entrada = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { mono?: boolean }
>(function Entrada({ className, mono, ...resto }, ref) {
  return (
    <input
      {...resto}
      ref={ref}
      className={cn(entrada, mono && "font-mono", className)}
    />
  );
});

/**
 * Campo de senha com botão de revelar.
 *
 * O botão é `type="button"` de propósito: dentro de um <form>, o padrão de
 * um <button> é submeter, e revelar a senha submeteria o login.
 */
export const CampoSenha = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(function CampoSenha({ className, ...resto }, ref) {
  const [visivel, setVisivel] = useState(false);
  const Ico = visivel ? IconeEsconder : IconeVer;
  return (
    <div className="relative flex">
      <input
        {...resto}
        ref={ref}
        type={visivel ? "text" : "password"}
        className={cn(entrada, "pr-11", className)}
      />
      <button
        type="button"
        onClick={() => setVisivel((v) => !v)}
        title={visivel ? "Esconder senha" : "Mostrar senha"}
        aria-label={visivel ? "Esconder senha" : "Mostrar senha"}
        aria-pressed={visivel}
        disabled={resto.disabled}
        className={
          "absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1.5 " +
          "text-acao2-texto hover:not-disabled:bg-acao2-hover " +
          "disabled:text-texto-fraco disabled:cursor-not-allowed"
        }
      >
        <Ico size={16} strokeWidth={2} aria-hidden />
      </button>
    </div>
  );
});

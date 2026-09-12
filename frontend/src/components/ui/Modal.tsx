import { useEffect, useRef, type ReactNode } from "react";
import { IconeFechar } from "@/constants/icons";
import { cn } from "@/lib/cn";

const TAMANHOS = {
  sm: "max-w-[440px]",
  md: "max-w-[640px]",
  lg: "max-w-[880px]",
} as const;

interface Props {
  aberto: boolean;
  aoFechar: () => void;
  titulo: ReactNode;
  sub?: ReactNode;
  tamanho?: keyof typeof TAMANHOS;
  rodape?: ReactNode;
  children: ReactNode;
}

/**
 * Diálogo sobre a tela.
 *
 * Usa o <dialog> nativo em vez de uma div com position:fixed — ele já traz de
 * graça o que costuma ser esquecido: foco preso dentro, Esc fechando, o resto
 * da página marcado como inerte para leitor de tela, e camada própria acima
 * de qualquer z-index.
 *
 * Sem `overflow: hidden` no cartão, de propósito: a spec pede combobox dentro
 * do modal, e overflow cortaria o painel do dropdown.
 */
export function Modal({
  aberto,
  aoFechar,
  titulo,
  sub,
  tamanho = "md",
  rodape,
  children,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (aberto && !d.open) d.showModal();
    if (!aberto && d.open) d.close();
  }, [aberto]);

  return (
    <dialog
      ref={ref}
      // o Esc do navegador dispara 'cancel'; sem isto o <dialog> fecharia
      // sozinho e o estado React continuaria dizendo que está aberto
      onCancel={(e) => {
        e.preventDefault();
        aoFechar();
      }}
      onClose={aoFechar}
      // clique no backdrop: o alvo é o próprio <dialog>, não o conteúdo
      onClick={(e) => {
        if (e.target === ref.current) aoFechar();
      }}
      className={cn(
        "m-auto w-[calc(100%-2.5rem)] bg-transparent p-0 text-texto",
        "backdrop:bg-[rgb(4_8_16/66%)] backdrop:backdrop-blur-[6px]",
        TAMANHOS[tamanho],
      )}
    >
      {aberto && (
        <div className="animate-entrada rounded-raio-g border border-borda bg-superficie-elevada shadow-cat-alta">
          <header className="flex items-start gap-4 border-b border-borda px-6 py-5">
            <div className="min-w-0 flex-1">
              <h2 className="m-0 text-xl font-extrabold">{titulo}</h2>
              {sub && <p className="m-0 mt-1 text-[13px] text-texto-suave">{sub}</p>}
            </div>
            <button
              type="button"
              onClick={aoFechar}
              title="Fechar"
              aria-label="Fechar"
              className="-mr-1.5 h-8 w-8 shrink-0 rounded-raio text-texto-suave hover:bg-acao2-hover"
            >
              <IconeFechar size={17} strokeWidth={2} className="mx-auto" aria-hidden />
            </button>
          </header>

          <div className="px-6 py-6">{children}</div>

          {rodape && (
            <footer className="flex items-center justify-end gap-2.5 border-t border-borda px-6 py-4">
              {rodape}
            </footer>
          )}
        </div>
      )}
    </dialog>
  );
}

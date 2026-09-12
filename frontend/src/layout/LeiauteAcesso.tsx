import type { ReactNode } from "react";
import { LogoBMS } from "@/components/ui/LogoBMS";

/**
 * A moldura das telas de acesso (login e troca de senha).
 *
 * Metade marinho com o logotipo, metade formulário. Em tela estreita o lado
 * da marca some e o logotipo entra acima do formulário — em celular, metade
 * da tela ocupada por identidade tira espaço do que importa.
 */
export function LeiauteAcesso({
  titulo,
  sub,
  rodape,
  children,
}: {
  titulo: string;
  sub?: ReactNode;
  rodape?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="grid min-h-screen grid-cols-1 md:grid-cols-2">
      {/* a linha dourada na borda vem da propria marca */}
      <aside
        aria-hidden
        className="hidden flex-col items-center justify-center gap-6 border-r-[3px] border-marca-dourado bg-marca-azul p-12 md:flex"
      >
        <LogoBMS sobre="escuro" alt="" className="w-[min(340px,70%)]" />
        <p className="m-0 max-w-[30ch] text-center text-[15px] leading-relaxed text-moldura-texto-suave">
          Sistema de apuração das obrigações da CAT
        </p>
      </aside>

      <main className="flex flex-col items-center justify-center gap-8 bg-fundo px-6 py-12">
        <div className="flex w-full max-w-[380px] flex-col gap-4">
          <LogoBMS sobre="claro" className="mx-auto mb-2 w-[190px] md:hidden" />
          <h1 className="m-0 text-[26px] font-[650] tracking-[-0.01em]">
            {titulo}
          </h1>
          {sub && <p className="m-0 -mt-2 text-sm text-texto-suave">{sub}</p>}
          {children}
        </div>
        {rodape}
        <footer className="text-xs text-texto-fraco">
          BMS Consultoria Tributária · Sistema CAT
        </footer>
      </main>
    </div>
  );
}

import type { ReactNode } from "react";
import { LogoBMS } from "@/components/ui/LogoBMS";

/**
 * A moldura das telas de acesso (login e troca de senha).
 *
 * Metade marinho com o logotipo, metade formulário. Em tela estreita o lado
 * da marca some e o logotipo entra acima do formulário — em celular, metade
 * da tela ocupada por identidade tira espaço do que importa.
 *
 * O painel da marca tem os dois efeitos que a spec pede, ambos em CSS e
 * ambos `aria-hidden`: um halo laranja que deriva devagar e uma grade de
 * 56px esmaecida nas bordas por máscara radial. Quem pediu menos movimento
 * ao sistema operacional não vê a deriva (styles/animations.css).
 *
 * O fundo é `moldura-fundo`, e não o azul da marca escrito à mão: assim ele
 * acompanha o tema — marinho no claro, preto no escuro. Fixo, a tela de
 * entrada era a única que não obedecia à escolha de tema da pessoa.
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
      <aside
        aria-hidden
        className="relative hidden flex-col items-center justify-center gap-6 overflow-hidden border-r border-laranja-500/30 bg-moldura-fundo p-12 md:flex"
      >
        {/* grade de 56px, apagando nas bordas */}
        <div
          className="pointer-events-none absolute inset-0 opacity-100"
          style={{
            backgroundImage:
              "linear-gradient(to right, rgb(255 255 255 / 3.5%) 1px, transparent 1px), linear-gradient(to bottom, rgb(255 255 255 / 3.5%) 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage: "radial-gradient(ellipse 70% 60% at 50% 45%, black, transparent)",
          }}
        />
        {/* halo laranja: a única coisa que se move nesta tela */}
        <div
          className="pointer-events-none absolute left-1/2 top-1/2 h-[520px] w-[520px] -translate-x-1/2 -translate-y-1/2 animate-deriva rounded-full"
          style={{
            background:
              "radial-gradient(circle, color-mix(in srgb, var(--marca-laranja) 14%, transparent), transparent 65%)",
          }}
        />

        <div className="relative flex flex-col items-center gap-5">
          <LogoBMS sobre="escuro" alt="" className="w-[min(340px,70%)]" />
          <span className="h-0.5 w-16 rounded-full bg-[linear-gradient(90deg,transparent,var(--marca-laranja),transparent)]" />
          <p className="m-0 text-center text-xl font-extrabold tracking-tight text-moldura-texto">
            CRM Fiscal
          </p>
          <p className="m-0 -mt-3 max-w-[30ch] text-center text-[17px] leading-relaxed text-moldura-texto-suave">
            Apuração e recuperação de tributos
          </p>
        </div>
      </aside>

      <main className="flex flex-col items-center justify-center gap-8 bg-fundo px-6 py-12">
        <div className="flex w-full max-w-[412px] flex-col gap-4">
          <LogoBMS sobre="claro" className="mx-auto mb-2 w-[190px] md:hidden" />
          <h1 className="m-0 text-[30px] font-extrabold tracking-[-0.02em]">{titulo}</h1>
          {sub && <p className="m-0 -mt-2 text-sm leading-relaxed text-texto-suave">{sub}</p>}
          {children}
        </div>
        {rodape}
        <footer className="text-xs text-texto-fraco">
          BMS Consultoria Tributária · CRM Fiscal
        </footer>
      </main>
    </div>
  );
}

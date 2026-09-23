import { Outlet } from "react-router-dom";
import { LogoBMS } from "@/components/ui/LogoBMS";
import { BarraTopo } from "./BarraTopo";
import { useAuth } from "@/hooks/useAuth";

/**
 * A moldura da porta de entrada: logotipo e sessão, sem menu lateral.
 *
 * O hub de segmentos é onde se escolhe o **contexto** — e o menu lateral é
 * justamente o que aquele contexto passa a mostrar. Oferecê-lo antes da
 * escolha seria pedir que a pessoa navegue para dentro de algo que ela ainda
 * não escolheu.
 *
 * Do segundo nível em diante o menu volta, porque aí já há contexto: a pessoa
 * está dentro de um segmento e precisa circular por ele.
 *
 * O fundo repete os dois efeitos da tela de acesso — a grade de 56px esmaecida
 * nas bordas e o halo laranja que deriva devagar —, ambos em CSS e ambos
 * `aria-hidden`. É o que faz a porta de entrada parecer porta de entrada.
 */
export default function LeiauteDeEntrada() {
  const { usuario } = useAuth();
  // a rota só chega aqui autenticada; o null é do tipo, não da realidade
  if (!usuario) return null;

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-fundo">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgb(255 255 255 / 3%) 1px, transparent 1px), linear-gradient(to bottom, rgb(255 255 255 / 3%) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse 80% 60% at 50% 0%, black, transparent)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-40 -top-56 h-[520px] w-[520px] animate-deriva rounded-full bg-laranja-500/10 blur-[120px]"
      />

      <div className="relative z-10 pt-2">
        <BarraTopo
          usuario={usuario}
          solta
          antes={<LogoBMS sobre="escuro" className="mr-3 w-[132px] shrink-0" />}
        />
      </div>

      <main className="relative z-10 mx-auto flex w-full max-w-[1100px] flex-1 flex-col gap-7 p-6 pt-8">
        <Outlet />
      </main>
    </div>
  );
}

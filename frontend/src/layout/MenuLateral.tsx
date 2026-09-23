import { NavLink } from "react-router-dom";
import { LogoBMS } from "@/components/ui/LogoBMS";
import { IconeExpandir } from "@/constants/icons";
import { MENU, podeVer } from "@/constants/navigation";
import { ROTAS } from "@/constants/routes";
import { useMenuRecolhido } from "@/hooks/useMenuRecolhido";
import { cn } from "@/lib/cn";
import type { Papel } from "@/types/auth";

/**
 * O menu lateral.
 *
 * Preto, como o resto da moldura — ver docs/IDENTIDADE.md seção 3. Em tela
 * estreita vira uma barra horizontal no topo: reservar 232px de largura em
 * celular tiraria espaço da tabela, que é o que importa.
 *
 * **Recolhe.** Quem trabalha numa tabela larga — a 037, o razão, os 36 quadros
 * — quer os 232px de volta. Recolhido, sobram os ícones, e o rótulo aparece no
 * `title` ao passar o mouse. A escolha fica guardada: quem recolheu quer a tela
 * larga sempre, não só até o próximo F5.
 *
 * O botão não existe em tela estreita, onde o menu já é horizontal e não há
 * largura a recuperar.
 */
export function MenuLateral({ papel }: { papel: Papel }) {
  const [recolhido, alternar] = useMenuRecolhido();

  return (
    <aside
      className={cn(
        "flex shrink-0 gap-7 border-moldura-borda bg-moldura-fundo",
        "max-md:flex-row max-md:items-center max-md:gap-4 max-md:border-b max-md:px-4 max-md:py-3",
        "md:sticky md:top-0 md:h-screen md:flex-col md:border-r md:py-6",
        // a largura é a única coisa que muda, e muda com transição para que o
        // conteúdo ao lado não pareça saltar
        "md:transition-[width] md:duration-200",
        recolhido ? "md:w-[68px] md:px-2" : "md:w-[232px] md:px-4",
      )}
    >
      <LogoBMS
        sobre="escuro"
        className={cn(
          "max-md:w-[110px] md:mx-auto md:mb-2",
          recolhido ? "md:w-[44px]" : "w-[150px]",
        )}
      />

      <nav className="flex gap-1 max-md:flex-1 md:flex-col">
        {MENU.filter((i) => podeVer(i, papel)).map((i) => (
          <NavLink
            key={i.para}
            to={i.para}
            end={i.para === ROTAS.inicio}
            title={recolhido ? i.rotulo : undefined}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-raio py-2.5 text-sm font-semibold",
                "transition-colors duration-150",
                recolhido ? "md:justify-center md:px-0 px-3" : "px-3",
                isActive
                  ? // barra laranja à esquerda: o laranja é ação e posição atual,
                    // nunca decoração
                    "bg-white/8 text-moldura-texto md:border-l-2 md:border-moldura-ativo"
                  : "text-moldura-texto-suave hover:bg-white/5 hover:text-moldura-texto",
              )
            }
          >
            <i.icone size={16} strokeWidth={2} aria-hidden />
            {/* o rótulo some por `hidden`, e não por não ser renderizado: o
                leitor de tela continua anunciando o nome do item */}
            <span className={cn(recolhido && "md:sr-only")}>{i.rotulo}</span>
          </NavLink>
        ))}
      </nav>

      <div className="max-md:hidden md:mt-auto md:flex md:flex-col md:gap-3">
        <button
          type="button"
          onClick={alternar}
          aria-pressed={recolhido}
          title={recolhido ? "Fixar o menu aberto" : "Recolher o menu"}
          className={cn(
            "flex items-center gap-2.5 rounded-raio py-2 text-[13px] font-semibold",
            "text-moldura-texto-suave transition-colors hover:bg-white/5 hover:text-moldura-texto",
            recolhido ? "justify-center px-0" : "px-3",
          )}
        >
          <IconeExpandir
            size={15}
            strokeWidth={2}
            aria-hidden
            className={cn("transition-transform", !recolhido && "rotate-180")}
          />
          <span className={cn(recolhido && "sr-only")}>Recolher</span>
        </button>

        {!recolhido && <p className="m-0 text-xs text-moldura-texto-suave">CRM Fiscal</p>}
      </div>
    </aside>
  );
}

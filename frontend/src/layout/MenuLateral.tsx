import { NavLink } from "react-router-dom";
import { LogoBMS } from "@/components/ui/LogoBMS";
import { MENU, podeVer } from "@/constants/navigation";
import { ROTAS } from "@/constants/routes";
import { cn } from "@/lib/cn";
import type { Papel } from "@/types/auth";

/**
 * O menu lateral.
 *
 * Fica marinho porque é a moldura da identidade — ver docs/IDENTIDADE.md
 * secao 3. Em tela estreita vira uma barra horizontal no topo: reservar 232px
 * de largura em celular tiraria espaço da tabela, que é o que importa.
 */
export function MenuLateral({ papel }: { papel: Papel }) {
  return (
    <aside
      className={cn(
        "flex shrink-0 gap-7 border-moldura-borda bg-moldura-fundo",
        "max-md:flex-row max-md:items-center max-md:gap-4 max-md:border-b max-md:px-4 max-md:py-3",
        "md:sticky md:top-0 md:h-screen md:w-[232px] md:flex-col md:border-r md:px-4 md:py-6",
      )}
    >
      <LogoBMS
        sobre="escuro"
        className="w-[150px] max-md:w-[110px] md:mx-auto md:mb-2"
      />

      <nav className="flex gap-1 max-md:flex-1 md:flex-col">
        {MENU.filter((i) => podeVer(i, papel)).map((i) => (
          <NavLink
            key={i.para}
            to={i.para}
            end={i.para === ROTAS.inicio}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-raio px-3 py-2.5 text-sm font-semibold",
                "transition-colors duration-150",
                isActive
                  ? // barra laranja à esquerda: o laranja é ação e posição atual,
                    // nunca decoração
                    "bg-white/8 text-moldura-texto md:border-l-2 md:border-moldura-ativo"
                  : "text-moldura-texto-suave hover:bg-white/5 hover:text-moldura-texto",
              )
            }
          >
            <i.icone size={16} strokeWidth={2} aria-hidden />
            {i.rotulo}
          </NavLink>
        ))}
      </nav>

      <p className="m-0 text-xs text-moldura-texto-suave max-md:hidden md:mt-auto">
        CRM Fiscal
      </p>
    </aside>
  );
}

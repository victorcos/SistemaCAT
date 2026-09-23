import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";
import type { Etapa } from "@/services/importacao";

/**
 * A barra do trabalho: as funcionalidades, lado a lado.
 *
 *     | Arquivos | Quebras | Apuração | Gestão | Quebra XML |
 *
 * Substituiu a lista vertical de etapas em 23/09/2026. A lista dizia que o
 * trabalho é uma fila — importar, depois conferir, depois apurar — e **não é**:
 * a pessoa vai à funcionalidade de que precisa. Quebrar um SPED para olhar um
 * C170 não tem nada a ver com apurar PIS/COFINS, e esperar uma para chegar à
 * outra era invenção da tela.
 *
 * **Nada fica travado.** Só o que ainda não existe sai apagado, e com a razão
 * dita no `title`. Falta de base não barra: a pessoa entra, e a funcionalidade
 * diz o que falta — uma frase explica, uma aba apagada não.
 *
 * A ordem é a do servidor (`Etapas.Roteiros`), e muda com o módulo: o trabalho
 * de ICMS percorre a CAT 42, o de PIS/COFINS percorre o dele.
 */

/** A cor da bolinha, por situação. A aba em si não muda de cor. */
const PONTO: Record<string, string> = {
  concluida: "bg-sucesso",
  em_andamento: "bg-marca-laranja animate-pulso",
  pendente: "bg-borda-forte",
  nao_disponivel: "bg-transparent border border-borda-forte",
};

export function BarraDeFuncionalidades({
  etapas,
  rota,
}: {
  etapas: Etapa[];
  /** para onde cada chave leva; sem destino, a aba não vira link */
  rota: (chave: string) => string | null;
}) {
  return (
    <nav
      aria-label="Funcionalidades do trabalho"
      className="flex gap-1 overflow-x-auto rounded-raio-g border border-borda bg-superficie-vidro p-1"
    >
      {etapas.map((e) => {
        const destino = e.acessivel ? rota(e.chave) : null;
        const conteudo = (
          <>
            <span aria-hidden className={cn("h-1.5 w-1.5 shrink-0 rounded-full", PONTO[e.situacao] ?? PONTO.pendente)} />
            {e.nome_curto ?? e.nome}
          </>
        );
        const classes = cn(
          "flex items-center gap-2 whitespace-nowrap rounded-raio px-3.5 py-2 text-[13px] font-bold transition-colors",
        );

        if (destino === null) {
          return (
            <span
              key={e.chave}
              title={
                e.acessivel
                  ? "Esta funcionalidade ainda não tem tela."
                  : `${e.nome}: ainda não construída.`
              }
              className={cn(classes, "cursor-default text-texto-fraco opacity-60")}
            >
              {conteudo}
            </span>
          );
        }
        return (
          <NavLink
            key={e.chave}
            to={destino}
            end
            title={e.descricao}
            className={({ isActive }) =>
              cn(
                classes,
                "no-underline",
                isActive
                  ? "bg-superficie text-texto shadow-cat"
                  : "text-texto-suave hover:bg-superficie-alt hover:text-texto",
              )
            }
          >
            {conteudo}
          </NavLink>
        );
      })}
    </nav>
  );
}

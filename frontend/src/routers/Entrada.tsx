import { Navigate } from "react-router-dom";
import { ROTAS } from "@/constants/routes";
import { useAuth } from "@/hooks/useAuth";

/**
 * A raiz (`/`) não mostra tela: leva a pessoa para onde ela pertence.
 *
 * Até 24/09/2026 ela era a **lista de todos os trabalhos**, de todos os
 * tributos. Era a única tela do sistema que misturava assunto — e o assunto é o
 * recorte de tudo desde que o hub existe: quem entra em ICMS entra em ICMS. Ver
 * um trabalho de PIS/COFINS ali não é informação a mais, é o recorte desfeito.
 *
 * **Para onde vai é decisão do servidor** (`Segmentos.Entrada`), que a tela de
 * acesso já usa: a tela de segmentos para quem enxerga vários, o segmento para
 * quem tem um, o módulo direto para quem tem um só de um só. Repetir a regra
 * aqui daria duas respostas para a mesma pergunta.
 *
 * Nenhum destino conhecido é `/`, mas a guarda existe mesmo assim: um laço de
 * redirecionamento é o tipo de defeito que trava a tela sem dizer nada.
 */
export default function Entrada() {
  const { usuario } = useAuth();
  const destino = usuario?.entrada;
  return <Navigate to={destino && destino !== ROTAS.inicio ? destino : ROTAS.segmentos} replace />;
}

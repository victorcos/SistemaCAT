import { ROTAS } from "@/constants/routes";
import type { ProjetoDetalhe, Trilha } from "@/services/importacao";

/**
 * A frente a que uma etapa pertence — e que tem tela própria para voltar.
 *
 * Qual frente é a da etapa não se decide aqui: vem do servidor, em
 * `trilhas[].etapas`. Repetir esse mapa na tela criaria duas verdades sobre
 * quais etapas compõem cada frente, e elas divergiriam na primeira frente
 * nova — que é justamente quando ninguém lembra de procurar a cópia.
 *
 * **Frente de uma etapa só não conta**, e é a parte que não se adivinha: o
 * card dela no trabalho vai direto para a tela da etapa, sem passar pelo
 * painel da frente (`FrentesDoTrabalho.escolhaDe`). Mandar essa pessoa de
 * volta para o painel a levaria a uma tela que ela nunca viu, com um card
 * só — o clique que o card direto existe para poupar. Quem tem painel hoje é
 * a CAT 42, com sete etapas.
 */
function frenteComPainel(
  etapa: string,
  projeto: ProjetoDetalhe | null | undefined,
): Trilha | undefined {
  const dona = projeto?.trilhas?.find((t) => t.etapas.includes(etapa));
  return dona && dona.etapas.length > 1 ? dona : undefined;
}

/**
 * Para onde a seta "voltar" de uma etapa deve levar.
 *
 * Quem abriu a etapa pelo painel da frente veio da lista de etapas dela —
 * Conferência, Movimentos, Suportado, Razão... — e espera voltar para lá.
 * Mandar essa pessoa para a lista de FRENTES (CAT 42, Quebra de XML, Crédito
 * outorgado) a tira um nível acima do que ela estava, e ela tem de entrar na
 * frente de novo para seguir para a etapa seguinte.
 *
 * Sem o detalhe carregado ainda, com etapa que nenhuma frente reivindica, ou
 * com frente que não tem painel, cai no trabalho. É o destino de antes: o
 * link nunca fica quebrado nem esperando dado.
 */
export function voltarDaEtapa(
  projetoId: number | string,
  etapa: string,
  projeto: ProjetoDetalhe | null | undefined,
): string {
  const dona = frenteComPainel(etapa, projeto);
  return dona ? ROTAS.frente(projetoId, dona.chave) : ROTAS.projeto(projetoId);
}

/**
 * O rótulo que acompanha a seta.
 *
 * "Voltar ao trabalho" mentiria quando o destino é o painel da frente, e a
 * pessoa clicaria esperando a lista de frentes.
 */
export function rotuloDoVoltar(
  etapa: string,
  projeto: ProjetoDetalhe | null | undefined,
): string {
  const dona = frenteComPainel(etapa, projeto);
  return dona ? `Voltar a ${dona.rotulo}` : "Voltar ao trabalho";
}

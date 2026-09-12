import type { TomDeEtiqueta } from "@/components/ui/Etiqueta";

/**
 * A situação de um trabalho, do lado da tela.
 *
 * Os rótulos e as explicações vêm do servidor (`GET /api/status-de-projeto`)
 * — aqui ficam só as decisões visuais e as duas perguntas que a tela faz o
 * tempo todo: que cor usar, e se este status deixa a etapa rodar.
 */

export type Status = "em_andamento" | "pausado" | "cancelado" | "concluido";

export const TOM_DO_STATUS: Record<Status, TomDeEtiqueta> = {
  em_andamento: "info",
  pausado: "atencao",
  cancelado: "erro",
  concluido: "sucesso",
};

/** Cor da barra de progresso e da faixa lateral do cartão. */
export const BARRA_DO_STATUS: Record<Status, "destaque" | "sucesso"> = {
  em_andamento: "destaque",
  pausado: "destaque",
  cancelado: "destaque",
  concluido: "sucesso",
};

export const ROTULO_DO_STATUS: Record<Status, string> = {
  em_andamento: "Em andamento",
  pausado: "Pausado",
  cancelado: "Cancelado",
  concluido: "Concluído",
};

/**
 * Se o trabalho neste status deixa rodar etapa.
 *
 * Espelha `StatusDoProjeto.aceita_processamento` no domínio. A tela usa isto
 * para **desabilitar o botão e dizer por quê** antes de a pessoa clicar — a
 * API recusaria de qualquer jeito, mas descobrir o impedimento depois de
 * clicar é pior do que vê-lo antes.
 */
export const aceitaProcessamento = (status: string) =>
  status === "em_andamento" || status === "concluido";

/** O aviso que a tela mostra quando o trabalho está parado. */
export function avisoDeTrabalhoParado(status: string): {
  titulo: string;
  texto: string;
} | null {
  if (status === "pausado") {
    return {
      titulo: "Este trabalho está pausado",
      texto:
        "As etapas ficam indisponíveis enquanto ele estiver assim — é o que pausar significa. " +
        "Veja no histórico por que foi pausado e retome-o por lá para seguir.",
    };
  }
  if (status === "cancelado") {
    return {
      titulo: "Este trabalho está cancelado",
      texto:
        "Fica só para consulta: o histórico e tudo que já foi apurado continuam aqui, " +
        "mas nenhuma etapa roda. Se ele voltou a valer, mude a situação no histórico.",
    };
  }
  return null;
}

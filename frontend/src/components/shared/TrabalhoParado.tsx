import { Aviso } from "@/components/ui/Aviso";
import { BotaoLink } from "@/components/ui/Botao";
import { ROTAS } from "@/constants/routes";
import { avisoDeTrabalhoParado } from "@/constants/status";

/**
 * A faixa que explica por que a etapa não roda.
 *
 * Aparece nas três telas de etapa e no detalhe do trabalho, sempre com a
 * mesma frase e o mesmo caminho de saída — o histórico, que é onde se vê por
 * que foi pausado e onde se retoma.
 *
 * Devolve `null` quando o trabalho anda: quem chama não precisa de `if`.
 */
export function TrabalhoParado({
  status,
  projetoId,
}: {
  status: string | undefined;
  projetoId: number;
}) {
  const parado = status ? avisoDeTrabalhoParado(status) : null;
  if (!parado) return null;

  return (
    <Aviso
      tom={status === "cancelado" ? "erro" : "atencao"}
      titulo={parado.titulo}
      acao={
        <BotaoLink para={ROTAS.historico(projetoId)} tamanho="sm" variante="secundario">
          Abrir o histórico
        </BotaoLink>
      }
    >
      {parado.texto}
    </Aviso>
  );
}

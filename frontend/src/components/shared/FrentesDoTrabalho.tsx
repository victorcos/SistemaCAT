import { CardDeEscolha, type Escolha } from "@/components/shared/CardDeEscolha";
import { FaixaDeLeiautes } from "@/components/shared/PainelDoTrabalho";
import { Vazio } from "@/components/ui/Pagina";
import { ROTAS } from "@/constants/routes";
import type { Trilha } from "@/services/importacao";

/**
 * As frentes de trabalho de um trabalho: a CAT 42, o crédito outorgado, e as
 * que vierem — CAT 207, quebra de XML.
 *
 * **É o mesmo card do hub de tributos**, de propósito. Quem escolheu ICMS numa
 * tela de cards não deveria aprender uma segunda gramática para escolher a CAT
 * 42 dentro dele: muda o que está escrito, não como se lê.
 *
 * A cor é a do **módulo**, e não a da frente. Dentro do trabalho o assunto já é
 * um só — todo card aqui é ICMS, e pintar cada frente de uma cor inventaria uma
 * distinção que não existe. O que separa os cards é a sigla e o nome.
 *
 * **Nada some por não existir ainda.** A frente sem nenhuma etapa construída
 * entra apagada e dizendo isso; lá dentro, a etapa explica o que falta. Card
 * que desaparece faz a pessoa procurar a frente que ela sabe que foi contratada.
 */
export function FrentesDoTrabalho({
  projetoId,
  modulo,
  trilhas,
}: {
  projetoId: number;
  /** de onde sai a cor dos cards */
  modulo: string;
  trilhas: Trilha[];
}) {
  return (
    <div className="flex flex-col gap-4">
      <FaixaDeLeiautes projetoId={projetoId} />

      {trilhas.length === 0 ? (
        <Vazio titulo="Nenhuma frente de trabalho construída ainda">
          Este módulo importa a base e para aí. Assim que a primeira frente existir, ela aparece
          aqui como um card.
        </Vazio>
      ) : (
        <section className="grid grid-cols-[repeat(auto-fit,minmax(288px,1fr))] gap-4">
          {trilhas.map((t) => (
            <CardDeEscolha key={t.chave} escolha={escolhaDe(t, projetoId, modulo)} />
          ))}
        </section>
      )}
    </div>
  );
}

function escolhaDe(t: Trilha, projetoId: number, modulo: string): Escolha {
  return {
    chave: t.chave,
    rotulo: t.rotulo,
    descricao: t.descricao,
    para: ROTAS.frente(projetoId, t.chave),
    sigla: t.sigla,
    cor: modulo,
    apagado: !t.construida,
    etiqueta: t.construida ? `${t.totais} etapa${t.totais === 1 ? "" : "s"}` : "Ainda não construída",
    // o número grande é o que já foi feito; sem frente construída não há o que
    // contar, e um "0 de 1" ali seria contar o que não existe
    contagem: t.construida
      ? { quantos: t.feitas, rotulo: `de ${t.totais} concluída${t.totais === 1 ? "" : "s"}` }
      : undefined,
    chamada: t.construida ? "Abrir as etapas" : "Ver o que falta",
  };
}

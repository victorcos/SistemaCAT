import { Botao } from "@/components/ui/Botao";
import { IconeBaixar } from "@/constants/icons";
import type { Formato } from "@/services/conferencia";

/**
 * O par de botões de download: a planilha e o CSV da mesma lista.
 *
 * Existe como componente porque são sete listas em duas telas, e o par
 * precisa dizer a mesma coisa nas sete. Repetir o JSX levaria, na primeira
 * manutenção, a uma tela com CSV e outra sem.
 *
 * **Por que dois botões e não um seletor de formato.** O xlsx é o caminho de
 * todo dia e continua sendo o botão grande. O CSV serve a outra coisa:
 * carregar em outra ferramenta, ou baixar lista que passa do que o Excel
 * aguenta. Esconder isso atrás de um menu tornaria a saída comum mais
 * trabalhosa para dar destaque à rara.
 */
export function BaixarPlanilha({
  aoBaixar,
  desabilitado,
  rotulo = "Baixar planilha",
  destaque,
  baixando = null,
  aoCancelar,
}: {
  aoBaixar: (formato: Formato) => void;
  desabilitado: boolean;
  rotulo?: string;
  /** o botão principal desta tela, com sombra de ação */
  destaque?: boolean;
  /** qual formato desta lista está baixando agora, se algum */
  baixando?: Formato | null;
  /** só chega depois de uns instantes: botão que pisca ninguém acerta */
  aoCancelar?: () => void;
}) {
  // o botão que está baixando vira Cancelar; o outro fica fora do caminho
  const saida = (formato: Formato) =>
    baixando === formato ? aoCancelar : undefined;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Botao
        variante={destaque ? "principal" : "secundario"}
        icone={IconeBaixar}
        onClick={() => aoBaixar("xlsx")}
        disabled={desabilitado}
        carregando={baixando === "xlsx"}
        aoCancelar={saida("xlsx")}
        className={destaque ? "shadow-acao" : undefined}
      >
        {rotulo}
      </Botao>
      <Botao
        variante="fantasma"
        tamanho="sm"
        onClick={() => aoBaixar("csv")}
        disabled={desabilitado}
        carregando={baixando === "csv"}
        aoCancelar={saida("csv")}
        // a chave de acesso tem 44 dígitos, e o Excel a converte em notação
        // científica ao abrir um CSV com dois cliques. Quem precisa do Excel
        // usa o botão ao lado, que é imune — este é para carregar em outra
        // ferramenta. Dizer isso aqui evita o erro antes de ele acontecer
        title="CSV para carregar em outra ferramenta. Não abra no Excel com dois cliques: a chave de 44 dígitos vira notação científica. Para o Excel, use a planilha."
      >
        CSV
      </Botao>
    </div>
  );
}

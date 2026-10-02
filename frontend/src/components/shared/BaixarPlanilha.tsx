import { Botao } from "@/components/ui/Botao";
import { IconeBaixar } from "@/constants/icons";
import { motivoSemSeletor } from "@/lib/download";
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
 *
 * **O clique pode morrer antes da rede**, e já morreu: o seletor de "salvar
 * como" fica no caminho, e quando ele não abre o download sumia em silêncio.
 * Ver `lib/download.ts` — hoje o seletor que falha cai na pasta padrão em vez
 * de não baixar nada.
 *
 * **E quando não há seletor nenhum, a tela diz.** Em 02/10/2026 um 037 de 2,93
 * milhões de linhas foi pedido de outra máquina, pelo IP do dev server: sem
 * contexto seguro não existe seletor, o arquivo foi para a pasta de downloads
 * passando inteiro pela memória, e o relato foi "nem gerou a opção de escolher
 * o caminho". Era o comportamento correto, mudo. O aviso aqui existe porque
 * ninguém abre o console — e porque, nesse caminho, lista grande **falha**, e o
 * CSV ao lado é a saída.
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
  // **O botão que baixa não vira Cancelar.** Virava, e isso punia o clique
  // impaciente: quem clicava de novo achando que travou abortava o próprio
  // download — e o arquivo já criado era apagado, sem erro na tela. Relatado
  // em 01/10/2026, na tela de exclusões.
  //
  // Agora o Cancelar aparece **ao lado**, e só depois dos 400 ms em que a
  // ação ainda pode estar acontecendo. Clicar duas vezes no mesmo lugar passa
  // a ser inofensivo, que é o que se espera de um botão de baixar.
  const cancelavel = baixando !== null && aoCancelar !== undefined;
  const semSeletor = motivoSemSeletor();

  const botoes = (
    <div className="flex flex-wrap items-center gap-2">
      <Botao
        variante={destaque ? "principal" : "secundario"}
        icone={IconeBaixar}
        onClick={() => aoBaixar("xlsx")}
        disabled={desabilitado}
        carregando={baixando === "xlsx"}
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
        // a chave de acesso tem 44 dígitos, e o Excel a converte em notação
        // científica ao abrir um CSV com dois cliques. Quem precisa do Excel
        // usa o botão ao lado, que é imune — este é para carregar em outra
        // ferramenta. Dizer isso aqui evita o erro antes de ele acontecer
        title="CSV para carregar em outra ferramenta. Não abra no Excel com dois cliques: a chave de 44 dígitos vira notação científica. Para o Excel, use a planilha."
      >
        CSV
      </Botao>
      {cancelavel && (
        <Botao variante="fantasma" tamanho="sm" onClick={aoCancelar}>
          Cancelar
        </Botao>
      )}
    </div>
  );

  // **o DOM só muda quando há algo a dizer.** Este componente está em quinze
  // telas, em contêineres de linha e de coluna; envolver sempre mudaria o
  // layout de todas para avisar de um caso excepcional
  if (!semSeletor) return botoes;

  return (
    <div className="flex flex-col items-end gap-1.5">
      {botoes}
      <p className="m-0 max-w-[46ch] text-right text-[11px] leading-relaxed text-atencao">
        {semSeletor === "contexto-inseguro" ? (
          <>
            Vai para a pasta de downloads: esta página está em <strong>http</strong> por
            IP, e escolher a pasta só funciona em <strong>localhost</strong> ou https.
            Nesse caminho o arquivo passa inteiro pela memória — em lista grande,
            prefira o CSV.
          </>
        ) : (
          <>
            Vai para a pasta de downloads: este navegador não tem seletor de pasta.
            Nesse caminho o arquivo passa inteiro pela memória — em lista grande,
            prefira o CSV.
          </>
        )}
      </p>
    </div>
  );
}

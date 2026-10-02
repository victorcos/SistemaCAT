/**
 * Onde o arquivo baixado vai parar, e como ele chega lá.
 *
 * Duas coisas, e a segunda é a que mais importa:
 *
 * **Escolher a pasta.** `<a download>` não pergunta nada: joga na pasta de
 * downloads do navegador. Em máquina com pouco espaço isso enche o disco sem
 * o usuário decidir nada, e obriga a mover o arquivo depois. O seletor nativo
 * (`showSaveFilePicker`) deixa escolher pasta e nome na hora.
 *
 * **Não passar pela memória.** O jeito antigo fazia `await r.blob()`: o
 * arquivo inteiro ia para a memória antes de qualquer byte chegar ao disco.
 * A lista analítica de uma base real desta casa tem 37,9 milhões de
 * documentos — um CSV de vários GB, que derruba a aba antes de salvar. Com o
 * seletor, a resposta é canalizada direto da rede para o arquivo, e a memória
 * usada não depende do tamanho do download.
 *
 * Onde o seletor não existe (Firefox, Safari) ou a página não está em
 * contexto seguro, cai no caminho antigo. Continua funcionando, só sem
 * escolher pasta — e aí vale o que estiver configurado no navegador.
 *
 * **E dizendo por quê.** Cair no caminho antigo em silêncio custou uma
 * investigação em 02/10/2026: o 037 de um cliente de 7,53 GB foi pedido de
 * outra máquina, pelo IP do dev server, e o relato foi "nem gerou a opção de
 * escolher o caminho". Não havia defeito — `http` num IP de rede não é
 * contexto seguro, a API não existe ali, e o código saía por este ramo sem
 * uma linha no console. Ver `motivoSemSeletor`.
 */

/** O que o seletor devolve. `null` = não há seletor; use o caminho antigo. */
type Destino = FileSystemFileHandle | null;

/** Por que não há seletor. Vazio quando há. Ver `motivoSemSeletor`. */
export type MotivoSemSeletor = "" | "sem-suporte" | "contexto-inseguro";

/**
 * Quem cancelou não errou nada: não há o que avisar.
 *
 * Vale para os dois cancelamentos: fechar a janela de "salvar como" sem
 * escolher pasta, e apertar Cancelar com o download já em curso.
 */
export class DownloadCancelado extends Error {
  constructor() {
    super("Download cancelado.");
    this.name = "DownloadCancelado";
  }
}

/** Se este erro é um aborto — do seletor ou do sinal de cancelamento. */
export function foiAbortado(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

interface OpcoesDeSelecao {
  suggestedName?: string;
  types?: { description: string; accept: Record<string, string[]> }[];
}

type ComSeletor = typeof window & {
  showSaveFilePicker?: (o: OpcoesDeSelecao) => Promise<FileSystemFileHandle>;
};

const TIPOS: Record<string, { descricao: string; mime: string }> = {
  ".xlsx": {
    descricao: "Planilha do Excel",
    mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  },
  ".csv": { descricao: "CSV", mime: "text/csv" },
  ".zip": { descricao: "Arquivo compactado", mime: "application/zip" },
};

/**
 * Por que esta página não tem seletor de pasta — se não tiver.
 *
 * **Os dois motivos têm soluções diferentes, e por isso são valores
 * diferentes.** "Sem suporte" é o navegador (Firefox, Safari) e não há o que
 * fazer além de aceitar a pasta de downloads. "Contexto inseguro" é a página,
 * tem conserto imediato, e é o caso que aparece na prática: a
 * `File System Access API` só existe em https, `localhost` ou `127.0.0.1`, e o
 * dev server desta casa é aberto para a rede por padrão (`vite.config.ts`,
 * `host: CAT_HOST ?? true`). Quem abre `http://<ip>:5173` de outra máquina
 * perde o seletor sem saber por quê.
 *
 * Serve à tela, não só ao console: o analista não abre o console, e a diferença
 * entre "não baixou" e "não baixou porque X, faça Y" é meia hora de
 * investigação. Ver `BaixarPlanilha`.
 */
export function motivoSemSeletor(): MotivoSemSeletor {
  if (typeof (window as ComSeletor).showSaveFilePicker === "function") return "";
  return window.isSecureContext ? "sem-suporte" : "contexto-inseguro";
}

function extensaoDe(nome: string): string {
  const ponto = nome.lastIndexOf(".");
  return ponto === -1 ? "" : nome.slice(ponto).toLowerCase();
}

/**
 * Quanto tempo o seletor precisa ficar aberto para a recusa ser do usuário.
 *
 * Ninguém abre uma janela do sistema, lê o nome do arquivo e desiste em menos
 * de um décimo de segundo. `AbortError` imediato não é alguém cancelando: é o
 * seletor que **não chegou a aparecer**.
 */
const DEPRESSA_DEMAIS_PARA_SER_DESISTENCIA_MS = 150;

/**
 * Abre o seletor de "salvar como".
 *
 * **Tem de ser chamado antes de qualquer `await`** a partir do clique. O
 * navegador só abre o seletor enquanto a ativação do gesto do usuário está
 * válida, e ela não sobrevive a uma ida à rede. Buscar primeiro e perguntar
 * depois faz o seletor ser recusado.
 *
 * ## Por que o relógio
 *
 * O seletor avisa das duas coisas do mesmo jeito — `AbortError` tanto para
 * "desisti" quanto para "não consegui abrir". Tratar os dois como desistência
 * custou um download que **não baixava e não dizia nada**: nenhuma requisição
 * saía do navegador, nenhum arquivo aparecia no disco, nenhum erro na tela.
 * Relatado em 01/10/2026, na tela de exclusões, e levou meia hora de
 * investigação para provar que o clique morria aqui.
 *
 * Então mede-se. Abortou depressa demais para alguém ter lido a janela? O
 * seletor não apareceu, e vale o caminho antigo — que entrega o arquivo na
 * pasta de downloads e sempre funciona. Demorou o bastante? Foi decisão de
 * quem clicou, e aí silêncio é a resposta certa.
 *
 * Errar a favor do download é de propósito: baixar para a pasta errada é um
 * aborrecimento, não baixar nada é um defeito.
 */
export async function escolherOndeSalvar(nomeSugerido: string): Promise<Destino> {
  const seletor = (window as ComSeletor).showSaveFilePicker;
  if (typeof seletor !== "function") {
    // **este ramo saía calado**, e era o mais comum dos dois. O `console.warn`
    // de 01/10 ficou só no `catch`, que cobre o seletor que existe e falha
    console.warn(
      motivoSemSeletor() === "contexto-inseguro"
        ? "sem seletor de pasta: a página não está em contexto seguro. `http` num " +
          "IP de rede não vale — abra por `localhost` ou https. O arquivo vai para " +
          "a pasta de downloads e passa inteiro pela memória antes de gravar."
        : "sem seletor de pasta: este navegador não implementa `showSaveFilePicker`. " +
          "O arquivo vai para a pasta de downloads e passa inteiro pela memória " +
          "antes de gravar.",
    );
    return null;
  }

  const extensao = extensaoDe(nomeSugerido);
  const tipo = TIPOS[extensao];
  const comecou = Date.now();
  try {
    return await seletor.call(window, {
      suggestedName: nomeSugerido,
      types: tipo
        ? [{ description: tipo.descricao, accept: { [tipo.mime]: [extensao] } }]
        : undefined,
    });
  } catch (e) {
    const aberto = Date.now() - comecou;
    if (foiAbortado(e) && aberto >= DEPRESSA_DEMAIS_PARA_SER_DESISTENCIA_MS) {
      throw new DownloadCancelado();
    }
    // o seletor não apareceu — bloqueado por política, contexto inseguro, ou
    // recusado sem dizer por quê. Segue pelo caminho antigo em vez de deixar
    // a pessoa sem download nenhum e sem explicação
    console.warn("o seletor de pasta não abriu; baixando para a pasta padrão", e);
    return null;
  }
}

/**
 * Escreve a resposta no arquivo escolhido, sem passar pela memória.
 *
 * `pipeTo` liga o corpo da resposta ao arquivo: os bytes vão da rede para o
 * disco em blocos. É o que permite salvar um CSV de vários GB numa aba de
 * navegador — e é o que torna o cancelamento possível de verdade, porque a
 * qualquer momento há um bloco em trânsito e não um arquivo inteiro já
 * comprometido.
 *
 * `sinal` interrompe no meio. O que já foi escrito é descartado com o
 * arquivo: quem cancela não quer metade de uma planilha no disco.
 */
export async function gravarNoArquivo(
  destino: FileSystemFileHandle,
  r: Response,
  sinal?: AbortSignal,
): Promise<void> {
  const escrita = await destino.createWritable();
  try {
    if (r.body) {
      await r.body.pipeTo(escrita, { signal: sinal });
      return;
    }
    // navegador sem corpo em fluxo: ainda assim grava no arquivo escolhido
    await escrita.write(await r.blob());
    await escrita.close();
  } catch (e) {
    // pipeTo já errou o destino ao abortar; abortar de novo é inofensivo e
    // cobre o caminho sem fluxo, onde ninguém fechou nada
    try {
      await escrita.abort();
    } catch {
      /* já estava fechado */
    }
    if (foiAbortado(e)) throw new DownloadCancelado();
    throw e;
  }
}

/**
 * Descarta o arquivo que o seletor já criou.
 *
 * O seletor cria a entrada em disco no momento em que a pessoa confirma o
 * nome. Se a busca falhar depois disso, ficaria um arquivo de 0 byte com cara
 * de planilha — pior que não ter nada, porque alguém vai tentar abrir.
 */
export async function descartar(destino: FileSystemFileHandle): Promise<void> {
  const remover = (destino as FileSystemFileHandle & {
    remove?: () => Promise<void>;
  }).remove;
  if (typeof remover !== "function") return;
  try {
    await remover.call(destino);
  } catch {
    /* sem permissão para remover: o arquivo vazio fica, e paciência */
  }
}

/** O caminho antigo: o navegador decide a pasta. */
export function baixarPelaPastaPadrao(conteudo: Blob, nome: string): void {
  const url = URL.createObjectURL(conteudo);
  const link = document.createElement("a");
  link.href = url;
  link.download = nome;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // o navegador precisa do endereço enquanto o download começa
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

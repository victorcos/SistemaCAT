/**
 * Quanto já andou a planilha que está sendo montada do outro lado.
 *
 * ## Por que existe
 *
 * Montar a Consulta de Entradas da empresa 24 levou **39 minutos** em
 * 14/10/2026 — 4,7 milhões de linhas em seis abas, 13 GB de rascunho. A tela
 * mostrava um girador e nada mais. Quem espera assim não sabe se falta um
 * minuto ou meia hora, nem se ainda está vivo; houve quem concluísse que tinha
 * travado e clicasse de novo, pondo dois pedidos a disputar o mesmo disco.
 *
 * ## Por que um canal solto, e não um parâmetro
 *
 * São **vinte e duas** chamadas de download, todas passando por
 * `baixarArquivo`. Levar o andamento até o botão por parâmetro obrigaria a
 * mudar as vinte e duas e todos os serviços no meio do caminho — para carregar
 * um número que só interessa a quem está olhando.
 *
 * O canal é seguro aqui porque **só há um download por vez**: `useAcao` aborta
 * o anterior antes de começar o seguinte. Quem assina recebe o que estiver em
 * curso, e `nada()` limpa ao terminar.
 */

export interface AndamentoDoDownload {
  /** "Montando a planilha", "Compactando o arquivo" */
  passo: string;
  feito: number;
  total: number;
  /** 0 a 1; zero quando o passo não tem contagem */
  fracao: number;
  terminado: boolean;
}

type Ouvinte = (a: AndamentoDoDownload | null) => void;

let atual: AndamentoDoDownload | null = null;
const ouvintes = new Set<Ouvinte>();

export function assinar(ouvinte: Ouvinte): () => void {
  ouvintes.add(ouvinte);
  ouvinte(atual);
  return () => {
    ouvintes.delete(ouvinte);
  };
}

export function publicar(andamento: AndamentoDoDownload | null): void {
  atual = andamento;
  for (const ouvinte of ouvintes) ouvinte(andamento);
}

export function nada(): void {
  publicar(null);
}

/** O que está em curso agora, para quem não quer assinar. */
export function agora(): AndamentoDoDownload | null {
  return atual;
}

/** De quanto em quanto tempo se pergunta ao servidor. */
export const INTERVALO_DE_CONSULTA_MS = 1000;

/**
 * Pergunta o andamento até alguém mandar parar.
 *
 * Erro de rede aqui **não interrompe nada**: o andamento é enfeite ao lado do
 * download de verdade, e derrubá-lo por causa de uma consulta que falhou
 * trocaria um incômodo por um defeito. Só para de perguntar quando o download
 * acaba — quem chama devolve a função de parada.
 */
export function acompanhar(
  chave: string,
  buscar: (chave: string) => Promise<AndamentoDoDownload>,
): () => void {
  let vivo = true;
  const relogio = setInterval(async () => {
    if (!vivo) return;
    try {
      const a = await buscar(chave);
      if (vivo) publicar(a);
    } catch {
      /* consulta de andamento que falha não derruba o download */
    }
  }, INTERVALO_DE_CONSULTA_MS);

  return () => {
    vivo = false;
    clearInterval(relogio);
    nada();
  };
}

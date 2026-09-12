import { useCallback, useEffect, useRef, useState } from "react";
import { DownloadCancelado, foiAbortado } from "@/lib/download";
import { comoErro } from "@/lib/errors";
import type { ErroApi } from "@/types/erro";

/**
 * Uma ação que carrega, com erro e cancelamento.
 *
 * É o padrão da casa para tudo que mostra "carregando": a tela diz o que
 * fazer, e daqui saem o estado do botão, a mensagem de erro e o cancelamento.
 * Antes cada tela repetia `setOcupado(true) / try / catch / finally`, e cada
 * repetição era uma chance de esquecer o `finally` e deixar a tela travada.
 *
 * **O cancelamento é de verdade ou não existe.** `executar` entrega um
 * `AbortSignal` à tarefa, e cancelar aborta a requisição. Onde abortar não
 * desfaz nada — um POST que o servidor já processou —, a tela simplesmente
 * não oferece Cancelar: um botão que diz ter cancelado a criação de um
 * usuário que foi criado é pior do que não ter botão.
 *
 * **Só uma ação por vez.** Começar outra aborta a anterior. Sem isso, duas
 * respostas voltando fora de ordem deixariam a tela mostrando a mais velha.
 */
export interface Acao {
  carregando: boolean;
  erro: ErroApi | null;
  setErro: (e: ErroApi | null) => void;
  /** Roda a tarefa. Devolve `undefined` se deu erro ou se foi cancelada. */
  executar: <T>(tarefa: (sinal: AbortSignal) => Promise<T>) => Promise<T | undefined>;
  cancelar: () => void;
  /**
   * Se o botão de cancelar deve aparecer agora.
   *
   * Fica falso nos primeiros instantes: ação que termina em 200 ms faria o
   * botão piscar, e um botão que pisca é pior que nenhum — ninguém acerta o
   * clique e todo mundo vê a tela tremer.
   */
  podeCancelar: boolean;
}

/** Tempo até o Cancelar aparecer. Abaixo disto a ação já acabou. */
const ESPERA_PARA_OFERECER_CANCELAR = 400;

export function useAcao(): Acao {
  const [carregando, setCarregando] = useState(false);
  const [podeCancelar, setPodeCancelar] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const controle = useRef<AbortController | null>(null);
  const relogio = useRef<ReturnType<typeof setTimeout> | null>(null);
  const vivo = useRef(true);

  useEffect(() => {
    vivo.current = true;
    return () => {
      // sair da tela no meio de um download não deve deixar a requisição
      // pendurada nem o React avisando sobre estado em componente desmontado
      vivo.current = false;
      controle.current?.abort();
      if (relogio.current) clearTimeout(relogio.current);
    };
  }, []);

  const cancelar = useCallback(() => controle.current?.abort(), []);

  const executar = useCallback(
    async <T,>(tarefa: (sinal: AbortSignal) => Promise<T>): Promise<T | undefined> => {
      controle.current?.abort();
      const meu = new AbortController();
      controle.current = meu;

      setCarregando(true);
      setErro(null);
      setPodeCancelar(false);
      if (relogio.current) clearTimeout(relogio.current);
      relogio.current = setTimeout(() => {
        if (controle.current === meu) setPodeCancelar(true);
      }, ESPERA_PARA_OFERECER_CANCELAR);

      try {
        return await tarefa(meu.signal);
      } catch (e) {
        // quem cancelou sabe que cancelou: avisar em vermelho seria dizer
        // que algo deu errado quando foi a pessoa que decidiu parar
        if (!cancelamento(e) && vivo.current) setErro(comoErro(e));
        return undefined;
      } finally {
        // uma ação mais nova já assumiu: quem terminou agora não manda mais
        // no estado da tela
        if (controle.current === meu) {
          controle.current = null;
          if (relogio.current) clearTimeout(relogio.current);
          if (vivo.current) {
            setCarregando(false);
            setPodeCancelar(false);
          }
        }
      }
    },
    [],
  );

  return { carregando, erro, setErro, executar, cancelar, podeCancelar };
}

/** Os dois jeitos de uma ação acabar por vontade de quem clicou. */
export function cancelamento(e: unknown): boolean {
  return e instanceof DownloadCancelado || foiAbortado(e);
}

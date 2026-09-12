import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { CHAVE_TEMA } from "@/constants/storage";

export type Tema = "claro" | "escuro" | "sistema";
export type TemaEfetivo = "claro" | "escuro";

interface Contexto {
  /** o que o usuário escolheu, incluindo "seguir o sistema" */
  tema: Tema;
  /** o que está de fato na tela agora */
  temaEfetivo: TemaEfetivo;
  definirTema: (t: Tema) => void;
}

export const ContextoDeTema = createContext<Contexto | null>(null);

const CONSULTA = "(prefers-color-scheme: dark)";

/** Lê a escolha guardada. Se o localStorage estiver bloqueado (aba anônima,
 *  cookies de terceiro desligados), cair no padrão é melhor que estourar. */
export function lerTemaGuardado(): Tema {
  try {
    const t = localStorage.getItem(CHAVE_TEMA);
    return t === "claro" || t === "escuro" || t === "sistema" ? t : "escuro";
  } catch {
    return "escuro";
  }
}

const resolver = (t: Tema): TemaEfetivo =>
  t === "sistema" ? (window.matchMedia(CONSULTA).matches ? "escuro" : "claro") : t;

/**
 * Aplica o tema em <html data-tema>.
 *
 * O CSS já estava pronto para isto desde sempre: tokens.css tem os blocos
 * [data-tema="escuro"] e prefers-color-scheme. O que faltava era alguém
 * escrever o atributo — nenhum código TS lia ou gravava `data-tema`.
 *
 * Padrão é "escuro" por decisão de projeto: o redesenho das telas parte do
 * marinho da marca como fundo. O tema claro continua inteiro e disponível.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [tema, setTema] = useState<Tema>(lerTemaGuardado);
  const [temaEfetivo, setTemaEfetivo] = useState<TemaEfetivo>(() =>
    resolver(lerTemaGuardado()),
  );

  useEffect(() => {
    const aplicar = () => {
      const efetivo = resolver(tema);
      setTemaEfetivo(efetivo);
      document.documentElement.dataset.tema = efetivo;
    };
    aplicar();

    // só interessa ouvir o sistema operacional quando o usuário pediu
    // explicitamente para segui-lo
    if (tema !== "sistema") return;
    const mq = window.matchMedia(CONSULTA);
    mq.addEventListener("change", aplicar);
    return () => mq.removeEventListener("change", aplicar);
  }, [tema]);

  const definirTema = useCallback((t: Tema) => {
    setTema(t);
    try {
      localStorage.setItem(CHAVE_TEMA, t);
    } catch {
      /* sem persistência: vale para esta aba e pronto */
    }
  }, []);

  const valor = useMemo(
    () => ({ tema, temaEfetivo, definirTema }),
    [tema, temaEfetivo, definirTema],
  );

  return (
    <ContextoDeTema.Provider value={valor}>{children}</ContextoDeTema.Provider>
  );
}

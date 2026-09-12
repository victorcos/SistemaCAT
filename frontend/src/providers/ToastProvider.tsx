import {
  createContext,
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Aviso, type TomDeAviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { IconeCopiar } from "@/constants/icons";

export interface Recado {
  tom?: TomDeAviso;
  titulo?: ReactNode;
  texto?: ReactNode;
  codigo?: string;
  /** Segredo mostrado uma única vez, em bloco monoespaçado com botão Copiar.
   *  É a senha provisória: o servidor não a devolve de novo. */
  segredo?: string;
  /** ms até sumir sozinho. `null` fica até o usuário dispensar — o padrão
   *  quando há segredo, porque ninguém decora senha em cinco segundos. */
  duracao?: number | null;
}

interface Contexto {
  mostrar: (r: Recado) => void;
  sucesso: (titulo: ReactNode, texto?: ReactNode) => void;
  erro: (titulo: ReactNode, texto?: ReactNode) => void;
}

export const ContextoDeToast = createContext<Contexto | null>(null);

const PADRAO_MS = 5000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [fila, setFila] = useState<(Recado & { id: number })[]>([]);

  const dispensar = useCallback(
    (id: number) => setFila((f) => f.filter((r) => r.id !== id)),
    [],
  );

  const mostrar = useCallback(
    (r: Recado) => {
      const id = Date.now() + Math.random();
      setFila((f) => [...f, { ...r, id }]);
      const duracao = r.duracao === undefined ? (r.segredo ? null : PADRAO_MS) : r.duracao;
      if (duracao !== null) window.setTimeout(() => dispensar(id), duracao);
    },
    [dispensar],
  );

  const valor = useMemo<Contexto>(
    () => ({
      mostrar,
      sucesso: (titulo, texto) => mostrar({ tom: "sucesso", titulo, texto }),
      erro: (titulo, texto) => mostrar({ tom: "erro", titulo, texto }),
    }),
    [mostrar],
  );

  return (
    <ContextoDeToast.Provider value={valor}>
      {children}
      {createPortal(
        <div
          aria-live="polite"
          className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4"
        >
          {fila.map((r) => (
            <Aviso
              key={r.id}
              tom={r.tom ?? "info"}
              titulo={r.titulo}
              codigo={r.codigo}
              aoFechar={() => dispensar(r.id)}
              className="animate-entrada pointer-events-auto w-full max-w-[520px] shadow-cat-alta"
            >
              {r.texto}
              {r.segredo && <Segredo valor={r.segredo} />}
            </Aviso>
          ))}
        </div>,
        document.body,
      )}
    </ContextoDeToast.Provider>
  );
}

function Segredo({ valor }: { valor: string }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <code className="rounded-raio border border-dashed border-current/50 bg-black/25 px-3 py-2 font-mono text-[15px] tracking-[0.06em]">
        {valor}
      </code>
      <Botao
        tamanho="sm"
        variante="secundario"
        icone={IconeCopiar}
        onClick={() => {
          navigator.clipboard.writeText(valor).then(
            () => {
              setCopiado(true);
              window.setTimeout(() => setCopiado(false), 2000);
            },
            () => {
              /* sem permissão de área de transferência: a senha está à vista */
            },
          );
        }}
      >
        {copiado ? "Copiado" : "Copiar"}
      </Botao>
    </div>
  );
}

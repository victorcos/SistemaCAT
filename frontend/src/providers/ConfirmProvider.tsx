import { createContext, useCallback, useRef, useState, type ReactNode } from "react";
import { Botao, type VarianteDeBotao } from "@/components/ui/Botao";
import { Modal } from "@/components/ui/Modal";

export interface PedidoDeConfirmacao {
  titulo: ReactNode;
  texto?: ReactNode;
  rotuloConfirmar?: string;
  rotuloCancelar?: string;
  variante?: VarianteDeBotao;
}

interface Contexto {
  confirmar: (pedido: PedidoDeConfirmacao) => Promise<boolean>;
}

export const ContextoDeConfirmacao = createContext<Contexto | null>(null);

/**
 * Confirmação como promessa, no lugar de `window.confirm`.
 *
 *   if (await confirmar({ titulo: "Desativar Ana?" })) { ... }
 *
 * O confirm nativo trava a aba inteira, não é estilizável, não dá para
 * traduzir e em alguns navegadores mostra "esta página diz:" — péssimo para
 * uma ação destrutiva. Estava em uso em pages/Usuarios.tsx (duas vezes).
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pedido, setPedido] = useState<PedidoDeConfirmacao | null>(null);
  // guarda o resolve da promessa entre o pedido e o clique do usuário
  const resolver = useRef<((ok: boolean) => void) | null>(null);

  const confirmar = useCallback((p: PedidoDeConfirmacao) => {
    setPedido(p);
    return new Promise<boolean>((res) => {
      resolver.current = res;
    });
  }, []);

  const responder = useCallback((ok: boolean) => {
    setPedido(null);
    resolver.current?.(ok);
    resolver.current = null;
  }, []);

  return (
    <ContextoDeConfirmacao.Provider value={{ confirmar }}>
      {children}
      <Modal
        aberto={!!pedido}
        // fechar pelo X, pelo Esc ou pelo backdrop conta como "não"
        aoFechar={() => responder(false)}
        titulo={pedido?.titulo ?? ""}
        tamanho="sm"
        rodape={
          <>
            <Botao variante="secundario" onClick={() => responder(false)}>
              {pedido?.rotuloCancelar ?? "Cancelar"}
            </Botao>
            <Botao
              variante={pedido?.variante ?? "principal"}
              onClick={() => responder(true)}
              autoFocus
            >
              {pedido?.rotuloConfirmar ?? "Confirmar"}
            </Botao>
          </>
        }
      >
        <p className="m-0 text-[13px] leading-relaxed text-texto-suave">
          {pedido?.texto}
        </p>
      </Modal>
    </ContextoDeConfirmacao.Provider>
  );
}

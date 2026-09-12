import { useContext } from "react";
import { ContextoDeConfirmacao } from "@/providers/ConfirmProvider";

export function useConfirm() {
  const ctx = useContext(ContextoDeConfirmacao);
  if (!ctx)
    throw new Error("useConfirm precisa estar dentro de <ConfirmProvider>");
  return ctx.confirmar;
}

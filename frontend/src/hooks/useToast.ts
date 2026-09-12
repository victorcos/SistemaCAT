import { useContext } from "react";
import { ContextoDeToast } from "@/providers/ToastProvider";

export function useToast() {
  const ctx = useContext(ContextoDeToast);
  if (!ctx) throw new Error("useToast precisa estar dentro de <ToastProvider>");
  return ctx;
}

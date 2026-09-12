import { useContext } from "react";
import { ContextoDeAuth } from "@/providers/AuthProvider";

export function useAuth() {
  const ctx = useContext(ContextoDeAuth);
  if (!ctx) throw new Error("useAuth precisa estar dentro de <AuthProvider>");
  return ctx;
}

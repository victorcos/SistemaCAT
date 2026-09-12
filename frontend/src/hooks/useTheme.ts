import { useContext } from "react";
import { ContextoDeTema } from "@/providers/ThemeProvider";

export function useTheme() {
  const ctx = useContext(ContextoDeTema);
  if (!ctx) throw new Error("useTheme precisa estar dentro de <ThemeProvider>");
  return ctx;
}

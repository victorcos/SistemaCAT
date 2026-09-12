import { Navigate, Outlet } from "react-router-dom";
import { ROTAS } from "@/constants/routes";
import { useAuth } from "@/hooks/useAuth";
import type { Papel } from "@/types/auth";

/**
 * Esconde a tela de quem não tem o papel.
 *
 * A API recusaria de todo jeito — oferecer o que vai dar 403 é má educação.
 * Quem barra de verdade continua sendo o servidor.
 */
export function ExigePapel({ papeis }: { papeis: Papel[] }) {
  const { usuario } = useAuth();
  if (!usuario || !papeis.includes(usuario.papel)) {
    return <Navigate to={ROTAS.inicio} replace />;
  }
  return <Outlet />;
}

import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Carregando } from "@/components/ui/Carregando";
import { destinoDeVolta } from "@/constants/routes";
import { useAuth } from "@/hooks/useAuth";

interface Estado {
  de?: string;
}

/** O contrário da RotaProtegida: quem já entrou não vê a tela de login. */
export function RotaPublica() {
  const { usuario, verificando } = useAuth();
  const local = useLocation();

  if (verificando) return <Carregando texto="Verificando sessão…" />;
  if (usuario) {
    return <Navigate to={destinoDeVolta((local.state as Estado | null)?.de)} replace />;
  }
  return <Outlet />;
}

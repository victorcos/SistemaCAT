import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Carregando } from "@/components/ui/Carregando";
import { destinoDaEntrada } from "@/constants/routes";
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
    // mesmo destino do login: quem já entrou e volta ao /login vai parar onde
    // teria parado ao entrar — e não numa lista que talvez não seja a dele
    return <Navigate to={destinoDaEntrada(usuario, (local.state as Estado | null)?.de)} replace />;
  }
  return <Outlet />;
}

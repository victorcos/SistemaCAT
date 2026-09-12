import { Outlet } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { BarraTopo } from "./BarraTopo";
import { MenuLateral } from "./MenuLateral";

/**
 * A moldura da aplicação: menu lateral + barra de topo + conteúdo.
 *
 * Não recebe mais prop nenhuma. Antes vinham `usuario` e `aoSair` descendo de
 * App.tsx; hoje a sessão está no AuthProvider e quem precisa dela pega.
 */
export default function Leiaute() {
  const { usuario } = useAuth();
  // a rota so chega aqui autenticada; o null e do tipo, nao da realidade
  if (!usuario) return null;

  return (
    <div className="flex min-h-screen flex-col bg-fundo md:flex-row">
      <MenuLateral papel={usuario.papel} />
      <div className="flex min-w-0 flex-1 flex-col">
        <BarraTopo usuario={usuario} />
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

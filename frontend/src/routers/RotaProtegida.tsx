import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Carregando } from "@/components/ui/Carregando";
import { ROTAS } from "@/constants/routes";
import { useAuth } from "@/hooks/useAuth";

/**
 * Exige sessão, e trata a senha provisória.
 *
 * Antes isto eram dois `early return` em App.tsx, ANTES do <BrowserRouter> —
 * por isso não existia a URL /login, e Login e TrocarSenha não podiam usar
 * nenhum hook de rota. A garantia continua a mesma ("não existe rota que
 * escape da troca de senha"), só que agora é uma guarda de rota, auditável.
 */
export function RotaProtegida() {
  const { usuario, verificando } = useAuth();
  const local = useLocation();

  if (verificando) return <Carregando texto="Verificando sessão…" />;

  if (!usuario) {
    // guarda de onde veio, para voltar para lá depois de entrar
    return <Navigate to={ROTAS.login} replace state={{ de: local.pathname }} />;
  }

  // A guarda vale nos DOIS sentidos, e o segundo nao e detalhe: sem ele, quem
  // nao tem senha provisoria consegue ficar parado em /trocar-senha para
  // sempre — inclusive logo depois de trocar a senha, quando a marca acabou de
  // cair e nada mais navegaria para fora.
  const naTroca = local.pathname === ROTAS.trocarSenha;
  if (usuario.senha_provisoria && !naTroca) {
    return <Navigate to={ROTAS.trocarSenha} replace />;
  }
  if (!usuario.senha_provisoria && naTroca) {
    return <Navigate to={ROTAS.inicio} replace />;
  }

  return <Outlet />;
}

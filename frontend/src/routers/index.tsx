import { createBrowserRouter, Outlet } from "react-router-dom";
import { ADMINISTRA_USUARIOS } from "@/constants/roles";
import { ROTAS } from "@/constants/routes";
import Leiaute from "@/layout/Leiaute";
import Conferencia from "@/pages/Conferencia";
import Importar from "@/pages/Importar";
import Inicio from "@/pages/Inicio";
import Login from "@/pages/Login";
import Lote from "@/pages/Lote";
import Movimentos from "@/pages/Movimentos";
import Projeto from "@/pages/Projeto";
import TrocarSenha from "@/pages/TrocarSenha";
import Usuarios from "@/pages/Usuarios";
import { AuthProvider } from "@/providers/AuthProvider";
import { ConfirmProvider } from "@/providers/ConfirmProvider";
import { ToastProvider } from "@/providers/ToastProvider";
import { ExigePapel } from "./ExigePapel";
import NaoEncontrada from "./NaoEncontrada";
import { RotaProtegida } from "./RotaProtegida";
import { RotaPublica } from "./RotaPublica";

/**
 * A raiz da árvore existe para hospedar os providers.
 *
 * O AuthProvider usa useNavigate (para mandar ao login quando a sessão
 * expira), e useNavigate só funciona dentro do router. Por isso ele fica
 * aqui, e não em volta do <RouterProvider>. O ThemeProvider, que não depende
 * de rota, fica em main.tsx.
 */
function Raiz() {
  return (
    <AuthProvider>
      <ToastProvider>
        <ConfirmProvider>
          <Outlet />
        </ConfirmProvider>
      </ToastProvider>
    </AuthProvider>
  );
}

/**
 * Lazy loading ainda NÃO.
 *
 * As primitivas compartilhadas ainda vivem em styles/legacy-kit.css e o CSS
 * das páginas ainda é importado por cada uma delas. Enquanto uma página
 * depender do CSS de outra, dividir o bundle deixa telas sem botão e sem
 * tabela. Ligar `lazy:` nas quatro pesadas (Importar, Lote, Conferencia,
 * Movimentos) na fase de fechamento, junto com a reativação do preflight.
 */
export const roteador = createBrowserRouter([
  {
    element: <Raiz />,
    children: [
      {
        element: <RotaPublica />,
        children: [{ path: ROTAS.login, element: <Login /> }],
      },
      {
        element: <RotaProtegida />,
        children: [
          { path: ROTAS.trocarSenha, element: <TrocarSenha /> },
          {
            element: <Leiaute />,
            children: [
              { path: ROTAS.inicio, element: <Inicio /> },
              { path: ROTAS.importar, element: <Importar /> },
              { path: "/projetos/:id", element: <Projeto /> },
              { path: "/projetos/:id/arquivos", element: <Lote /> },
              { path: "/projetos/:id/conferencia", element: <Conferencia /> },
              { path: "/projetos/:id/movimentos", element: <Movimentos /> },
              {
                element: <ExigePapel papeis={ADMINISTRA_USUARIOS} />,
                children: [{ path: ROTAS.usuarios, element: <Usuarios /> }],
              },
            ],
          },
        ],
      },
      { path: "*", element: <NaoEncontrada /> },
    ],
  },
]);

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
 * Sobre dividir o pacote (`lazy:`).
 *
 * O impedimento que havia aqui — páginas dependendo do CSS umas das outras —
 * acabou em 12/09/2026, quando a última tela migrou e styles/legacy-kit.css
 * saiu do projeto. Hoje cada página é autossuficiente e a divisão é segura.
 *
 * Segue sem dividir porque ainda não se paga: o pacote inteiro tem 110 kB
 * comprimido, e o sistema roda em rede interna. Dividir aqui trocaria uma
 * carga única e rápida por um piscar de Suspense a cada navegação. Vale
 * reavaliar quando alguma tela trouxer biblioteca pesada — tabela
 * virtualizada ou gráfico, por exemplo.
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

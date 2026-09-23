import { createBrowserRouter, Outlet } from "react-router-dom";
import { ADMINISTRA_USUARIOS } from "@/constants/roles";
import { ROTAS } from "@/constants/routes";
import Leiaute from "@/layout/Leiaute";
import Conferencia from "@/pages/Conferencia";
import Gestao from "@/pages/Gestao";
import Historico from "@/pages/Historico";
import Importar from "@/pages/Importar";
import Inicio from "@/pages/Inicio";
import Login from "@/pages/Login";
import Lote from "@/pages/Lote";
import Movimentos from "@/pages/Movimentos";
import Apuracao from "@/pages/Apuracao";
import ArquivoDigital from "@/pages/ArquivoDigital";
import PreValidacao from "@/pages/PreValidacao";
import QuebraDeSped from "@/pages/QuebraDeSped";
import Entrega from "@/pages/Entrega";
import ModulosDoSegmento from "@/pages/ModulosDoSegmento";
import Razao from "@/pages/Razao";
import Segmentos from "@/pages/Segmentos";
import RazaoContabil from "@/pages/RazaoContabil";
import DePara from "@/pages/DePara";
import Suportado from "@/pages/Suportado";
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
              // o hub e a escolha de frente: a porta de entrada, antes de
              // qualquer trabalho. Ficam na mesma moldura do resto porque o
              // menu lateral é o caminho de volta — sem ele, quem entrasse
              // direto num módulo não teria como trocar de assunto
              { path: "/segmentos", element: <Segmentos /> },
              { path: "/segmentos/:chave", element: <ModulosDoSegmento /> },
              { path: "/modulos/:chave", element: <Inicio /> },
              { path: ROTAS.importar, element: <Importar /> },
              { path: "/projetos/:id", element: <Projeto /> },
              { path: "/projetos/:id/arquivos", element: <Lote /> },
              { path: "/projetos/:id/conferencia", element: <Conferencia /> },
              { path: "/projetos/:id/movimentos", element: <Movimentos /> },
              { path: "/projetos/:id/suportado", element: <Suportado /> },
              { path: "/projetos/:id/razao", element: <Razao /> },
              { path: "/projetos/:id/depara", element: <DePara /> },
              { path: "/projetos/:id/apuracao", element: <Apuracao /> },
              { path: "/projetos/:id/arquivo-digital", element: <ArquivoDigital /> },
              { path: "/projetos/:id/pre-validacao", element: <PreValidacao /> },
              { path: "/projetos/:id/quebra-de-sped", element: <QuebraDeSped /> },
              { path: "/projetos/:id/razao-contabil", element: <RazaoContabil /> },
              { path: "/projetos/:id/apuracao-contribuicoes", element: <Gestao /> },
              { path: "/projetos/:id/entrega", element: <Entrega /> },
              { path: "/projetos/:id/historico", element: <Historico /> },
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

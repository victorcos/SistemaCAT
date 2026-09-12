import { RouterProvider } from "react-router-dom";
import { roteador } from "@/routers";

/** O App encolheu de propósito: a sessão virou provider (providers/
 *  AuthProvider) e as rotas viraram árvore (routers/index). O que sobrou é
 *  montar o roteador. */
export default function App() {
  return <RouterProvider router={roteador} />;
}

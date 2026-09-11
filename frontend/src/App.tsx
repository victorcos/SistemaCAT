import { useEffect, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import Leiaute from "./componentes/Leiaute";
import Conferencia from "./paginas/Conferencia";
import Importar from "./paginas/Importar";
import Inicio from "./paginas/Inicio";
import Login from "./paginas/Login";
import Lote from "./paginas/Lote";
import Movimentos from "./paginas/Movimentos";
import Projeto from "./paginas/Projeto";
import TrocarSenha from "./paginas/TrocarSenha";
import Usuarios from "./paginas/Usuarios";
import { lerToken } from "./servicos/api";
import { quemSouEu, sair } from "./servicos/auth";
import { ADMINISTRA_USUARIOS, type Usuario } from "./tipos/auth";

export default function App() {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [verificando, setVerificando] = useState(true);

  // havendo token guardado, confirma com o servidor antes de mostrar a
  // aplicação: ele pode ter expirado ou o usuário ter sido desativado
  useEffect(() => {
    if (!lerToken()) {
      setVerificando(false);
      return;
    }
    quemSouEu()
      .then(setUsuario)
      .catch(() => sair())
      .finally(() => setVerificando(false));
  }, []);

  if (verificando) {
    return <div className="carregando">Verificando sessão…</div>;
  }

  if (!usuario) {
    return <Login aoEntrar={setUsuario} />;
  }

  // quem entrou com senha provisória só faz uma coisa: trocar a senha.
  // Fica antes do roteador de propósito — não existe rota que escape disto.
  if (usuario.senha_provisoria) {
    return <TrocarSenha usuario={usuario} aoTrocar={setUsuario} />;
  }

  const admin = ADMINISTRA_USUARIOS.includes(usuario.papel);

  return (
    <BrowserRouter>
      <Routes>
        <Route
          element={<Leiaute usuario={usuario} aoSair={() => setUsuario(null)} />}
        >
          <Route path="/" element={<Inicio usuario={usuario} />} />
          <Route path="/importar" element={<Importar />} />
          <Route path="/projetos/:id" element={<Projeto usuario={usuario} />} />
          <Route path="/projetos/:id/arquivos" element={<Lote />} />
          <Route path="/projetos/:id/conferencia" element={<Conferencia />} />
          <Route path="/projetos/:id/movimentos" element={<Movimentos />} />
          <Route
            path="/usuarios"
            element={
              // a tela some para quem não administra; a API recusaria de todo
              // jeito, mas oferecer o que vai dar 403 é má educação
              admin ? <Usuarios eu={usuario} /> : <Navigate to="/" replace />
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

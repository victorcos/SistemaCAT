import { useEffect, useState } from "react";
import Login from "./paginas/Login";
import { quemSouEu, sair } from "./servicos/auth";
import { lerToken } from "./servicos/api";
import type { Usuario } from "./tipos/auth";

export default function App() {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [verificando, setVerificando] = useState(true);

  // se já houver token guardado, confirma com o servidor antes de mostrar a
  // aplicação — o token pode ter expirado ou o usuário ter sido desativado
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

  // provisório: a aplicação em si entra na etapa 5 do roteiro
  return (
    <div style={{ padding: 32 }}>
      <h1>Olá, {usuario.nome_exibicao}</h1>
      <p>
        Papel: {usuario.papel} · Empresas no seu escopo:{" "}
        {usuario.empresas.length}
      </p>
      <button
        className="botao botao--principal"
        onClick={() => {
          sair();
          setUsuario(null);
        }}
      >
        Sair
      </button>
    </div>
  );
}

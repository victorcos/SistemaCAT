import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ROTAS } from "@/constants/routes";
import { ADMINISTRA_USUARIOS, PODE_EXCLUIR_TRABALHO } from "@/constants/roles";
import { entrar as entrarNaApi, quemSouEu } from "@/services/auth";
import { aoExpirarSessao, lerToken, limparToken } from "@/services/sessao";
import type { Usuario } from "@/types/auth";

interface Contexto {
  usuario: Usuario | null;
  /** true enquanto a sessão guardada ainda está sendo confirmada com o servidor */
  verificando: boolean;
  entrar: (usuario: string, senha: string) => Promise<Usuario>;
  sair: () => void;
  /** troca o usuário em memória sem ir ao servidor (após trocar a senha, p. ex.) */
  definirUsuario: (u: Usuario) => void;
  administraUsuarios: boolean;
  podeExcluirTrabalho: boolean;
}

export const ContextoDeAuth = createContext<Contexto | null>(null);

/**
 * A sessão, num lugar só.
 *
 * Antes o usuário morava no estado de App.tsx e descia por prop para Leiaute,
 * Inicio, Projeto e Usuarios. Além do incômodo, isso impedia qualquer
 * componente fundo na árvore de saber quem está logado sem receber prop.
 *
 * Precisa ficar DENTRO do router: usa useNavigate para mandar ao login quando
 * a sessão expira.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [verificando, setVerificando] = useState(true);
  const navegar = useNavigate();
  const local = useLocation();

  // havendo token guardado, confirma com o servidor antes de mostrar a
  // aplicação: ele pode ter expirado ou o usuário ter sido desativado
  useEffect(() => {
    if (!lerToken()) {
      setVerificando(false);
      return;
    }
    quemSouEu()
      .then(setUsuario)
      .catch(() => limparToken())
      .finally(() => setVerificando(false));
  }, []);

  // sessão que expira no meio do uso: services/api.ts avisa por aqui.
  // Sem isto o token sumia e a tela ficava presa no erro, sem saída.
  useEffect(
    () =>
      aoExpirarSessao(() => {
        setUsuario(null);
        navegar(ROTAS.login, { replace: true, state: { de: local.pathname } });
      }),
    [navegar, local.pathname],
  );

  const entrar = useCallback(async (nome: string, senha: string) => {
    const r = await entrarNaApi(nome, senha);
    setUsuario(r.usuario);
    return r.usuario;
  }, []);

  const sair = useCallback(() => {
    limparToken();
    setUsuario(null);
    navegar(ROTAS.login, { replace: true });
  }, [navegar]);

  const valor = useMemo<Contexto>(
    () => ({
      usuario,
      verificando,
      entrar,
      sair,
      definirUsuario: setUsuario,
      administraUsuarios: !!usuario && ADMINISTRA_USUARIOS.includes(usuario.papel),
      podeExcluirTrabalho:
        !!usuario && PODE_EXCLUIR_TRABALHO.includes(usuario.papel),
    }),
    [usuario, verificando, entrar, sair],
  );

  return (
    <ContextoDeAuth.Provider value={valor}>{children}</ContextoDeAuth.Provider>
  );
}

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Campo, CampoSenha, Entrada } from "@/components/ui/Campo";
import { destinoDeVolta, ROTAS } from "@/constants/routes";
import { useAuth } from "@/hooks/useAuth";
import { LeiauteAcesso } from "@/layout/LeiauteAcesso";
import { comoErro } from "@/lib/errors";
import type { ErroApi } from "@/types/erro";

export default function Login() {
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const campoUsuario = useRef<HTMLInputElement>(null);
  const { entrar } = useAuth();
  const navegar = useNavigate();
  const local = useLocation();

  useEffect(() => {
    campoUsuario.current?.focus();
  }, []);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (enviando) return;
    setErro(null);
    setEnviando(true);
    try {
      const u = await entrar(usuario.trim(), senha);
      // quem entra com senha provisória só faz uma coisa: trocar a senha
      const destino = u.senha_provisoria
        ? ROTAS.trocarSenha
        : destinoDeVolta((local.state as { de?: string } | null)?.de);
      navegar(destino, { replace: true });
    } catch (e) {
      setErro(comoErro(e));
      setSenha("");
    } finally {
      setEnviando(false);
    }
  }

  const podeEnviar = usuario.trim().length >= 3 && senha.length > 0 && !enviando;

  return (
    <LeiauteAcesso
      titulo="Entrar"
      sub="Use as credenciais fornecidas pelo gestor da sua equipe."
      rodape={
        <p className="m-0 max-w-[380px] text-[13px] leading-relaxed text-texto-fraco">
          Esqueceu a senha ou o acesso está bloqueado? Procure um gestor da
          equipe. Por segurança, a redefinição não é automática.
        </p>
      }
    >
      <form className="flex flex-col gap-4" onSubmit={enviar} noValidate>
        <Campo rotulo="Usuário">
          {(props) => (
            <Entrada
              {...props}
              ref={campoUsuario}
              type="text"
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              disabled={enviando}
              required
            />
          )}
        </Campo>

        <Campo rotulo="Senha">
          {(props) => (
            <CampoSenha
              {...props}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              autoComplete="current-password"
              disabled={enviando}
              required
            />
          )}
        </Campo>

        {erro && (
          <Aviso tom="erro" titulo={erro.message} codigo={erro.requisicaoId} />
        )}

        <Botao type="submit" disabled={!podeEnviar} carregando={enviando} largo>
          {enviando ? "Entrando…" : "Entrar"}
        </Botao>
      </form>
    </LeiauteAcesso>
  );
}

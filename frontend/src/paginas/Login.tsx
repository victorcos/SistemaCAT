import { useEffect, useRef, useState, type FormEvent } from "react";
import { entrar } from "../servicos/auth";
import { ErroApi, type Usuario } from "../tipos/auth";
import logo from "../ativos/bms-branco.png";
import logoMarinho from "../ativos/bms-marinho.png";
import "./Login.css";

interface Props {
  aoEntrar: (usuario: Usuario) => void;
}

export default function Login({ aoEntrar }: Props) {
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const campoUsuario = useRef<HTMLInputElement>(null);

  useEffect(() => {
    campoUsuario.current?.focus();
  }, []);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (enviando) return;
    setErro(null);
    setEnviando(true);
    try {
      const r = await entrar(usuario.trim(), senha);
      aoEntrar(r.usuario);
    } catch (e) {
      setErro(
        e instanceof ErroApi
          ? e
          : new ErroApi("Erro inesperado. Tente novamente.", 0),
      );
      setSenha("");
    } finally {
      setEnviando(false);
    }
  }

  const podeEnviar = usuario.trim().length >= 3 && senha.length > 0 && !enviando;

  return (
    <div className="login">
      {/* Lado da marca, em marinho: aqui vale a versão de tinta clara. */}
      <aside className="login__marca" aria-hidden="true">
        <img src={logo} alt="" className="login__logo" />
        <p className="login__assinatura">
          Sistema de apuração das obrigações da CAT
        </p>
      </aside>

      <main className="login__area">
        <form className="login__caixa" onSubmit={enviar} noValidate>
          {/* em tela estreita o formulário fica sobre fundo claro, então
              entra a versão marinho, sem caixa azul de remendo */}
          <img
            src={logoMarinho}
            alt="BMS Consultoria Tributária"
            className="login__logo-movel"
          />

          <h1 className="login__titulo">Entrar</h1>
          <p className="login__subtitulo">
            Use as credenciais fornecidas pelo gestor da sua equipe.
          </p>

          <label className="campo">
            <span className="campo__rotulo">Usuário</span>
            <input
              ref={campoUsuario}
              className="campo__entrada"
              type="text"
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              disabled={enviando}
              required
            />
          </label>

          <label className="campo">
            <span className="campo__rotulo">Senha</span>
            <div className="campo__com-botao">
              <input
                className="campo__entrada"
                type={mostrarSenha ? "text" : "password"}
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                autoComplete="current-password"
                disabled={enviando}
                required
              />
              <button
                type="button"
                className="campo__alternar"
                onClick={() => setMostrarSenha((v) => !v)}
                aria-label={mostrarSenha ? "Ocultar senha" : "Mostrar senha"}
                disabled={enviando}
              >
                {mostrarSenha ? "ocultar" : "mostrar"}
              </button>
            </div>
          </label>

          {/* role=alert faz o leitor de tela anunciar sem precisar de foco */}
          {erro && (
            <div className="aviso aviso--erro" role="alert">
              <strong>{erro.message}</strong>
              {erro.requisicaoId && (
                <span className="aviso__codigo">
                  Código para suporte: {erro.requisicaoId}
                </span>
              )}
            </div>
          )}

          <button className="botao botao--principal" type="submit" disabled={!podeEnviar}>
            {enviando ? "Entrando…" : "Entrar"}
          </button>

          <p className="login__ajuda">
            Esqueceu a senha ou o acesso está bloqueado? Procure um gestor da
            equipe. Por segurança, a redefinição não é automática.
          </p>
        </form>

        <footer className="login__rodape">
          BMS Consultoria Tributária · Sistema CAT
        </footer>
      </main>
    </div>
  );
}

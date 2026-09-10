import { useState, type FormEvent } from "react";
import { trocarPropriaSenha } from "../servicos/usuarios";
import { quemSouEu } from "../servicos/auth";
import { ErroApi, type Usuario } from "../tipos/auth";
import logo from "../ativos/logo-bms-branco.png";
import "./TrocarSenha.css";

interface Props {
  usuario: Usuario;
  aoTrocar: (u: Usuario) => void;
}

const MINIMO = 10;

/**
 * Troca obrigatória da senha provisória.
 *
 * Aparece no lugar da aplicação, sem menu e sem saída pelos lados: quem entrou
 * com senha provisória só faz isto. É o que fecha o ciclo desenhado no backend,
 * onde a senha gerada pelo gestor vale para um acesso só.
 */
export default function TrocarSenha({ usuario, aoTrocar }: Props) {
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [repetida, setRepetida] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);

  const problemas = avaliar(nova);
  const confere = nova.length > 0 && nova === repetida;
  const podeEnviar =
    atual.length > 0 && problemas.length === 0 && confere && !enviando;

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (!podeEnviar) return;
    setEnviando(true);
    setErro(null);
    try {
      await trocarPropriaSenha(atual, nova);
      // relê do servidor: é ele quem diz se a marca de provisória saiu
      aoTrocar(await quemSouEu());
    } catch (e) {
      setErro(
        e instanceof ErroApi
          ? e
          : new ErroApi("Erro inesperado. Tente novamente.", 0),
      );
      setAtual("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="troca">
      <div className="troca__caixa">
        <img src={logo} alt="" className="troca__logo" aria-hidden="true" />

        <h1 className="troca__titulo">Defina sua senha</h1>
        <p className="troca__sub">
          Olá, {usuario.nome_exibicao}. Você entrou com uma senha provisória,
          que vale para este acesso apenas. Escolha uma senha sua para
          continuar.
        </p>

        <form onSubmit={enviar} noValidate>
          <label className="campo">
            <span className="campo__rotulo">Senha provisória</span>
            <input
              className="campo__entrada"
              type="password"
              value={atual}
              onChange={(e) => setAtual(e.target.value)}
              autoComplete="current-password"
              autoFocus
              disabled={enviando}
            />
          </label>

          <label className="campo">
            <span className="campo__rotulo">Nova senha</span>
            <input
              className="campo__entrada"
              type="password"
              value={nova}
              onChange={(e) => setNova(e.target.value)}
              autoComplete="new-password"
              disabled={enviando}
            />
          </label>

          {/* a política aparece antes do erro, não depois: o usuário vê o que
              falta enquanto digita, em vez de descobrir ao enviar */}
          <ul className="regras">
            {REGRAS.map((r) => {
              const ok = nova.length > 0 && r.testa(nova);
              return (
                <li
                  key={r.texto}
                  className={`regras__item${ok ? " regras__item--ok" : ""}`}
                >
                  <span aria-hidden="true">{ok ? "✓" : "•"}</span> {r.texto}
                </li>
              );
            })}
          </ul>

          <label className="campo">
            <span className="campo__rotulo">Repita a nova senha</span>
            <input
              className="campo__entrada"
              type="password"
              value={repetida}
              onChange={(e) => setRepetida(e.target.value)}
              autoComplete="new-password"
              disabled={enviando}
            />
            {repetida.length > 0 && !confere && (
              <span className="campo__dica campo__dica--erro">
                As duas senhas não são iguais.
              </span>
            )}
          </label>

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

          <button type="submit" className="botao botao--principal" disabled={!podeEnviar}>
            {enviando ? "Salvando…" : "Salvar e entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}

/* A política é a mesma do domínio. Repetida aqui para dar retorno imediato,
   mas quem decide continua sendo o servidor. */
const REGRAS = [
  { texto: `Pelo menos ${MINIMO} caracteres`, testa: (s: string) => s.length >= MINIMO },
  {
    texto: "Maiúsculas e minúsculas",
    testa: (s: string) => s !== s.toLowerCase() && s !== s.toUpperCase(),
  },
  { texto: "Pelo menos um número", testa: (s: string) => /\d/.test(s) },
  { texto: "Sem espaço no início ou no fim", testa: (s: string) => s.trim() === s },
];

function avaliar(senha: string): string[] {
  return REGRAS.filter((r) => !r.testa(senha)).map((r) => r.texto);
}

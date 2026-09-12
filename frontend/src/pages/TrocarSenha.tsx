import { useState, type FormEvent } from "react";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Campo, CampoSenha } from "@/components/ui/Campo";
import { ForcaDaSenha, senhaServe } from "@/components/ui/ForcaDaSenha";
import { useAuth } from "@/hooks/useAuth";
import { LeiauteAcesso } from "@/layout/LeiauteAcesso";
import { comoErro } from "@/lib/errors";
import { quemSouEu } from "@/services/auth";
import { trocarPropriaSenha } from "@/services/usuarios";
import type { ErroApi } from "@/types/erro";

/**
 * Troca obrigatória da senha provisória.
 *
 * Aparece no lugar da aplicação, sem menu e sem saída pelos lados: quem entrou
 * com senha provisória só faz isto. É o que fecha o ciclo desenhado no
 * backend, onde a senha gerada pelo gestor vale para um acesso só.
 */
export default function TrocarSenha() {
  const { usuario, definirUsuario } = useAuth();
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [repetida, setRepetida] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);

  const confere = nova.length > 0 && nova === repetida;
  const podeEnviar = atual.length > 0 && senhaServe(nova) && confere && !enviando;

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (!podeEnviar) return;
    setEnviando(true);
    setErro(null);
    try {
      await trocarPropriaSenha(atual, nova);
      // relê do servidor: é ele quem diz se a marca de provisória saiu
      definirUsuario(await quemSouEu());
    } catch (e) {
      setErro(comoErro(e));
      setAtual("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <LeiauteAcesso
      titulo="Defina sua senha"
      sub={
        <>
          Olá, {usuario?.nome_exibicao}. Você entrou com uma senha provisória, que vale para este
          acesso apenas. Escolha uma senha sua para continuar.
        </>
      }
    >
      <form className="flex flex-col gap-4" onSubmit={enviar} noValidate>
        <Campo rotulo="Senha provisória">
          {(props) => (
            <CampoSenha
              {...props}
              value={atual}
              onChange={(e) => setAtual(e.target.value)}
              autoComplete="current-password"
              autoFocus
              disabled={enviando}
            />
          )}
        </Campo>

        <Campo rotulo="Nova senha">
          {(props) => (
            <CampoSenha
              {...props}
              value={nova}
              onChange={(e) => setNova(e.target.value)}
              autoComplete="new-password"
              disabled={enviando}
            />
          )}
        </Campo>

        <ForcaDaSenha senha={nova} />

        <Campo
          rotulo="Repita a nova senha"
          erro={repetida.length > 0 && !confere ? "As duas senhas não são iguais." : undefined}
        >
          {(props) => (
            <CampoSenha
              {...props}
              value={repetida}
              onChange={(e) => setRepetida(e.target.value)}
              autoComplete="new-password"
              disabled={enviando}
            />
          )}
        </Campo>

        {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} />}

        <Botao type="submit" largo carregando={enviando} disabled={!podeEnviar}>
          Salvar e entrar
        </Botao>
      </form>
    </LeiauteAcesso>
  );
}

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/hooks/useAuth";
import { dataHora } from "@/lib/format";
import { comoErro } from "@/lib/errors";
import {
  alterarCargo,
  alterarPapel,
  criarUsuario,
  definirSituacao,
  desbloquear,
  listarUsuarios,
  redefinirSenha,
} from "@/services/usuarios";
import { CARGOS, PAPEIS } from "@/constants/roles";
import { ErroApi } from "@/types/erro";
import { type Cargo, type Papel, type Usuario, type UsuarioResumo } from "@/types/auth";
import SenhaProvisoria from "@/components/shared/SenhaProvisoria";
import "./Usuarios.css";

/** Senha recém-gerada, mostrada uma única vez. */
interface Revelada {
  senha: string;
  usuario: string;
  motivo: "criado" | "redefinido";
}

export default function Usuarios() {
  const { usuario: eu } = useAuth();
  const [usuarios, setUsuarios] = useState<UsuarioResumo[] | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [revelada, setRevelada] = useState<Revelada | null>(null);
  const [criando, setCriando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setUsuarios(await listarUsuarios());
      setErro(null);
    } catch (e) {
      setErro(comoErro(e));
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  /** Envolve toda ação de linha: marca ocupado, trata erro, recarrega. */
  async function agir(id: number, acao: () => Promise<unknown>) {
    setOcupado(id);
    setErro(null);
    try {
      await acao();
      await carregar();
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(null);
    }
  }

  async function aoRedefinir(u: UsuarioResumo) {
    const texto =
      `Gerar nova senha provisória para ${u.nome_exibicao}?\n\n` +
      "A senha atual deixa de funcionar na hora, e a nova aparece uma única vez.";
    if (!confirm(texto)) return;
    await agir(u.id, async () => {
      const r = await redefinirSenha(u.id);
      setRevelada({
        senha: r.senha_provisoria,
        usuario: u.nome_exibicao,
        motivo: "redefinido",
      });
    });
  }

  async function aoDesativar(u: UsuarioResumo) {
    if (u.ativo && !confirm(`Desativar ${u.nome_exibicao}? Ele perde o acesso.`)) {
      return;
    }
    await agir(u.id, () => definirSituacao(u.id, !u.ativo));
  }

  // Depois dos hooks, de proposito: um return antes deles mudaria a
  // quantidade de hooks entre renders e o React quebraria. A rota so chega
  // aqui autenticada; o null e do tipo, nao da realidade.
  if (!eu) return null;

  if (erro && !usuarios) {
    return <Aviso erro={erro} aoTentarDeNovo={carregar} />;
  }

  return (
    <div className="pagina">
      <header className="pagina__topo">
        <div>
          <h1 className="pagina__titulo">Usuários</h1>
          <p className="pagina__sub">
            Cadastro e redefinição de senha ficam com gestores. Não há
            autocadastro nem recuperação por e-mail.
          </p>
        </div>
        <button
          type="button"
          className="botao botao--principal"
          onClick={() => setCriando(true)}
        >
          Novo usuário
        </button>
      </header>

      {erro && <Aviso erro={erro} />}

      {revelada && (
        <SenhaProvisoria
          senha={revelada.senha}
          usuario={revelada.usuario}
          motivo={revelada.motivo}
          aoFechar={() => setRevelada(null)}
        />
      )}

      {criando && (
        <FormularioNovo
          aoCancelar={() => setCriando(false)}
          aoCriar={(r) => {
            setCriando(false);
            setRevelada({
              senha: r.senha,
              usuario: r.nome,
              motivo: "criado",
            });
            carregar();
          }}
          aoFalhar={setErro}
        />
      )}

      {!usuarios ? (
        <p className="pagina__carregando">Carregando…</p>
      ) : (
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead>
              <tr>
                <th>Usuário</th>
                <th>Nome</th>
                <th>Papel</th>
                <th>Cargo</th>
                <th>Situação</th>
                <th>Último acesso</th>
                <th className="tabela__acoes-cabecalho">Ações</th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map((u) => (
                <Linha
                  key={u.id}
                  u={u}
                  eu={eu}
                  ocupado={ocupado === u.id}
                  aoMudarPapel={(p) => agir(u.id, () => alterarPapel(u.id, p))}
                  aoMudarCargo={(c) => agir(u.id, () => alterarCargo(u.id, c))}
                  aoRedefinir={() => aoRedefinir(u)}
                  aoDesbloquear={() => agir(u.id, () => desbloquear(u.id))}
                  aoAlternarSituacao={() => aoDesativar(u)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
function Linha({
  u,
  eu,
  ocupado,
  aoMudarPapel,
  aoMudarCargo,
  aoRedefinir,
  aoDesbloquear,
  aoAlternarSituacao,
}: {
  u: UsuarioResumo;
  eu: Usuario;
  ocupado: boolean;
  aoMudarPapel: (p: Papel) => void;
  aoMudarCargo: (c: Cargo) => void;
  aoRedefinir: () => void;
  aoDesbloquear: () => void;
  aoAlternarSituacao: () => void;
}) {
  const souEu = u.id === eu.id;

  return (
    <tr className={`${!u.ativo ? "tabela__linha--inativa" : ""}`}>
      <td>
        <span className="mono">{u.usuario}</span>
        {souEu && <span className="marca-voce">você</span>}
      </td>
      <td>
        {u.nome_exibicao}
        <div className="celula__secundaria">{u.email}</div>
      </td>
      <td>
        <select
          className="selecao"
          value={u.papel}
          disabled={ocupado || souEu}
          title={souEu ? "Você não pode alterar o próprio papel." : undefined}
          onChange={(e) => aoMudarPapel(e.target.value as Papel)}
        >
          {(Object.keys(PAPEIS) as Papel[]).map((p) => (
            <option key={p} value={p}>
              {PAPEIS[p].rotulo}
            </option>
          ))}
        </select>
      </td>
      <td>
        <select
          className="selecao"
          value={u.cargo}
          disabled={ocupado}
          onChange={(e) => aoMudarCargo(e.target.value as Cargo)}
        >
          {(Object.keys(CARGOS) as Cargo[]).map((c) => (
            <option key={c} value={c}>
              {CARGOS[c]}
            </option>
          ))}
        </select>
      </td>
      <td>
        <div className="situacao">
          {!u.ativo && <span className="pilula pilula--inativa">Inativo</span>}
          {u.bloqueado && (
            <span className="pilula pilula--bloqueada">
              Bloqueado · {u.tentativas_falhas} tentativas
            </span>
          )}
          {u.senha_provisoria && (
            <span className="pilula pilula--provisoria">Senha provisória</span>
          )}
          {u.ativo && !u.bloqueado && !u.senha_provisoria && (
            <span className="pilula pilula--ok">Ativo</span>
          )}
        </div>
      </td>
      <td className="celula__secundaria">{dataHora(u.ultimo_acesso)}</td>
      <td>
        <div className="acoes">
          <button type="button" className="acao" disabled={ocupado} onClick={aoRedefinir}>
            Redefinir senha
          </button>
          {u.bloqueado && (
            <button type="button" className="acao" disabled={ocupado} onClick={aoDesbloquear}>
              Desbloquear
            </button>
          )}
          <button
            type="button"
            className={`acao ${u.ativo ? "acao--perigo" : ""}`}
            disabled={ocupado || souEu}
            title={souEu ? "Você não pode desativar a si mesmo." : undefined}
            onClick={aoAlternarSituacao}
          >
            {u.ativo ? "Desativar" : "Reativar"}
          </button>
        </div>
      </td>
    </tr>
  );
}

/* ------------------------------------------------------------------ */
function FormularioNovo({
  aoCriar,
  aoCancelar,
  aoFalhar,
}: {
  aoCriar: (r: { senha: string; nome: string }) => void;
  aoCancelar: () => void;
  aoFalhar: (e: ErroApi) => void;
}) {
  const [usuario, setUsuario] = useState("");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [papel, setPapel] = useState<Papel>("leitura");
  const [cargo, setCargo] = useState<Cargo>("analista");
  const [enviando, setEnviando] = useState(false);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setEnviando(true);
    try {
      const r = await criarUsuario({
        usuario: usuario.trim(),
        email: email.trim(),
        nome_exibicao: nome.trim(),
        papel,
        cargo,
      });
      aoCriar({ senha: r.senha_provisoria, nome: r.usuario.nome_exibicao });
    } catch (e) {
      aoFalhar(comoErro(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form className="cartao cartao--formulario" onSubmit={enviar}>
      <h2 className="cartao__titulo">Novo usuário</h2>
      <p className="cartao__sub">
        A senha é gerada pelo sistema e aparece uma única vez. A troca é
        obrigatória no primeiro acesso.
      </p>

      <div className="grade">
        <label className="campo">
          <span className="campo__rotulo">Nome de usuário</span>
          <input
            className="campo__entrada mono"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            placeholder="ana.silva"
            autoCapitalize="none"
            spellCheck={false}
            required
          />
          <span className="campo__dica">
            Não pode ser alterado depois. Letras minúsculas, números, ponto,
            hífen e sublinhado.
          </span>
        </label>

        <label className="campo">
          <span className="campo__rotulo">Nome completo</span>
          <input
            className="campo__entrada"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            required
          />
        </label>

        <label className="campo">
          <span className="campo__rotulo">E-mail</span>
          <input
            className="campo__entrada"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>

        <label className="campo">
          <span className="campo__rotulo">Papel</span>
          <select
            className="campo__entrada"
            value={papel}
            onChange={(e) => setPapel(e.target.value as Papel)}
          >
            {(Object.keys(PAPEIS) as Papel[]).map((p) => (
              <option key={p} value={p}>
                {PAPEIS[p].rotulo}
              </option>
            ))}
          </select>
          <span className="campo__dica">{PAPEIS[papel].ajuda}</span>
        </label>

        <label className="campo">
          <span className="campo__rotulo">Cargo</span>
          <select
            className="campo__entrada"
            value={cargo}
            onChange={(e) => setCargo(e.target.value as Cargo)}
          >
            {(Object.keys(CARGOS) as Cargo[]).map((c) => (
              <option key={c} value={c}>
                {CARGOS[c]}
              </option>
            ))}
          </select>
          <span className="campo__dica">
            Posição na empresa. Não define permissão.
          </span>
        </label>
      </div>

      <div className="cartao__acoes">
        <button
          type="button"
          className="botao botao--secundario"
          onClick={aoCancelar}
          disabled={enviando}
        >
          Cancelar
        </button>
        <button type="submit" className="botao botao--principal" disabled={enviando}>
          {enviando ? "Criando…" : "Criar usuário"}
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
function Aviso({
  erro,
  aoTentarDeNovo,
}: {
  erro: ErroApi;
  aoTentarDeNovo?: () => void;
}) {
  return (
    <div className="aviso aviso--erro" role="alert">
      <strong>{erro.message}</strong>
      {erro.requisicaoId && (
        <span className="aviso__codigo">
          Código para suporte: {erro.requisicaoId}
        </span>
      )}
      {aoTentarDeNovo && (
        <button type="button" className="botao botao--secundario" onClick={aoTentarDeNovo}>
          Tentar de novo
        </button>
      )}
    </div>
  );
}


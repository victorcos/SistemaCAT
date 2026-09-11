import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  detalharProjeto,
  excluirProjeto,
  previaDaExclusao,
  type OQueSeraApagado,
  type ProjetoDetalhe,
} from "../servicos/importacao";
import { ErroApi, PODE_EXCLUIR_TRABALHO, type Usuario } from "../tipos/auth";
import "./Projeto.css";

export default function Projeto({ usuario }: { usuario: Usuario }) {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<ProjetoDetalhe | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [aExcluir, setAExcluir] = useState<OQueSeraApagado | null>(null);
  const podeExcluir = PODE_EXCLUIR_TRABALHO.includes(usuario.papel);

  useEffect(() => {
    if (!id) return;
    detalharProjeto(Number(id))
      .then(setD)
      .catch((e) =>
        setErro(e instanceof ErroApi ? e : new ErroApi("Erro inesperado.", 0)),
      );
  }, [id]);

  if (erro) {
    return (
      <div className="pagina">
        <div className="aviso aviso--erro" role="alert">
          <strong>{erro.message}</strong>
          {erro.requisicaoId && (
            <span className="aviso__codigo">
              Código para suporte: {erro.requisicaoId}
            </span>
          )}
        </div>
        <Link to="/">Voltar aos trabalhos</Link>
      </div>
    );
  }

  if (!d) return <p className="pagina__carregando">Carregando…</p>;

  const p = d.projeto;

  return (
    <div className="pagina">
      <Link to="/" className="voltar">
        ← Trabalhos
      </Link>

      <header className="projeto__cabecalho">
        <div>
          <h1 className="pagina__titulo">{p.empresa}</h1>
          <p className="projeto__cnpj mono">
            {p.cnpj_matriz_formatado ?? "CNPJ não informado"}
            {p.uf && <span className="projeto__uf">{p.uf}</span>}
          </p>
        </div>
        <dl className="projeto__resumo">
          <div>
            <dt>Frente</dt>
            <dd>{p.frente_rotulo}</dd>
          </div>
          <div>
            <dt>Projeto</dt>
            <dd>{p.nome}</dd>
          </div>
          <div>
            <dt>Competências</dt>
            <dd className="mono">
              {mes(p.competencia_ini)} a {mes(p.competencia_fim)}
            </dd>
          </div>
        </dl>
      </header>

      <h2 className="secao__titulo">Etapas do processamento</h2>
      <p className="secao__sub">
        A ordem é de dependência real: sem os movimentos não há razão, e sem o
        razão não há apuração.
      </p>

      <ol className="etapas">
        {d.etapas.map((e, i) => (
          <li key={e.chave} className={`etapa etapa--${e.situacao}`}>
            <div className="etapa__marca">
              {e.situacao === "concluida" ? "✓" : i + 1}
            </div>
            <div className="etapa__corpo">
              <div className="etapa__linha">
                <h3 className="etapa__nome">{e.nome}</h3>
                <span className={`selo selo--${e.situacao}`}>
                  {e.situacao_rotulo}
                </span>
              </div>
              <p className="etapa__descricao">{e.descricao}</p>
              {/* leva ao lote DESTE trabalho. Antes apontava para /importar,
                  que é o cadastro: recomeçaria a criação da empresa. */}
              {e.chave === "importar" && e.acessivel && (
                <Link className="etapa__acao" to={`/projetos/${id}/arquivos`}>
                  {e.situacao === "concluida"
                    ? "Importar mais arquivos"
                    : "Importar a base de dados"}
                </Link>
              )}
              {e.chave === "conferencia" && e.acessivel && (
                <Link className="etapa__acao" to={`/projetos/${id}/conferencia`}>
                  {e.situacao === "concluida"
                    ? "Ver o resultado e baixar as planilhas"
                    : e.situacao === "em_andamento"
                      ? "Acompanhar a conferência"
                      : "Conferir documentos"}
                </Link>
              )}
              {e.chave === "movimentos" && e.acessivel && (
                <Link className="etapa__acao" to={`/projetos/${id}/movimentos`}>
                  {e.situacao === "concluida"
                    ? "Ver o histórico e baixar as planilhas"
                    : e.situacao === "em_andamento"
                      ? "Acompanhar a extração"
                      : "Extrair movimentos"}
                </Link>
              )}
            </div>
          </li>
        ))}
      </ol>

      {podeExcluir && (
        <section className="zona-perigosa">
          <div>
            <h2 className="zona-perigosa__titulo">Excluir este trabalho</h2>
            <p className="zona-perigosa__texto">
              Some o projeto, os lotes importados e as conferências já feitas.
              Não há como desfazer, e não há lixeira. Os arquivos do cliente em
              disco não são tocados.
            </p>
          </div>
          <button
            type="button"
            className="botao botao--perigo"
            onClick={() =>
              previaDaExclusao(Number(id))
                .then(setAExcluir)
                .catch((e) => setErro(comoErro(e)))
            }
          >
            Excluir trabalho
          </button>
        </section>
      )}

      {aExcluir && (
        <ConfirmarExclusao
          projetoId={Number(id)}
          alvo={aExcluir}
          aoFechar={() => setAExcluir(null)}
        />
      )}
    </div>
  );
}

/**
 * A confirmação da exclusão.
 *
 * Pede a senha de novo de propósito: a sessão fica aberta a jornada inteira, e
 * uma tela deixada em máquina destravada não pode bastar para desfazer meses
 * de apuração. É a única operação do sistema que exige isso.
 */
function ConfirmarExclusao({
  projetoId,
  alvo,
  aoFechar,
}: {
  projetoId: number;
  alvo: OQueSeraApagado;
  aoFechar: () => void;
}) {
  const navegar = useNavigate();
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function apagar(evento: FormEvent) {
    evento.preventDefault();
    setOcupado(true);
    setErro(null);
    try {
      await excluirProjeto(projetoId, senha);
      navegar("/", { replace: true });
    } catch (e) {
      setErro(comoErro(e));
      setSenha("");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="cortina" role="dialog" aria-modal="true"
         aria-labelledby="titulo-exclusao">
      <form className="caixa" onSubmit={apagar}>
        <h2 className="caixa__titulo" id="titulo-exclusao">
          Apagar &ldquo;{alvo.projeto}&rdquo;?
        </h2>
        <p className="caixa__texto">
          De <strong>{alvo.empresa}</strong>. Vão junto:
        </p>
        <ul className="caixa__lista">
          <li>
            <strong>{alvo.lotes.toLocaleString("pt-BR")}</strong> lote(s)
            importado(s)
          </li>
          <li>
            <strong>{alvo.arquivos.toLocaleString("pt-BR")}</strong> arquivo(s)
            registrado(s)
          </li>
          <li>
            <strong>{alvo.execucoes.toLocaleString("pt-BR")}</strong>{" "}
            conferência(s)
          </li>
        </ul>
        <p className="caixa__texto">
          Não há como desfazer. Os arquivos do cliente em disco continuam onde
          estão — some o trabalho dentro do sistema.
        </p>

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

        <div className="campo campo--largo">
          <label htmlFor="senha-exclusao">
            Confirme com a sua senha de acesso
          </label>
          <input
            id="senha-exclusao"
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            autoComplete="current-password"
            autoFocus
            required
          />
        </div>

        <div className="caixa__acoes">
          <button
            type="submit"
            className="botao botao--perigo"
            disabled={ocupado || senha.length === 0}
          >
            {ocupado ? "Apagando…" : "Sim, apagar este trabalho"}
          </button>
          <button
            type="button"
            className="botao botao--secundario"
            onClick={aoFechar}
            disabled={ocupado}
          >
            Cancelar
          </button>
        </div>
      </form>
    </div>
  );
}

function comoErro(e: unknown): ErroApi {
  return e instanceof ErroApi ? e : new ErroApi("Erro inesperado.", 0);
}

function mes(iso: string): string {
  const [a, m] = iso.split("-");
  return `${m}/${a}`;
}

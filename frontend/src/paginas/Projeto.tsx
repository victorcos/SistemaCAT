import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { detalharProjeto, type ProjetoDetalhe } from "../servicos/importacao";
import { ErroApi } from "../tipos/auth";
import "./Projeto.css";

export default function Projeto() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<ProjetoDetalhe | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);

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
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function mes(iso: string): string {
  const [a, m] = iso.split("-");
  return `${m}/${a}`;
}

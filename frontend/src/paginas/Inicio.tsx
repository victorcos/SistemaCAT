import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listarProjetos, type Projeto } from "../servicos/importacao";
import { ErroApi, type Usuario } from "../tipos/auth";
import "./Inicio.css";

const STATUS: Record<string, string> = {
  em_andamento: "Em andamento",
  concluido: "Concluído",
  pausado: "Pausado",
};

export default function Inicio({ usuario }: { usuario: Usuario }) {
  const [projetos, setProjetos] = useState<Projeto[] | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);

  useEffect(() => {
    listarProjetos()
      .then(setProjetos)
      .catch((e) =>
        setErro(
          e instanceof ErroApi ? e : new ErroApi("Erro inesperado.", 0),
        ),
      );
  }, []);

  return (
    <div className="pagina">
      <header className="pagina__topo">
        <div>
          <h1 className="pagina__titulo">Trabalhos</h1>
          <p className="pagina__sub">
            Olá, {usuario.nome_exibicao}. Cada cartão é um projeto. Clique para
            ver as etapas de processamento.
          </p>
        </div>
        <Link className="botao botao--principal" to="/importar">
          Importar arquivos
        </Link>
      </header>

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

      {!projetos ? (
        <p className="pagina__carregando">Carregando…</p>
      ) : projetos.length === 0 ? (
        <Vazio />
      ) : (
        <div className="cartoes">
          {projetos.map((p) => (
            <CartaoProjeto key={p.id} p={p} />
          ))}
        </div>
      )}
    </div>
  );
}

function CartaoProjeto({ p }: { p: Projeto }) {
  const pct = p.etapas_totais
    ? Math.round((p.etapas_feitas / p.etapas_totais) * 100)
    : 0;

  return (
    <Link to={`/projetos/${p.id}`} className="cartao-projeto">
      <div className="cartao-projeto__topo">
        <span className={`selo selo--${p.status}`}>
          {STATUS[p.status] ?? p.status}
        </span>
        {p.pre_cadastro && (
          <span className="selo selo--pre" title="Dados vieram do arquivo e ainda não foram conferidos">
            Pré-cadastro
          </span>
        )}
      </div>

      <h2 className="cartao-projeto__empresa">{p.empresa}</h2>
      <p className="cartao-projeto__cnpj mono">
        {p.cnpj_matriz_formatado ?? "CNPJ não informado"}
        {p.uf && <span className="cartao-projeto__uf">{p.uf}</span>}
      </p>

      <div className="cartao-projeto__meio">
        <span className="cartao-projeto__frente">{p.frente_rotulo}</span>
        <span className="cartao-projeto__nome">{p.nome}</span>
      </div>

      <dl className="cartao-projeto__dados">
        <div>
          <dt>Competências</dt>
          <dd className="mono">
            {mes(p.competencia_ini)} a {mes(p.competencia_fim)}
          </dd>
        </div>
        <div>
          <dt>Etapas</dt>
          <dd className="mono">
            {p.etapas_feitas} de {p.etapas_totais}
          </dd>
        </div>
      </dl>

      <div className="barra" aria-hidden="true">
        <div className="barra__preenchida" style={{ width: `${pct}%` }} />
      </div>
    </Link>
  );
}

function Vazio() {
  return (
    <div className="vazio">
      <h2 className="vazio__titulo">Nenhum trabalho ainda</h2>
      <p className="vazio__texto">
        Comece importando o SPED de uma empresa. O sistema identifica o CNPJ e a
        razão social pelo próprio arquivo.
      </p>
      <Link className="botao botao--principal" to="/importar">
        Importar arquivos
      </Link>
    </div>
  );
}

function mes(iso: string): string {
  const [a, m] = iso.split("-");
  return `${m}/${a}`;
}

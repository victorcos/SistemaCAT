import { useCallback, useEffect, useRef, useState } from "react";
import { dinheiro, numero, tamanho } from "@/lib/format";
import { comoErro } from "@/lib/errors";
import { INTERVALO_POLL_MS } from "@/constants/polling";
import { Link, useParams } from "react-router-dom";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import {
  EM_CURSO,
  type Fatia,
} from "@/services/conferencia";
import {
  baixarPlanilhaDeMovimentos,
  detalharMovimentos,
  iniciarMovimentos,
  listarMovimentos,
  type ExecucaoDeMovimentos,
  type PlanilhaDeMovimentos,
  type ResumoDaMovimentacao,
} from "@/services/movimentos";
import { ErroApi } from "@/types/erro";
import "./Conferencia.css";

/**
 * Histórico de movimentação — terceira etapa.
 *
 * Lê os itens de cada documento da EFD (C170), o analítico (C190/C850), o
 * cadastro (0200) e o inventário (bloco H), e marca cada movimento com o que
 * a conferência achou. A tela diz também o que a EFD não tem: NF-e própria e
 * cupom SAT vêm sem item, e esse detalhe virá do XML.
 */
export default function Movimentos() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [execucao, setExecucao] = useState<ExecucaoDeMovimentos | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [classes, setClasses] = useState<string[]>([]);
  const relogio = useRef<number | null>(null);

  const acompanhar = useCallback(async (execucaoId: number) => {
    try {
      const atual = await detalharMovimentos(execucaoId);
      setExecucao(atual);
      if (!EM_CURSO.includes(atual.situacao) && relogio.current !== null) {
        window.clearInterval(relogio.current);
        relogio.current = null;
      }
    } catch (e) {
      setErro(comoErro(e));
    }
  }, []);

  useEffect(() => {
    if (!projetoId) return;
    detalharProjeto(projetoId).then(setProjeto).catch((e) => setErro(comoErro(e)));
    listarMovimentos(projetoId)
      .then((lista) => {
        const ultima = lista[0] ?? null;
        setExecucao(ultima);
        if (ultima && EM_CURSO.includes(ultima.situacao)) {
          relogio.current = window.setInterval(
            () => acompanhar(ultima.id),
            INTERVALO_POLL_MS,
          );
        }
      })
      .catch((e) => setErro(comoErro(e)));

    return () => {
      if (relogio.current !== null) window.clearInterval(relogio.current);
    };
  }, [projetoId, acompanhar]);

  async function comecar() {
    setOcupado(true);
    setErro(null);
    try {
      const nova = await iniciarMovimentos(projetoId);
      setExecucao(nova);
      setClasses([]);
      relogio.current = window.setInterval(() => acompanhar(nova.id), INTERVALO_POLL_MS);
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  async function baixar(qual: PlanilhaDeMovimentos) {
    if (!execucao) return;
    setOcupado(true);
    setErro(null);
    try {
      await baixarPlanilhaDeMovimentos(
        execucao.id,
        qual,
        [],
        qual === "movimentos" ? classes : [],
      );
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  const rodando = execucao !== null && EM_CURSO.includes(execucao.situacao);
  const resumo = execucao?.situacao === "concluida" ? execucao.resumo : null;

  return (
    <div className="pagina">
      <Link to={`/projetos/${projetoId}`} className="voltar">
        ← Voltar ao trabalho
      </Link>

      <header className="pagina__topo">
        <div>
          <h1 className="pagina__titulo">Extrair movimentos</h1>
          <p className="pagina__sub">
            {projeto ? (
              <>
                Lê os itens de cada documento da EFD de{" "}
                <strong>{projeto.projeto.empresa}</strong> (C170), o analítico,
                o cadastro de item e o inventário — e marca cada movimento com o
                que a conferência achou. É a matéria-prima do razão.
              </>
            ) : (
              "Carregando…"
            )}
          </p>
        </div>
        <button
          type="button"
          className="botao botao--principal"
          onClick={comecar}
          disabled={ocupado || rodando}
        >
          {rodando ? "Extraindo…" : execucao ? "Extrair de novo" : "Extrair"}
        </button>
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

      {!execucao && (
        <div className="vazio">
          <h2 className="vazio__titulo">Nenhuma extração ainda</h2>
          <p className="vazio__texto">
            Precisa de uma conferência concluída: é a lista de conferidos dela
            que marca cada movimento. Lê toda a EFD do trabalho — numa base
            grande leva minutos, e continua rodando se você sair desta tela.
          </p>
        </div>
      )}

      {rodando && execucao && <Andamento e={execucao} />}

      {execucao?.situacao === "falhou" && (
        <div className="aviso aviso--erro" role="alert">
          <strong>A extração falhou.</strong>
          <span className="aviso__codigo mono">{execucao.erro}</span>
        </div>
      )}

      {resumo && (
        <Resultado
          resumo={resumo}
          execucao={execucao}
          classes={classes}
          aoAlternarClasse={(codigo) =>
            setClasses((atuais) =>
              atuais.includes(codigo)
                ? atuais.filter((c) => c !== codigo)
                : [...atuais, codigo],
            )
          }
          aoBaixar={baixar}
          ocupado={ocupado}
        />
      )}
    </div>
  );
}

function Andamento({ e }: { e: ExecucaoDeMovimentos }) {
  const pct = Math.round(e.fracao * 100);
  return (
    <section className="cartao">
      <h2 className="cartao__titulo">{e.passo ?? "Processando"}</h2>
      <p className="cartao__sub">
        {numero(e.arquivos_lidos)} de {numero(e.arquivos_totais)} arquivos ·{" "}
        {numero(e.documentos)} documentos · {tamanho(e.bytes_lidos)}
      </p>
      <div className="barra" aria-label={`${pct}% concluído`}>
        <div className="barra__preenchida" style={{ width: `${pct}%` }} />
      </div>
      <p className="campo__dica">
        Pode fechar esta tela. A extração continua rodando no servidor.
      </p>
    </section>
  );
}

function Resultado({
  resumo,
  execucao,
  classes,
  aoAlternarClasse,
  aoBaixar,
  ocupado,
}: {
  resumo: ResumoDaMovimentacao;
  execucao: ExecucaoDeMovimentos | null;
  classes: string[];
  aoAlternarClasse: (codigo: string) => void;
  aoBaixar: (qual: PlanilhaDeMovimentos) => void;
  ocupado: boolean;
}) {
  const cobertura = Math.round(resumo.cobertura_de_item * 100);

  return (
    <>
      <section className="cartao">
        <h2 className="cartao__titulo">Resultado</h2>
        <p className="cartao__sub">
          {execucao?.terminada_em &&
            `Concluída em ${new Date(execucao.terminada_em).toLocaleString("pt-BR")}`}
        </p>

        <dl className="ficha">
          <div className="ficha__item">
            <dt className="ficha__rotulo">Documentos na EFD</dt>
            <dd className="ficha__valor">{numero(resumo.documentos)}</dd>
          </div>
          <div className="ficha__item">
            <dt className="ficha__rotulo">Com item na EFD</dt>
            <dd className="ficha__valor ficha__valor--destaque">
              {numero(resumo.documentos_com_item)}
              <span className="ficha__nota">{cobertura}% dos documentos</span>
            </dd>
          </div>
          <div className="ficha__item">
            <dt className="ficha__rotulo">Movimentos (linhas de item)</dt>
            <dd className="ficha__valor ficha__valor--destaque">
              {numero(resumo.movimentos)}
              <span className="ficha__nota">
                {dinheiro(resumo.valor_entradas)} em entradas ·{" "}
                {dinheiro(resumo.st_nas_entradas)} de ICMS-ST
              </span>
            </dd>
          </div>
          <div className="ficha__item">
            <dt className="ficha__rotulo">Saídas sem item na EFD</dt>
            <dd className="ficha__valor ficha__valor--destaque">
              {numero(resumo.saidas_sem_item)}
              <span className="ficha__nota">
                {dinheiro(resumo.valor_saidas_sem_item_st)} com CST 60
              </span>
            </dd>
          </div>
        </dl>

        <div className="barra barra--larga" aria-label="Cobertura de item">
          <div className="barra__preenchida" style={{ width: `${cobertura}%` }} />
        </div>

        {resumo.avisos.map((a) => (
          <div key={a} className="aviso aviso--atencao">
            {a}
          </div>
        ))}

        {resumo.recusados.length > 0 && (
          <div className="aviso aviso--atencao">
            <strong>Arquivos com problema na leitura</strong> — o que está
            aqui não entrou:
            <ul className="recusados">
              {resumo.recusados.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="cartao">
        <h2 className="cartao__titulo">Movimentos</h2>
        <p className="cartao__sub">
          Cada item de documento com o cadastro (descrição, NCM, CEST) e a marca
          da conferência. Ordenado por estabelecimento, item e data — é a ordem
          em que a ficha se lê.
        </p>
        <p className="numerao">{numero(resumo.movimentos)}</p>
        <Recortes titulo="Por CST das entradas" fatias={resumo.por_cst} />
        <Filtro
          titulo="Por marca da conferência"
          explicacao="Sem escolher nenhuma, a planilha traz todos."
          fatias={resumo.por_classificacao}
          escolhidos={classes}
          aoAlternar={aoAlternarClasse}
        />
        <button
          type="button"
          className="botao botao--principal"
          onClick={() => aoBaixar("movimentos")}
          disabled={ocupado || resumo.movimentos === 0}
        >
          {classes.length ? "Baixar planilha filtrada" : "Baixar planilha"}
        </button>
      </section>

      <section className="cartao">
        <h2 className="cartao__titulo">Cadastro de itens</h2>
        <p className="cartao__sub">
          O 0200 que vale: por estabelecimento e código, o do período mais
          recente. {numero(resumo.itens_movimentados)} códigos movimentados
          {resumo.itens_sem_cadastro > 0 &&
            `, ${numero(resumo.itens_sem_cadastro)} sem cadastro`}
          .
        </p>
        <p className="numerao">{numero(resumo.itens_cadastrados)}</p>
        <button
          type="button"
          className="botao botao--secundario"
          onClick={() => aoBaixar("itens")}
          disabled={ocupado || resumo.itens_cadastrados === 0}
        >
          Baixar planilha
        </button>
      </section>

      <section className="cartao">
        <h2 className="cartao__titulo">Inventário</h2>
        <p className="cartao__sub">
          O bloco H: o saldo de abertura da ficha, item a item.{" "}
          {numero(resumo.inventarios)} inventário(s),{" "}
          {dinheiro(resumo.valor_em_estoque)} em estoque.
        </p>
        <p className="numerao">{numero(resumo.itens_em_estoque)}</p>
        <button
          type="button"
          className="botao botao--secundario"
          onClick={() => aoBaixar("inventario")}
          disabled={ocupado || resumo.itens_em_estoque === 0}
        >
          Baixar planilha
        </button>
      </section>

      <section className="cartao">
        <h2 className="cartao__titulo">Analítico por documento</h2>
        <p className="cartao__sub">
          C190 e C850: o total por CST e CFOP de cada documento, com a marca de
          quem tem item na EFD e quem não tem. É por aqui que se vê o que o
          XML terá de detalhar.
        </p>
        <p className="numerao">{numero(resumo.analiticos)}</p>
        <Recortes
          titulo="Saídas sem item, por modelo"
          fatias={resumo.saidas_sem_item_por_modelo}
        />
        <button
          type="button"
          className="botao botao--secundario"
          onClick={() => aoBaixar("analitico")}
          disabled={ocupado || resumo.analiticos === 0}
        >
          Baixar planilha
        </button>
      </section>
    </>
  );
}

/** Uma lista de recortes só para ler, sem filtro. */
function Recortes({ titulo, fatias }: { titulo: string; fatias: Fatia[] }) {
  if (!fatias.length) return null;
  return (
    <>
      <p className="filtro__titulo">{titulo}</p>
      <div className="modelos">
        {fatias.map((f) => (
          <span key={f.codigo || f.rotulo} className="modelo">
            {f.rotulo} · {numero(f.documentos)} · {dinheiro(f.valor)}
          </span>
        ))}
      </div>
    </>
  );
}

function Filtro({
  titulo,
  explicacao,
  fatias,
  escolhidos,
  aoAlternar,
}: {
  titulo: string;
  explicacao: string;
  fatias: Fatia[];
  escolhidos: string[];
  aoAlternar: (codigo: string) => void;
}) {
  if (!fatias.length) return null;
  return (
    <>
      <p className="filtro__titulo">{titulo}</p>
      <p className="campo__dica">{explicacao}</p>
      <div className="modelos">
        {fatias.map((f) => (
          <label key={f.codigo} className="modelo">
            <input
              type="checkbox"
              checked={escolhidos.includes(f.codigo)}
              onChange={() => aoAlternar(f.codigo)}
            />
            {f.rotulo} · {numero(f.documentos)}
          </label>
        ))}
      </div>
    </>
  );
}


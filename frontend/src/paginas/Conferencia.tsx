import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { detalharProjeto, type ProjetoDetalhe } from "../servicos/importacao";
import {
  baixarPlanilha,
  detalharConferencia,
  dinheiro,
  EM_CURSO,
  iniciarConferencia,
  listarConferencias,
  numero,
  type Execucao,
  type Fatia,
  type ResumoDaConferencia,
} from "../servicos/conferencia";
import { tamanho } from "../servicos/lote";
import { ErroApi } from "../tipos/auth";
import "./Conferencia.css";

const INTERVALO_MS = 2000;

/**
 * Conferência de documentos.
 *
 * Cruza o que a EFD escriturou (C100 e C800) com o XML e o relatório do
 * cliente, e entrega as duas listas do trabalho: o que está na pasta e não foi
 * escriturado, que sai da análise, e o que foi escriturado sem documento, que
 * é o que se cobra.
 */
export default function Conferencia() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [execucao, setExecucao] = useState<Execucao | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [modelos, setModelos] = useState<string[]>([]);
  const [classes, setClasses] = useState<string[]>([]);
  const relogio = useRef<number | null>(null);

  const acompanhar = useCallback(async (execucaoId: number) => {
    try {
      const atual = await detalharConferencia(execucaoId);
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
    listarConferencias(projetoId)
      .then((lista) => {
        const ultima = lista[0] ?? null;
        setExecucao(ultima);
        if (ultima && EM_CURSO.includes(ultima.situacao)) {
          relogio.current = window.setInterval(
            () => acompanhar(ultima.id),
            INTERVALO_MS,
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
      const nova = await iniciarConferencia(projetoId);
      setExecucao(nova);
      setModelos([]);
      setClasses([]);
      if (relogio.current !== null) window.clearInterval(relogio.current);
      relogio.current = window.setInterval(() => acompanhar(nova.id), INTERVALO_MS);
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  async function baixar(qual: "nao-escrituradas" | "a-cobrar") {
    if (!execucao) return;
    setOcupado(true);
    setErro(null);
    try {
      await baixarPlanilha(
        execucao.id,
        qual,
        qual === "a-cobrar" ? modelos : [],
        qual === "a-cobrar" ? classes : [],
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
          <h1 className="pagina__titulo">Conferir documentos</h1>
          <p className="pagina__sub">
            {projeto ? (
              <>
                Cruza o que a EFD de <strong>{projeto.projeto.empresa}</strong>{" "}
                escriturou (C100 e C800) com o XML e o relatório do cliente. O
                que está na pasta e não foi escriturado sai da análise; o que
                foi escriturado sem documento é o que se cobra.
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
          {rodando ? "Conferindo…" : execucao ? "Conferir de novo" : "Conferir"}
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
          <h2 className="vazio__titulo">Nenhuma conferência ainda</h2>
          <p className="vazio__texto">
            A conferência lê toda a EFD do trabalho. Numa base grande isso leva
            minutos — pode sair desta tela, que ela continua rodando.
          </p>
        </div>
      )}

      {rodando && execucao && <Andamento e={execucao} />}

      {execucao?.situacao === "falhou" && (
        <div className="aviso aviso--erro" role="alert">
          <strong>A conferência falhou.</strong>
          <span className="aviso__codigo mono">{execucao.erro}</span>
        </div>
      )}

      {resumo && (
        <Resultado
          resumo={resumo}
          execucao={execucao}
          modelos={modelos}
          classes={classes}
          aoAlternarModelo={(codigo) => setModelos(alternar(codigo))}
          aoAlternarClasse={(codigo) => setClasses(alternar(codigo))}
          aoBaixar={baixar}
          ocupado={ocupado}
        />
      )}
    </div>
  );
}

/** Liga ou desliga um código na lista de filtros. */
const alternar = (codigo: string) => (atuais: string[]) =>
  atuais.includes(codigo)
    ? atuais.filter((c) => c !== codigo)
    : [...atuais, codigo];

function Andamento({ e }: { e: Execucao }) {
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
        Pode fechar esta tela. A conferência continua rodando no servidor.
      </p>
    </section>
  );
}

function Resultado({
  resumo,
  execucao,
  modelos,
  classes,
  aoAlternarModelo,
  aoAlternarClasse,
  aoBaixar,
  ocupado,
}: {
  resumo: ResumoDaConferencia;
  execucao: Execucao | null;
  modelos: string[];
  classes: string[];
  aoAlternarModelo: (codigo: string) => void;
  aoAlternarClasse: (codigo: string) => void;
  aoBaixar: (qual: "nao-escrituradas" | "a-cobrar") => void;
  ocupado: boolean;
}) {
  const cobertura = Math.round(resumo.cobertura * 100);

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
            <dt className="ficha__rotulo">Escrituradas na EFD</dt>
            <dd className="ficha__valor">{numero(resumo.escriturados)}</dd>
          </div>
          <div className="ficha__item">
            <dt className="ficha__rotulo">Com documento</dt>
            <dd className="ficha__valor ficha__valor--destaque">
              {numero(resumo.conferidos)}
              <span className="ficha__nota">{cobertura}% de cobertura</span>
            </dd>
          </div>
          <div className="ficha__item">
            <dt className="ficha__rotulo">Sem documento</dt>
            <dd className="ficha__valor ficha__valor--destaque">
              {numero(resumo.sem_documento)}
              <span className="ficha__nota">
                {dinheiro(resumo.valor_sem_documento)}
              </span>
            </dd>
          </div>
          <div className="ficha__item">
            <dt className="ficha__rotulo">Não escrituradas</dt>
            <dd className="ficha__valor ficha__valor--destaque">
              {numero(resumo.nao_escrituradas)}
              <span className="ficha__nota">saíram da análise</span>
            </dd>
          </div>
        </dl>

        <div className="barra barra--larga" aria-label="Cobertura">
          <div className="barra__preenchida" style={{ width: `${cobertura}%` }} />
        </div>

        {resumo.comparou && (
          <div className="andou">
            <strong>Desde a conferência anterior:</strong> {resumo.andou}
          </div>
        )}

        {resumo.avisos.map((a) => (
          <div key={a} className="aviso aviso--atencao">
            {a}
          </div>
        ))}
      </section>

      <section className="cartao">
        <h2 className="cartao__titulo">Notas não escrituradas</h2>
        <p className="cartao__sub">
          Estão na pasta do cliente e não estão na EFD. Ficam fora da análise:
          ressarcimento se pede sobre o que foi declarado ao fisco.
        </p>
        <p className="numerao">{numero(resumo.nao_escrituradas)}</p>
        <button
          type="button"
          className="botao botao--secundario"
          onClick={() => aoBaixar("nao-escrituradas")}
          disabled={ocupado || resumo.nao_escrituradas === 0}
        >
          Baixar planilha
        </button>
      </section>

      <section className="cartao cartao--cobranca">
        <h2 className="cartao__titulo">Notas a cobrar do cliente</h2>
        <p className="cartao__sub">
          Foram escrituradas e o documento não veio. Sem o XML não há como saber
          o ICMS-ST retido daquela nota. A planilha sai inteira: nada é
          excluído, e o que não se espera cobrar vai marcado do que é.
        </p>
        <p className="numerao">{numero(resumo.sem_documento)}</p>
        <p className="campo__dica">
          {numero(resumo.sem_documento_cobravel)} esperam documento do cliente.
        </p>

        <Filtro
          titulo="Por classificação"
          explicacao="Sem escolher nenhuma, a planilha traz todas — inclusive as canceladas e as sem chave, cada uma marcada."
          fatias={resumo.por_classificacao}
          escolhidos={classes}
          aoAlternar={aoAlternarClasse}
        />
        <Filtro
          titulo="Por modelo de documento"
          explicacao="Cupom de consumidor costuma dominar o volume, e não é XML que se peça um a um."
          fatias={resumo.por_modelo}
          escolhidos={modelos}
          aoAlternar={aoAlternarModelo}
        />

        <button
          type="button"
          className="botao botao--principal"
          onClick={() => aoBaixar("a-cobrar")}
          disabled={ocupado || resumo.sem_documento === 0}
        >
          {modelos.length || classes.length
            ? "Baixar planilha filtrada"
            : "Baixar planilha"}
        </button>
      </section>

      <section className="cartao">
        <h2 className="cartao__titulo">O cliente mandou o que faltava?</h2>
        <p className="cartao__sub">
          Importe os arquivos novos na base de dados e rode a conferência de
          novo. A próxima rodada compara com esta e diz quantas pendências
          saíram, quantas continuam e quantas apareceram — por isso nada é
          excluído da lista.
        </p>
        <Link
          className="botao botao--secundario"
          to={`/projetos/${execucao?.projeto_id}/arquivos`}
        >
          Importar mais arquivos
        </Link>
      </section>
    </>
  );
}

/** Um grupo de filtros da planilha, com a contagem de cada recorte. */
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
  // com um recorte só não há o que escolher
  if (fatias.length < 2) return null;
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
            <span>
              {f.rotulo} · {numero(f.documentos)}
            </span>
          </label>
        ))}
      </div>
    </>
  );
}

function comoErro(e: unknown): ErroApi {
  return e instanceof ErroApi ? e : new ErroApi("Erro inesperado.", 0);
}

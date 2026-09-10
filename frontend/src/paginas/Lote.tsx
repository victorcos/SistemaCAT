import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { detalharProjeto, type ProjetoDetalhe } from "../servicos/importacao";
import {
  competencia,
  inspecionarPasta,
  listarLotes,
  registrarLote,
  tamanho,
  type Lote as LoteRegistrado,
  type ResumoDoLote,
} from "../servicos/lote";
import { ErroApi } from "../tipos/auth";
import "./Lote.css";

/**
 * Importar a base de dados de um trabalho que já existe.
 *
 * É a outra ponta do cadastro: lá se descobre a empresa a partir de uma
 * amostra do SPED, aqui entra a base inteira. Os dois estavam na mesma tela, e
 * o link de dentro do projeto voltava ao cadastro — que recomeçaria a criação
 * da empresa.
 *
 * A tela pede um caminho de pasta, não um arquivo. A maior base que medimos
 * tem 7.036 arquivos, e um relatório gerencial sozinho tem 194 MB.
 */
export default function Lote() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [detalhe, setDetalhe] = useState<ProjetoDetalhe | null>(null);
  const [lotes, setLotes] = useState<LoteRegistrado[]>([]);
  const [pasta, setPasta] = useState("");
  const [observacao, setObservacao] = useState("");
  const [resumo, setResumo] = useState<ResumoDoLote | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [registrado, setRegistrado] = useState<LoteRegistrado | null>(null);

  useEffect(() => {
    if (!projetoId) return;
    detalharProjeto(projetoId).then(setDetalhe).catch((e) => setErro(comoErro(e)));
    listarLotes(projetoId).then(setLotes).catch((e) => setErro(comoErro(e)));
  }, [projetoId]);

  async function conferir(evento: FormEvent) {
    evento.preventDefault();
    setOcupado(true);
    setErro(null);
    setRegistrado(null);
    try {
      setResumo(await inspecionarPasta(projetoId, pasta));
    } catch (e) {
      setResumo(null);
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  async function confirmar() {
    if (!resumo) return;
    setOcupado(true);
    setErro(null);
    try {
      const novo = await registrarLote(projetoId, resumo.pasta, observacao || null);
      setRegistrado(novo);
      setResumo(null);
      setPasta("");
      setObservacao("");
      setLotes(await listarLotes(projetoId));
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  const p = detalhe?.projeto;

  return (
    <div className="pagina">
      <Link to={`/projetos/${projetoId}`} className="voltar">
        ← Voltar ao trabalho
      </Link>

      <header className="pagina__topo">
        <div>
          <h1 className="pagina__titulo">Importar base de dados</h1>
          <p className="pagina__sub">
            {p ? (
              <>
                Base de trabalho de <strong>{p.empresa}</strong>. Aponte a pasta
                onde estão a EFD ICMS/IPI, os XML e os relatórios do ERP. Nada é
                copiado: o sistema registra onde os arquivos estão e o que cada
                um é.
              </>
            ) : (
              "Carregando…"
            )}
          </p>
        </div>
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

      {registrado && (
        <div className="cartao cartao--sucesso">
          <h2 className="cartao__titulo">Lote registrado</h2>
          <p className="cartao__sub">
            {registrado.total_arquivos.toLocaleString("pt-BR")} arquivo(s),{" "}
            {registrado.arquivos_uteis.toLocaleString("pt-BR")} que a CAT 42 lê,{" "}
            {tamanho(registrado.bytes_totais)}.
          </p>
        </div>
      )}

      <form className="lote__forma" onSubmit={conferir}>
        <div className="campo campo--largo">
          <label htmlFor="pasta">Pasta com os arquivos</label>
          <input
            id="pasta"
            className="mono"
            value={pasta}
            onChange={(e) => setPasta(e.target.value)}
            placeholder="Z:\GRUPO PLURIX\...\EFD Fiscal - EFD ICMS IPI"
            spellCheck={false}
            autoComplete="off"
            required
          />
          <span className="campo__dica">
            Caminho como esta máquina o enxerga. Subpastas entram junto. Pasta
            grande em unidade de rede leva alguns minutos na primeira vez —
            depois disso o Windows já a tem em cache.
          </span>
        </div>
        <button type="submit" className="botao botao--principal" disabled={ocupado}>
          {ocupado ? "Lendo a pasta…" : "Conferir pasta"}
        </button>
      </form>

      {resumo && (
        <Conferencia
          resumo={resumo}
          observacao={observacao}
          aoMudarObservacao={setObservacao}
          aoConfirmar={confirmar}
          ocupado={ocupado}
        />
      )}

      <section className="lote__historico">
        <h2 className="secao__titulo">Lotes já importados</h2>
        {lotes.length === 0 ? (
          <p className="secao__sub">
            Nenhum ainda. Enquanto não houver base, as etapas seguintes ficam
            aguardando.
          </p>
        ) : (
          <ul className="lotes">
            {lotes.map((l) => (
              <li key={l.id} className="lote-item">
                <div className="lote-item__topo">
                  <span className="lote-item__pasta mono">{l.pasta}</span>
                  <span className="lote-item__data">
                    {new Date(l.criado_em).toLocaleDateString("pt-BR")}
                  </span>
                </div>
                <div className="lote-item__numeros">
                  <span>
                    <strong>{l.total_arquivos.toLocaleString("pt-BR")}</strong>{" "}
                    arquivos
                  </span>
                  <span>
                    <strong>{l.arquivos_uteis.toLocaleString("pt-BR")}</strong>{" "}
                    para a CAT
                  </span>
                  <span>{tamanho(l.bytes_totais)}</span>
                  {l.competencia_ini && (
                    <span className="mono">
                      {competencia(l.competencia_ini)} a{" "}
                      {competencia(l.competencia_fim)}
                    </span>
                  )}
                </div>
                <div className="etiquetas">
                  {l.contagens.map((c) => (
                    <span
                      key={c.tipo}
                      className={`etiqueta ${c.alimenta_a_cat ? "etiqueta--util" : ""}`}
                    >
                      {c.rotulo} · {c.quantidade.toLocaleString("pt-BR")}
                    </span>
                  ))}
                </div>
                {l.observacao && <p className="lote-item__nota">{l.observacao}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Conferencia({
  resumo,
  observacao,
  aoMudarObservacao,
  aoConfirmar,
  ocupado,
}: {
  resumo: ResumoDoLote;
  observacao: string;
  aoMudarObservacao: (v: string) => void;
  aoConfirmar: () => void;
  ocupado: boolean;
}) {
  const novos = resumo.total_arquivos - resumo.ja_no_trabalho;

  return (
    <section className="cartao">
      <h2 className="cartao__titulo">O que há nesta pasta</h2>
      <p className="cartao__sub mono">{resumo.pasta}</p>

      <dl className="ficha">
        <div className="ficha__item">
          <dt className="ficha__rotulo">Arquivos</dt>
          <dd className="ficha__valor">
            {resumo.total_arquivos.toLocaleString("pt-BR")}
          </dd>
        </div>
        <div className="ficha__item">
          <dt className="ficha__rotulo">A CAT 42 lê</dt>
          <dd className="ficha__valor ficha__valor--destaque">
            {resumo.arquivos_uteis.toLocaleString("pt-BR")}
          </dd>
        </div>
        <div className="ficha__item">
          <dt className="ficha__rotulo">Tamanho</dt>
          <dd className="ficha__valor">{tamanho(resumo.bytes_totais)}</dd>
        </div>
        <div className="ficha__item">
          <dt className="ficha__rotulo">Competências</dt>
          <dd className="ficha__valor mono">
            {resumo.competencia_ini
              ? `${competencia(resumo.competencia_ini)} a ${competencia(resumo.competencia_fim)}`
              : "—"}
          </dd>
        </div>
      </dl>

      <div className="etiquetas">
        {resumo.contagens.map((c) => (
          <span
            key={c.tipo}
            className={`etiqueta ${c.alimenta_a_cat ? "etiqueta--util" : ""}`}
            title={c.alimenta_a_cat ? "Alimenta a apuração" : "Não é lido pela CAT 42"}
          >
            {c.rotulo} · {c.quantidade.toLocaleString("pt-BR")}
          </span>
        ))}
      </div>

      {resumo.avisos.map((a) => (
        <div key={a} className="aviso aviso--atencao">
          {a}
        </div>
      ))}

      {resumo.ja_no_trabalho > 0 && (
        <div className="aviso aviso--atencao">
          {resumo.ja_no_trabalho.toLocaleString("pt-BR")} arquivo(s) já estão
          neste trabalho e não entram de novo. O mesmo SPED contado duas vezes
          dobraria movimento na apuração.
        </div>
      )}

      <h3 className="lote__subtitulo">
        Amostra — o que não entra aparece primeiro
      </h3>
      <div className="tabela-rolagem">
        <table className="tabela">
          <thead>
            <tr>
              <th>Arquivo</th>
              <th>Reconhecido como</th>
              <th>CNPJ</th>
              <th>Competência</th>
              <th>Tamanho</th>
            </tr>
          </thead>
          <tbody>
            {resumo.amostra.map((a) => (
              <tr
                key={a.caminho}
                className={a.alimenta_a_cat ? "" : "tabela__linha--inativa"}
              >
                <td title={a.caminho}>{a.nome}</td>
                <td>
                  {a.tipo_rotulo}
                  {a.detalhe && <span className="celula__nota">{a.detalhe}</span>}
                  {a.motivo && <span className="celula__nota">{a.motivo}</span>}
                </td>
                <td className="mono">{a.cnpj ?? "—"}</td>
                <td className="mono">{competencia(a.competencia)}</td>
                <td className="mono">{tamanho(a.tamanho)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="campo campo--largo">
        <label htmlFor="observacao">Observação (opcional)</label>
        <input
          id="observacao"
          value={observacao}
          onChange={(e) => aoMudarObservacao(e.target.value)}
          placeholder="De onde veio, o que a empresa disse, o que ainda falta"
          maxLength={500}
        />
      </div>

      <button
        type="button"
        className="botao botao--principal"
        onClick={aoConfirmar}
        disabled={ocupado || !resumo.serve || novos === 0}
      >
        {ocupado
          ? "Registrando…"
          : `Importar ${novos.toLocaleString("pt-BR")} arquivo(s)`}
      </button>
      {!resumo.serve && (
        <p className="campo__dica">
          Nada aqui alimenta a CAT 42, então não há o que importar.
        </p>
      )}
    </section>
  );
}

function comoErro(e: unknown): ErroApi {
  return e instanceof ErroApi ? e : new ErroApi("Erro inesperado.", 0);
}

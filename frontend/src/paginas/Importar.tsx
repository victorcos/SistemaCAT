import { useRef, useState, type DragEvent, type FormEvent } from "react";
import {
  analisarRemessa,
  criarEmpresa,
  criarProjeto,
  FRENTES,
  type Frente,
  type Remessa,
} from "../servicos/importacao";
import { ErroApi } from "../tipos/auth";
import "./Importar.css";

type Etapa = "envio" | "conferencia" | "projeto" | "pronto";

export default function Importar() {
  const [etapa, setEtapa] = useState<Etapa>("envio");
  const [remessa, setRemessa] = useState<Remessa | null>(null);
  const [empresaId, setEmpresaId] = useState<number | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState(false);

  function reiniciar() {
    setEtapa("envio");
    setRemessa(null);
    setEmpresaId(null);
    setErro(null);
  }

  async function enviar(arquivo: File) {
    setOcupado(true);
    setErro(null);
    try {
      const r = await analisarRemessa(arquivo);
      setRemessa(r);
      // remessa de empresa já cadastrada pula direto para o projeto
      if (r.ja_cadastrada && r.empresa_id) {
        setEmpresaId(r.empresa_id);
        setEtapa("projeto");
      } else {
        setEtapa("conferencia");
      }
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  async function confirmarEmpresa() {
    if (!remessa?.cnpj_matriz) return;
    setOcupado(true);
    setErro(null);
    try {
      const e = await criarEmpresa({
        cnpj_raiz: remessa.cnpj_raiz,
        cnpj_matriz: remessa.cnpj_matriz,
        razao_social: remessa.razao_social,
        uf: remessa.uf,
        inscricao_estadual: remessa.inscricao_estadual,
      });
      setEmpresaId(e.id);
      setEtapa("projeto");
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="pagina">
      <header className="pagina__topo">
        <div>
          <h1 className="pagina__titulo">Importar arquivos</h1>
          <p className="pagina__sub">
            Envie o SPED, solto ou compactado. O sistema lê o cabeçalho de cada
            arquivo e identifica a empresa, sem você digitar CNPJ.
          </p>
        </div>
        {etapa !== "envio" && (
          <button type="button" className="botao botao--secundario" onClick={reiniciar}>
            Começar de novo
          </button>
        )}
      </header>

      <Passos atual={etapa} />

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

      {etapa === "envio" && <ZonaDeEnvio aoEnviar={enviar} ocupado={ocupado} />}

      {etapa === "conferencia" && remessa && (
        <Conferencia
          remessa={remessa}
          ocupado={ocupado}
          aoConfirmar={confirmarEmpresa}
        />
      )}

      {etapa === "projeto" && remessa && empresaId && (
        <FormularioProjeto
          remessa={remessa}
          empresaId={empresaId}
          aoCriar={() => setEtapa("pronto")}
          aoFalhar={setErro}
        />
      )}

      {etapa === "pronto" && remessa && (
        <div className="cartao cartao--sucesso">
          <h2 className="cartao__titulo">Projeto criado</h2>
          <p className="cartao__sub">
            {remessa.razao_social} está cadastrada e o projeto foi aberto. A
            leitura do conteúdo dos arquivos entra na próxima etapa.
          </p>
          <button type="button" className="botao botao--principal" onClick={reiniciar}>
            Importar outra empresa
          </button>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
const NOMES: Record<Etapa, string> = {
  envio: "Enviar",
  conferencia: "Conferir empresa",
  projeto: "Criar projeto",
  pronto: "Pronto",
};
const ORDEM: Etapa[] = ["envio", "conferencia", "projeto", "pronto"];

function Passos({ atual }: { atual: Etapa }) {
  const i = ORDEM.indexOf(atual);
  return (
    <ol className="passos">
      {ORDEM.map((e, n) => (
        <li
          key={e}
          className={`passos__item${n < i ? " passos__item--feito" : ""}${
            n === i ? " passos__item--atual" : ""
          }`}
        >
          <span className="passos__numero">{n < i ? "✓" : n + 1}</span>
          {NOMES[e]}
        </li>
      ))}
    </ol>
  );
}

/* ------------------------------------------------------------------ */
function ZonaDeEnvio({
  aoEnviar,
  ocupado,
}: {
  aoEnviar: (a: File) => void;
  ocupado: boolean;
}) {
  const [sobre, setSobre] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);

  function soltar(e: DragEvent) {
    e.preventDefault();
    setSobre(false);
    const a = e.dataTransfer.files?.[0];
    if (a) aoEnviar(a);
  }

  return (
    <div
      className={`zona${sobre ? " zona--sobre" : ""}${ocupado ? " zona--ocupada" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setSobre(true);
      }}
      onDragLeave={() => setSobre(false)}
      onDrop={soltar}
    >
      <input
        ref={entrada}
        type="file"
        accept=".txt,.zip,.sped,.efd"
        hidden
        onChange={(e) => {
          const a = e.target.files?.[0];
          if (a) aoEnviar(a);
          e.target.value = "";
        }}
      />
      {ocupado ? (
        <p className="zona__texto">Lendo os cabeçalhos…</p>
      ) : (
        <>
          <p className="zona__texto">
            Arraste o arquivo aqui, ou{" "}
            <button
              type="button"
              className="zona__botao"
              onClick={() => entrada.current?.click()}
            >
              escolha do computador
            </button>
          </p>
          <p className="zona__dica">
            Um SPED por competência e filial, ou um .zip com a remessa inteira.
            Só o cabeçalho é lido nesta etapa, então mesmo milhares de arquivos
            respondem em segundos.
          </p>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
function Conferencia({
  remessa,
  ocupado,
  aoConfirmar,
}: {
  remessa: Remessa;
  ocupado: boolean;
  aoConfirmar: () => void;
}) {
  return (
    <div className="cartao">
      <h2 className="cartao__titulo">Confira a empresa</h2>
      <p className="cartao__sub">
        Estes dados vieram do registro 0000 dos próprios arquivos.
      </p>

      {remessa.avisos.map((a) => (
        <div key={a} className="aviso aviso--atencao" role="alert">
          {a}
        </div>
      ))}

      <dl className="ficha">
        <Campo rotulo="Razão social" valor={remessa.razao_social} destaque />
        <Campo
          rotulo="CNPJ da matriz"
          valor={remessa.cnpj_matriz_formatado ?? "—"}
          mono
          destaque
          nota={remessa.matriz_encontrada ? undefined : "deduzido da raiz"}
        />
        <Campo rotulo="UF" valor={remessa.uf || "—"} />
        <Campo rotulo="Inscrição estadual" valor={remessa.inscricao_estadual || "—"} mono />
        <Campo
          rotulo="Filiais na remessa"
          valor={String(remessa.filiais)}
          nota="só a matriz identifica a empresa"
        />
        <Campo
          rotulo="Competências"
          valor={`${mes(remessa.primeira_competencia)} a ${mes(remessa.ultima_competencia)}`}
        />
        <Campo
          rotulo="Arquivos"
          valor={
            `${remessa.lidos} lidos` +
            (remessa.recusados ? `, ${remessa.recusados} recusados` : "")
          }
          nota={`${remessa.arquivos_para_cat} servem à CAT 42`}
        />
      </dl>

      <div className="cartao__acoes">
        <button
          type="button"
          className="botao botao--principal"
          onClick={aoConfirmar}
          disabled={ocupado || !remessa.cnpj_matriz}
        >
          {ocupado ? "Cadastrando…" : "Pré-cadastrar empresa"}
        </button>
      </div>
    </div>
  );
}

function Campo({
  rotulo,
  valor,
  mono,
  destaque,
  nota,
}: {
  rotulo: string;
  valor: string;
  mono?: boolean;
  destaque?: boolean;
  nota?: string;
}) {
  return (
    <div className="ficha__item">
      <dt className="ficha__rotulo">{rotulo}</dt>
      <dd className={`ficha__valor${destaque ? " ficha__valor--destaque" : ""}${mono ? " mono" : ""}`}>
        {valor}
        {nota && <span className="ficha__nota">{nota}</span>}
      </dd>
    </div>
  );
}

/* ------------------------------------------------------------------ */
function FormularioProjeto({
  remessa,
  empresaId,
  aoCriar,
  aoFalhar,
}: {
  remessa: Remessa;
  empresaId: number;
  aoCriar: () => void;
  aoFalhar: (e: ErroApi) => void;
}) {
  const [frente, setFrente] = useState<Frente>("cat42");
  const [nome, setNome] = useState(
    `Ressarcimento ST ${ano(remessa.primeira_competencia)}`,
  );
  // as competências já vêm dos arquivos: é o período que existe de fato
  const [ini, setIni] = useState(remessa.primeira_competencia ?? "");
  const [fim, setFim] = useState(remessa.ultima_competencia ?? "");
  const [obs, setObs] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    try {
      await criarProjeto({
        empresa_id: empresaId,
        frente,
        nome: nome.trim(),
        competencia_ini: ini,
        competencia_fim: fim,
        observacao: obs.trim() || null,
      });
      aoCriar();
    } catch (err) {
      aoFalhar(comoErro(err));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form className="cartao" onSubmit={enviar}>
      <h2 className="cartao__titulo">Novo projeto</h2>
      <p className="cartao__sub">
        Para {remessa.razao_social}. As competências vieram dos arquivos
        enviados e podem ser ajustadas.
      </p>

      <div className="grade">
        <label className="campo">
          <span className="campo__rotulo">Frente</span>
          <select
            className="campo__entrada"
            value={frente}
            onChange={(e) => setFrente(e.target.value as Frente)}
          >
            {Object.entries(FRENTES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>

        <label className="campo">
          <span className="campo__rotulo">Nome do projeto</span>
          <input
            className="campo__entrada"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            required
          />
        </label>

        <label className="campo">
          <span className="campo__rotulo">Competência inicial</span>
          <input
            className="campo__entrada"
            type="date"
            value={ini}
            onChange={(e) => setIni(e.target.value)}
            required
          />
        </label>

        <label className="campo">
          <span className="campo__rotulo">Competência final</span>
          <input
            className="campo__entrada"
            type="date"
            value={fim}
            onChange={(e) => setFim(e.target.value)}
            required
          />
        </label>
      </div>

      <label className="campo campo--largo">
        <span className="campo__rotulo">Observação</span>
        <textarea
          className="campo__entrada"
          rows={2}
          value={obs}
          onChange={(e) => setObs(e.target.value)}
        />
      </label>

      <div className="cartao__acoes">
        <button type="submit" className="botao botao--principal" disabled={enviando}>
          {enviando ? "Criando…" : "Criar projeto"}
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
function comoErro(e: unknown): ErroApi {
  return e instanceof ErroApi
    ? e
    : new ErroApi("Erro inesperado. Tente novamente.", 0);
}

function mes(iso: string | null): string {
  if (!iso) return "—";
  const [a, m] = iso.split("-");
  return `${m}/${a}`;
}

function ano(iso: string | null): string {
  return iso ? iso.slice(0, 4) : "";
}

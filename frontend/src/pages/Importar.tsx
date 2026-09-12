import {
  useRef,
  useState,
  type DragEvent,
  type FormEvent,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Campo, Entrada } from "@/components/ui/Campo";
import { Combobox, type OpcaoDeCombobox } from "@/components/ui/Combobox";
import { CabecalhoDePagina, Secao } from "@/components/ui/Pagina";
import { FRENTES, type Frente } from "@/constants/fronts";
import { IconeConfirma, IconeEnviar, IconeTentarDeNovo } from "@/constants/icons";
import { ROTAS } from "@/constants/routes";
import { cn } from "@/lib/cn";
import { compara, mascarar, paraIso, paraTexto, valida } from "@/lib/competencia";
import { useAcao } from "@/hooks/useAcao";
import { comoErro } from "@/lib/errors";
import { numero } from "@/lib/format";
import {
  analisarRemessa,
  criarEmpresa,
  criarProjeto,
  type Projeto,
  type Remessa,
} from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

type Passo = "envio" | "conferencia" | "projeto" | "pronto";

const NOMES: Record<Passo, string> = {
  envio: "Enviar",
  conferencia: "Conferir empresa",
  projeto: "Criar projeto",
  pronto: "Pronto",
};
const ORDEM: Passo[] = ["envio", "conferencia", "projeto", "pronto"];

/**
 * Cadastrar trabalho — o wizard de quatro passos.
 *
 * O cadastro começa por um arquivo do SPED porque é ele que traz CNPJ, razão
 * social, inscrição estadual e UF. Digitar isso à mão é como o cadastro erra,
 * e um CNPJ errado só aparece meses depois, na entrega.
 */
export default function Importar() {
  const navegar = useNavigate();
  const [passo, setPasso] = useState<Passo>("envio");
  const [remessa, setRemessa] = useState<Remessa | null>(null);
  const [empresaId, setEmpresaId] = useState<number | null>(null);
  const [criado, setCriado] = useState<Projeto | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState(false);
  // o envio do SPED é o carregamento longo desta tela, e cancelar desfaz
  // mesmo: a análise não grava nada. Já criar a empresa é POST que o
  // servidor conclui — ali não há Cancelar, porque não haveria o que desfazer
  const envio = useAcao();

  function reiniciar() {
    setPasso("envio");
    setRemessa(null);
    setEmpresaId(null);
    setCriado(null);
    setErro(null);
  }

  async function enviar(arquivo: File) {
    setErro(null);
    const r = await envio.executar((sinal) => analisarRemessa(arquivo, sinal));
    if (!r) return;          // erro já mostrado, ou a pessoa cancelou
    setRemessa(r);
    // remessa de empresa já cadastrada pula direto para o projeto
    if (r.ja_cadastrada && r.empresa_id) {
      setEmpresaId(r.empresa_id);
      setPasso("projeto");
    } else {
      setPasso("conferencia");
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
      setPasso("projeto");
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-[1000px] flex-col gap-4">
      <CabecalhoDePagina
        eyebrow="Cadastro"
        titulo="Cadastrar trabalho"
        sub="Envie o SPED, solto ou compactado. O sistema lê o cabeçalho de cada arquivo e identifica a empresa, sem você digitar CNPJ."
        acao={
          passo !== "envio" && (
            <Botao variante="secundario" icone={IconeTentarDeNovo} onClick={reiniciar}>
              Começar de novo
            </Botao>
          )
        }
      >
        <Stepper atual={passo} />
      </CabecalhoDePagina>

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} />}
      {envio.erro && (
        <Aviso titulo={envio.erro.message} codigo={envio.erro.requisicaoId} />
      )}

      {passo === "envio" && (
        <ZonaDeEnvio
          aoEnviar={enviar}
          ocupado={ocupado || envio.carregando}
          aoCancelar={envio.podeCancelar ? envio.cancelar : undefined}
        />
      )}

      {passo === "conferencia" && remessa && (
        <ConferirEmpresa remessa={remessa} ocupado={ocupado} aoConfirmar={confirmarEmpresa} />
      )}

      {passo === "projeto" && remessa && empresaId && (
        <FormularioDeProjeto
          remessa={remessa}
          empresaId={empresaId}
          aoCriar={(p) => {
            setCriado(p);
            setPasso("pronto");
          }}
          aoFalhar={setErro}
        />
      )}

      {passo === "pronto" && remessa && (
        <Secao>
          <div className="flex flex-col items-center gap-4 py-6 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-sucesso-fundo text-sucesso">
              <IconeConfirma size={26} strokeWidth={2.5} aria-hidden />
            </div>
            <div>
              <h2 className="m-0 text-xl font-extrabold text-texto">Trabalho cadastrado</h2>
              <p className="m-0 mt-1.5 max-w-[540px] text-[13px] leading-relaxed text-texto-suave">
                {remessa.razao_social} está cadastrada e o projeto foi aberto. A base de dados
                inteira entra na etapa 1, apontando a pasta onde os arquivos estão.
              </p>
            </div>

            <dl className="m-0 grid w-full max-w-[720px] grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3 text-left">
              <Fato rotulo="Empresa" valor={remessa.razao_social} />
              <Fato rotulo="Frente" valor={criado?.frente_rotulo ?? "—"} />
              <Fato rotulo="Projeto" valor={criado?.nome ?? "—"} />
              <Fato
                rotulo="Competências"
                mono
                valor={
                  criado
                    ? `${paraTexto(criado.competencia_ini)} a ${paraTexto(criado.competencia_fim)}`
                    : "—"
                }
              />
            </dl>

            <div className="flex flex-wrap justify-center gap-3">
              {criado && (
                <Botao
                  onClick={() => navegar(ROTAS.projeto(criado.id))}
                  className="shadow-acao"
                >
                  Ver o trabalho
                </Botao>
              )}
              <Botao variante="secundario" onClick={reiniciar}>
                Cadastrar outra empresa
              </Botao>
            </div>
          </div>
        </Secao>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function Stepper({ atual }: { atual: Passo }) {
  const i = ORDEM.indexOf(atual);
  return (
    <ol className="m-0 flex list-none flex-wrap gap-2 p-0">
      {ORDEM.map((e, n) => {
        const feito = n < i;
        const agora = n === i;
        return (
          <li
            key={e}
            aria-current={agora ? "step" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-full border px-3.5 py-2 text-[13px] transition-colors",
              feito && "border-sucesso/30 text-sucesso",
              agora && "border-laranja-500/50 font-bold text-texto",
              !feito && !agora && "border-borda text-texto-fraco",
            )}
          >
            <span
              aria-hidden
              className={cn(
                "flex h-[22px] w-[22px] items-center justify-center rounded-full text-[11px] font-extrabold",
                feito && "bg-sucesso text-marca-branco",
                agora && "bg-marca-laranja text-acao-texto",
                !feito && !agora && "bg-superficie-alt text-texto-fraco",
              )}
            >
              {feito ? <IconeConfirma size={12} strokeWidth={3} /> : n + 1}
            </span>
            {NOMES[e]}
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------------ */

function ZonaDeEnvio({
  aoEnviar,
  ocupado,
  aoCancelar,
}: {
  aoEnviar: (a: File) => void;
  ocupado: boolean;
  /** só chega depois de uns instantes: ver useAcao */
  aoCancelar?: () => void;
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
      onDragOver={(e) => {
        e.preventDefault();
        setSobre(true);
      }}
      onDragLeave={() => setSobre(false)}
      onDrop={soltar}
      className={cn(
        "flex flex-col items-center gap-3 rounded-cartao border border-dashed px-6 py-12 text-center transition-colors",
        sobre ? "border-marca-laranja bg-laranja-500/8" : "border-borda-forte bg-superficie",
        ocupado && "opacity-70",
      )}
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
        <div className="flex flex-col items-center gap-3">
          <p className="m-0 text-[15px] font-semibold text-texto-suave">
            Lendo os cabeçalhos…
          </p>
          {aoCancelar && (
            <Botao variante="secundario" tamanho="sm" onClick={aoCancelar}>
              Cancelar envio
            </Botao>
          )}
        </div>
      ) : (
        <>
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-laranja-500/12 text-laranja-700 escuro:text-laranja-300">
            <IconeEnviar size={22} strokeWidth={2} aria-hidden />
          </div>
          <p className="m-0 text-[15px] font-semibold text-texto">
            Arraste o arquivo aqui, ou{" "}
            <button
              type="button"
              onClick={() => entrada.current?.click()}
              className="cursor-pointer font-semibold text-link underline underline-offset-2 hover:text-link-hover"
            >
              escolha do computador
            </button>
          </p>
          <p className="m-0 max-w-[520px] text-[13px] leading-relaxed text-texto-fraco">
            Um SPED por competência e filial, ou um .zip com a remessa inteira. Só o cabeçalho é
            lido nesta etapa, então mesmo milhares de arquivos respondem em segundos.
          </p>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function ConferirEmpresa({
  remessa,
  ocupado,
  aoConfirmar,
}: {
  remessa: Remessa;
  ocupado: boolean;
  aoConfirmar: () => void;
}) {
  return (
    <Secao
      titulo="Confira a empresa"
      sub="Estes dados vieram do registro 0000 dos próprios arquivos. Nada foi digitado."
    >
      {remessa.avisos.length > 0 && (
        <div className="mt-4 flex flex-col gap-2">
          {remessa.avisos.map((a) => (
            <Aviso key={a} tom="atencao">
              {a}
            </Aviso>
          ))}
        </div>
      )}

      <dl className="m-0 mt-4 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
        <Fato rotulo="Razão social" valor={remessa.razao_social} />
        <Fato
          rotulo="CNPJ da matriz"
          valor={remessa.cnpj_matriz_formatado ?? "—"}
          mono
          nota={remessa.matriz_encontrada ? undefined : "deduzido da raiz"}
        />
        <Fato rotulo="UF" valor={remessa.uf || "—"} />
        <Fato rotulo="Inscrição estadual" valor={remessa.inscricao_estadual || "—"} mono />
        <Fato
          rotulo="Filiais na remessa"
          valor={numero(remessa.filiais)}
          nota="só a matriz identifica a empresa"
        />
        <Fato
          rotulo="Competências"
          mono
          valor={`${paraTexto(remessa.primeira_competencia)} a ${paraTexto(remessa.ultima_competencia)}`}
        />
        <Fato
          rotulo="Arquivos"
          valor={
            `${numero(remessa.lidos)} lidos` +
            (remessa.recusados ? `, ${numero(remessa.recusados)} recusados` : "")
          }
          nota={`${numero(remessa.arquivos_para_cat)} servem à CAT 42`}
        />
      </dl>

      <div className="mt-6">
        <Botao
          onClick={aoConfirmar}
          carregando={ocupado}
          disabled={!remessa.cnpj_matriz}
          className="shadow-acao"
        >
          Pré-cadastrar empresa
        </Botao>
      </div>
    </Secao>
  );
}

/** Um fato lido do arquivo: rótulo pequeno, valor grande, barra laranja. */
function Fato({
  rotulo,
  valor,
  mono,
  nota,
}: {
  rotulo: string;
  valor: ReactNode;
  mono?: boolean;
  nota?: string;
}) {
  return (
    <div className="border-l-2 border-l-marca-laranja pl-3">
      <dt className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
        {rotulo}
      </dt>
      <dd className={cn("m-0 mt-1 text-[15px] font-bold text-texto", mono && "font-mono")}>
        {valor}
      </dd>
      {nota && <dd className="m-0 mt-0.5 text-xs text-texto-fraco">{nota}</dd>}
    </div>
  );
}

/* ------------------------------------------------------------------ */

const OPCOES_DE_FRENTE: OpcaoDeCombobox<Frente>[] = (Object.keys(FRENTES) as Frente[]).map(
  (f) => ({ valor: f, rotulo: FRENTES[f] }),
);

function FormularioDeProjeto({
  remessa,
  empresaId,
  aoCriar,
  aoFalhar,
}: {
  remessa: Remessa;
  empresaId: number;
  aoCriar: (p: Projeto) => void;
  aoFalhar: (e: ErroApi) => void;
}) {
  const [frente, setFrente] = useState<Frente>("cat42");
  const [nome, setNome] = useState(
    `Ressarcimento ST ${remessa.primeira_competencia?.slice(0, 4) ?? ""}`.trim(),
  );
  // as competências já vêm dos arquivos: é o período que existe de fato
  const [ini, setIni] = useState(paraTextoOuVazio(remessa.primeira_competencia));
  const [fim, setFim] = useState(paraTextoOuVazio(remessa.ultima_competencia));
  const [obs, setObs] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!nome.trim()) {
      setErro("Informe o nome do trabalho.");
      return;
    }
    if (!valida(ini) || !valida(fim)) {
      setErro("Competências em MM/AAAA, como 05/2021.");
      return;
    }
    if (compara(ini, fim) > 0) {
      setErro("A competência inicial não pode ser depois da final.");
      return;
    }
    setErro(null);
    setEnviando(true);
    try {
      aoCriar(
        await criarProjeto({
          empresa_id: empresaId,
          frente,
          nome: nome.trim(),
          competencia_ini: paraIso(ini)!,
          competencia_fim: paraIso(fim, true)!,
          observacao: obs.trim() || null,
        }),
      );
    } catch (err) {
      aoFalhar(comoErro(err));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Secao
      titulo="Novo projeto"
      sub={`Para ${remessa.razao_social}. As competências vieram dos arquivos enviados e podem ser ajustadas.`}
    >
      <form
        onSubmit={enviar}
        noValidate
        className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(230px,1fr))] gap-[18px]"
      >
        <Campo rotulo="Frente de trabalho">
          {(props) => (
            <Combobox {...props} valor={frente} opcoes={OPCOES_DE_FRENTE} aoMudar={setFrente} />
          )}
        </Campo>
        <Campo rotulo="Nome do trabalho">
          {(props) => (
            <Entrada {...props} value={nome} onChange={(e) => setNome(e.target.value)} required />
          )}
        </Campo>
        <Campo rotulo="Competência inicial">
          {(props) => (
            <Entrada
              {...props}
              mono
              value={ini}
              onChange={(e) => setIni(mascarar(e.target.value))}
              placeholder="01/2021"
              inputMode="numeric"
            />
          )}
        </Campo>
        <Campo rotulo="Competência final">
          {(props) => (
            <Entrada
              {...props}
              mono
              value={fim}
              onChange={(e) => setFim(mascarar(e.target.value))}
              placeholder="12/2025"
              inputMode="numeric"
            />
          )}
        </Campo>

        <div className="col-span-full">
          <Campo rotulo="Observação (opcional)">
            {(props) => (
              <textarea
                {...props}
                rows={3}
                value={obs}
                onChange={(e) => setObs(e.target.value)}
                className="w-full rounded-raio border border-borda-forte bg-superficie px-3 py-2.5 text-[15px] text-texto focus:border-borda-foco focus:outline-none"
              />
            )}
          </Campo>
        </div>

        <div className="col-span-full flex flex-wrap items-center gap-3">
          <Botao type="submit" carregando={enviando} className="shadow-acao">
            Criar projeto
          </Botao>
          {erro && <span className="text-xs text-erro">{erro}</span>}
        </div>
      </form>
    </Secao>
  );
}

const paraTextoOuVazio = (iso: string | null) => (iso ? paraTexto(iso) : "");

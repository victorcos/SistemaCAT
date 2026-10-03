import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { BotaoIcone } from "@/components/ui/BotaoIcone";
import { Campo, Entrada } from "@/components/ui/Campo";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import {
  CabecalhoDePagina,
  Metrica,
  Metricas,
  Secao,
  Vazio,
  Voltar,
} from "@/components/ui/Pagina";
import { Celula, Linha, Tabela } from "@/components/ui/Tabela";
import { IconeApagar, IconeFechar, IconePasta } from "@/constants/icons";
import { ROTAS } from "@/constants/routes";
import { aceitaProcessamento } from "@/constants/status";
import { useConfirm } from "@/hooks/useConfirm";
import { cn } from "@/lib/cn";
import { comoErro } from "@/lib/errors";
import { competencia, numero, tamanho } from "@/lib/format";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import {
  inspecionarPasta,
  listarLotes,
  registrarLote,
  removerLote,
  type ArquivoDoLote,
  type Contagem,
  type EmpresaDeFora,
  type Lote,
  type LoteRegistrado,
  type ResumoDoLote,
} from "@/services/lote";
import type { ErroApi } from "@/types/erro";

/**
 * Etapa 1 — importar a base de dados de um trabalho que já existe.
 *
 * É a outra ponta do cadastro: lá se descobre a empresa a partir de uma
 * amostra do SPED, aqui entra a base inteira.
 *
 * A tela pede um caminho de pasta, não um arquivo. A maior base que medimos
 * tem 7.036 arquivos, e um relatório gerencial sozinho tem 194 MB.
 */
/** O que cada trabalho espera achar na pasta. Mandar quem apura PIS/COFINS
 *  procurar "a EFD ICMS/IPI e os XML" é mandar procurar a pasta errada. */
const ARQUIVOS_DO_MODULO: Record<string, string> = {
  icms: "a EFD ICMS/IPI, os XML e os relatórios do ERP",
  piscofins: "a EFD-Contribuições, a ECD, a EFD ICMS/IPI e os XML das notas",
  irpj_csll: "a ECF e a ECD",
};

export default function Lote() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);
  const confirmar = useConfirm();

  const [detalhe, setDetalhe] = useState<ProjetoDetalhe | null>(null);
  const [lotes, setLotes] = useState<Lote[]>([]);
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

  /** Descarta a conferência da pasta sem gravar nada. */
  function cancelar() {
    setResumo(null);
    setObservacao("");
    setErro(null);
  }

  async function remover(l: Lote) {
    const ok = await confirmar({
      icone: IconeApagar,
      tom: "perigo",
      titulo: "Remover este lote?",
      texto:
        "Os arquivos do cliente em disco não são tocados — some só o registro da importação, e a conferência precisará ser refeita.",
      rotuloConfirmar: "Remover",
      variante: "perigo",
    });
    if (!ok) return;
    setOcupado(true);
    setErro(null);
    try {
      await removerLote(projetoId, l.id);
      setLotes(await listarLotes(projetoId));
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  async function importar() {
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
  // importar arquivo num trabalho cancelado é registrar base que ninguém vai
  // usar; num pausado, é fazer o trabalho andar pelas costas da decisão de
  // pará-lo. A API recusa as etapas; aqui a tela recusa antes.
  const anda = !p || aceitaProcessamento(p.status);

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="Etapa 1"
        titulo="Importar base de dados"
        sub={
          p ? (
            <>
              Base de trabalho de <strong className="text-texto">{p.empresa}</strong>. Aponte a
              pasta onde estão {ARQUIVOS_DO_MODULO[p.modulo] ?? ARQUIVOS_DO_MODULO.icms}. Nada é
              copiado: o sistema registra onde os arquivos estão e o que cada um é.
            </>
          ) : (
            "Carregando…"
          )
        }
      />

      <TrabalhoParado status={p?.status} projetoId={projetoId} />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} />}

      {registrado && (
        <Aviso
          tom="sucesso"
          titulo={registrado.criado ? "Lote registrado" : "Arquivos reclassificados"}
          aoFechar={() => setRegistrado(null)}
        >
          {registrado.criado && (
            <>
              {numero(registrado.total_arquivos)} arquivo(s),{" "}
              {numero(registrado.arquivos_uteis)} que a CAT 42 lê,{" "}
              {tamanho(registrado.bytes_totais)}.{" "}
            </>
          )}
          {registrado.reclassificados > 0 &&
            `${numero(registrado.reclassificados)} arquivo(s) que já estavam no trabalho foram reconhecidos como outro tipo e atualizados. Para que entrem na conta, rode de novo da conferência em diante.`}
        </Aviso>
      )}

      <Secao>
        <form onSubmit={conferir} className="flex flex-col gap-4">
          <div className="max-w-[720px]">
            <Campo
              rotulo="Pasta com os arquivos"
              dica="Caminho como esta máquina o enxerga. Subpastas entram junto. Pasta grande em unidade de rede leva alguns minutos na primeira vez — depois disso o Windows já a tem em cache."
            >
              {(props) => (
                <Entrada
                  {...props}
                  mono
                  value={pasta}
                  onChange={(e) => setPasta(e.target.value)}
                  placeholder="Z:\CLIENTE\...\EFD Fiscal - EFD ICMS IPI"
                  spellCheck={false}
                  autoComplete="off"
                  required
                />
              )}
            </Campo>
          </div>
          <div>
            <Botao
              type="submit"
              icone={IconePasta}
              carregando={ocupado && !resumo}
              disabled={!anda}
              className="shadow-acao"
            >
              Conferir pasta
            </Botao>
          </div>
        </form>
      </Secao>

      {resumo && (
        <ConferenciaDaPasta
          resumo={resumo}
          modulo={p?.modulo_rotulo ?? "ICMS"}
          observacao={observacao}
          aoMudarObservacao={setObservacao}
          aoImportar={importar}
          aoCancelar={cancelar}
          ocupado={ocupado}
        />
      )}

      <Secao
        titulo="Lotes já importados"
        sub="Cada lote é uma pasta registrada. Importar de novo a mesma pasta não duplica arquivo: o que já está no trabalho fica de fora."
      >
        {lotes.length === 0 ? (
          <div className="mt-4">
            <Vazio titulo="Nenhum lote ainda">
              Enquanto não houver base, as etapas seguintes ficam aguardando.
            </Vazio>
          </div>
        ) : (
          <ul className="m-0 mt-4 flex list-none flex-col gap-3 p-0">
            {lotes.map((l) => (
              <li
                key={l.id}
                className="rounded-[14px] border border-borda border-l-[3px] border-l-sucesso bg-superficie-vidro p-4"
              >
                <div className="flex items-start gap-3">
                  <p
                    className="m-0 min-w-0 flex-1 break-all font-mono text-[13px] text-texto-suave"
                    title={l.pasta}
                  >
                    {l.pasta}
                  </p>
                  <span className="shrink-0 text-xs text-texto-fraco">
                    {new Date(l.criado_em).toLocaleDateString("pt-BR")}
                  </span>
                  <BotaoIcone
                    icone={IconeFechar}
                    rotulo="Remover este lote do trabalho"
                    tom="perigo"
                    disabled={ocupado}
                    onClick={() => remover(l)}
                    className="h-[30px] w-[30px]"
                  />
                </div>

                <div className="mt-2.5 flex flex-wrap items-center gap-x-5 gap-y-1 text-[13px] text-texto-suave">
                  <span>
                    <strong className="font-mono text-texto">{numero(l.total_arquivos)}</strong>{" "}
                    arquivos
                  </span>
                  <span>
                    <strong className="font-mono text-texto">{numero(l.arquivos_uteis)}</strong>{" "}
                    para {p?.modulo_rotulo ?? "a CAT"}
                  </span>
                  <span className="font-mono">{tamanho(l.bytes_totais)}</span>
                  {l.competencia_ini && (
                    <span className="font-mono">
                      {competencia(l.competencia_ini)} a {competencia(l.competencia_fim)}
                    </span>
                  )}
                </div>

                <EtiquetasDeTipo
                  contagens={l.contagens}
                  modulo={p?.modulo_rotulo ?? "ICMS"}
                  className="mt-2.5"
                />

                {l.observacao && (
                  <p className="m-0 mt-2.5 text-[13px] italic text-texto-fraco">{l.observacao}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Secao>
    </div>
  );
}

/* ------------------------------------------------------------------ */

/** Uma pílula por tipo de arquivo. O que ESTE trabalho lê ganha a cor da marca;
 *  o resto fica neutro — a diferença é o que importa nesta tela. */
function EtiquetasDeTipo({
  contagens,
  modulo,
  className,
}: {
  contagens: Contagem[];
  modulo: string;
  className?: string;
}) {
  if (contagens.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {contagens.map((c) => (
        <span
          key={c.tipo}
          title={c.alimenta ? "Alimenta a apuração" : `Não é lido no trabalho de ${modulo}`}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs",
            c.alimenta
              ? "border-laranja-500/35 bg-laranja-500/10 text-laranja-800 escuro:text-laranja-300"
              : "border-borda bg-superficie-alt text-texto-fraco",
          )}
        >
          {c.rotulo}
          <span className="font-mono font-semibold">{numero(c.quantidade)}</span>
        </span>
      ))}
    </div>
  );
}

/**
 * O que a pasta trazia de outra empresa, aberto.
 *
 * O descarte é automático e não pede confirmação — arquivo de outra empresa
 * entrar no trabalho contamina a apuração de dois clientes de uma vez. Mas
 * descarte que ninguém vê é boato: pasta de rede guarda o grupo inteiro, e
 * quem importa precisa conferir que o que saiu não era seu antes de gravar.
 */
function DeOutraEmpresa({
  quantos,
  empresas,
  arquivos,
}: {
  quantos: number;
  empresas: EmpresaDeFora[];
  arquivos: ArquivoDoLote[];
}) {
  const [aberto, setAberto] = useState(false);
  if (quantos === 0) return null;
  return (
    <section className="mt-4 rounded-cartao border border-borda bg-superficie-alt p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="m-0 text-[13px] font-bold text-texto-suave">
          {numero(quantos)} arquivo(s) de outra empresa ficaram de fora
        </h3>
        <button
          type="button"
          onClick={() => setAberto((v) => !v)}
          className="text-[13px] font-semibold text-laranja-700 underline-offset-2 hover:underline escuro:text-laranja-300"
          aria-expanded={aberto}
        >
          {aberto ? "Ocultar" : "Ver o que saiu"}
        </button>
      </div>
      <p className="m-0 mt-1 text-[13px] text-texto-fraco">
        Nem emitente nem destinatário é o CNPJ deste trabalho. Eles não entram na importação —
        misturar empresa contamina a apuração das duas.
      </p>
      {aberto && (
        <>
          <ul className="m-0 mt-3 flex list-none flex-wrap gap-2 p-0">
            {empresas.map((e) => (
              <li
                key={e.cnpj}
                className="inline-flex items-center gap-1.5 rounded-full border border-borda bg-superficie px-3 py-1 text-xs"
              >
                <span className="font-mono">{e.cnpj || "sem CNPJ"}</span>
                <span className="font-mono font-semibold">{numero(e.arquivos)}</span>
                <span className="text-texto-fraco">{tamanho(e.bytes_totais)}</span>
              </li>
            ))}
          </ul>
          {arquivos.length > 0 && (
            <div className="mt-3">
              <Tabela colunas={["Arquivo", "Reconhecido como", "CNPJ", "Competência", "Tamanho"]}>
                {arquivos.map((a) => (
                  <Linha key={a.caminho} apagada>
                    <Celula title={a.caminho}>{a.nome}</Celula>
                    <Celula>{a.tipo_rotulo}</Celula>
                    <Celula mono>{a.cnpj ?? "—"}</Celula>
                    <Celula mono>{competencia(a.competencia)}</Celula>
                    <Celula mono>{tamanho(a.tamanho)}</Celula>
                  </Linha>
                ))}
              </Tabela>
              {quantos > arquivos.length && (
                <p className="m-0 mt-2 text-[13px] text-texto-fraco">
                  Mostrando {numero(arquivos.length)} de {numero(quantos)}. O log da importação tem a
                  conta completa por CNPJ.
                </p>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function ConferenciaDaPasta({
  resumo,
  modulo,
  observacao,
  aoMudarObservacao,
  aoImportar,
  aoCancelar,
  ocupado,
}: {
  resumo: ResumoDoLote;
  /** o tributo do trabalho, para dizer a quem a pasta serve ou deixa de servir */
  modulo: string;
  observacao: string;
  aoMudarObservacao: (v: string) => void;
  aoImportar: () => void;
  aoCancelar: () => void;
  ocupado: boolean;
}) {
  const novos = resumo.total_arquivos - resumo.ja_no_trabalho;

  return (
    <Secao
      titulo="O que há nesta pasta"
      sub={<span className="break-all font-mono">{resumo.pasta}</span>}
      acao={
        <BotaoIcone
          icone={IconeFechar}
          rotulo="Descartar esta conferência"
          onClick={aoCancelar}
          disabled={ocupado}
        />
      }
    >
      <div className="mt-4">
        <Metricas>
          <Metrica rotulo="Arquivos" valor={resumo.total_arquivos} />
          <Metrica rotulo={`${modulo} lê`} valor={resumo.arquivos_uteis} tom="destaque" />
          <Metrica rotulo="Tamanho" valor={tamanho(resumo.bytes_totais)} />
          <Metrica
            rotulo="Competências"
            valor={
              <span className="font-mono text-xl">
                {resumo.competencia_ini
                  ? `${competencia(resumo.competencia_ini)} a ${competencia(resumo.competencia_fim)}`
                  : "—"}
              </span>
            }
          />
        </Metricas>
      </div>

      <EtiquetasDeTipo contagens={resumo.contagens} modulo={modulo} className="mt-4" />

      <div className="mt-4 flex flex-col gap-2">
        {resumo.avisos.map((a) => (
          <Aviso key={a} tom="atencao">
            {a}
          </Aviso>
        ))}
        {resumo.ja_no_trabalho > 0 && (
          <Aviso tom="atencao">
            {numero(resumo.ja_no_trabalho)} arquivo(s) já estão neste trabalho e não entram de
            novo. O mesmo SPED contado duas vezes dobraria movimento na apuração.
            {resumo.reclassificados > 0 &&
              ` Destes, ${numero(resumo.reclassificados)} são reconhecidos hoje como outro tipo (zip de XML, evento de cancelamento) e têm o tipo atualizado ao importar.`}
          </Aviso>
        )}
      </div>

      <DeOutraEmpresa
        quantos={resumo.de_outra_empresa}
        empresas={resumo.empresas_de_fora ?? []}
        arquivos={resumo.fora_por_empresa ?? []}
      />

      <h3 className="mb-2 mt-6 text-[13px] font-bold text-texto-suave">
        Amostra — o que não entra aparece primeiro
      </h3>
      <Tabela colunas={["Arquivo", "Reconhecido como", "CNPJ", "Competência", "Tamanho"]}>
        {resumo.amostra.map((a) => (
          <Linha key={a.caminho} apagada={!a.alimenta}>
            <Celula title={a.caminho}>{a.nome}</Celula>
            <Celula nota={a.detalhe || a.motivo}>{a.tipo_rotulo}</Celula>
            <Celula mono>{a.cnpj ?? "—"}</Celula>
            <Celula mono>{competencia(a.competencia)}</Celula>
            <Celula mono>{tamanho(a.tamanho)}</Celula>
          </Linha>
        ))}
      </Tabela>

      <div className="mt-5 max-w-[560px]">
        <Campo rotulo="Observação (opcional)">
          {(props) => (
            <Entrada
              {...props}
              value={observacao}
              onChange={(e) => aoMudarObservacao(e.target.value)}
              placeholder="De onde veio, o que a empresa disse, o que ainda falta"
              maxLength={500}
            />
          )}
        </Campo>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Botao
          onClick={aoImportar}
          carregando={ocupado}
          disabled={!resumo.serve || (novos === 0 && resumo.reclassificados === 0)}
          className="shadow-acao"
        >
          {novos === 0 && resumo.reclassificados > 0
            ? `Atualizar ${numero(resumo.reclassificados)} arquivo(s)`
            : `Importar ${numero(novos)} arquivo(s)`}
        </Botao>
        <Botao variante="fantasma" onClick={aoCancelar} disabled={ocupado}>
          Cancelar
        </Botao>
        {!resumo.serve && (
          <span className="text-[13px] text-texto-fraco">
            Nada aqui alimenta o trabalho de {modulo}, então não há o que importar.
          </span>
        )}
      </div>
    </Secao>
  );
}

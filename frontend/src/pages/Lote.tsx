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
  type Contagem,
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
              pasta onde estão a EFD ICMS/IPI, os XML e os relatórios do ERP. Nada é copiado: o
              sistema registra onde os arquivos estão e o que cada um é.
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
                  placeholder="Z:\GRUPO PLURIX\...\EFD Fiscal - EFD ICMS IPI"
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
                    para a CAT
                  </span>
                  <span className="font-mono">{tamanho(l.bytes_totais)}</span>
                  {l.competencia_ini && (
                    <span className="font-mono">
                      {competencia(l.competencia_ini)} a {competencia(l.competencia_fim)}
                    </span>
                  )}
                </div>

                <EtiquetasDeTipo contagens={l.contagens} className="mt-2.5" />

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

/** Uma pílula por tipo de arquivo. O que a CAT lê ganha a cor da marca; o
 *  resto fica neutro — a diferença é o que importa nesta tela. */
function EtiquetasDeTipo({
  contagens,
  className,
}: {
  contagens: Contagem[];
  className?: string;
}) {
  if (contagens.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {contagens.map((c) => (
        <span
          key={c.tipo}
          title={c.alimenta_a_cat ? "Alimenta a apuração" : "Não é lido pela CAT 42"}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs",
            c.alimenta_a_cat
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

function ConferenciaDaPasta({
  resumo,
  observacao,
  aoMudarObservacao,
  aoImportar,
  aoCancelar,
  ocupado,
}: {
  resumo: ResumoDoLote;
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
          <Metrica rotulo="A CAT 42 lê" valor={resumo.arquivos_uteis} tom="destaque" />
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

      <EtiquetasDeTipo contagens={resumo.contagens} className="mt-4" />

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

      <h3 className="mb-2 mt-6 text-[13px] font-bold text-texto-suave">
        Amostra — o que não entra aparece primeiro
      </h3>
      <Tabela colunas={["Arquivo", "Reconhecido como", "CNPJ", "Competência", "Tamanho"]}>
        {resumo.amostra.map((a) => (
          <Linha key={a.caminho} apagada={!a.alimenta_a_cat}>
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
            Nada aqui alimenta a CAT 42, então não há o que importar.
          </span>
        )}
      </div>
    </Secao>
  );
}

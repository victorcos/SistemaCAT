import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { BarraFina, Cartao, Faixa, ListaDoLog, Rotulo, duracao, quando, valor, zero } from "@/components/shared/Rodada";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Aviso } from "@/components/ui/Aviso";
import { Botao, BotaoLink } from "@/components/ui/Botao";
import { Busca, Segmentado } from "@/components/ui/Filtros";
import { Modal } from "@/components/ui/Modal";
import { CabecalhoDePagina, Voltar } from "@/components/ui/Pagina";
import {
  IconeAprovar,
  IconeBaixar,
  IconeCarregando,
  IconeEntrega,
  IconeParar,
  IconeTentarDeNovo,
} from "@/constants/icons";
import { INTERVALO_POLL_MS } from "@/constants/polling";
import { ROTAS } from "@/constants/routes";
import { aceitaProcessamento } from "@/constants/status";
import { useAcao } from "@/hooks/useAcao";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { cn } from "@/lib/cn";
import { comoErro } from "@/lib/errors";
import { numero, tamanho } from "@/lib/format";
import type { Pagina } from "@/services/apuracao";
import { EM_CURSO } from "@/services/conferencia";
import {
  VERSAO_DO_RESUMO_DA_ENTREGA,
  aprovarEntrega,
  baixarPacoteDaEntrega,
  baixarRelatorioDaEntrega,
  cancelarEntrega,
  detalharEntrega,
  estabelecimentosDaEntrega,
  iniciarEntrega,
  listarEntrega,
  type EstabelecimentoDaEntrega,
  type ExecucaoDaEntrega,
  type Gravidade,
  type RecorteDeEstabelecimento,
  type ResumoDaEntrega,
} from "@/services/entrega";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/**
 * Etapa 8 — relatórios e entrega.
 *
 * Três regras mandam na tela: **o relatório mostra tudo e o dossiê só o que vai
 * à SEFAZ**; **montar não é entregar** — a entrega espera um revisor ou gestor
 * aprovar, e é isso que fecha a etapa; e **toda pendência diz o que fazer**,
 * da etapa em que nasceu.
 */

const ESPERA_PARA_CANCELAR_MS = 400;
const POR_PAGINA = 50;
const ESPERA_DA_BUSCA_MS = 350;

const cnpjFormatado = (c: string) =>
  c.length === 14 ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}` : c;

const TOM: Record<Gravidade, { borda: string; texto: string; titulo: string }> = {
  trava: { borda: "border-erro/35 bg-erro/8", texto: "text-erro", titulo: "Travam o envio" },
  atencao: { borda: "border-atencao/35 bg-atencao-fundo", texto: "text-atencao", titulo: "Pedem atenção" },
  informacao: { borda: "border-borda bg-superficie-vidro", texto: "text-texto-suave", titulo: "Para informação" },
};

export default function Entrega() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDaEntrega | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDaEntrega | null>(null);
  const [carregado, setCarregado] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [podeCancelar, setPodeCancelar] = useState(false);
  const relogio = useRef<number | null>(null);

  const parar = () => {
    if (relogio.current !== null) {
      window.clearInterval(relogio.current);
      relogio.current = null;
    }
  };

  const acompanhar = useCallback(async (execucaoId: number) => {
    try {
      const e = await detalharEntrega(execucaoId);
      setAtual(e);
      if (e.situacao === "concluida") setResultado(e);
      if (!EM_CURSO.includes(e.situacao)) parar();
    } catch (x) {
      setErro(comoErro(x));
    }
  }, []);

  const seguir = useCallback(
    (execucaoId: number) => {
      parar();
      relogio.current = window.setInterval(() => acompanhar(execucaoId), INTERVALO_POLL_MS);
    },
    [acompanhar],
  );

  useEffect(() => {
    if (!projetoId) return;
    detalharProjeto(projetoId).then(setProjeto).catch((x) => setErro(comoErro(x)));
    listarEntrega(projetoId)
      .then((lista) => {
        const ultima = lista[0] ?? null;
        setAtual(ultima);
        setResultado(lista.find((e) => e.situacao === "concluida") ?? null);
        if (ultima && EM_CURSO.includes(ultima.situacao)) seguir(ultima.id);
      })
      .catch((x) => setErro(comoErro(x)))
      .finally(() => setCarregado(true));
    return parar;
  }, [projetoId, seguir]);

  const rodando = atual !== null && EM_CURSO.includes(atual.situacao);

  useEffect(() => {
    setPodeCancelar(false);
    if (!rodando) return;
    const t = window.setTimeout(() => setPodeCancelar(true), ESPERA_PARA_CANCELAR_MS);
    return () => window.clearTimeout(t);
  }, [rodando, atual?.id]);

  async function comecar() {
    setOcupado(true);
    setErro(null);
    try {
      const nova = await iniciarEntrega(projetoId);
      setAtual(nova);
      seguir(nova.id);
    } catch (x) {
      setErro(comoErro(x));
    } finally {
      setOcupado(false);
    }
  }

  async function cancelar() {
    if (!atual) return;
    try {
      const e = await cancelarEntrega(atual.id);
      setAtual(e);
      if (!EM_CURSO.includes(e.situacao)) parar();
    } catch (x) {
      setErro(comoErro(x));
    }
  }

  const anda = !projeto || aceitaProcessamento(projeto.projeto.status);
  const resumo = resultado?.resumo ?? null;
  const anterior = resultado !== null && (resumo?.versao ?? 0) < VERSAO_DO_RESUMO_DA_ENTREGA;
  const p = projeto?.projeto;

  let acao: ReactNode = null;
  if (rodando && atual) {
    acao =
      atual.situacao === "cancelando" ? (
        <Botao variante="secundario" carregando>
          Cancelando…
        </Botao>
      ) : podeCancelar ? (
        <Botao variante="secundario" icone={IconeParar} onClick={cancelar}>
          Cancelar
        </Botao>
      ) : (
        <Botao carregando>Montando…</Botao>
      );
  } else if (atual) {
    acao = (
      <Botao
        icone={IconeTentarDeNovo}
        onClick={comecar}
        carregando={ocupado}
        disabled={!anda}
        variante={resultado?.aprovada_em ? "secundario" : "principal"}
        className={resultado?.aprovada_em ? undefined : "shadow-acao"}
      >
        {resultado && !anterior ? "Montar de novo" : "Montar a entrega"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="Etapa 8 · Entrega"
        titulo="Relatórios e entrega"
        sub="O relatório executivo com todas as competências e o que falta em cada uma, e o dossiê de cada estabelecimento só com o que vai à SEFAZ. A etapa fecha quando um revisor ou gestor aprova."
        acao={
          <div className="flex flex-col items-end gap-2.5">
            {acao}
            {resultado && !rodando && (
              <p className="m-0 text-right text-[11px] leading-normal text-texto-fraco">
                Montado em {quando(resultado.terminada_em)}
                {resumo?.iniciada_por ? ` por ${resumo.iniciada_por}` : ""}
              </p>
            )}
          </div>
        }
      >
        {p && (
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-[13px] font-semibold text-texto-suave">{p.empresa}</span>
            {p.cnpj_matriz_formatado && (
              <code className="font-mono text-xs text-texto-fraco">{p.cnpj_matriz_formatado}</code>
            )}
          </div>
        )}
      </CabecalhoDePagina>

      <TrabalhoParado status={p?.status} projetoId={projetoId} />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}

      {atual?.situacao === "falhou" && (
        <Aviso titulo="A montagem da entrega falhou">
          <span className="block">{atual.erro}</span>
          <code className="mt-2 inline-block rounded-lg border border-dashed border-erro/40 bg-erro/5 px-2.5 py-1.5 font-mono text-xs">
            execução #{atual.id}
          </code>
        </Aviso>
      )}

      {atual?.situacao === "cancelada" && (
        <Faixa titulo="A última rodada foi cancelada">
          Parou a pedido, sem deixar pacote pela metade.
          {resultado ? " Abaixo, a última entrega que foi montada." : " Rode de novo quando quiser."}
        </Faixa>
      )}

      {carregado && !atual && (
        <section className="flex flex-col items-center gap-3.5 rounded-cartao border border-dashed border-borda-forte px-7 py-10 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-[13px] border border-laranja-500/30 bg-laranja-500/14 text-laranja-700 escuro:text-laranja-300">
            <IconeEntrega size={20} strokeWidth={1.8} aria-hidden />
          </div>
          <p className="m-0 text-[17px] font-extrabold text-texto">A entrega ainda não foi montada</p>
          <p className="m-0 max-w-[620px] text-[13px] leading-relaxed text-texto-suave [text-wrap:pretty]">
            Precisa do arquivo digital gerado. O pacote leva o relatório de todas as competências e o dossiê
            dos estabelecimentos com competência pronta para envio; prévia nunca entra no dossiê.
          </p>
          <Botao onClick={comecar} carregando={ocupado} disabled={!anda} className="mt-1 shadow-acao">
            Montar a entrega
          </Botao>
        </section>
      )}

      {rodando && atual && <EmCurso e={atual} />}

      {anterior && !rodando && (
        <Faixa titulo="Execução de versão anterior">Esta entrega não guarda o resumo que a tela pede. Monte de novo.</Faixa>
      )}

      {resultado && resumo && !anterior && (
        <Concluida
          execucao={resultado}
          resumo={resumo}
          superada={atual !== null && atual.id !== resultado.id}
          anda={anda}
          aoAprovar={(e) => {
            setResultado(e);
            if (atual?.id === e.id) setAtual(e);
          }}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function EmCurso({ e }: { e: ExecucaoDaEntrega }) {
  const a = e.resumo?.andamento;
  return (
    <Cartao className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <IconeCarregando size={17} className="animate-spin text-marca-laranja" aria-hidden />
        <p className="m-0 text-[15px] font-extrabold text-texto">
          {e.situacao === "cancelando" ? "Cancelando…" : (e.passo ?? "Montando…")}
        </p>
        <code className="ml-auto font-mono text-[13px] text-laranja-700 escuro:text-laranja-300">
          {a && a.total ? `${numero(a.estabelecimentos)} de ${numero(a.total)} dossiês` : `${Math.round(e.fracao * 100)}%`}
        </code>
      </div>
      <BarraFina fracao={e.fracao} classe="bg-marca-laranja" />
      <p className="m-0 text-xs text-texto-fraco">Pode fechar esta tela: a montagem continua no servidor.</p>
      {(e.resumo?.log ?? []).length > 0 && <ListaDoLog log={e.resumo?.log ?? []} emCurso />}
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function Concluida({
  execucao,
  resumo,
  superada,
  anda,
  aoAprovar,
}: {
  execucao: ExecucaoDaEntrega;
  resumo: ResumoDaEntrega;
  /** há rodada mais nova (em curso, falha ou cancelada) que esta */
  superada: boolean;
  anda: boolean;
  aoAprovar: (e: ExecucaoDaEntrega) => void;
}) {
  const download = useAcao();
  const [baixando, setBaixando] = useState<"pacote" | "relatorio" | null>(null);

  async function baixar(qual: "pacote" | "relatorio") {
    setBaixando(qual);
    await download.executar((sinal) =>
      qual === "pacote" ? baixarPacoteDaEntrega(execucao.id, sinal) : baixarRelatorioDaEntrega(execucao.id, sinal),
    );
    setBaixando(null);
  }

  const envio = resumo.para_envio ?? 0;
  const pendencias = resumo.pendencias ?? [];

  return (
    <div className="flex flex-col gap-5">
      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} aoFechar={() => download.setErro(null)} />
      )}

      <Aprovacao execucao={execucao} resumo={resumo} superada={superada} anda={anda} aoAprovar={aoAprovar} />

      <section className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-4">
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Prontas para enviar à SEFAZ</Rotulo>
          <p className={cn("m-0 font-mono text-[32px] leading-none", envio ? "text-sucesso" : "text-texto-fraco")}>
            {numero(envio)}
            <span className="ml-2 text-sm text-texto-fraco">de {numero(resumo.competencias_de_sp ?? 0)} de SP</span>
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Em {numero(resumo.estabelecimentos_no_dossie ?? 0)} estabelecimentos. Ressarcimento a pedir:{" "}
            <strong className="font-mono text-texto">{valor(resumo.ressarcimento_para_envio)}</strong>; complemento a
            recolher: <strong className="font-mono text-texto">{valor(resumo.complemento_para_envio)}</strong>. Os dois
            nunca se compensam.
          </p>
        </Cartao>
        <Cartao className="flex flex-col gap-2">
          <Rotulo>O que ficou de fora do dossiê</Rotulo>
          <p className={cn("m-0 font-mono text-[32px] leading-none", resumo.previas ? "text-atencao" : "text-texto-fraco")}>
            {numero(resumo.previas ?? 0)}
            <span className="ml-2 text-sm text-texto-fraco">prévias</span>
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Competências de SP com pendência: estão no relatório, com o que falta em cada uma.{" "}
            {(resumo.fora_de_sp ?? 0) > 0 && `${numero(resumo.fora_de_sp ?? 0)} fora de SP não geram arquivo. `}
            Apurado em todas: {valor(resumo.ressarcimento)} de ressarcimento.
          </p>
        </Cartao>
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Pacote</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-texto">
            {numero(resumo.arquivos_no_pacote ?? 0)}
            <span className="ml-2 text-sm text-texto-fraco">arquivos · {tamanho(resumo.bytes_do_pacote ?? 0)}</span>
          </p>
          <p className="m-0 truncate font-mono text-[11px] text-texto-fraco" title={resumo.sha256_do_pacote}>
            SHA-256 {resumo.sha256_do_pacote?.slice(0, 24)}…
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            <Botao
              icone={IconeBaixar}
              className="shadow-acao"
              disabled={download.carregando}
              carregando={baixando === "pacote"}
              aoCancelar={baixando === "pacote" && download.podeCancelar ? download.cancelar : undefined}
              onClick={() => baixar("pacote")}
            >
              Baixar o pacote
            </Botao>
            <Botao
              variante="secundario"
              icone={IconeBaixar}
              disabled={download.carregando}
              carregando={baixando === "relatorio"}
              aoCancelar={baixando === "relatorio" && download.podeCancelar ? download.cancelar : undefined}
              onClick={() => baixar("relatorio")}
            >
              Só o relatório
            </Botao>
          </div>
        </Cartao>
      </section>

      {pendencias.length > 0 && (
        <Cartao className="flex flex-col gap-4">
          <div>
            <h2 className="m-0 text-base font-extrabold text-texto">Pendências de todas as etapas</h2>
            <p className="m-0 mt-1 max-w-[820px] text-xs leading-relaxed text-texto-suave">
              O que o revisor precisa ver antes de aprovar: cada pendência vem da etapa em que nasceu, com o que
              fazer. As mesmas estão na aba «Pendências» do relatório.
            </p>
          </div>
          {(["trava", "atencao", "informacao"] as Gravidade[]).map((g) => {
            const doTipo = pendencias.filter((x) => x.gravidade === g);
            if (doTipo.length === 0) return null;
            return (
              <div key={g} className="flex flex-col">
                <p className={cn("m-0 text-[11px] font-extrabold uppercase tracking-[0.14em]", TOM[g].texto)}>
                  {TOM[g].titulo} · {numero(doTipo.length)}
                </p>
                {doTipo.map((x) => (
                  <div key={`${x.etapa}-${x.codigo}`} className="flex flex-wrap items-center gap-3 border-t border-borda-sutil py-2.5">
                    <span className={cn("min-w-[92px] rounded-full border px-2 py-0.5 text-center font-mono text-[11px]", TOM[g].borda, TOM[g].texto)}>
                      {numero(x.quantidade)}
                    </span>
                    <span className="min-w-[260px] flex-1 text-[13px] text-texto">
                      <strong>{x.rotulo}</strong>
                      <span className="block text-[11px] text-texto-fraco">
                        {(x.medidas?.length ? x.medidas : [{ quantidade: x.quantidade, unidade: x.unidade, nome_da_etapa: x.nome_da_etapa }])
                          .map((m) => `${numero(m.quantidade)} ${m.unidade} em «${m.nome_da_etapa.toLowerCase()}»`)
                          .join(" · ")}
                      </span>
                    </span>
                    <span className="max-w-[520px] text-xs leading-relaxed text-texto-suave">{x.o_que_fazer}</span>
                  </div>
                ))}
              </div>
            );
          })}
        </Cartao>
      )}

      <Estabelecimentos execucaoId={execucao.id} total={resumo.estabelecimentos ?? 0} />

      {(resumo.log ?? []).length > 0 && (
        <Cartao className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <h2 className="m-0 flex-1 text-base font-extrabold text-texto">Log da última execução</h2>
            <code className="font-mono text-[11px] text-texto-fraco">
              execução #{execucao.id}
              {resumo.segundos ? ` · ${duracao(resumo.segundos)}` : ""}
            </code>
          </div>
          <ListaDoLog log={resumo.log ?? []} />
        </Cartao>
      )}

      <section className="flex flex-wrap items-center gap-3.5 rounded-cartao border border-borda bg-superficie-vidro px-5.5 py-4.5">
        <div className="min-w-[240px] flex-1">
          <p className="m-0 text-sm font-extrabold text-texto">Depois de baixar</p>
          <p className="m-0 mt-1 text-xs leading-relaxed text-texto-suave">
            O pacote é montado no disco local. Ao copiar para a pasta do cliente na rede, confira o SHA-256 de cada
            arquivo com o MANIFESTO.txt que vai dentro dele.
          </p>
        </div>
        <BotaoLink para={ROTAS.projeto(execucao.projeto_id)} variante="secundario">
          Ver as etapas
        </BotaoLink>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function Aprovacao({
  execucao,
  resumo,
  superada,
  anda,
  aoAprovar,
}: {
  execucao: ExecucaoDaEntrega;
  resumo: ResumoDaEntrega;
  superada: boolean;
  anda: boolean;
  aoAprovar: (e: ExecucaoDaEntrega) => void;
}) {
  const { podeAprovarEntrega } = useAuth();
  const toast = useToast();
  const [aberto, setAberto] = useState(false);
  const [observacao, setObservacao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);

  if (execucao.aprovada_em) {
    return (
      <section className="flex flex-wrap items-center gap-3.5 rounded-cartao border border-sucesso/25 border-l-[3px] border-l-sucesso bg-sucesso-fundo px-5 py-4">
        <IconeAprovar size={20} className="text-sucesso" aria-hidden />
        <p className="m-0 flex-1 text-[13px] leading-relaxed text-texto">
          <strong className="text-sucesso">Entrega aprovada</strong>
          {execucao.aprovada_por ? ` por ${execucao.aprovada_por}` : ""} em {quando(execucao.aprovada_em)}. A etapa 8 está
          concluída; o histórico do trabalho guarda a aprovação.
        </p>
      </section>
    );
  }

  const travas = resumo.por_gravidade?.trava ?? 0;

  async function confirmar() {
    setEnviando(true);
    setErro(null);
    try {
      const e = await aprovarEntrega(execucao.id, observacao);
      aoAprovar(e);
      setAberto(false);
      toast.sucesso("Entrega aprovada", "A etapa 8 está concluída.");
    } catch (x) {
      setErro(comoErro(x));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="flex flex-wrap items-center gap-3.5 rounded-cartao border border-atencao/25 border-l-[3px] border-l-atencao bg-atencao-fundo px-5 py-4">
      <div className="min-w-[260px] flex-1">
        <p className="m-0 text-sm font-extrabold text-atencao">Aguardando aprovação</p>
        <p className="m-0 mt-1 max-w-[820px] text-[13px] leading-relaxed text-texto">
          {superada
            ? "Há uma rodada mais nova desta entrega. Aprove a mais recente quando ela concluir."
            : podeAprovarEntrega
              ? "Confira o pacote, o relatório e as pendências abaixo. Aprovar conclui a etapa 8 e fica no histórico com o seu nome."
              : "Só um revisor ou gestor aprova a entrega. Quando aprovarem, a etapa 8 fica concluída."}
        </p>
      </div>
      {podeAprovarEntrega && !superada && (
        <Botao icone={IconeAprovar} onClick={() => setAberto(true)} disabled={!anda} className="shadow-acao">
          Aprovar a entrega
        </Botao>
      )}

      <Modal
        aberto={aberto}
        aoFechar={() => !enviando && setAberto(false)}
        tamanho="sm"
        titulo="Aprovar a entrega?"
        sub={`${numero(resumo.para_envio ?? 0)} competências para envio · ${valor(resumo.ressarcimento_para_envio)} de ressarcimento`}
        rodape={
          <>
            <Botao variante="fantasma" onClick={() => setAberto(false)} disabled={enviando}>
              Cancelar
            </Botao>
            <Botao onClick={confirmar} carregando={enviando} className="shadow-acao">
              Sim, aprovar
            </Botao>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}
          {(resumo.para_envio ?? 0) === 0 && (
            <p className="m-0 rounded-raio-g border border-atencao/25 bg-atencao-fundo px-3 py-2.5 text-[13px] leading-relaxed text-texto">
              Nenhuma competência está pronta para envio: aprovar entrega só o relatório, com o que falta.
            </p>
          )}
          {travas > 0 && (
            <p className="m-0 text-[13px] leading-relaxed text-texto-suave">
              {numero(travas)} pendências travam o envio das competências que ficaram de fora. Elas seguem no relatório.
            </p>
          )}
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold text-texto-suave">Observação (opcional)</span>
            <textarea
              rows={3}
              value={observacao}
              onChange={(e) => setObservacao(e.target.value)}
              maxLength={500}
              placeholder="O que foi conferido, com quem, o que fica para depois"
              className="w-full resize-y rounded-raio border border-borda-forte bg-superficie px-3 py-2.5 text-[14px] text-texto placeholder:text-texto-fraco focus:border-borda-foco focus:outline-none"
            />
          </label>
        </div>
      </Modal>
    </section>
  );
}

/* ------------------------------------------------------------------ */

function Estabelecimentos({ execucaoId, total }: { execucaoId: number; total: number }) {
  const [recorte, setRecorte] = useState<RecorteDeEstabelecimento>("todos");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<Pagina<EstabelecimentoDaEntrega> | null>(null);
  const leitura = useAcao();
  const { executar } = leitura;

  useEffect(() => {
    const t = window.setTimeout(() => setBuscaAplicada(busca), ESPERA_DA_BUSCA_MS);
    return () => window.clearTimeout(t);
  }, [busca]);

  const chave = `${recorte}|${buscaAplicada}`;
  const [chaveDaPagina, setChaveDaPagina] = useState(chave);
  const paginaAtual = chaveDaPagina === chave ? pagina : 1;
  useEffect(() => {
    setChaveDaPagina(chave);
    setPagina(1);
  }, [chave]);

  useEffect(() => {
    let vivo = true;
    executar((sinal) =>
      estabelecimentosDaEntrega(
        execucaoId,
        { recorte, busca: buscaAplicada, pagina: paginaAtual, porPagina: POR_PAGINA },
        sinal,
      ),
    ).then((r) => {
      if (vivo && r) setDados(r);
    });
    return () => {
      vivo = false;
    };
  }, [execucaoId, recorte, buscaAplicada, paginaAtual, executar]);

  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  const colunas = "grid-cols-[1.4fr_.5fr_.7fr_.7fr_.9fr_.9fr_1fr]";

  return (
    <section className="overflow-hidden rounded-cartao border border-borda bg-superficie shadow-cat">
      <div className="flex flex-wrap items-center gap-3.5 border-b border-borda px-5.5 py-4.5">
        <div className="min-w-0 flex-1">
          <h2 className="m-0 text-lg font-extrabold text-texto">Estabelecimentos</h2>
          <p className="m-0 mt-1 text-xs text-texto-fraco">
            {dados ? `${numero(dados.total)} neste recorte · ${numero(total)} no total` : "Carregando…"}
          </p>
        </div>
        <Busca valor={busca} aoMudar={setBusca} placeholder="Buscar CNPJ…" className="max-w-[260px]" />
        <Segmentado<RecorteDeEstabelecimento>
          rotulo="Recorte dos estabelecimentos"
          valor={recorte}
          aoMudar={setRecorte}
          opcoes={[
            { chave: "todos", rotulo: "Todos" },
            { chave: "no_dossie", rotulo: "No dossiê" },
            { chave: "com_previa", rotulo: "Com prévia" },
            { chave: "fora_de_sp", rotulo: "Fora de SP" },
          ]}
        />
      </div>

      {leitura.erro && (
        <div className="px-5.5 pt-4">
          <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />
        </div>
      )}

      <div className={cn("overflow-x-auto transition-opacity", leitura.carregando && "opacity-60")}>
        <div className="min-w-[980px]">
          <div className={cn("grid gap-3 bg-tabela-cabecalho-fundo px-5.5 py-3", colunas)}>
            {["Estabelecimento", "UF", "Competências", "Para envio", "Ressarcimento p/ envio", "Complemento p/ envio", "Dossiê"].map(
              (c, i) => (
                <span
                  key={c}
                  className={cn(
                    "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                    i >= 2 && i <= 5 && "text-right",
                  )}
                >
                  {c}
                </span>
              ),
            )}
          </div>
          {dados?.linhas.map((e) => (
            <div key={e.cnpj} className={cn("grid items-center gap-3 border-t border-borda-sutil px-5.5 py-3", colunas)}>
              <code className="font-mono text-xs text-texto">{cnpjFormatado(e.cnpj)}</code>
              <span className="text-xs text-texto-suave">{e.uf || "—"}</span>
              <span className="text-right font-mono text-xs text-texto-suave">
                {numero(e.competencias)}
                {e.previas > 0 && <span className="block text-[11px] text-atencao">{numero(e.previas)} prévias</span>}
              </span>
              <span className={cn("text-right font-mono text-[13px]", e.para_envio ? "text-sucesso" : "text-texto-fraco")}>
                {numero(e.para_envio)}
              </span>
              <span className={cn("text-right font-mono text-[13px]", zero(e.ressarcimento_para_envio) ? "text-texto-fraco" : "text-sucesso")}>
                {valor(e.ressarcimento_para_envio)}
              </span>
              <span className="text-right font-mono text-[13px] text-texto-suave">{valor(e.complemento_para_envio)}</span>
              <span>
                {e.no_dossie ? (
                  <span className="rounded-full border border-sucesso/35 bg-sucesso-fundo px-2 py-0.5 text-[10px] font-bold text-sucesso">
                    {numero(e.arquivos_no_dossie)} arquivos · {tamanho(e.bytes_no_dossie)}
                  </span>
                ) : (
                  <span className="text-[11px] text-texto-fraco">{e.fora_de_sp ? "fora de SP" : "só no relatório"}</span>
                )}
              </span>
            </div>
          ))}
          {dados && dados.linhas.length === 0 && (
            <p className="m-0 border-t border-borda-sutil px-5.5 py-10 text-center text-[13px] text-texto-fraco">
              Nenhum estabelecimento neste recorte.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-borda bg-superficie-vidro px-5.5 py-3.5">
        <Botao
          variante="secundario"
          tamanho="sm"
          onClick={() => setPagina(Math.max(1, paginaAtual - 1))}
          disabled={paginaAtual <= 1 || leitura.carregando}
        >
          Anterior
        </Botao>
        <span className="font-mono text-xs text-texto-fraco">
          {numero(paginaAtual)} / {numero(paginas)}
        </span>
        <Botao
          variante="secundario"
          tamanho="sm"
          onClick={() => setPagina(Math.min(paginas, paginaAtual + 1))}
          disabled={paginaAtual >= paginas || leitura.carregando}
        >
          Próxima
        </Botao>
      </div>
    </section>
  );
}

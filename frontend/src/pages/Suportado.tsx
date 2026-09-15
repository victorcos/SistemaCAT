import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Aviso } from "@/components/ui/Aviso";
import { Botao, BotaoLink } from "@/components/ui/Botao";
import { Busca, Segmentado } from "@/components/ui/Filtros";
import { Modal } from "@/components/ui/Modal";
import { CabecalhoDePagina, Voltar } from "@/components/ui/Pagina";
import {
  IconeApuracao,
  IconeBaixar,
  IconeCarregando,
  IconeExpandir,
  IconeParar,
  IconeTentarDeNovo,
} from "@/constants/icons";
import { INTERVALO_POLL_MS } from "@/constants/polling";
import { ROTAS } from "@/constants/routes";
import { aceitaProcessamento } from "@/constants/status";
import { useAcao } from "@/hooks/useAcao";
import { cn } from "@/lib/cn";
import { comoErro } from "@/lib/errors";
import { numero } from "@/lib/format";
import { EM_CURSO, type Formato } from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import { listarMovimentos } from "@/services/movimentos";
import {
  FONTES,
  VERSAO_DO_RESUMO,
  baixarPlanilhaDoSuportado,
  cancelarSuportado,
  detalharSuportado,
  iniciarSuportado,
  linhasDoSuportado,
  listarSuportado,
  nomeDaPlanilha,
  type DocumentoDoAnalitico,
  type EntradaDoLog,
  type Escopo,
  type ExecucaoDoSuportado,
  type Fonte,
  type ItemDoAnalitico,
  type PaginaDoAnalitico,
  type ResumoDoSuportado,
} from "@/services/suportado";
import type { ErroApi } from "@/types/erro";

/**
 * Etapa 4 — apurar o ICMS suportado.
 *
 * O imposto que entrou com a mercadoria não vem pronto: sai de uma cascata de
 * quatro fontes, e a tela existe para dizer de onde veio cada real. Duas
 * regras não se negociam (docs do handoff da etapa 4):
 *
 * 1. **o total nunca aparece sem a fração documental ao lado** — um número
 *    alto apoiado em reconstrução não é o mesmo trabalho que o mesmo número
 *    apoiado em nota;
 * 2. **não apurável não é sempre erro** — CST 40 não tem imposto suportado
 *    por definição, e pintá-lo de alerta treina quem confere a ignorar o
 *    alerta que importa.
 */

/** Tempo até o Cancelar da rodada aparecer: abaixo disto, trocar o rótulo pisca. */
const ESPERA_PARA_CANCELAR_MS = 400;
const POR_PAGINA = 50;
const ESPERA_DA_BUSCA_MS = 350;

/* ------------------------------------------------------------------ */
/* as quatro fontes: cor, rótulo curto e o que cada uma é               */
/* ------------------------------------------------------------------ */

interface AparenciaDaFonte {
  curto: string;
  oQueE: string;
  barra: string;
  ponto: string;
  pilula: string;
  texto: string;
}

/** Verde e azul são documento; âmbar é reconstrução; cinza é neutro, não erro. */
const FONTE: Record<Fonte, AparenciaDaFonte> = {
  documento: {
    curto: "Destacado",
    oQueE: "Operação própria mais retenção, destacadas no próprio C170 da entrada.",
    barra: "border-l-sucesso",
    ponto: "bg-sucesso",
    pilula: "border-sucesso/30 bg-sucesso-fundo text-sucesso",
    texto: "text-sucesso",
  },
  informado_pelo_fornecedor: {
    curto: "Informado",
    oQueE:
      "O imposto que o relatório do cliente informa para o item — XML, ERP ou ST retido antes, nessa ordem.",
    barra: "border-l-info",
    ponto: "bg-info",
    pilula: "border-info/30 bg-info-fundo text-info",
    texto: "text-info",
  },
  base_e_aliquota: {
    curto: "Reconstruído",
    oQueE: "Sem valor, mas com base de ST e alíquota interna do cadastro de itens (0200).",
    barra: "border-l-atencao",
    ponto: "bg-atencao",
    pilula: "border-atencao/35 bg-atencao-fundo text-atencao",
    texto: "text-atencao",
  },
  nao_apuravel: {
    curto: "Não apurável",
    oQueE: "Nada disso existe. Entra com zero e fica marcado com o motivo.",
    barra: "border-l-texto-fraco",
    ponto: "bg-texto-fraco",
    pilula: "border-borda-forte bg-superficie-alt text-texto-suave",
    texto: "text-texto-suave",
  },
};

const ROTULO_DO_CST: Record<string, string> = {
  "00": "Tributada integralmente",
  "10": "Tributada com ST",
  "20": "Com redução de base",
  "30": "Isenta ou não tributada, com ST",
  "40": "Isenta",
  "41": "Não tributada",
  "50": "Suspensão",
  "51": "Diferimento",
  "60": "ST já recolhida na origem",
  "70": "Redução de base com ST",
  "90": "Outras",
};

/** CST em que deveria haver imposto suportado: sem valor, é dado que falta. */
const CST_DE_SUBSTITUICAO = new Set(["10", "30", "60", "70", "90"]);

const MODELO: Record<string, string> = {
  "55": "NF-e",
  "65": "NFC-e",
  "59": "CF-e-SAT",
  "01": "NF",
  "04": "NF produtor",
  "57": "CT-e",
};

/* ------------------------------------------------------------------ */
/* formatação: número de tabela é monoespaçado e sem "R$"               */
/* ------------------------------------------------------------------ */

const valor = (texto: string | number | undefined) =>
  Number(texto ?? 0).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

const pct = (fracao: number | undefined) =>
  `${((fracao ?? 0) * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`;

const zero = (texto: string | undefined) => Number(texto ?? 0) === 0;

const mesAno = (competencia: string) => {
  const [ano, mes] = competencia.split("-");
  return mes && ano ? `${mes}/${ano}` : competencia || "—";
};

function quando(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("pt-BR")} às ${d.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

function duracao(segundos: number): string {
  const m = Math.floor(segundos / 60);
  const s = Math.round(segundos % 60);
  return m ? `${m} min ${String(s).padStart(2, "0")} s` : `${s} s`;
}

/* ------------------------------------------------------------------ */

export default function Suportado() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  // a última rodada diz o estado; a última concluída é a que tem o que mostrar
  const [atual, setAtual] = useState<ExecucaoDoSuportado | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDoSuportado | null>(null);
  const [carregado, setCarregado] = useState(false);
  const [itensProntos, setItensProntos] = useState<number | null>(null);
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
      const e = await detalharSuportado(execucaoId);
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
    // o contexto do estado vazio: quantos itens a etapa 3 deixou prontos
    listarMovimentos(projetoId)
      .then((l) => {
        const m = l.find((e) => e.situacao === "concluida");
        setItensProntos(m?.resumo?.movimentos_entrada ?? null);
      })
      .catch(() => setItensProntos(null));
    listarSuportado(projetoId)
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

  // o Cancelar só aparece depois de um instante: botão que pisca ninguém acerta
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
      const nova = await iniciarSuportado(projetoId);
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
    setErro(null);
    try {
      const e = await cancelarSuportado(atual.id);
      setAtual(e);
      if (!EM_CURSO.includes(e.situacao)) parar();
    } catch (x) {
      setErro(comoErro(x));
    }
  }

  const anda = !projeto || aceitaProcessamento(projeto.projeto.status);
  const resumo = resultado?.resumo ?? null;
  const anterior = resultado !== null && (resumo?.versao ?? 0) < VERSAO_DO_RESUMO;
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
        <Botao carregando>Apurando…</Botao>
      );
  } else if (atual) {
    acao = (
      <Botao
        icone={IconeTentarDeNovo}
        onClick={comecar}
        carregando={ocupado}
        disabled={!anda}
        className="shadow-acao"
      >
        {resultado && !anterior ? "Apurar de novo" : "Rodar a apuração"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="Etapa 4 · Apuração"
        titulo="Apurar o ICMS suportado"
        sub="O imposto que entrou com a mercadoria não vem pronto: sai de uma cascata de quatro fontes. Esta tela existe para dizer de onde veio cada real."
        acao={
          <div className="flex flex-col items-end gap-2.5">
            {acao}
            {resultado && !rodando && (
              <p className="m-0 text-right text-[11px] leading-normal text-texto-fraco">
                Apurado em {quando(resultado.terminada_em)}
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
            {p.uf && (
              <span className="rounded-md border border-borda-forte bg-superficie-alt px-1.5 py-0.5 text-[10px] font-extrabold tracking-[0.08em] text-texto-suave">
                {p.uf}
              </span>
            )}
          </div>
        )}
      </CabecalhoDePagina>

      <TrabalhoParado status={p?.status} projetoId={projetoId} />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}

      {atual?.situacao === "falhou" && (
        <Aviso titulo="A apuração falhou">
          <span className="block">{atual.erro}</span>
          <code className="mt-2 inline-block rounded-lg border border-dashed border-erro/40 bg-erro/5 px-2.5 py-1.5 font-mono text-xs">
            execução #{atual.id}
          </code>
          {resultado && (
            <span className="mt-2 block text-texto-suave">
              Abaixo, a última apuração que concluiu.
            </span>
          )}
        </Aviso>
      )}

      {atual?.situacao === "cancelada" && (
        <Faixa titulo="A última rodada foi cancelada">
          Parou a pedido, sem deixar resultado pela metade.
          {resultado ? " Abaixo, a última apuração que concluiu." : " Rode de novo quando quiser."}
        </Faixa>
      )}

      {anterior && !rodando && (
        <Faixa titulo="Execução de versão anterior">
          Esta apuração é de {quando(resultado?.terminada_em)} e não guarda a lista por fonte que a
          tela pede. Não é defeito: rode de novo para ver o detalhamento e baixar a planilha.
        </Faixa>
      )}

      {carregado && !atual && (
        <section className="flex flex-col items-center gap-3.5 rounded-cartao border border-dashed border-borda-forte px-7 py-10 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-[13px] border border-laranja-500/30 bg-laranja-500/14 text-laranja-700 escuro:text-laranja-300">
            <IconeApuracao size={20} strokeWidth={1.8} aria-hidden />
          </div>
          <p className="m-0 text-[17px] font-extrabold text-texto">A apuração ainda não rodou</p>
          <p className="m-0 max-w-[520px] text-[13px] leading-relaxed text-texto-suave [text-wrap:pretty]">
            {itensProntos !== null ? (
              <>
                Os movimentos da etapa 3 já estão extraídos:{" "}
                <strong className="font-mono text-texto">{numero(itensProntos)}</strong> itens de
                entrada prontos.{" "}
              </>
            ) : (
              "Precisa da extração de movimentos concluída. "
            )}
            Falta percorrer a cascata das quatro fontes e dizer quanto do total se apoia em
            documento.
          </p>
          <Botao onClick={comecar} carregando={ocupado} disabled={!anda} className="mt-1 shadow-acao">
            Apurar o ICMS suportado
          </Botao>
        </section>
      )}

      {rodando && atual && <EmCurso e={atual} />}

      {resultado && resumo && !anterior && (
        <Concluido execucao={resultado} resumo={resumo} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

/** Faixa neutra: informa sem acusar. */
function Faixa({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="rounded-raio-g border border-borda-forte border-l-[3px] border-l-texto-fraco bg-superficie-alt px-4.5 py-3.5">
      <p className="m-0 text-[13px] font-extrabold text-texto">{titulo}</p>
      <p className="m-0 mt-1.5 text-[13px] leading-relaxed text-texto-suave">{children}</p>
    </section>
  );
}

function Rotulo({ children }: { children: ReactNode }) {
  return (
    <p className="m-0 text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
      {children}
    </p>
  );
}

function Cartao({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-cartao border border-borda bg-superficie p-6 shadow-cat", className)}>
      {children}
    </div>
  );
}

function BarraFina({ fracao, classe, altura = "h-2" }: { fracao: number; classe: string; altura?: string }) {
  return (
    <div className={cn("overflow-hidden rounded-full bg-superficie-alt", altura)}>
      <div
        className={cn("h-full rounded-full transition-[width] duration-300", classe)}
        style={{ width: `${Math.max(0, Math.min(100, fracao * 100))}%` }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */

function EmCurso({ e }: { e: ExecucaoDoSuportado }) {
  const a = e.resumo?.andamento;
  // sem andamento, a rodada ainda está nos relatórios do cliente
  const contadores = !a
    ? [
        { rotulo: "Relatórios lidos", valor: `${numero(e.arquivos_lidos)} de ${numero(e.arquivos_totais)}` },
        { rotulo: "Itens percorridos", valor: "—" },
        { rotulo: "Estabelecimentos", valor: "—" },
      ]
    : [
        { rotulo: "Itens percorridos", valor: `${numero(a.itens)} de ${numero(a.total)}` },
        { rotulo: "Apurados até agora", valor: numero(a.apurados) },
        { rotulo: "Estabelecimentos", valor: numero(a.estabelecimentos) },
      ];
  const log = e.resumo?.log ?? [];

  return (
    <Cartao className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <IconeCarregando size={17} className="animate-spin text-marca-laranja" aria-hidden />
        <p className="m-0 text-[15px] font-extrabold text-texto">
          {e.situacao === "cancelando" ? "Cancelando…" : "Apurando…"}
        </p>
        <code className="ml-auto font-mono text-[13px] text-laranja-700 escuro:text-laranja-300">
          {Math.round(e.fracao * 100)}%
        </code>
      </div>
      <BarraFina fracao={e.fracao} classe="bg-marca-laranja" />
      <div className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-3">
        {contadores.map((c) => (
          <div key={c.rotulo} className="rounded-[11px] border border-borda bg-superficie-vidro px-3.5 py-3">
            <Rotulo>{c.rotulo}</Rotulo>
            <p className="m-0 mt-1.5 font-mono text-[17px] text-texto">{c.valor}</p>
          </div>
        ))}
      </div>
      <p className="m-0 text-xs text-texto-fraco">
        {e.passo ?? "Na fila"}
        {e.situacao === "cancelando"
          ? " · para no próximo ponto seguro, sem deixar resultado pela metade."
          : " · pode fechar esta tela: a apuração continua no servidor."}
      </p>
      {log.length > 0 && <ListaDoLog log={log} emCurso />}
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function Concluido({ execucao, resumo }: { execucao: ExecucaoDoSuportado; resumo: ResumoDoSuportado }) {
  const [fonte, setFonte] = useState<Fonte | null>(null);
  const download = useAcao();
  const [baixando, setBaixando] = useState<Formato | null>(null);
  const [confirmar, setConfirmar] = useState<Formato | null>(null);

  const fatias = resumo.por_fonte ?? [];
  const fatia = (f: Fonte) => fatias.find((x) => x.codigo === f);
  const itens = resumo.itens ?? 0;
  const reconstruido = fatia("base_e_aliquota");
  const naoApuraveis = fatia("nao_apuravel")?.itens ?? 0;

  async function baixar(formato: Formato) {
    setConfirmar(null);
    setBaixando(formato);
    // o clique em "Baixar" do modal é o gesto que abre o "salvar como"
    await download.executar((sinal) =>
      baixarPlanilhaDoSuportado(execucao.id, fonte, formato, sinal),
    );
    setBaixando(null);
  }

  const par = (destaque?: boolean) => (
    <BaixarPlanilha
      destaque={destaque}
      aoBaixar={setConfirmar}
      desabilitado={download.carregando || itens === 0}
      baixando={baixando}
      aoCancelar={download.podeCancelar ? download.cancelar : undefined}
      rotulo={fonte ? "Baixar planilha filtrada" : "Baixar planilha"}
    />
  );

  return (
    <div className="flex flex-col gap-5">
      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} aoFechar={() => download.setErro(null)} />
      )}

      {/* cobertura e fração documental, e o total — nunca um sem o outro */}
      <section className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-4">
        <Cartao className="flex flex-col gap-4">
          <div>
            <Rotulo>Cobertura da apuração</Rotulo>
            <div className="mt-2 flex items-baseline gap-2.5">
              <span className="font-mono text-[38px] leading-none text-sucesso">{pct(resumo.cobertura)}</span>
              <span className="text-[13px] text-texto-suave">dos itens de entrada</span>
            </div>
            <div className="mt-3">
              <BarraFina fracao={resumo.cobertura ?? 0} classe="bg-sucesso" />
            </div>
            <p className="m-0 mt-2 font-mono text-xs text-texto-fraco">
              {numero(resumo.apurados ?? 0)} de {numero(itens)} itens
            </p>
          </div>
          <div className="h-px bg-borda" />
          <div>
            <Rotulo>Fração documental</Rotulo>
            <div className="mt-2 flex items-baseline gap-2.5">
              <span className="font-mono text-[38px] leading-none text-sucesso">
                {pct(resumo.fracao_documental)}
              </span>
              <span className="text-[13px] text-texto-suave">do valor apurado</span>
            </div>
            <div className="mt-3">
              <BarraFina fracao={resumo.fracao_documental ?? 0} classe="bg-sucesso" />
            </div>
            <p className="m-0 mt-2 text-xs leading-relaxed text-texto-fraco">
              Quanto do total se apoia em documento fiscal.{" "}
              {zero(reconstruido?.valor)
                ? "Nada aqui foi reconstruído por alíquota."
                : `${valor(reconstruido?.valor)} foram reconstruídos por base e alíquota — não é documento.`}
            </p>
          </div>
        </Cartao>

        <Cartao className="flex flex-col gap-3.5">
          <Rotulo>ICMS suportado apurado</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-texto">{valor(resumo.valor_total)}</p>
          <div className="mt-0.5 flex flex-col gap-2.5">
            <LinhaDoTotal rotulo="Apoiado em documento" valor={valor(resumo.valor_documental)} classe="text-sucesso" />
            <LinhaDoTotal rotulo="Reconstruído por alíquota" valor={valor(reconstruido?.valor)} classe="text-atencao" />
            <LinhaDoTotal rotulo="Itens sem apuração" valor={numero(naoApuraveis)} classe="text-texto-suave" />
          </div>
          <p className="m-0 mt-auto pt-2 text-xs text-texto-fraco">
            {numero(resumo.estabelecimentos ?? 0)} estabelecimento(s)
            {resumo.relatorios
              ? ` · ${numero(resumo.relatorios.arquivos)} relatório(s) do cliente lido(s)`
              : ""}
          </p>
        </Cartao>
      </section>

      <Cascata
        fatias={fatias}
        fonte={fonte}
        aoEscolher={(f) => setFonte((atual) => (atual === f ? null : f))}
        acao={par(true)}
      />

      {naoApuraveis > 0 && <Pendencias resumo={resumo} naoApuraveis={naoApuraveis} />}

      <section className="grid grid-cols-[repeat(auto-fit,minmax(340px,1fr))] gap-4">
        <PorCst resumo={resumo} />
        <PorCompetencia resumo={resumo} />
      </section>

      <Analitico
        execucaoId={execucao.id}
        total={itens}
        fonte={fonte}
        aoLimparFonte={() => setFonte(null)}
        rodape={par()}
      />

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
          <p className="m-0 text-sm font-extrabold text-texto">Próxima etapa: a Ficha 3, item a item</p>
          <p className="m-0 mt-1 text-xs leading-relaxed text-texto-suave">
            Com o suportado apurado, o razão de controle de estoque pode ser montado por custo médio
            ponderado móvel.
          </p>
        </div>
        <BotaoLink para={ROTAS.projeto(execucao.projeto_id)} variante="secundario">
          Ver as etapas
        </BotaoLink>
      </section>

      <ConfirmarDownload
        formato={confirmar}
        fonte={fonte}
        linhas={fonte ? fatia(fonte)?.itens ?? 0 : itens}
        aoFechar={() => setConfirmar(null)}
        aoBaixar={baixar}
      />
    </div>
  );
}

function LinhaDoTotal({ rotulo, valor: v, classe }: { rotulo: string; valor: string; classe: string }) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="flex-1 text-[13px] text-texto-suave">{rotulo}</span>
      <span className={cn("font-mono text-sm", classe)}>{v}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function Cascata({
  fatias,
  fonte,
  aoEscolher,
  acao,
}: {
  fatias: NonNullable<ResumoDoSuportado["por_fonte"]>;
  fonte: Fonte | null;
  aoEscolher: (f: Fonte) => void;
  acao: ReactNode;
}) {
  const colunas = "grid-cols-[1.25fr_2fr_.75fr_1fr_.8fr]";
  return (
    <section className="overflow-hidden rounded-cartao border border-borda bg-superficie shadow-cat">
      <div className="flex flex-wrap items-center gap-3.5 border-b border-borda px-5.5 py-4.5">
        <div className="min-w-0 flex-1">
          <h2 className="m-0 text-lg font-extrabold text-texto">Cascata das quatro fontes</h2>
          <p className="m-0 mt-1 text-xs text-texto-fraco">
            Clique numa fonte para filtrar o analítico e a planilha.
            {fonte ? "" : " Nenhuma fonte selecionada."}
          </p>
        </div>
        {acao}
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[900px]" role="table">
          <div
            role="row"
            className={cn("grid gap-3.5 border-b border-borda bg-tabela-cabecalho-fundo px-5.5 py-3", colunas)}
          >
            {["Fonte", "O que é", "Itens", "Valor", "Documental"].map((c, i) => (
              <span
                key={c}
                role="columnheader"
                className={cn(
                  "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                  (i === 2 || i === 3) && "text-right",
                )}
              >
                {c}
              </span>
            ))}
          </div>
          {FONTES.map((codigo) => {
            const f = fatias.find((x) => x.codigo === codigo);
            const ap = FONTE[codigo];
            const ativo = fonte === codigo;
            return (
              <button
                key={codigo}
                type="button"
                role="row"
                aria-pressed={ativo}
                onClick={() => aoEscolher(codigo)}
                className={cn(
                  "grid w-full cursor-pointer gap-3.5 border-0 border-b border-l-[3px] border-b-borda-sutil px-5.5 py-3.5 text-left transition-colors",
                  colunas,
                  ap.barra,
                  ativo ? "bg-laranja-500/8" : "bg-transparent hover:bg-tabela-linha-hover",
                )}
              >
                <span className="flex min-w-0 items-center gap-2.5">
                  <span className={cn("h-[7px] w-[7px] shrink-0 rounded-full", ap.ponto)} />
                  <span
                    className={cn(
                      "text-[13px] font-bold",
                      ativo ? "text-laranja-700 escuro:text-laranja-300" : "text-texto",
                    )}
                  >
                    {f?.rotulo ?? codigo}
                  </span>
                </span>
                <span className="text-xs leading-normal text-texto-suave [text-wrap:pretty]">{ap.oQueE}</span>
                <span className="text-right font-mono text-[13px] text-texto-suave">{numero(f?.itens ?? 0)}</span>
                <span
                  className={cn(
                    "text-right font-mono text-[13px]",
                    zero(f?.valor) ? "text-texto-fraco" : "text-texto",
                  )}
                >
                  {valor(f?.valor)}
                </span>
                <span
                  className={cn(
                    "text-xs font-bold",
                    f?.documental === true
                      ? "text-sucesso"
                      : f?.documental === false
                        ? "text-atencao"
                        : "text-texto-fraco",
                  )}
                >
                  {f?.documental === true ? "sim" : f?.documental === false ? "não" : "—"}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <p className="m-0 border-t border-borda-sutil px-5.5 py-3.5 text-xs leading-relaxed text-texto-fraco">
        A ordem das linhas é a ordem da cascata: cada item é apurado pela primeira fonte que o atende.
      </p>
    </section>
  );
}

/* ------------------------------------------------------------------ */

function Pendencias({ resumo, naoApuraveis }: { resumo: ResumoDoSuportado; naoApuraveis: number }) {
  const semOQue = resumo.por_pendencia?.sem_o_que_apurar ?? 0;
  const falta = resumo.por_pendencia?.falta_dado ?? 0;
  const dominante = resumo.cst_sem_o_que_apurar;
  const parte = dominante && naoApuraveis ? dominante.itens / naoApuraveis : 0;
  const rotuloDominante = dominante
    ? `CST ${dominante.cst}${ROTULO_DO_CST[dominante.cst] ? ` — ${ROTULO_DO_CST[dominante.cst].toLowerCase()}` : ""}`
    : "CST sem substituição";

  return (
    <section className="rounded-cartao border border-atencao/25 border-l-[3px] border-l-atencao bg-atencao-fundo px-5 py-4.5">
      <p className="m-0 text-sm font-extrabold text-atencao">Não apurável não é sempre erro</p>
      <p className="m-0 mb-3.5 mt-2 max-w-[760px] text-[13px] leading-relaxed text-texto [text-wrap:pretty]">
        Dos {numero(naoApuraveis)} itens sem apuração,{" "}
        {dominante ? (
          <>
            <strong>
              {pct(parte)} são {rotuloDominante}
            </strong>{" "}
            — que não tem imposto suportado a apurar por definição.
          </>
        ) : (
          "nenhum é de CST sem substituição."
        )}{" "}
        Só o que falta dado exige providência.
      </p>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-3">
        <CartaoDePendencia
          etiqueta="Sem o que apurar"
          borda="border-borda-forte"
          texto="text-texto-suave"
          quantos={semOQue}
          rotulo={dominante ? `${rotuloDominante} e outros CST sem ST` : "CST sem substituição tributária"}
          nota="Não tem imposto suportado por definição. Não é pendência."
        />
        <CartaoDePendencia
          etiqueta="Falta dado"
          borda="border-atencao/35"
          texto="text-atencao"
          quantos={falta}
          rotulo="CST de substituição sem valor informado nem base com alíquota"
          nota="Exige providência: obter o relatório do cliente ou o XML com o retido, ou completar o cadastro de itens."
        />
      </div>
    </section>
  );
}

function CartaoDePendencia({
  etiqueta,
  borda,
  texto,
  quantos,
  rotulo,
  nota,
}: {
  etiqueta: string;
  borda: string;
  texto: string;
  quantos: number;
  rotulo: string;
  nota: string;
}) {
  return (
    <div className={cn("rounded-raio-g border bg-superficie px-4 py-3.5", borda)}>
      <span
        className={cn(
          "rounded-md border px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.1em]",
          borda,
          texto,
        )}
      >
        {etiqueta}
      </span>
      <p className={cn("m-0 mt-2.5 font-mono text-[22px]", texto)}>{numero(quantos)}</p>
      <p className="m-0 mt-1.5 text-xs font-bold text-texto">{rotulo}</p>
      <p className="m-0 mt-1 text-xs leading-relaxed text-texto-suave [text-wrap:pretty]">{nota}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function PorCst({ resumo }: { resumo: ResumoDoSuportado }) {
  const linhas = resumo.por_cst ?? [];
  const maior = Math.max(1, ...linhas.map((c) => Number(c.valor)));
  return (
    <Cartao className="flex flex-col gap-3.5">
      <h2 className="m-0 text-base font-extrabold text-texto">Por CST</h2>
      <div className="flex max-h-[420px] flex-col gap-2.5 overflow-y-auto pr-1">
        {linhas.map((c) => {
          const temValor = !zero(c.valor);
          // valor zero em CST de substituição é dado que falta; nos outros, é o esperado
          const barra = temValor
            ? "bg-info"
            : CST_DE_SUBSTITUICAO.has(c.cst)
              ? "bg-atencao/60"
              : "bg-texto-fraco/50";
          return (
            <div key={c.cst || "sem"} className="flex flex-col gap-1.5">
              <div className="flex items-baseline gap-2.5">
                <code className="min-w-8 font-mono text-xs text-laranja-700 escuro:text-laranja-300">
                  {c.cst || "—"}
                </code>
                <span className="flex-1 text-xs text-texto-suave">
                  {ROTULO_DO_CST[c.cst] ?? (c.cst ? "Outro" : "Sem CST")}
                </span>
                <span className="font-mono text-xs text-texto-suave">{numero(c.itens)}</span>
                <span
                  className={cn(
                    "min-w-[116px] text-right font-mono text-xs",
                    temValor ? "text-texto" : "text-texto-fraco",
                  )}
                >
                  {valor(c.valor)}
                </span>
              </div>
              <BarraFina
                fracao={temValor ? Number(c.valor) / maior : 0.02}
                classe={barra}
                altura="h-[5px]"
              />
            </div>
          );
        })}
      </div>
    </Cartao>
  );
}

function PorCompetencia({ resumo }: { resumo: ResumoDoSuportado }) {
  const linhas = resumo.por_competencia ?? [];
  const maior = Math.max(1, ...linhas.map((m) => Number(m.valor)));
  return (
    <Cartao className="flex flex-col gap-3.5">
      <h2 className="m-0 text-base font-extrabold text-texto">Por competência</h2>
      <div className="flex max-h-[420px] flex-col gap-2 overflow-y-auto pr-1">
        {linhas.map((m) => (
          <div key={m.competencia} className="flex items-center gap-3">
            <code className="min-w-[58px] font-mono text-xs text-texto-suave">{mesAno(m.competencia)}</code>
            <div className="flex-1">
              <BarraFina fracao={Number(m.valor) / maior} classe="bg-marca-laranja/85" />
            </div>
            <span className="min-w-[112px] text-right font-mono text-xs text-texto">{valor(m.valor)}</span>
            <span
              className={cn(
                "min-w-[50px] text-right font-mono text-[11px]",
                m.cobertura >= 0.65 ? "text-sucesso" : "text-atencao",
              )}
            >
              {pct(m.cobertura)}
            </span>
          </div>
        ))}
      </div>
      <p className="m-0 text-[11px] text-texto-fraco">
        A última coluna é a cobertura do mês — quanto dos itens daquela competência foi apurado.
      </p>
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function PilulaDaFonte({ fonte, motivo, pequena }: { fonte: Fonte; motivo?: string; pequena?: boolean }) {
  const ap = FONTE[fonte] ?? FONTE.nao_apuravel;
  return (
    <span
      title={motivo || undefined}
      className={cn(
        "inline-block whitespace-nowrap rounded-full border font-bold",
        pequena ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-[11px]",
        ap.pilula,
      )}
    >
      {ap.curto}
    </span>
  );
}

const truncarChave = (chave: string) =>
  !chave ? "Sem chave de acesso" : chave.length > 22 ? `${chave.slice(0, 22)}…` : chave;

function Analitico({
  execucaoId,
  total,
  fonte,
  aoLimparFonte,
  rodape,
}: {
  execucaoId: number;
  total: number;
  fonte: Fonte | null;
  aoLimparFonte: () => void;
  rodape: ReactNode;
}) {
  const [escopo, setEscopo] = useState<Escopo>("documento");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [pagina, setPagina] = useState(1);
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const [dados, setDados] = useState<PaginaDoAnalitico<DocumentoDoAnalitico | ItemDoAnalitico> | null>(null);
  const leitura = useAcao();
  const { executar } = leitura;

  // a busca espera a pessoa parar de digitar: uma ida ao servidor por tecla
  // agruparia milhões de itens a cada letra
  useEffect(() => {
    const t = window.setTimeout(() => setBuscaAplicada(busca), ESPERA_DA_BUSCA_MS);
    return () => window.clearTimeout(t);
  }, [busca]);

  // recorte novo começa da primeira página e com tudo fechado. A página vale
  // 1 já no render em que o recorte muda: resetar só num efeito depois
  // buscaria a página velha do recorte novo antes de buscar a certa
  const recorte = `${escopo}|${fonte ?? ""}|${buscaAplicada}`;
  const [recorteDaPagina, setRecorteDaPagina] = useState(recorte);
  const paginaAtual = recorteDaPagina === recorte ? pagina : 1;
  useEffect(() => {
    setRecorteDaPagina(recorte);
    setPagina(1);
    setAbertos(new Set());
  }, [recorte]);

  useEffect(() => {
    let vivo = true;
    executar((sinal) =>
      linhasDoSuportado(
        execucaoId,
        { escopo, fonte, busca: buscaAplicada, pagina: paginaAtual, porPagina: POR_PAGINA },
        sinal,
      ),
    ).then((r) => {
      if (vivo && r) setDados(r);
    });
    return () => {
      vivo = false;
    };
  }, [execucaoId, escopo, fonte, buscaAplicada, paginaAtual, executar]);

  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  const porDocumento = dados?.escopo === "documento";
  const colunas = "grid-cols-[26px_1.3fr_.85fr_.7fr_1fr_.9fr_.95fr]";
  const alternar = (chave: string) =>
    setAbertos((a) => {
      const novo = new Set(a);
      if (novo.has(chave)) novo.delete(chave);
      else novo.add(chave);
      return novo;
    });

  const dica = dados
    ? `${porDocumento ? "Clique na linha para abrir os itens. " : ""}${numero(dados.total)} ${
        porDocumento ? "documentos" : "itens"
      } neste recorte · ${numero(total)} itens no total`
    : "Carregando…";

  return (
    <section className="overflow-hidden rounded-cartao border border-borda bg-superficie shadow-cat">
      <div className="flex flex-wrap items-center gap-3.5 border-b border-borda px-5.5 py-4.5">
        <div className="min-w-0 flex-1">
          <h2 className="m-0 text-lg font-extrabold text-texto">Analítico</h2>
          <p className="m-0 mt-1 text-xs text-texto-fraco">{dica}</p>
        </div>
        <Busca
          valor={busca}
          aoMudar={setBusca}
          placeholder="Buscar documento, item ou chave…"
          className="max-w-[320px]"
        />
        <Segmentado<Escopo>
          rotulo="Escopo do analítico"
          valor={escopo}
          aoMudar={setEscopo}
          opcoes={[
            { chave: "documento", rotulo: "Por documento" },
            { chave: "item", rotulo: "Por item" },
          ]}
        />
      </div>

      {fonte && (
        <div className="flex items-center gap-2.5 border-b border-laranja-500/20 bg-laranja-500/7 px-5.5 py-3">
          <span className="text-xs text-texto-suave">Filtrado por fonte:</span>
          <span className="text-xs font-bold text-laranja-700 escuro:text-laranja-300">
            {FONTE[fonte].curto}
          </span>
          <Botao variante="secundario" tamanho="sm" onClick={aoLimparFonte}>
            limpar
          </Botao>
        </div>
      )}

      {leitura.erro && (
        <div className="px-5.5 pt-4">
          <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />
        </div>
      )}

      <div className={cn("overflow-x-auto transition-opacity", leitura.carregando && "opacity-60")}>
        <div className="min-w-[1080px]" role="table" aria-busy={leitura.carregando}>
          <div
            role="row"
            className={cn("grid gap-3 border-b border-borda bg-tabela-cabecalho-fundo px-5.5 py-3", colunas)}
          >
            {[
              "",
              porDocumento ? "Chave / documento" : "Código / descrição",
              porDocumento ? "Fornecedor" : "Fornecedor / chave",
              "CST",
              "Fonte",
              "Base ST",
              "Suportado",
            ].map((c, i) => (
              <span
                key={i}
                role="columnheader"
                className={cn(
                  "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                  i >= 5 && "text-right",
                )}
              >
                {c}
              </span>
            ))}
          </div>

          {dados?.linhas.map((linha) =>
            porDocumento ? (
              <LinhaDeDocumento
                key={linha.documento}
                d={linha as DocumentoDoAnalitico}
                aberto={abertos.has(linha.documento)}
                aoAlternar={() => alternar(linha.documento)}
                colunas={colunas}
              />
            ) : (
              <LinhaDeItem key={`${linha.documento}-${(linha as ItemDoAnalitico).codigo}`} i={linha as ItemDoAnalitico} colunas={colunas} />
            ),
          )}

          {dados && dados.linhas.length === 0 && (
            <div className="px-5.5 py-11 text-center">
              <p className="m-0 text-sm font-bold text-texto-suave">Nenhuma linha com esse recorte</p>
              <p className="m-0 mt-1 text-xs text-texto-fraco">Limpe a busca ou o filtro de fonte.</p>
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-borda bg-superficie-vidro px-5.5 py-3.5">
        <div className="flex items-center gap-2">
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
        <span className="min-w-[200px] flex-1 text-[11px] text-texto-fraco">
          A tela mostra uma página por vez, montada no servidor. A lista inteira sai pelos botões de
          download.
        </span>
        {rodape}
      </div>
    </section>
  );
}

function Dinheiro({ texto, forte }: { texto: string; forte?: boolean }) {
  return (
    <span
      className={cn(
        "text-right font-mono text-[13px]",
        zero(texto) ? "text-texto-fraco" : forte ? "text-texto" : "text-texto-suave",
      )}
    >
      {valor(texto)}
    </span>
  );
}

function LinhaDeDocumento({
  d,
  aberto,
  aoAlternar,
  colunas,
}: {
  d: DocumentoDoAnalitico;
  aberto: boolean;
  aoAlternar: () => void;
  colunas: string;
}) {
  return (
    <Fragment>
      <button
        type="button"
        role="row"
        aria-expanded={aberto}
        onClick={aoAlternar}
        className={cn(
          "grid w-full cursor-pointer items-center gap-3 border-0 border-b border-borda-sutil px-5.5 py-3.5 text-left transition-colors hover:bg-tabela-linha-hover",
          colunas,
          aberto ? "bg-superficie-alt" : "bg-transparent",
        )}
      >
        <IconeExpandir
          size={13}
          strokeWidth={2}
          aria-hidden
          className={cn("text-texto-fraco transition-transform", aberto && "rotate-90")}
        />
        <span className="min-w-0">
          <span
            className={cn("block font-mono text-[13px]", d.chave ? "text-texto" : "text-texto-fraco")}
            title={d.chave || undefined}
          >
            {truncarChave(d.chave)}
          </span>
          <span className="mt-0.5 block text-[11px] text-texto-fraco">
            {MODELO[d.modelo] ?? (d.modelo ? `Modelo ${d.modelo}` : "Documento")} {d.numero_documento ?? ""} ·{" "}
            {mesAno(d.competencia)} · {numero(d.itens)} {d.itens === 1 ? "item" : "itens"}
          </span>
        </span>
        <span className="truncate font-mono text-xs text-texto-suave">{d.participante ?? "—"}</span>
        <code className="font-mono text-xs text-laranja-700 escuro:text-laranja-300">{d.cst || "—"}</code>
        <span>
          <PilulaDaFonte fonte={d.fonte} />
        </span>
        <Dinheiro texto={d.bc_st} />
        <Dinheiro texto={d.suportado} forte />
      </button>

      {aberto && (
        <div className="animate-entrada border-b border-borda-sutil bg-superficie-alt/60 pb-4 pl-12 pr-5.5 pt-1">
          <Rotulo>
            <span className="block pb-2 pt-3">Itens do documento</span>
          </Rotulo>
          {d.filhos.map((i) => (
            <div
              key={i.codigo ?? i.descricao ?? ""}
              className="grid grid-cols-[1.2fr_1.1fr_.6fr_1fr_.85fr_.9fr] items-center gap-3 border-t border-borda-sutil py-2.5"
            >
              <span className="font-mono text-xs text-texto-suave">{i.codigo ?? "—"}</span>
              <span className="truncate text-xs text-texto-suave" title={i.descricao ?? undefined}>
                {i.descricao ?? "—"}
              </span>
              <code className="font-mono text-xs text-laranja-700 escuro:text-laranja-300">{i.cst || "—"}</code>
              <span>
                <PilulaDaFonte fonte={i.fonte} motivo={i.motivo} pequena />
              </span>
              <Dinheiro texto={i.bc_st} />
              <Dinheiro texto={i.suportado} forte />
            </div>
          ))}
        </div>
      )}
    </Fragment>
  );
}

function LinhaDeItem({ i, colunas }: { i: ItemDoAnalitico; colunas: string }) {
  return (
    <div
      role="row"
      className={cn(
        "grid items-center gap-3 border-b border-borda-sutil px-5.5 py-3.5 transition-colors hover:bg-tabela-linha-hover",
        colunas,
      )}
    >
      <span />
      <span className="min-w-0">
        <span className="block font-mono text-[13px] text-texto">{i.codigo ?? "—"}</span>
        <span className="mt-0.5 block truncate text-[11px] text-texto-fraco" title={i.descricao ?? undefined}>
          {i.descricao ?? "Sem descrição no cadastro"}
        </span>
      </span>
      <span className="min-w-0">
        <span className="block truncate font-mono text-xs text-texto-suave">{i.participante ?? "—"}</span>
        <span className="mt-0.5 block font-mono text-[11px] text-texto-fraco" title={i.chave}>
          {truncarChave(i.chave)} · {mesAno(i.competencia)}
        </span>
      </span>
      <code className="font-mono text-xs text-laranja-700 escuro:text-laranja-300">{i.cst || "—"}</code>
      <span>
        <PilulaDaFonte fonte={i.fonte} motivo={i.motivo} />
      </span>
      <Dinheiro texto={i.bc_st} />
      <Dinheiro texto={i.suportado} forte />
    </div>
  );
}

/* ------------------------------------------------------------------ */

/** Nível que a tela mostra: início, fonte lida, aviso, fim. */
function nivelDoLog(e: EntradaDoLog, i: number, todos: EntradaDoLog[]): [string, string] {
  if (e.nivel === "erro") return ["erro", "text-erro"];
  if (e.nivel === "aviso") return ["aviso", "text-atencao"];
  if (i === 0) return ["início", "text-info"];
  if (i === todos.length - 1 && e.texto.startsWith("Concluída")) return ["fim", "text-texto-suave"];
  return ["info", "text-sucesso"];
}

function ListaDoLog({ log, emCurso }: { log: EntradaDoLog[]; emCurso?: boolean }) {
  return (
    <div className="flex flex-col">
      {log.map((e, i) => {
        const [rotulo, classe] = nivelDoLog(e, i, log);
        return (
          <div key={`${e.em}-${i}`} className="flex gap-3.5 border-t border-borda-sutil py-2">
            <code className="w-[60px] shrink-0 font-mono text-xs text-texto-fraco">
              {new Date(e.em).toLocaleTimeString("pt-BR")}
            </code>
            <span className={cn("w-[90px] shrink-0 text-xs font-bold", classe)}>
              {emCurso && rotulo === "fim" ? "info" : rotulo}
            </span>
            <span className="flex-1 text-xs leading-relaxed text-texto-suave [text-wrap:pretty]">{e.texto}</span>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */

/**
 * O que a pessoa precisa saber antes de o download começar — nunca em
 * tooltip. As estimativas são por linha medida: a planilha comprime, o CSV
 * não; e o CSV tem o problema da chave de 44 dígitos no Excel.
 */
const BYTES_POR_LINHA: Record<Formato, number> = { xlsx: 110, csv: 260 };

function ConfirmarDownload({
  formato,
  fonte,
  linhas,
  aoFechar,
  aoBaixar,
}: {
  formato: Formato | null;
  fonte: Fonte | null;
  linhas: number;
  aoFechar: () => void;
  aoBaixar: (f: Formato) => void;
}) {
  const f = formato ?? "xlsx";
  const bytes = linhas * BYTES_POR_LINHA[f];
  const mb = bytes / 1024 / 1024;
  const tamanho = mb < 1 ? "< 1 MB" : `≈ ${numero(Math.round(mb))} MB`;
  const grande = mb >= 100;
  const abas = Math.ceil(linhas / 900_000);

  return (
    <Modal
      aberto={formato !== null}
      aoFechar={aoFechar}
      tamanho="sm"
      titulo={
        f === "xlsx"
          ? fonte
            ? "Baixar planilha filtrada"
            : "Baixar planilha completa"
          : "Baixar CSV"
      }
      sub={<code className="font-mono text-xs">{nomeDaPlanilha(fonte, f)}</code>}
      rodape={
        <>
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao icone={IconeBaixar} onClick={() => aoBaixar(f)}>
            {f === "xlsx" ? "Gerar e baixar" : "Baixar CSV"}
          </Botao>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-[11px] border border-borda bg-superficie-vidro px-3.5 py-3">
          <Rotulo>Linhas</Rotulo>
          <p className="m-0 mt-1.5 font-mono text-[17px] text-texto">{numero(linhas)}</p>
        </div>
        <div className="rounded-[11px] border border-borda bg-superficie-vidro px-3.5 py-3">
          <Rotulo>Tamanho estimado</Rotulo>
          <p className={cn("m-0 mt-1.5 font-mono text-[17px]", grande ? "text-atencao" : "text-sucesso")}>
            {tamanho}
          </p>
        </div>
      </div>

      {f === "xlsx" ? (
        <Aviso tom="atencao" titulo="Gerada no servidor antes de o download começar" className="mt-3.5">
          Uma linha por item, com a coluna Fonte dizendo de onde veio cada real e o Motivo de quem não
          apurou. A chave de acesso sai como texto.{" "}
          {abas > 1 ? `Passa do limite do Excel e sai em ${abas} abas. ` : ""}
          Numa base grande a geração leva minutos — dá para cancelar enquanto isso.
        </Aviso>
      ) : (
        <Aviso tom="erro" titulo="Importe como texto, não abra com dois cliques" className="mt-3.5">
          Abrir o CSV direto no Excel transforma a chave de acesso de 44 dígitos em notação
          científica e ela se perde. Use Dados › Obter dados › De texto/CSV e marque a coluna da
          chave como Texto.
        </Aviso>
      )}
    </Modal>
  );
}

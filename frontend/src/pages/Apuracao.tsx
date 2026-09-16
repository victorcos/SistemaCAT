import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import {
  BarraFina,
  Cartao,
  Faixa,
  ListaDoLog,
  Rotulo,
  duracao,
  mesAno,
  quando,
  valor,
  zero,
} from "@/components/shared/Rodada";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Aviso } from "@/components/ui/Aviso";
import { Botao, BotaoLink } from "@/components/ui/Botao";
import { Busca, Segmentado } from "@/components/ui/Filtros";
import { CabecalhoDePagina, Voltar } from "@/components/ui/Pagina";
import {
  IconeApuracao,
  IconeCarregando,
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
import {
  VERSAO_DO_RESUMO_DA_APURACAO,
  baixarPlanilhaDaApuracao,
  cancelarApuracao,
  competenciasApuradas,
  detalharApuracao,
  iniciarApuracao,
  listarApuracao,
  type Competencia,
  type ExecucaoDaApuracao,
  type Pagina,
  type PlanilhaDaApuracao,
  type RecorteDeCompetencia,
  type ResumoDaApuracao,
} from "@/services/apuracao";
import { EM_CURSO, type Formato } from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/**
 * Etapa 6 — apurar ressarcimento e complemento.
 *
 * O fechamento por estabelecimento e mês, que é a unidade do arquivo digital.
 * Duas regras mandam na tela: **ressarcimento e complemento nunca aparecem
 * somados** — um se pede, o outro se recolhe —, e **apurar não é poder
 * entregar**: o valor aparece sempre, e ao lado dele o que trava a competência.
 */

const ESPERA_PARA_CANCELAR_MS = 400;
const POR_PAGINA = 50;
const ESPERA_DA_BUSCA_MS = 350;

const cnpjFormatado = (c: string) =>
  c.length === 14 ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}` : c;

export default function Apuracao() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDaApuracao | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDaApuracao | null>(null);
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
      const e = await detalharApuracao(execucaoId);
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
    listarApuracao(projetoId)
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
      const nova = await iniciarApuracao(projetoId);
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
      const e = await cancelarApuracao(atual.id);
      setAtual(e);
      if (!EM_CURSO.includes(e.situacao)) parar();
    } catch (x) {
      setErro(comoErro(x));
    }
  }

  const anda = !projeto || aceitaProcessamento(projeto.projeto.status);
  const resumo = resultado?.resumo ?? null;
  const anterior = resultado !== null && (resumo?.versao ?? 0) < VERSAO_DO_RESUMO_DA_APURACAO;
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
      <Botao icone={IconeTentarDeNovo} onClick={comecar} carregando={ocupado} disabled={!anda} className="shadow-acao">
        {resultado && !anterior ? "Apurar de novo" : "Apurar o período"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="Etapa 6 · Apuração"
        titulo="Apurar ressarcimento e complemento"
        sub="O fechamento por estabelecimento e mês, que é a unidade do arquivo digital. O ressarcimento se pede, o complemento se recolhe, e eles nunca se compensam."
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
          </div>
        )}
      </CabecalhoDePagina>

      <TrabalhoParado status={p?.status} projetoId={projetoId} />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}

      {atual?.situacao === "falhou" && (
        <Aviso titulo="A apuração do período falhou">
          <span className="block">{atual.erro}</span>
          <code className="mt-2 inline-block rounded-lg border border-dashed border-erro/40 bg-erro/5 px-2.5 py-1.5 font-mono text-xs">
            execução #{atual.id}
          </code>
        </Aviso>
      )}

      {atual?.situacao === "cancelada" && (
        <Faixa titulo="A última rodada foi cancelada">
          Parou a pedido, sem gravar nada.
          {resultado ? " Abaixo, a última apuração que concluiu." : " Rode de novo quando quiser."}
        </Faixa>
      )}

      {carregado && !atual && (
        <section className="flex flex-col items-center gap-3.5 rounded-cartao border border-dashed border-borda-forte px-7 py-10 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-[13px] border border-laranja-500/30 bg-laranja-500/14 text-laranja-700 escuro:text-laranja-300">
            <IconeApuracao size={20} strokeWidth={1.8} aria-hidden />
          </div>
          <p className="m-0 text-[17px] font-extrabold text-texto">O período ainda não foi apurado</p>
          <p className="m-0 max-w-[560px] text-[13px] leading-relaxed text-texto-suave [text-wrap:pretty]">
            Precisa do razão montado. Aqui a Ficha 3 fecha por estabelecimento e mês, com os saldos que
            o arquivo digital vai exigir, e cada competência diz se está pronta para virar arquivo.
          </p>
          <Botao onClick={comecar} carregando={ocupado} disabled={!anda} className="mt-1 shadow-acao">
            Apurar o período
          </Botao>
        </section>
      )}

      {rodando && atual && <EmCurso e={atual} />}

      {anterior && !rodando && (
        <Faixa titulo="Execução de versão anterior">
          Esta apuração não guarda o resumo que a tela pede. Rode de novo.
        </Faixa>
      )}

      {resultado && resumo && !anterior && <Concluido execucao={resultado} resumo={resumo} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function EmCurso({ e }: { e: ExecucaoDaApuracao }) {
  const a = e.resumo?.andamento;
  return (
    <Cartao className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <IconeCarregando size={17} className="animate-spin text-marca-laranja" aria-hidden />
        <p className="m-0 text-[15px] font-extrabold text-texto">
          {e.situacao === "cancelando" ? "Cancelando…" : "Fechando o período…"}
        </p>
        <code className="ml-auto font-mono text-[13px] text-laranja-700 escuro:text-laranja-300">
          {numero(a?.competencias ?? 0)} competências
        </code>
      </div>
      <BarraFina fracao={e.fracao} classe="bg-marca-laranja" />
      <p className="m-0 text-xs text-texto-fraco">
        {e.passo ?? "Na fila"} · pode fechar esta tela: a apuração continua no servidor.
      </p>
      {(e.resumo?.log ?? []).length > 0 && <ListaDoLog log={e.resumo?.log ?? []} emCurso />}
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function Concluido({ execucao, resumo }: { execucao: ExecucaoDaApuracao; resumo: ResumoDaApuracao }) {
  const download = useAcao();
  const [baixando, setBaixando] = useState<{ qual: PlanilhaDaApuracao; formato: Formato } | null>(null);

  async function baixar(qual: PlanilhaDaApuracao, formato: Formato) {
    setBaixando({ qual, formato });
    await download.executar((sinal) => baixarPlanilhaDaApuracao(execucao.id, qual, formato, sinal));
    setBaixando(null);
  }

  const par = (qual: PlanilhaDaApuracao, rotulo: string, destaque?: boolean) => (
    <BaixarPlanilha
      destaque={destaque}
      aoBaixar={(formato) => baixar(qual, formato)}
      desabilitado={download.carregando || (resumo.competencias ?? 0) === 0}
      baixando={baixando?.qual === qual ? baixando.formato : null}
      aoCancelar={download.podeCancelar ? download.cancelar : undefined}
      rotulo={rotulo}
    />
  );

  const aptas = resumo.aptas ?? 0;
  const total = resumo.competencias ?? 0;

  return (
    <div className="flex flex-col gap-5">
      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} aoFechar={() => download.setErro(null)} />
      )}

      <section className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-4">
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Ressarcimento a pedir</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-sucesso">{valor(resumo.ressarcimento)}</p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Apurado no período inteiro. Pronto para pedir hoje, só das competências sem pendência:{" "}
            <strong className="font-mono text-texto">{valor(resumo.ressarcimento_apto)}</strong>.
          </p>
        </Cartao>
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Complemento a recolher</Rotulo>
          <p className={cn("m-0 font-mono text-[32px] leading-none", zero(resumo.complemento) ? "text-texto-fraco" : "text-atencao")}>
            {valor(resumo.complemento)}
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Não se compensa com o ressarcimento: um é crédito a pedir, o outro é imposto a recolher. Só
            existe no enquadramento 1.
          </p>
        </Cartao>
        {!zero(resumo.credito_operacao_propria ?? "0") && (
          <Cartao className="flex flex-col gap-2">
            <Rotulo>Crédito da operação própria (art. 271)</Rotulo>
            <p className="m-0 font-mono text-[32px] leading-none text-sucesso">{valor(resumo.credito_operacao_propria ?? "0")}</p>
            <p className="m-0 text-xs leading-relaxed text-texto-fraco">
              Nas saídas para outro estado, o ICMS próprio das entradas volta como crédito, ao lado do ressarcimento.
            </p>
          </Cartao>
        )}
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Competências prontas</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-texto">
            {numero(aptas)}
            <span className="ml-2 text-sm text-texto-fraco">de {numero(total)}</span>
          </p>
          <div className="mt-1">
            <BarraFina fracao={total ? aptas / total : 0} classe={aptas === total ? "bg-sucesso" : "bg-atencao"} />
          </div>
          <p className="m-0 font-mono text-xs text-texto-fraco">
            {numero(resumo.estabelecimentos_aptos ?? 0)} de {numero(resumo.estabelecimentos ?? 0)} estabelecimentos ·{" "}
            {numero(resumo.saldos ?? 0)} saldos para o registro 1050
          </p>
        </Cartao>
      </section>

      {(resumo.por_motivo ?? []).length > 0 && (
        <section className="rounded-cartao border border-atencao/25 border-l-[3px] border-l-atencao bg-atencao-fundo px-5 py-4.5">
          <p className="m-0 text-sm font-extrabold text-atencao">O que trava as competências</p>
          <p className="m-0 mt-1.5 max-w-[760px] text-[13px] leading-relaxed text-texto">
            Apurar e poder entregar são coisas diferentes: o valor está calculado, mas só a competência
            limpa segue para o arquivo digital.
          </p>
          <ul className="m-0 mt-3 flex list-none flex-col gap-2 p-0">
            {(resumo.por_motivo ?? []).map((m) => (
              <li key={m.codigo} className="flex flex-wrap gap-3 text-[13px] leading-relaxed">
                <span className="min-w-[70px] text-right font-mono text-atencao">{numero(m.competencias)}</span>
                <span className="font-bold text-texto">{m.rotulo}</span>
                <span className="text-texto-suave">{m.o_que_fazer}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <PorCompetencia resumo={resumo} acao={par("saldos", "Baixar os saldos (1050)")} />

      <Competencias execucaoId={execucao.id} total={total} rodape={par("apuracao", "Baixar a apuração", true)} />

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
          <p className="m-0 text-sm font-extrabold text-texto">Próxima etapa: gerar o arquivo digital</p>
          <p className="m-0 mt-1 text-xs leading-relaxed text-texto-suave">
            Os registros 0000 a 1200 no leiaute da CAT 42, um arquivo por estabelecimento de SP e por
            mês. As competências prontas vão para o envio; as outras de SP saem como prévia.
          </p>
        </div>
        <BotaoLink para={ROTAS.arquivoDigital(execucao.projeto_id)} variante="secundario">
          Ir para o arquivo digital
        </BotaoLink>
      </section>
    </div>
  );
}

function PorCompetencia({ resumo, acao }: { resumo: ResumoDaApuracao; acao: ReactNode }) {
  const linhas = resumo.por_competencia ?? [];
  if (linhas.length === 0) return null;
  const maior = Math.max(1, ...linhas.map((m) => Number(m.ressarcimento)));
  return (
    <Cartao className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="m-0 flex-1 text-base font-extrabold text-texto">Mês a mês</h2>
        {acao}
      </div>
      <div className="flex max-h-[420px] flex-col gap-2 overflow-y-auto pr-1">
        {linhas.map((m) => (
          <div key={m.competencia} className="flex items-center gap-3">
            <code className="min-w-[58px] font-mono text-xs text-texto-suave">{mesAno(m.competencia)}</code>
            <div className="flex-1">
              <BarraFina fracao={Number(m.ressarcimento) / maior} classe="bg-sucesso" />
            </div>
            <span className="min-w-[116px] text-right font-mono text-xs text-texto">{valor(m.ressarcimento)}</span>
            <span
              className={cn(
                "min-w-[116px] text-right font-mono text-xs",
                zero(m.complemento) ? "text-texto-fraco" : "text-atencao",
              )}
            >
              {valor(m.complemento)}
            </span>
            <span
              className={cn(
                "min-w-[92px] text-right font-mono text-[11px]",
                m.aptas === m.competencias ? "text-sucesso" : "text-atencao",
              )}
            >
              {numero(m.aptas)}/{numero(m.competencias)} prontas
            </span>
          </div>
        ))}
      </div>
      <p className="m-0 text-[11px] text-texto-fraco">
        Ressarcimento e complemento, lado a lado e nunca somados. A última coluna é quantos
        estabelecimentos daquele mês estão prontos para o arquivo.
      </p>
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function Competencias({
  execucaoId,
  total,
  rodape,
}: {
  execucaoId: number;
  total: number;
  rodape: ReactNode;
}) {
  const [recorte, setRecorte] = useState<RecorteDeCompetencia>("todas");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<Pagina<Competencia> | null>(null);
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
      competenciasApuradas(execucaoId, { recorte, busca: buscaAplicada, pagina: paginaAtual, porPagina: POR_PAGINA }, sinal),
    ).then((r) => {
      if (vivo && r) setDados(r);
    });
    return () => {
      vivo = false;
    };
  }, [execucaoId, recorte, buscaAplicada, paginaAtual, executar]);

  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  const colunas = "grid-cols-[1.1fr_.6fr_1fr_1fr_.7fr_1.6fr]";

  return (
    <section className="overflow-hidden rounded-cartao border border-borda bg-superficie shadow-cat">
      <div className="flex flex-wrap items-center gap-3.5 border-b border-borda px-5.5 py-4.5">
        <div className="min-w-0 flex-1">
          <h2 className="m-0 text-lg font-extrabold text-texto">Competências</h2>
          <p className="m-0 mt-1 text-xs text-texto-fraco">
            {dados
              ? `Uma linha por estabelecimento e mês. ${numero(dados.total)} neste recorte · ${numero(total)} no total`
              : "Carregando…"}
          </p>
        </div>
        <Busca valor={busca} aoMudar={setBusca} placeholder="Buscar CNPJ ou competência…" className="max-w-[320px]" />
        <Segmentado<RecorteDeCompetencia>
          rotulo="Recorte das competências"
          valor={recorte}
          aoMudar={setRecorte}
          opcoes={[
            { chave: "todas", rotulo: "Todas" },
            { chave: "aptas", rotulo: "Prontas" },
            { chave: "bloqueadas", rotulo: "Travadas" },
          ]}
        />
      </div>

      {leitura.erro && (
        <div className="px-5.5 pt-4">
          <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />
        </div>
      )}

      <div className={cn("overflow-x-auto transition-opacity", leitura.carregando && "opacity-60")}>
        <div className="min-w-[1040px]">
          <div className={cn("grid gap-3 bg-tabela-cabecalho-fundo px-5.5 py-3", colunas)}>
            {["Estabelecimento", "Competência", "Ressarcimento", "Complemento", "Mercadorias", "Situação"].map((c, i) => (
              <span
                key={c}
                className={cn(
                  "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                  i >= 2 && i <= 4 && "text-right",
                )}
              >
                {c}
              </span>
            ))}
          </div>
          {dados?.linhas.map((c) => (
            <div
              key={`${c.cnpj}|${c.competencia}`}
              className={cn("grid items-center gap-3 border-t border-borda-sutil px-5.5 py-3", colunas)}
            >
              <span className="min-w-0">
                <span className="block font-mono text-xs text-texto">{cnpjFormatado(c.cnpj)}</span>
                <span className={cn("mt-0.5 block text-[11px]", c.uf && c.uf !== "SP" ? "text-atencao" : "text-texto-fraco")}>
                  {c.uf || "UF ?"}
                </span>
              </span>
              <code className="font-mono text-[13px] text-texto">{mesAno(c.competencia)}</code>
              <span className={cn("text-right font-mono text-[13px]", zero(c.ressarcimento) ? "text-texto-fraco" : "text-sucesso")}>
                {valor(c.ressarcimento)}
              </span>
              <span className={cn("text-right font-mono text-[13px]", zero(c.complemento) ? "text-texto-fraco" : "text-atencao")}>
                {valor(c.complemento)}
              </span>
              <span className="text-right font-mono text-[13px] text-texto-suave">{numero(c.itens)}</span>
              <span className="flex flex-wrap items-center gap-1.5">
                {c.apta ? (
                  <span className="rounded-full border border-sucesso/35 bg-sucesso-fundo px-2 py-0.5 text-[10px] font-bold text-sucesso">
                    pronta para o arquivo
                  </span>
                ) : (
                  c.motivos.map((m) => (
                    <span
                      key={m.codigo}
                      title={m.o_que_fazer}
                      className="rounded-full border border-atencao/35 bg-atencao-fundo px-2 py-0.5 text-[10px] font-bold text-atencao"
                    >
                      {m.rotulo}
                    </span>
                  ))
                )}
              </span>
            </div>
          ))}
          {dados && dados.linhas.length === 0 && (
            <p className="m-0 border-t border-borda-sutil px-5.5 py-10 text-center text-[13px] text-texto-fraco">
              Nenhuma competência neste recorte.
            </p>
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
          Passe o mouse sobre o que trava para ver o que fazer.
        </span>
        {rodape}
      </div>
    </section>
  );
}

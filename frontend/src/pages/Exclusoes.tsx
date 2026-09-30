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
} from "@/components/shared/Rodada";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { CabecalhoDePagina, Voltar } from "@/components/ui/Pagina";
import { IconeParar, IconeTentarDeNovo } from "@/constants/icons";
import { INTERVALO_POLL_MS } from "@/constants/polling";
import { ROTAS } from "@/constants/routes";
import { aceitaProcessamento } from "@/constants/status";
import { useAcao } from "@/hooks/useAcao";
import { cn } from "@/lib/cn";
import { comoErro } from "@/lib/errors";
import { dinheiro, numero } from "@/lib/format";
import { EM_CURSO, type Formato } from "@/services/conferencia";
import {
  baixarPlanilhaDasExclusoes,
  baixarPlanilhaDoIcms,
  cancelarExclusoes,
  detalharExclusoes,
  iniciarExclusoes,
  listarExclusoes,
  type CompetenciaDoIcms,
  type ExecucaoDasExclusoes,
  type LinhaDaCompetencia,
  type ResumoDasExclusoes,
  type ResumoDoIcms,
} from "@/services/exclusoes";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/**
 * Exclusões da base do PIS/COFINS. Duas teses, uma rodada.
 *
 * As **próprias contribuições fora da base**: a receita embute PIS e COFINS, e
 * a base de cada uma perde as duas — a leitura escolhida entre as três
 * possíveis, e vale só no débito.
 *
 * O **ICMS destacado fora da base**, o Tema 69: apurado item a item e corrigido
 * pela Selic. Cada tese tem seu bloco, seu total e sua planilha — somar as duas
 * num número só esconderia que são pedidos diferentes, com fundamentos
 * diferentes.
 *
 * **A tela é feita para ser conferida, não para impressionar.** O número que
 * volta aparece grande, mas ao lado dele vem a base, o quanto saiu dela e —
 * com o mesmo destaque — o que a conta recusou e por quê. Número de tese que
 * não diz o que deixou de fora é número que ninguém assina.
 *
 * **E o Tema 69 vem sempre com a data da correção.** Selic acumulada sem o mês
 * até onde acumulou é número que ninguém consegue reconferir depois.
 */

const ESPERA_PARA_CANCELAR_MS = 400;

/** "2026-09-24" -> "24/09/2026". Vazio quando não há data. */
const data = (iso: string | undefined) =>
  iso?.length === 10 ? iso.split("-").reverse().join("/") : "";

/** "2026-09" -> "09/2026". O mês até onde a Selic acumulou. */
const mesDe = (aaaamm: string | undefined) =>
  aaaamm?.length === 7 ? `${aaaamm.slice(5)}/${aaaamm.slice(0, 4)}` : "";

export default function Exclusoes() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDasExclusoes | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDasExclusoes | null>(null);
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
      const e = await detalharExclusoes(execucaoId);
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
    listarExclusoes(projetoId)
      .then((lista) => {
        const ultima = lista[0] ?? null;
        setAtual(ultima);
        setResultado(lista.find((e) => e.situacao === "concluida") ?? null);
        if (ultima && EM_CURSO.includes(ultima.situacao)) seguir(ultima.id);
      })
      .catch((x) => setErro(comoErro(x)));
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
      const nova = await iniciarExclusoes(projetoId);
      setAtual(nova);
      seguir(nova.id);
    } catch (x) {
      setErro(comoErro(x));
    } finally {
      setOcupado(false);
    }
  }

  async function interromper() {
    if (!atual) return;
    try {
      const e = await cancelarExclusoes(atual.id);
      setAtual(e);
      if (!EM_CURSO.includes(e.situacao)) parar();
    } catch (x) {
      setErro(comoErro(x));
    }
  }

  const anda = !projeto || aceitaProcessamento(projeto.projeto.status);
  const resumo = resultado?.resumo ?? null;
  const p = projeto?.projeto;

  let acao: ReactNode = null;
  if (rodando && atual) {
    acao =
      atual.situacao === "cancelando" ? (
        <Botao variante="secundario" carregando>
          Cancelando…
        </Botao>
      ) : podeCancelar ? (
        <Botao variante="secundario" icone={IconeParar} onClick={interromper}>
          Cancelar
        </Botao>
      ) : (
        <Botao carregando>Apurando…</Botao>
      );
  } else {
    acao = (
      <Botao
        icone={IconeTentarDeNovo}
        onClick={comecar}
        carregando={ocupado}
        disabled={!anda}
        className="shadow-acao"
      >
        {resultado ? "Apurar de novo" : "Apurar as exclusões"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="PIS/COFINS · Exclusões"
        titulo="Exclusões da base"
        sub="A receita embute o PIS e a COFINS, e receita não é imposto. Excluindo as duas da base de cada uma, a contribuição é recalculada grupo a grupo — registro, CST e CFOP dentro da competência — e a diferença é o que volta. Vale só no débito: o crédito das aquisições fica como está."
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
        <Aviso titulo="A apuração das exclusões falhou">
          <span className="block">{atual.erro}</span>
          <code className="mt-2 inline-block rounded-lg border border-dashed border-erro/40 bg-erro/5 px-2.5 py-1.5 font-mono text-xs">
            execução #{atual.id}
          </code>
        </Aviso>
      )}

      {atual?.situacao === "cancelada" && (
        <Faixa titulo="A última rodada foi cancelada">
          Parou a pedido. O que ficou pela metade não vale.
          {resultado ? " Abaixo, a última apuração que concluiu." : " Rode de novo quando quiser."}
        </Faixa>
      )}

      {rodando && atual && <EmCurso e={atual} />}

      {!rodando && !resultado && atual === null && (
        <Faixa titulo="Esta tese ainda não foi apurada neste trabalho">
          Clique em <strong>Apurar as exclusões</strong>. Se a Gestão Fiscal já rodou, a conta sai
          em segundos: ela parte do que a Gestão leu. Se não rodou, os SPED são lidos agora — e o
          que for lido fica guardado para as próximas teses.
        </Faixa>
      )}

      {resultado && resumo && <Concluido execucao={resultado} resumo={resumo} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function EmCurso({ e }: { e: ExecucaoDasExclusoes }) {
  const lidos = e.resumo?.andamento?.arquivos ?? e.arquivos_lidos ?? 0;
  const total = e.arquivos_totais ?? 0;
  // são duas leituras do mesmo lote, e uma barra que volta a zero no meio
  // parece rodada travada. Dizer qual delas anda custa uma linha
  const noIcms = e.resumo?.andamento?.fase === "icms";
  return (
    <Cartao>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <Rotulo>{e.passo || "Apurando"}</Rotulo>
        <span className="font-mono text-[13px] text-texto-suave">
          {numero(lidos)} de {numero(total)} arquivos
          <span className="ml-2 text-[11px] font-sans text-texto-fraco">
            {noIcms ? "· tese 2 de 2: o ICMS" : "· tese 1 de 2: as contribuições"}
          </span>
        </span>
      </div>
      <BarraFina fracao={e.fracao ?? 0} classe="bg-marca-laranja" />
      {e.resumo?.log && <ListaDoLog log={e.resumo.log} emCurso />}
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function Concluido({
  execucao,
  resumo,
}: {
  execucao: ExecucaoDasExclusoes;
  resumo: ResumoDasExclusoes;
}) {
  const download = useAcao();
  const [baixando, setBaixando] = useState<Formato | null>(null);
  const linhas = resumo.por_competencia ?? [];
  const fora = Object.entries(resumo.fora ?? {});

  async function baixar(formato: Formato) {
    setBaixando(formato);
    await download.executar((sinal) => baixarPlanilhaDasExclusoes(execucao.id, formato, sinal));
    setBaixando(null);
  }

  return (
    <>
      {/* o número da tese, e o que ele custou de base */}
      <section className="flex flex-wrap items-stretch gap-4 rounded-cartao border border-borda bg-superficie p-6 shadow-cat">
        <div className="min-w-[280px] flex-1">
          <Rotulo>Crédito no prazo, excluindo as contribuições da base</Rotulo>
          <p className="m-0 mt-1 font-mono text-[34px] font-extrabold leading-none text-sucesso">
            {dinheiro(resumo.diferenca ?? "0")}
          </p>
          <p className="m-0 mt-2 text-[13px] text-texto-suave">
            {dinheiro(resumo.diferenca_pis ?? "0")} de PIS ·{" "}
            {dinheiro(resumo.diferenca_cofins ?? "0")} de COFINS
          </p>
          {(resumo.competencias_prescritas ?? 0) > 0 && (
            <p className="m-0 mt-2 text-[12px] leading-relaxed text-erro">
              <strong className="font-mono">{dinheiro(resumo.prescrito ?? "0")}</strong> em{" "}
              {numero(resumo.competencias_prescritas ?? 0)}{" "}
              {(resumo.competencias_prescritas ?? 0) === 1 ? "competência" : "competências"} fora
              dos cinco anos{data(resumo.data_de_referencia) ? `, contados de ${data(resumo.data_de_referencia)}` : ""} —
              não entram no crédito.
            </p>
          )}
        </div>

        <dl className="m-0 grid min-w-[300px] flex-1 grid-cols-2 gap-x-6 gap-y-3 self-center">
          <Numero rotulo="Base escriturada" valor={dinheiro(resumo.base ?? "0")} />
          <Numero rotulo="Excluído da base" valor={dinheiro(resumo.excluido ?? "0")} />
          <Numero rotulo="Grupos" valor={numero(resumo.grupos ?? 0)} />
          <Numero rotulo="Competências" valor={numero(resumo.competencias?.length ?? 0)} />
        </dl>

        <div className="flex min-w-[240px] flex-col items-end justify-between gap-3">
          <BaixarPlanilha
            aoBaixar={baixar}
            desabilitado={(resumo.grupos ?? 0) === 0}
            rotulo="Baixar as exclusões"
            destaque
            baixando={baixando}
            aoCancelar={download.cancelar}
          />
          <p className="m-0 text-right text-[11px] leading-relaxed text-texto-fraco">
            Uma linha por grupo: somar a coluna da diferença dá exatamente este total.
            {resumo.segundos ? ` Apurado em ${duracao(resumo.segundos)}` : ""}
            {resumo.fonte === "agregados"
              ? ", a partir do que a Gestão já tinha lido."
              : resumo.fonte === "sped"
                ? `, lendo ${numero(resumo.arquivos ?? 0)} SPED.`
                : "."}
          </p>
        </div>
      </section>

      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} />
      )}

      {/* o que ficou de fora vem antes da tabela de propósito: é o que decide
          se o número acima pode ser assinado */}
      {(fora.length > 0 || (resumo.avisos?.length ?? 0) > 0) && (
        <section className="rounded-cartao border border-borda bg-superficie-vidro p-6">
          <Rotulo>O que a conta não incluiu</Rotulo>
          {fora.length > 0 && (
            <ul className="m-0 mt-3 flex list-none flex-col gap-1.5 p-0">
              {fora
                .sort((a, b) => b[1] - a[1])
                .map(([motivo, quantas]) => (
                  <li key={motivo} className="flex items-baseline gap-3 text-[13px]">
                    <span className="min-w-[70px] text-right font-mono font-bold text-texto">
                      {numero(quantas)}
                    </span>
                    <span className="text-texto-suave">{motivo}</span>
                  </li>
                ))}
            </ul>
          )}
          {(resumo.avisos?.length ?? 0) > 0 && (
            <ul className="m-0 mt-3 flex list-none flex-col gap-1.5 p-0">
              {resumo.avisos?.map((aviso, i) => (
                <li key={i} className="text-[13px] leading-relaxed text-atencao">
                  {aviso}
                </li>
              ))}
            </ul>
          )}
          <p className="m-0 mt-3 max-w-[90ch] text-[12px] leading-relaxed text-texto-fraco">
            Alíquota em reais fica de fora porque a contribuição vem da quantidade, não da receita.
            Grupo cuja base é menor que a contribuição que ele mesmo gerou também fica: recalcular
            ali devolveria base zero e "recuperaria" o grupo inteiro.
          </p>
        </section>
      )}

      <PorCompetencia linhas={linhas} />

      <Tema69 execucao={execucao} icms={resumo.icms} />
    </>
  );
}

/* ------------------------------------------------------------------ */

/**
 * O ICMS fora da base — o Tema 69.
 *
 * Bloco próprio, e não mais uma linha na tabela da outra tese: são pedidos
 * diferentes, com fundamentos diferentes, e quem assina precisa ver os dois
 * separados. O que aqui aparece e na outra não é a **correção**: o principal e
 * a Selic vêm em números distintos, porque a Selic é a parte que muda de valor
 * a cada mês que o pedido demora.
 */
function Tema69({
  execucao,
  icms,
}: {
  execucao: ExecucaoDasExclusoes;
  icms: ResumoDoIcms | undefined;
}) {
  const download = useAcao();
  const [baixando, setBaixando] = useState<Formato | null>(null);

  async function baixar(formato: Formato) {
    setBaixando(formato);
    await download.executar((sinal) => baixarPlanilhaDoIcms(execucao.id, formato, sinal));
    setBaixando(null);
  }

  // sem `linhas` a tese não rodou — falta EFD-Contribuições, ou a série da
  // Selic não alcança o mês. O porquê já está na lista de avisos acima
  if (!icms || !(icms.linhas ?? 0)) {
    return (
      <Faixa titulo="O ICMS fora da base (Tema 69) não foi apurado nesta rodada">
        Ele se calcula no item da nota fiscal, direto da EFD-Contribuições, e precisa da série da
        Selic cobrindo o mês da restituição. O motivo está em{" "}
        <strong>o que a conta não incluiu</strong>, acima.
      </Faixa>
    );
  }

  const prescritas = icms.competencias_prescritas ?? 0;
  const ate = mesDe(icms.ate);

  return (
    <>
      <section className="flex flex-wrap items-stretch gap-4 rounded-cartao border border-borda bg-superficie p-6 shadow-cat">
        <div className="min-w-[280px] flex-1">
          <Rotulo>Crédito no prazo, excluindo o ICMS da base · Tema 69</Rotulo>
          <p className="m-0 mt-1 font-mono text-[34px] font-extrabold leading-none text-sucesso">
            {dinheiro(icms.total_atualizado ?? "0")}
          </p>
          <p className="m-0 mt-2 text-[13px] text-texto-suave">
            {dinheiro(icms.diferenca_pis ?? "0")} de PIS ·{" "}
            {dinheiro(icms.diferenca_cofins ?? "0")} de COFINS · {dinheiro(icms.selic ?? "0")} de
            Selic
          </p>
          {ate && (
            <p className="m-0 mt-2 text-[12px] leading-relaxed text-texto-fraco">
              Corrigido pela Selic até <strong className="font-mono">{ate}</strong>. A acumulada
              cresce a cada mês: rodar de novo depois dá um total maior.
            </p>
          )}
          {prescritas > 0 && (
            <p className="m-0 mt-2 text-[12px] leading-relaxed text-erro">
              <strong className="font-mono">{dinheiro(icms.prescrito ?? "0")}</strong> em{" "}
              {numero(prescritas)} {prescritas === 1 ? "competência" : "competências"} fora dos
              cinco anos
              {data(icms.data_de_referencia)
                ? `, contados de ${data(icms.data_de_referencia)}`
                : ""}{" "}
              — não entram no crédito.
            </p>
          )}
        </div>

        <dl className="m-0 grid min-w-[300px] flex-1 grid-cols-2 gap-x-6 gap-y-3 self-center">
          <Numero rotulo="Base escriturada" valor={dinheiro(icms.base ?? "0")} />
          <Numero rotulo="ICMS excluído" valor={dinheiro(icms.icms_excluido ?? "0")} />
          <Numero rotulo="Itens de nota" valor={numero(icms.linhas ?? 0)} />
          <Numero rotulo="Competências" valor={numero(icms.competencias?.length ?? 0)} />
        </dl>

        <div className="flex min-w-[240px] flex-col items-end justify-between gap-3">
          <BaixarPlanilha
            aoBaixar={baixar}
            desabilitado={(icms.linhas ?? 0) === 0}
            rotulo="Baixar o Tema 69"
            baixando={baixando}
            aoCancelar={download.cancelar}
          />
          <p className="m-0 text-right text-[11px] leading-relaxed text-texto-fraco">
            Uma linha por item de nota fiscal, nas quarenta colunas do relatório 903 — na ordem em
            que o escritório anterior exporta, para conferir lado a lado.
            {icms.segundos ? ` Apurado em ${duracao(icms.segundos)}.` : ""}
          </p>
        </div>
      </section>

      {download.erro && <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} />}

      <PorCompetenciaDoIcms linhas={icms.por_competencia ?? []} />
    </>
  );
}

const COLUNAS_DO_ICMS = "grid-cols-[110px_.7fr_.7fr_1.1fr_1.1fr_1fr_1fr_1.1fr]";

function PorCompetenciaDoIcms({ linhas }: { linhas: CompetenciaDoIcms[] }) {
  if (linhas.length === 0) return null;

  return (
    <section className="overflow-hidden rounded-raio-g border border-borda bg-superficie">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-borda px-5.5 py-3.5">
        <Rotulo>Tema 69, competência a competência</Rotulo>
        <span className="text-[11px] text-texto-fraco">
          {numero(linhas.length)} {linhas.length === 1 ? "competência" : "competências"} · a Selic
          de cada uma é a acumulada do mês dela até o da restituição
        </span>
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[980px]">
          <div className={cn("grid gap-3 bg-tabela-cabecalho-fundo px-5.5 py-3", COLUNAS_DO_ICMS)}>
            {[
              "Competência",
              "Itens",
              "Selic",
              "Base",
              "ICMS excluído",
              "PIS que volta",
              "COFINS que volta",
              "Total corrigido",
            ].map((c, i) => (
              <span
                key={c}
                className={cn(
                  "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                  i >= 1 && "text-right",
                )}
              >
                {c}
              </span>
            ))}
          </div>

          {linhas.map((l) => (
            <div
              key={l.competencia}
              title={l.prescrita ? "Fora dos cinco anos: não entra no crédito." : undefined}
              className={cn(
                "grid items-center gap-3 border-t border-borda-sutil px-5.5 py-2.5",
                COLUNAS_DO_ICMS,
                l.prescrita && "bg-erro/5 text-erro",
              )}
            >
              <span
                className={cn(
                  "font-mono text-[13px]",
                  l.prescrita ? "font-bold text-erro" : "text-texto",
                )}
              >
                {mesAno(l.competencia)}
              </span>
              <span className="text-right font-mono text-[12px] tabular-nums text-texto-fraco">
                {numero(l.linhas)}
              </span>
              <span className="text-right font-mono text-[12px] tabular-nums text-texto-fraco">
                {l.selic_acumulada}%
              </span>
              <span
                className={cn(
                  "text-right text-[13px]",
                  l.prescrita ? "text-erro" : "text-texto-suave",
                )}
              >
                {dinheiro(l.base)}
              </span>
              <span
                className={cn(
                  "text-right text-[13px]",
                  l.prescrita ? "text-erro" : "text-texto-suave",
                )}
              >
                {dinheiro(l.icms_excluido)}
              </span>
              <span className="text-right text-[13px] text-texto-suave">
                {dinheiro(l.diferenca_pis)}
              </span>
              <span className="text-right text-[13px] text-texto-suave">
                {dinheiro(l.diferenca_cofins)}
              </span>
              <span
                className={cn(
                  "text-right font-mono text-[13px] font-bold",
                  l.prescrita ? "text-erro line-through decoration-erro/50" : "text-sucesso",
                )}
              >
                {dinheiro(l.total_atualizado)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */

function Numero({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div>
      <dt className="m-0 text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
        {rotulo}
      </dt>
      <dd className="m-0 mt-0.5 font-mono text-[15px] font-bold text-texto">{valor}</dd>
    </div>
  );
}

const COLUNAS = "grid-cols-[110px_.7fr_1.1fr_1fr_1fr_1fr_1.1fr]";

function PorCompetencia({ linhas }: { linhas: LinhaDaCompetencia[] }) {
  if (linhas.length === 0) return null;

  return (
    <section className="overflow-hidden rounded-raio-g border border-borda bg-superficie">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-borda px-5.5 py-3.5">
        <Rotulo>Competência a competência</Rotulo>
        <span className="text-[11px] text-texto-fraco">
          {numero(linhas.length)} {linhas.length === 1 ? "competência" : "competências"} · o total
          de cada uma é a soma dos grupos dela, já arredondados
        </span>
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[900px]">
          <div className={cn("grid gap-3 bg-tabela-cabecalho-fundo px-5.5 py-3", COLUNAS)}>
            {["Competência", "Grupos", "Base", "Excluído", "PIS que volta", "COFINS que volta", "Total que volta"].map(
              (c, i) => (
                <span
                  key={c}
                  className={cn(
                    "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                    i >= 1 && "text-right",
                  )}
                >
                  {c}
                </span>
              ),
            )}
          </div>

          {linhas.map((l) => (
            <div
              key={l.competencia}
              title={l.prescrita ? "Fora dos cinco anos: não entra no crédito." : undefined}
              className={cn(
                "grid items-center gap-3 border-t border-borda-sutil px-5.5 py-2.5",
                COLUNAS,
                l.prescrita && "bg-erro/5 text-erro",
              )}
            >
              <span
                className={cn(
                  "font-mono text-[13px]",
                  l.prescrita ? "font-bold text-erro" : "text-texto",
                )}
              >
                {mesAno(l.competencia)}
              </span>
              <span className="text-right font-mono text-[12px] tabular-nums text-texto-fraco">
                {numero(l.grupos)}
              </span>
              <span className={cn("text-right text-[13px]", l.prescrita ? "text-erro" : "text-texto-suave")}>{dinheiro(l.base)}</span>
              <span className={cn("text-right text-[13px]", l.prescrita ? "text-erro" : "text-texto-suave")}>{dinheiro(l.excluido)}</span>
              <span className="text-right text-[13px] text-texto-suave">
                {dinheiro(l.diferenca_pis)}
              </span>
              <span className="text-right text-[13px] text-texto-suave">
                {dinheiro(l.diferenca_cofins)}
              </span>
              <span
                className={cn(
                  "text-right font-mono text-[13px] font-bold",
                  l.prescrita ? "text-erro line-through decoration-erro/50" : "text-sucesso",
                )}
              >
                {dinheiro(l.diferenca)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

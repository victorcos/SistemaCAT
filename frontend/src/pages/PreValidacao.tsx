import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import { OcorrenciasDoArquivo } from "@/components/shared/OcorrenciasDoArquivo";
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
import { Botao, BotaoLink } from "@/components/ui/Botao";
import { Busca, Segmentado } from "@/components/ui/Filtros";
import { CabecalhoDePagina, Voltar } from "@/components/ui/Pagina";
import {
  IconeArquivoDigital,
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
import type { Pagina } from "@/services/apuracao";
import { ocorrenciasDoArquivo } from "@/services/arquivoDigital";
import { EM_CURSO, type Formato } from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import {
  VERSAO_DO_RESUMO_DA_PRE_VALIDACAO,
  arquivosDoCliente,
  baixarPlanilhaDaPreValidacao,
  cancelarPreValidacao,
  detalharPreValidacao,
  iniciarPreValidacao,
  listarPreValidacao,
  type ArquivoDoCliente,
  type ExecucaoDaPreValidacao,
  type PlanilhaDaPreValidacao,
  type RecorteDoCliente,
  type ResumoDaPreValidacao,
} from "@/services/preValidacao";
import type { ErroApi } from "@/types/erro";

/**
 * Pré-validar os arquivos digitais que o cliente já transmitiu.
 *
 * A mesma pré-validação da etapa 7 — leiaute, tabela de natureza e a Ficha 3
 * recomposta a partir do próprio arquivo —, sobre o TXT que outra ferramenta
 * gerou. Serve à auditoria: dizer ao cliente o que a SEFAZ acharia.
 */

const ESPERA_PARA_CANCELAR_MS = 400;
const POR_PAGINA = 50;
const ESPERA_DA_BUSCA_MS = 350;

const cnpjFormatado = (c: string) =>
  c.length === 14 ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}` : c;

const tamanho = (bytes: number | undefined) => {
  const b = bytes ?? 0;
  if (b >= 1 << 30) return `${(b / (1 << 30)).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} GB`;
  if (b >= 1 << 20) return `${(b / (1 << 20)).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`;
  return `${Math.ceil(b / 1024).toLocaleString("pt-BR")} KB`;
};

export default function PreValidacao() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDaPreValidacao | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDaPreValidacao | null>(null);
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
      const e = await detalharPreValidacao(execucaoId);
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
    listarPreValidacao(projetoId)
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
      const nova = await iniciarPreValidacao(projetoId);
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
      const e = await cancelarPreValidacao(atual.id);
      setAtual(e);
      if (!EM_CURSO.includes(e.situacao)) parar();
    } catch (x) {
      setErro(comoErro(x));
    }
  }

  const anda = !projeto || aceitaProcessamento(projeto.projeto.status);
  const resumo = resultado?.resumo ?? null;
  const anterior = resultado !== null && (resumo?.versao ?? 0) < VERSAO_DO_RESUMO_DA_PRE_VALIDACAO;
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
        <Botao carregando>Pré-validando…</Botao>
      );
  } else if (atual) {
    acao = (
      <Botao icone={IconeTentarDeNovo} onClick={comecar} carregando={ocupado} disabled={!anda} className="shadow-acao">
        {resultado && !anterior ? "Pré-validar de novo" : "Pré-validar os arquivos"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="Auditoria · Arquivo digital do cliente"
        titulo="Pré-validar o que o cliente transmitiu"
        sub="Os arquivos da CAT 42 que o cliente já gerou, soltos no lote ou dentro de zip: o leiaute campo a campo, a tabela de natureza de operação e a Ficha 3 recomposta a partir do próprio arquivo, que tem de chegar ao 1050."
        acao={
          <div className="flex flex-col items-end gap-2.5">
            {acao}
            {resultado && !rodando && (
              <p className="m-0 text-right text-[11px] leading-normal text-texto-fraco">
                Pré-validado em {quando(resultado.terminada_em)}
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
        <Aviso titulo="A pré-validação falhou">
          <span className="block">{atual.erro}</span>
          <code className="mt-2 inline-block rounded-lg border border-dashed border-erro/40 bg-erro/5 px-2.5 py-1.5 font-mono text-xs">
            execução #{atual.id}
          </code>
        </Aviso>
      )}

      {atual?.situacao === "cancelada" && (
        <Faixa titulo="A última rodada foi cancelada">
          Parou a pedido, sem gravar nada.
          {resultado ? " Abaixo, a última pré-validação que concluiu." : " Rode de novo quando quiser."}
        </Faixa>
      )}

      {carregado && !atual && (
        <section className="flex flex-col items-center gap-3.5 rounded-cartao border border-dashed border-borda-forte px-7 py-10 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-[13px] border border-laranja-500/30 bg-laranja-500/14 text-laranja-700 escuro:text-laranja-300">
            <IconeArquivoDigital size={20} strokeWidth={1.8} aria-hidden />
          </div>
          <p className="m-0 text-[17px] font-extrabold text-texto">Nada pré-validado ainda</p>
          <p className="m-0 max-w-[600px] text-[13px] leading-relaxed text-texto-suave [text-wrap:pretty]">
            Importe no lote a pasta com os arquivos que o cliente transmitiu — o TXT solto ou os zips. Arquivo
            de outra empresa fica de fora, contado.
          </p>
          <div className="mt-1 flex flex-wrap justify-center gap-2">
            <Botao onClick={comecar} carregando={ocupado} disabled={!anda} className="shadow-acao">
              Pré-validar os arquivos
            </Botao>
            <BotaoLink para={ROTAS.arquivos(projetoId)} variante="secundario">
              Importar arquivos
            </BotaoLink>
          </div>
        </section>
      )}

      {rodando && atual && <EmCurso e={atual} />}

      {anterior && !rodando && (
        <Faixa titulo="Execução de versão anterior">
          Esta pré-validação não guarda o resumo que a tela pede. Rode de novo.
        </Faixa>
      )}

      {resultado && resumo && !anterior && <Concluido execucao={resultado} resumo={resumo} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function EmCurso({ e }: { e: ExecucaoDaPreValidacao }) {
  const a = e.resumo?.andamento;
  return (
    <Cartao className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <IconeCarregando size={17} className="animate-spin text-marca-laranja" aria-hidden />
        <p className="m-0 text-[15px] font-extrabold text-texto">
          {e.situacao === "cancelando" ? "Cancelando…" : "Lendo e recompondo…"}
        </p>
        <code className="ml-auto font-mono text-[13px] text-laranja-700 escuro:text-laranja-300">
          {a ? `${numero(a.arquivos)} arquivos · ${tamanho(a.bytes)}` : "—"}
        </code>
      </div>
      <BarraFina fracao={e.fracao} classe="bg-marca-laranja" />
      <p className="m-0 text-xs text-texto-fraco">
        {e.passo ?? "Na fila"} · pode fechar esta tela: a pré-validação continua no servidor.
      </p>
      {(e.resumo?.log ?? []).length > 0 && <ListaDoLog log={e.resumo?.log ?? []} emCurso />}
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function Concluido({ execucao, resumo }: { execucao: ExecucaoDaPreValidacao; resumo: ResumoDaPreValidacao }) {
  const download = useAcao();
  const [baixando, setBaixando] = useState<{ qual: PlanilhaDaPreValidacao; formato: Formato } | null>(null);

  async function baixar(qual: PlanilhaDaPreValidacao, formato: Formato) {
    setBaixando({ qual, formato });
    await download.executar((sinal) => baixarPlanilhaDaPreValidacao(execucao.id, qual, formato, sinal));
    setBaixando(null);
  }

  const par = (qual: PlanilhaDaPreValidacao, rotulo: string) => (
    <BaixarPlanilha
      aoBaixar={(formato) => baixar(qual, formato)}
      desabilitado={download.carregando || (resumo.arquivos ?? 0) === 0}
      baixando={baixando?.qual === qual ? baixando.formato : null}
      aoCancelar={download.podeCancelar ? download.cancelar : undefined}
      rotulo={rotulo}
    />
  );

  const arquivos = resumo.arquivos ?? 0;
  const comErro = resumo.com_erro ?? 0;
  const recompostos = resumo.itens_recompostos ?? 0;
  const fecham = resumo.itens_que_fecham ?? 0;

  return (
    <div className="flex flex-col gap-5">
      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} aoFechar={() => download.setErro(null)} />
      )}

      <section className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-4">
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Arquivos sem erro</Rotulo>
          <p className={cn("m-0 font-mono text-[32px] leading-none", comErro ? "text-atencao" : "text-sucesso")}>
            {numero(arquivos - comErro)}
            <span className="ml-2 text-sm text-texto-fraco">de {numero(arquivos)}</span>
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            {numero(resumo.estabelecimentos ?? 0)} estabelecimentos
            {resumo.competencia_inicial && resumo.competencia_final
              ? `, de ${mesAno(resumo.competencia_inicial)} a ${mesAno(resumo.competencia_final)}`
              : ""}
            . {numero(resumo.com_aviso ?? 0)} com aviso; {numero(resumo.linhas ?? 0)} linhas, {tamanho(resumo.bytes)}.
          </p>
        </Cartao>
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Ficha 3 recomposta</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-texto">
            {numero(fecham)}
            <span className="ml-2 text-sm text-texto-fraco">de {numero(recompostos)} itens fecham</span>
          </p>
          <div className="mt-1">
            <BarraFina fracao={recompostos ? fecham / recompostos : 0} classe={fecham === recompostos ? "bg-sucesso" : "bg-atencao"} />
          </div>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Do 1050 inicial e das linhas do arquivo, o saldo tem de chegar ao 1050 final: quantidade exata, valor
            até 5 centavos.
          </p>
        </Cartao>
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Ficaram de fora</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-texto">
            {numero((resumo.repetidos ?? 0) + (resumo.de_outra_empresa ?? 0))}
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            {numero(resumo.repetidos ?? 0)} repetidos (mesmo estabelecimento e mês já lido) e{" "}
            {numero(resumo.de_outra_empresa ?? 0)} de outra empresa, em {numero(resumo.fontes ?? 0)} fontes do lote.
          </p>
        </Cartao>
      </section>

      {(resumo.por_regra ?? []).length > 0 && (
        <Cartao className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="m-0 flex-1 text-base font-extrabold text-texto">O que a pré-validação achou</h2>
            {par("ocorrencias", "Baixar as ocorrências")}
          </div>
          <div className="flex flex-col">
            {(resumo.por_regra ?? []).map((r) => (
              <div key={r.codigo} className="flex flex-wrap items-center gap-3 border-t border-borda-sutil py-2.5">
                <span
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-[10px] font-bold",
                    r.severidade === "erro"
                      ? "border-erro/35 bg-erro/8 text-erro"
                      : "border-atencao/35 bg-atencao-fundo text-atencao",
                  )}
                >
                  {r.severidade}
                </span>
                <span className="min-w-[240px] flex-1 text-[13px] font-bold text-texto">{r.rotulo}</span>
                <span className="text-xs text-texto-suave">{r.o_que_fazer}</span>
                <code className="min-w-[160px] text-right font-mono text-xs text-texto-fraco">
                  {numero(r.ocorrencias)} em {numero(r.arquivos)} {r.arquivos === 1 ? "arquivo" : "arquivos"}
                </code>
              </div>
            ))}
          </div>
        </Cartao>
      )}

      <Arquivos execucaoId={execucao.id} total={arquivos} rodape={par("arquivos", "Baixar o índice dos arquivos")} />

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
    </div>
  );
}

/* ------------------------------------------------------------------ */

function Arquivos({ execucaoId, total, rodape }: { execucaoId: number; total: number; rodape: ReactNode }) {
  const [recorte, setRecorte] = useState<RecorteDoCliente>("todos");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<Pagina<ArquivoDoCliente> | null>(null);
  const [aberto, setAberto] = useState<string | null>(null);
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
      arquivosDoCliente(execucaoId, { recorte, busca: buscaAplicada, pagina: paginaAtual, porPagina: POR_PAGINA }, sinal),
    ).then((r) => {
      if (vivo && r) setDados(r);
    });
    return () => {
      vivo = false;
    };
  }, [execucaoId, recorte, buscaAplicada, paginaAtual, executar]);

  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  const colunas = "grid-cols-[28px_1.6fr_.6fr_.7fr_.9fr_.9fr_1fr]";

  return (
    <section className="overflow-hidden rounded-cartao border border-borda bg-superficie shadow-cat">
      <div className="flex flex-wrap items-center gap-3.5 border-b border-borda px-5.5 py-4.5">
        <div className="min-w-0 flex-1">
          <h2 className="m-0 text-lg font-extrabold text-texto">Arquivos do cliente</h2>
          <p className="m-0 mt-1 text-xs text-texto-fraco">
            {dados ? `${numero(dados.total)} neste recorte · ${numero(total)} lidos` : "Carregando…"}
          </p>
        </div>
        <Busca valor={busca} aoMudar={setBusca} placeholder="Buscar CNPJ, competência ou arquivo…" className="max-w-[320px]" />
        <Segmentado<RecorteDoCliente>
          rotulo="Recorte dos arquivos"
          valor={recorte}
          aoMudar={setRecorte}
          opcoes={[
            { chave: "todos", rotulo: "Todos" },
            { chave: "com_erro", rotulo: "Com erro" },
            { chave: "com_aviso", rotulo: "Com aviso" },
            { chave: "sem_ocorrencia", rotulo: "Limpos" },
          ]}
        />
      </div>

      {leitura.erro && (
        <div className="px-5.5 pt-4">
          <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />
        </div>
      )}

      <div className={cn("overflow-x-auto transition-opacity", leitura.carregando && "opacity-60")}>
        <div className="min-w-[1080px]">
          <div className={cn("grid gap-3 bg-tabela-cabecalho-fundo px-5.5 py-3", colunas)}>
            {["", "Arquivo", "Competência", "Registros", "Pré-validação", "Ficha 3", "Situação"].map((c, i) => (
              <span
                key={`${c}-${i}`}
                className={cn(
                  "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                  i >= 3 && i <= 5 && "text-right",
                )}
              >
                {c}
              </span>
            ))}
          </div>
          {dados?.linhas.map((a) => {
            const expandido = aberto === a.nome;
            return (
              <Fragment key={`${a.origem}|${a.nome}`}>
                <button
                  type="button"
                  onClick={() => setAberto(expandido ? null : a.nome)}
                  aria-expanded={expandido}
                  className={cn(
                    "grid w-full items-center gap-3 border-t border-borda-sutil px-5.5 py-3 text-left transition-colors hover:bg-superficie-vidro",
                    colunas,
                  )}
                >
                  <IconeExpandir
                    size={14}
                    className={cn("text-texto-fraco transition-transform", expandido && "rotate-90")}
                    aria-hidden
                  />
                  <span className="min-w-0">
                    <span className="block font-mono text-xs text-texto">{cnpjFormatado(a.cnpj)}</span>
                    <span className="mt-0.5 block truncate font-mono text-[11px] text-texto-fraco" title={a.origem}>
                      {a.nome}
                    </span>
                  </span>
                  <code className="font-mono text-[13px] text-texto">{mesAno(a.competencia)}</code>
                  <span className="text-right font-mono text-xs text-texto-suave">
                    {numero(a.eletronicos + a.nao_eletronicos)}
                    <span className="block text-[11px] text-texto-fraco">{tamanho(a.bytes)}</span>
                  </span>
                  <span className="text-right font-mono text-xs">
                    <span className={a.erros ? "text-erro" : "text-texto-suave"}>{numero(a.erros)} erros</span>
                    <span className="block text-[11px] text-texto-fraco">{numero(a.avisos)} avisos</span>
                  </span>
                  <span className="text-right font-mono text-xs text-texto-suave">
                    {numero(a.itens_que_fecham)}/{numero(a.itens_recompostos)}
                    <span className="block text-[11px] text-texto-fraco">itens fecham</span>
                  </span>
                  <span className="flex flex-wrap items-center gap-1.5">
                    {a.repetido ? (
                      <span className="rounded-full border border-borda-forte px-2 py-0.5 text-[10px] font-bold text-texto-fraco">
                        repetido, não lido
                      </span>
                    ) : a.erros ? (
                      <span className="rounded-full border border-erro/35 bg-erro/8 px-2 py-0.5 text-[10px] font-bold text-erro">
                        a SEFAZ recusaria
                      </span>
                    ) : (
                      <span className="rounded-full border border-sucesso/35 bg-sucesso-fundo px-2 py-0.5 text-[10px] font-bold text-sucesso">
                        {a.avisos ? "passa, com aviso" : "passa"}
                      </span>
                    )}
                  </span>
                </button>
                {expandido && (
                  <OcorrenciasDoArquivo
                    chave={`${execucaoId}|${a.nome}`}
                    carregar={(sinal) => ocorrenciasDoArquivo(execucaoId, a.nome, 1, sinal, "pre-validacao")}
                    cabecalho={
                      <div className="flex flex-wrap gap-x-6 gap-y-1.5 font-mono text-[11px] text-texto-suave">
                        <span>0150 · {numero(a.participantes)}</span>
                        <span>0200 · {numero(a.itens)}</span>
                        <span>1050 · {numero(a.saldos)}</span>
                        <span>1100 · {numero(a.eletronicos)}</span>
                        <span>1200 · {numero(a.nao_eletronicos)}</span>
                        <span className="truncate" title={a.origem}>
                          de {a.origem}
                        </span>
                      </div>
                    }
                  />
                )}
              </Fragment>
            );
          })}
          {dados && dados.linhas.length === 0 && (
            <p className="m-0 border-t border-borda-sutil px-5.5 py-10 text-center text-[13px] text-texto-fraco">
              Nenhum arquivo neste recorte.
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
          Abra um arquivo para ver o que a pré-validação achou nele.
        </span>
        {rodape}
      </div>
    </section>
  );
}

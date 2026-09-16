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
  valor,
  zero,
} from "@/components/shared/Rodada";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Aviso } from "@/components/ui/Aviso";
import { Botao, BotaoLink } from "@/components/ui/Botao";
import { Busca, Segmentado } from "@/components/ui/Filtros";
import { CabecalhoDePagina, Voltar } from "@/components/ui/Pagina";
import {
  IconeArquivoDigital,
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
import type { Pagina } from "@/services/apuracao";
import {
  VERSAO_DO_RESUMO_DO_ARQUIVO_DIGITAL,
  arquivosGerados,
  baixarPacote,
  baixarPlanilhaDoArquivoDigital,
  cancelarArquivoDigital,
  detalharArquivoDigital,
  iniciarArquivoDigital,
  listarArquivoDigital,
  ocorrenciasDoArquivo,
  type ArquivoGerado,
  type ExecucaoDoArquivoDigital,
  type PacoteDoArquivoDigital,
  type PlanilhaDoArquivoDigital,
  type RecorteDeArquivo,
  type ResumoDoArquivoDigital,
} from "@/services/arquivoDigital";
import { EM_CURSO, type Formato } from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/**
 * Etapa 7 — gerar o arquivo digital.
 *
 * Um arquivo por estabelecimento de SP e por mês. Duas regras mandam na tela:
 * **envio e prévia nunca se misturam** (zips separados, PREVIA no nome), e
 * **todo arquivo diz por que não foi para o envio** — o que a apuração deixou
 * pendente, o que não se escreve, e o que a pré-validação achou.
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

const VENDA: Record<string, string> = {
  enquadramento_1: "enquadramento 1 (ressarcimento e complemento)",
  demais_saidas: "demais saídas (0), como a BOA",
};

export default function ArquivoDigital() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDoArquivoDigital | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDoArquivoDigital | null>(null);
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
      const e = await detalharArquivoDigital(execucaoId);
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
    listarArquivoDigital(projetoId)
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
      const nova = await iniciarArquivoDigital(projetoId);
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
      const e = await cancelarArquivoDigital(atual.id);
      setAtual(e);
      if (!EM_CURSO.includes(e.situacao)) parar();
    } catch (x) {
      setErro(comoErro(x));
    }
  }

  const anda = !projeto || aceitaProcessamento(projeto.projeto.status);
  const resumo = resultado?.resumo ?? null;
  const anterior = resultado !== null && (resumo?.versao ?? 0) < VERSAO_DO_RESUMO_DO_ARQUIVO_DIGITAL;
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
        <Botao carregando>Gerando…</Botao>
      );
  } else if (atual) {
    acao = (
      <Botao icone={IconeTentarDeNovo} onClick={comecar} carregando={ocupado} disabled={!anda} className="shadow-acao">
        {resultado && !anterior ? "Gerar de novo" : "Gerar os arquivos"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="Etapa 7 · Arquivo digital"
        titulo="Gerar o arquivo digital"
        sub="Um arquivo por estabelecimento de SP e por mês, no leiaute da CAT 42. Cada um é lido de volta e pré-validado: a Ficha 3 é recomposta a partir do próprio arquivo e tem de chegar ao saldo do 1050."
        acao={
          <div className="flex flex-col items-end gap-2.5">
            {acao}
            {resultado && !rodando && (
              <p className="m-0 text-right text-[11px] leading-normal text-texto-fraco">
                Gerado em {quando(resultado.terminada_em)}
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
            <span className="text-xs text-texto-fraco">
              · venda a consumidor final no {VENDA[p.venda_a_consumidor] ?? p.venda_a_consumidor}
            </span>
          </div>
        )}
      </CabecalhoDePagina>

      <TrabalhoParado status={p?.status} projetoId={projetoId} />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}

      {atual?.situacao === "falhou" && (
        <Aviso titulo="A geração do arquivo digital falhou">
          <span className="block">{atual.erro}</span>
          <code className="mt-2 inline-block rounded-lg border border-dashed border-erro/40 bg-erro/5 px-2.5 py-1.5 font-mono text-xs">
            execução #{atual.id}
          </code>
        </Aviso>
      )}

      {atual?.situacao === "cancelada" && (
        <Faixa titulo="A última rodada foi cancelada">
          Parou a pedido, sem deixar arquivo pela metade.
          {resultado ? " Abaixo, a última geração que concluiu." : " Rode de novo quando quiser."}
        </Faixa>
      )}

      {carregado && !atual && (
        <section className="flex flex-col items-center gap-3.5 rounded-cartao border border-dashed border-borda-forte px-7 py-10 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-[13px] border border-laranja-500/30 bg-laranja-500/14 text-laranja-700 escuro:text-laranja-300">
            <IconeArquivoDigital size={20} strokeWidth={1.8} aria-hidden />
          </div>
          <p className="m-0 text-[17px] font-extrabold text-texto">O arquivo digital ainda não foi gerado</p>
          <p className="m-0 max-w-[600px] text-[13px] leading-relaxed text-texto-suave [text-wrap:pretty]">
            Precisa do período apurado. Só a competência pronta e sem erro na pré-validação vai para o
            envio; as outras de São Paulo saem como prévia, para conferir o que falta.
          </p>
          <Botao onClick={comecar} carregando={ocupado} disabled={!anda} className="mt-1 shadow-acao">
            Gerar os arquivos
          </Botao>
        </section>
      )}

      {rodando && atual && <EmCurso e={atual} />}

      {anterior && !rodando && (
        <Faixa titulo="Execução de versão anterior">
          Esta geração não guarda o resumo que a tela pede. Rode de novo.
        </Faixa>
      )}

      {resultado && resumo && !anterior && <Concluido execucao={resultado} resumo={resumo} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function EmCurso({ e }: { e: ExecucaoDoArquivoDigital }) {
  const a = e.resumo?.andamento;
  return (
    <Cartao className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <IconeCarregando size={17} className="animate-spin text-marca-laranja" aria-hidden />
        <p className="m-0 text-[15px] font-extrabold text-texto">
          {e.situacao === "cancelando" ? "Cancelando…" : "Escrevendo e pré-validando…"}
        </p>
        <code className="ml-auto font-mono text-[13px] text-laranja-700 escuro:text-laranja-300">
          {a ? `${numero(a.arquivos)} de ${numero(a.total)} arquivos` : `${Math.round(e.fracao * 100)}%`}
        </code>
      </div>
      <BarraFina fracao={e.fracao} classe="bg-marca-laranja" />
      <p className="m-0 text-xs text-texto-fraco">
        {e.passo ?? "Na fila"} · pode fechar esta tela: a geração continua no servidor.
      </p>
      {(e.resumo?.log ?? []).length > 0 && <ListaDoLog log={e.resumo?.log ?? []} emCurso />}
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function Concluido({ execucao, resumo }: { execucao: ExecucaoDoArquivoDigital; resumo: ResumoDoArquivoDigital }) {
  const download = useAcao();
  const [baixando, setBaixando] = useState<string | null>(null);

  async function baixar(qual: PlanilhaDoArquivoDigital, formato: Formato) {
    setBaixando(`${qual}.${formato}`);
    await download.executar((sinal) => baixarPlanilhaDoArquivoDigital(execucao.id, qual, formato, sinal));
    setBaixando(null);
  }

  async function pacote(qual: PacoteDoArquivoDigital) {
    setBaixando(qual);
    await download.executar((sinal) => baixarPacote(execucao.id, qual, sinal));
    setBaixando(null);
  }

  const par = (qual: PlanilhaDoArquivoDigital, rotulo: string) => (
    <BaixarPlanilha
      aoBaixar={(formato) => baixar(qual, formato)}
      desabilitado={download.carregando || (resumo.arquivos ?? 0) === 0}
      baixando={baixando?.startsWith(`${qual}.`) ? (baixando.split(".")[1] as Formato) : null}
      aoCancelar={download.podeCancelar ? download.cancelar : undefined}
      rotulo={rotulo}
    />
  );

  const envio = resumo.para_envio ?? 0;
  const previas = resumo.previas ?? 0;
  const recompostos = resumo.itens_recompostos ?? 0;
  const fecham = resumo.itens_que_fecham ?? 0;

  return (
    <div className="flex flex-col gap-5">
      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} aoFechar={() => download.setErro(null)} />
      )}

      <section className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-4">
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Prontos para enviar à SEFAZ</Rotulo>
          <p className={cn("m-0 font-mono text-[32px] leading-none", envio ? "text-sucesso" : "text-texto-fraco")}>
            {numero(envio)}
            <span className="ml-2 text-sm text-texto-fraco">de {numero(resumo.arquivos ?? 0)}</span>
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Competência apta, nenhuma trava e nenhum erro na pré-validação. Ressarcimento neles:{" "}
            <strong className="font-mono text-texto">{valor(resumo.ressarcimento_para_envio)}</strong>.
          </p>
          <Botao
            variante="principal"
            icone={IconeBaixar}
            className="mt-1 self-start shadow-acao"
            disabled={download.carregando || envio === 0}
            carregando={baixando === "envio"}
            aoCancelar={baixando === "envio" && download.podeCancelar ? download.cancelar : undefined}
            onClick={() => pacote("envio")}
          >
            Baixar os arquivos de envio
          </Botao>
        </Cartao>
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Prévias</Rotulo>
          <p className={cn("m-0 font-mono text-[32px] leading-none", previas ? "text-atencao" : "text-texto-fraco")}>
            {numero(previas)}
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Competências de SP com o que resolver antes. O arquivo sai para conferir, com PREVIA no nome, e
            nunca no pacote de envio.
            {(resumo.competencias_fora_de_sp ?? 0) > 0 &&
              ` ${numero(resumo.competencias_fora_de_sp ?? 0)} competências fora de SP não geram arquivo.`}
          </p>
          <Botao
            variante="secundario"
            icone={IconeBaixar}
            className="mt-1 self-start"
            disabled={download.carregando || previas === 0}
            carregando={baixando === "previas"}
            aoCancelar={baixando === "previas" && download.podeCancelar ? download.cancelar : undefined}
            onClick={() => pacote("previas")}
          >
            Baixar as prévias
          </Botao>
        </Cartao>
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Pré-validação</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-texto">
            {numero(fecham)}
            <span className="ml-2 text-sm text-texto-fraco">de {numero(recompostos)} itens fecham</span>
          </p>
          <div className="mt-1">
            <BarraFina fracao={recompostos ? fecham / recompostos : 0} classe={fecham === recompostos ? "bg-sucesso" : "bg-atencao"} />
          </div>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            A Ficha 3 recomposta de cada arquivo chega ao 1050?{" "}
            <span className={cn("font-mono", (resumo.erros ?? 0) > 0 ? "text-erro" : "text-texto")}>
              {numero(resumo.erros ?? 0)} erros
            </span>{" "}
            · <span className="font-mono text-texto">{numero(resumo.avisos ?? 0)} avisos</span> ·{" "}
            {numero(resumo.linhas ?? 0)} linhas, {tamanho(resumo.bytes)}
          </p>
        </Cartao>
      </section>

      {(resumo.por_trava ?? []).length > 0 && (
        <section className="rounded-cartao border border-atencao/25 border-l-[3px] border-l-atencao bg-atencao-fundo px-5 py-4.5">
          <p className="m-0 text-sm font-extrabold text-atencao">O que impede o envio</p>
          <p className="m-0 mt-1.5 max-w-[800px] text-[13px] leading-relaxed text-texto">
            Um arquivo pode ter mais de um motivo. Resolvido o motivo, gere de novo: o que ficar limpo passa
            para o envio.
          </p>
          <ul className="m-0 mt-3 flex list-none flex-col gap-2 p-0">
            {(resumo.por_trava ?? []).map((t) => (
              <li key={t.codigo} className="flex flex-wrap gap-3 text-[13px] leading-relaxed">
                <span className="min-w-[70px] text-right font-mono text-atencao">{numero(t.arquivos)}</span>
                <span className="font-bold text-texto">{t.rotulo}</span>
                <span className="text-texto-suave">{t.o_que_fazer}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {(resumo.entradas_sem_icms ?? 0) > 0 && (
        <section className="rounded-cartao border border-borda bg-superficie-vidro px-5 py-4">
          <p className="m-0 text-[13px] leading-relaxed text-texto">
            <strong className="font-mono">{numero(resumo.entradas_sem_icms ?? 0)}</strong> entradas vão com ICMS_TOT
            zero. O arquivo passa assim, mas o ressarcimento fica menor se o imposto existia e não foi achado:
            confira as pendências do ICMS suportado na etapa 4.
          </p>
        </section>
      )}

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

      <Arquivos execucaoId={execucao.id} total={resumo.arquivos ?? 0} rodape={par("arquivos", "Baixar o índice dos arquivos")} />

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
          <p className="m-0 text-sm font-extrabold text-texto">Antes de enviar</p>
          <p className="m-0 mt-1 text-xs leading-relaxed text-texto-suave">
            A pré-validação daqui aproxima a da SEFAZ: confere o leiaute e recompõe a Ficha 3, mas as regras
            de crítica do validador oficial não são públicas. Copie para a rede conferindo o SHA-256 do índice.
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

function Arquivos({ execucaoId, total, rodape }: { execucaoId: number; total: number; rodape: ReactNode }) {
  const [recorte, setRecorte] = useState<RecorteDeArquivo>("todos");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<Pagina<ArquivoGerado> | null>(null);
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
      arquivosGerados(execucaoId, { recorte, busca: buscaAplicada, pagina: paginaAtual, porPagina: POR_PAGINA }, sinal),
    ).then((r) => {
      if (vivo && r) setDados(r);
    });
    return () => {
      vivo = false;
    };
  }, [execucaoId, recorte, buscaAplicada, paginaAtual, executar]);

  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  const colunas = "grid-cols-[28px_1.5fr_.6fr_.9fr_.8fr_.8fr_1.8fr]";

  return (
    <section className="overflow-hidden rounded-cartao border border-borda bg-superficie shadow-cat">
      <div className="flex flex-wrap items-center gap-3.5 border-b border-borda px-5.5 py-4.5">
        <div className="min-w-0 flex-1">
          <h2 className="m-0 text-lg font-extrabold text-texto">Arquivos</h2>
          <p className="m-0 mt-1 text-xs text-texto-fraco">
            {dados
              ? `Um por estabelecimento e mês. ${numero(dados.total)} neste recorte · ${numero(total)} no total`
              : "Carregando…"}
          </p>
        </div>
        <Busca valor={busca} aoMudar={setBusca} placeholder="Buscar CNPJ, competência ou arquivo…" className="max-w-[320px]" />
        <Segmentado<RecorteDeArquivo>
          rotulo="Recorte dos arquivos"
          valor={recorte}
          aoMudar={setRecorte}
          opcoes={[
            { chave: "todos", rotulo: "Todos" },
            { chave: "envio", rotulo: "Envio" },
            { chave: "previa", rotulo: "Prévias" },
          ]}
        />
      </div>

      {leitura.erro && (
        <div className="px-5.5 pt-4">
          <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />
        </div>
      )}

      <div className={cn("overflow-x-auto transition-opacity", leitura.carregando && "opacity-60")}>
        <div className="min-w-[1120px]">
          <div className={cn("grid gap-3 bg-tabela-cabecalho-fundo px-5.5 py-3", colunas)}>
            {["", "Estabelecimento", "Competência", "Ressarcimento", "Registros", "Pré-validação", "Situação"].map((c, i) => (
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
              <Fragment key={a.nome}>
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
                    <span className="mt-0.5 block truncate font-mono text-[11px] text-texto-fraco">{a.nome}</span>
                  </span>
                  <code className="font-mono text-[13px] text-texto">{mesAno(a.competencia)}</code>
                  <span className={cn("text-right font-mono text-[13px]", zero(a.ressarcimento) ? "text-texto-fraco" : "text-sucesso")}>
                    {valor(a.ressarcimento)}
                  </span>
                  <span className="text-right font-mono text-xs text-texto-suave">
                    {numero(a.eletronicos + a.nao_eletronicos)}
                    {a.linhas_sem_documento > 0 && (
                      <span className="block text-[11px] text-atencao">{numero(a.linhas_sem_documento)} sem documento</span>
                    )}
                    {(a.entradas_sem_icms ?? 0) > 0 && (
                      <span className="block text-[11px] text-texto-fraco">{numero(a.entradas_sem_icms ?? 0)} entradas sem ICMS</span>
                    )}
                  </span>
                  <span className="text-right font-mono text-xs">
                    <span className={a.erros ? "text-erro" : "text-texto-suave"}>{numero(a.erros)} erros</span>
                    <span className="block text-[11px] text-texto-fraco">
                      {numero(a.itens_que_fecham)}/{numero(a.itens_recompostos)} itens fecham
                    </span>
                  </span>
                  <span className="flex flex-wrap items-center gap-1.5">
                    {a.destino === "envio" ? (
                      <span className="rounded-full border border-sucesso/35 bg-sucesso-fundo px-2 py-0.5 text-[10px] font-bold text-sucesso">
                        pronto para envio
                      </span>
                    ) : (
                      a.travas.map((t) => (
                        <span
                          key={t.codigo}
                          title={t.o_que_fazer}
                          className="rounded-full border border-atencao/35 bg-atencao-fundo px-2 py-0.5 text-[10px] font-bold text-atencao"
                        >
                          {t.rotulo}
                        </span>
                      ))
                    )}
                  </span>
                </button>
                {expandido && <Detalhe execucaoId={execucaoId} arquivo={a} />}
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

function Detalhe({ execucaoId, arquivo }: { execucaoId: number; arquivo: ArquivoGerado }) {
  return (
    <OcorrenciasDoArquivo
      chave={`${execucaoId}|${arquivo.nome}`}
      carregar={(sinal) => ocorrenciasDoArquivo(execucaoId, arquivo.nome, 1, sinal)}
      cabecalho={
        <>
          <div className="flex flex-wrap gap-x-6 gap-y-1.5 font-mono text-[11px] text-texto-suave">
            <span>0150 · {numero(arquivo.participantes)}</span>
            <span>0200 · {numero(arquivo.itens)}</span>
            <span>1050 · {numero(arquivo.saldos)}</span>
            <span>1100 · {numero(arquivo.eletronicos)}</span>
            <span>1200 · {numero(arquivo.nao_eletronicos)}</span>
            <span>{tamanho(arquivo.bytes)}</span>
            <span className="truncate" title={arquivo.sha256}>
              SHA-256 {arquivo.sha256.slice(0, 16)}…
            </span>
          </div>
          {arquivo.motivos.length > 0 && (
            <p className="m-0 mt-3 text-xs leading-relaxed text-texto-suave">
              <strong className="text-texto">Pendências da apuração:</strong>{" "}
              {arquivo.motivos.map((m) => m.rotulo.toLowerCase()).join("; ")}.
            </p>
          )}
        </>
      }
    />
  );
}

import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
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
import { EscolhaDaVendaAConsumidor } from "@/components/shared/VendaAConsumidor";
import { Aviso } from "@/components/ui/Aviso";
import { Botao, BotaoLink } from "@/components/ui/Botao";
import { Busca, Segmentado } from "@/components/ui/Filtros";
import { CabecalhoDePagina, Voltar } from "@/components/ui/Pagina";
import {
  IconeApuracao,
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
import {
  VERSAO_DO_RESUMO_DO_RAZAO,
  baixarPlanilhaDoRazao,
  cancelarRazao,
  detalharRazao,
  fichasDoRazao,
  iniciarRazao,
  linhasDaFicha,
  listarRazao,
  type ExecucaoDoRazao,
  type Ficha,
  type LinhaDaFicha,
  type Pagina,
  type PlanilhaDoRazao,
  type Recorte,
  type ResumoDoRazao,
} from "@/services/razao";
import type { ErroApi } from "@/types/erro";

/**
 * Etapa 5 — montar o razão dos itens (Ficha 3).
 *
 * Uma ficha por estabelecimento e mercadoria com ST, pelo custo médio
 * ponderado móvel. A tela segue a regra da etapa 4: o número nunca aparece
 * sem o que falta para ele valer — abertura sem imposto, saída sem alíquota,
 * confronto ainda não apurado, loja fora de SP.
 */

const ESPERA_PARA_CANCELAR_MS = 400;
const POR_PAGINA = 50;
const ESPERA_DA_BUSCA_MS = 350;

const qtd = (t: string | undefined) =>
  Number(t ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 3 });

const cnpjFormatado = (c: string) =>
  c.length === 14 ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}` : c;

export default function Razao() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDoRazao | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDoRazao | null>(null);
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
      const e = await detalharRazao(execucaoId);
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
    listarRazao(projetoId)
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
      const nova = await iniciarRazao(projetoId);
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
      const e = await cancelarRazao(atual.id);
      setAtual(e);
      if (!EM_CURSO.includes(e.situacao)) parar();
    } catch (x) {
      setErro(comoErro(x));
    }
  }

  const anda = !projeto || aceitaProcessamento(projeto.projeto.status);
  const resumo = resultado?.resumo ?? null;
  const anterior = resultado !== null && (resumo?.versao ?? 0) < VERSAO_DO_RESUMO_DO_RAZAO;
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
      <Botao icone={IconeTentarDeNovo} onClick={comecar} carregando={ocupado} disabled={!anda} className="shadow-acao">
        {resultado && !anterior ? "Montar de novo" : "Montar o razão"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="Etapa 5 · Razão"
        titulo="Montar o razão dos itens"
        sub="A Ficha 3: uma ficha por estabelecimento e mercadoria com ST, pelo custo médio ponderado móvel. É dela que sai o ressarcimento, saída a saída."
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

      <Faixa titulo="De-para de códigos">
        Entrada escriturada com um código e venda com outro (código do fornecedor, kit, marketplace) vira duas
        fichas: uma só com entradas e outra negativa, fora do total.{" "}
        <BotaoLink para={ROTAS.depara(projetoId)} variante="fantasma" tamanho="sm">
          Revisar o de-para
        </BotaoLink>{" "}
        — os pares aprovados entram na próxima montagem.
      </Faixa>

      {p && (
        <EscolhaDaVendaAConsumidor
          projeto={p}
          // razão de antes da escolha existir foi montado como o manual manda
          usadaNoRazao={resultado ? (resumo?.venda_a_consumidor ?? "enquadramento_1") : undefined}
          bloqueada={rodando || !anda}
          aoMudar={(novo) => setProjeto((d) => (d ? { ...d, projeto: novo } : d))}
        />
      )}

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}

      {atual?.situacao === "falhou" && (
        <Aviso titulo="A montagem do razão falhou">
          <span className="block">{atual.erro}</span>
          <code className="mt-2 inline-block rounded-lg border border-dashed border-erro/40 bg-erro/5 px-2.5 py-1.5 font-mono text-xs">
            execução #{atual.id}
          </code>
        </Aviso>
      )}

      {atual?.situacao === "cancelada" && (
        <Faixa titulo="A última rodada foi cancelada">
          Parou a pedido, sem deixar ficha pela metade.
          {resultado ? " Abaixo, o último razão que concluiu." : " Rode de novo quando quiser."}
        </Faixa>
      )}

      {carregado && !atual && (
        <section className="flex flex-col items-center gap-3.5 rounded-cartao border border-dashed border-borda-forte px-7 py-10 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-[13px] border border-laranja-500/30 bg-laranja-500/14 text-laranja-700 escuro:text-laranja-300">
            <IconeApuracao size={20} strokeWidth={1.8} aria-hidden />
          </div>
          <p className="m-0 text-[17px] font-extrabold text-texto">O razão ainda não foi montado</p>
          <p className="m-0 max-w-[560px] text-[13px] leading-relaxed text-texto-suave [text-wrap:pretty]">
            Precisa das etapas 3 e 4 concluídas. As entradas vêm da apuração do suportado; as saídas,
            da EFD e do relatório de saídas do cliente — no varejo, cupom e NFC-e vão à EFD sem item,
            e sem o relatório não há venda para baixar da ficha.
          </p>
          <Botao onClick={comecar} carregando={ocupado} disabled={!anda} className="mt-1 shadow-acao">
            Montar o razão
          </Botao>
        </section>
      )}

      {rodando && atual && <EmCurso e={atual} />}

      {anterior && !rodando && (
        <Faixa titulo="Execução de versão anterior">
          Este razão não guarda o resumo que a tela pede. Rode de novo.
        </Faixa>
      )}

      {resultado && resumo && !anterior && <Concluido execucao={resultado} resumo={resumo} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function EmCurso({ e }: { e: ExecucaoDoRazao }) {
  const a = e.resumo?.andamento;
  const contadores = !a
    ? [
        { rotulo: "Relatórios lidos", valor: `${numero(e.arquivos_lidos)} de ${numero(e.arquivos_totais)}` },
        { rotulo: "Linhas lançadas", valor: "—" },
        { rotulo: "Fichas", valor: "—" },
      ]
    : [
        { rotulo: "Relatórios lidos", valor: `${numero(e.arquivos_totais)} de ${numero(e.arquivos_totais)}` },
        { rotulo: "Linhas lançadas", valor: `${numero(a.linhas)} de ${numero(a.total)}` },
        { rotulo: "Fichas", valor: numero(a.fichas) },
      ];
  return (
    <Cartao className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <IconeCarregando size={17} className="animate-spin text-marca-laranja" aria-hidden />
        <p className="m-0 text-[15px] font-extrabold text-texto">
          {e.situacao === "cancelando" ? "Cancelando…" : "Montando…"}
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
        {e.passo ?? "Na fila"} · pode fechar esta tela: a montagem continua no servidor.
      </p>
      {(e.resumo?.log ?? []).length > 0 && <ListaDoLog log={e.resumo?.log ?? []} emCurso />}
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function Concluido({ execucao, resumo }: { execucao: ExecucaoDoRazao; resumo: ResumoDoRazao }) {
  const download = useAcao();
  const [baixando, setBaixando] = useState<{ qual: PlanilhaDoRazao; formato: Formato } | null>(null);
  const pend = resumo.pendencias;

  async function baixar(qual: PlanilhaDoRazao, formato: Formato) {
    setBaixando({ qual, formato });
    await download.executar((sinal) => baixarPlanilhaDoRazao(execucao.id, qual, formato, sinal));
    setBaixando(null);
  }

  const par = (qual: PlanilhaDoRazao, rotulo: string, destaque?: boolean) => (
    <BaixarPlanilha
      destaque={destaque}
      aoBaixar={(formato) => baixar(qual, formato)}
      desabilitado={download.carregando || (resumo.fichas ?? 0) === 0}
      baixando={baixando?.qual === qual ? baixando.formato : null}
      aoCancelar={download.podeCancelar ? download.cancelar : undefined}
      rotulo={rotulo}
    />
  );

  type Tom = "atencao" | "neutro";
  const pendencias: { n: number; texto: string; tom: Tom }[] = pend
    ? [
        { n: resumo.conferencia_inventario && "suspeita_unidade" in resumo.conferencia_inventario
            ? resumo.conferencia_inventario.suspeita_unidade : 0,
          texto: "comparações com o inventário com diferença do tamanho de um fator de embalagem — suspeita de unidade", tom: "atencao" as Tom },
        { n: pend.linhas_unidade_sem_fator ?? 0, texto: "linhas com unidade diferente da do inventário e sem fator de conversão (0220): a quantidade ficou como veio", tom: "atencao" as Tom },
        { n: pend.fichas_fora_de_sp, texto: "fichas de estabelecimento fora de SP — a CAT 42 é paulista, elas não entram no pedido", tom: "atencao" as Tom },
        { n: pend.fichas_abertura_sem_valor, texto: "fichas abertas com quantidade e sem ICMS suportado: o inventário não traz o imposto e a base não tem entrada anterior ao inventário para valorar a abertura (item 3.3.8) — importe as EFD dos meses antes do período", tom: "atencao" as Tom },
        { n: pend.fichas_abertura_parcial ?? 0, texto: "fichas com a abertura valorada só em parte: as entradas anteriores ao inventário não cobriram a quantidade, e o resto foi pela média delas", tom: "atencao" as Tom },
        { n: pend.confronto_pendente, texto: "saídas de enquadramento 2 ou 4 sem entrada anterior com o ICMS próprio: sem confronto, sem ressarcimento", tom: "atencao" as Tom },
        { n: pend.saidas_sem_aliquota, texto: "saídas sem alíquota interna no cadastro: sem confronto, sem ressarcimento", tom: "atencao" as Tom },
        { n: resumo.retiradas?.fichas ?? pend.fichas_negativas, texto: "fichas retiradas do total até os dados chegarem: o estoque ficou negativo — falta entrada, abertura ou algum tipo de saída (perdas, meses do relatório, produção)", tom: "atencao" as Tom },
        { n: pend.saidas_indefinidas, texto: "saídas com enquadramento indefinido (nota modelo 55 sem dizer quem comprou)", tom: "atencao" as Tom },
        { n: pend.relatorio_sem_estabelecimento, texto: "linhas do relatório de saídas sem loja identificável ficaram de fora", tom: "atencao" as Tom },
        { n: pend.relatorio_trocado_pela_efd, texto: "linhas do relatório trocadas pela nota com item da EFD ou do XML, que vence", tom: "neutro" as Tom },
      ].filter((x) => x.n > 0)
    : [];

  return (
    <div className="flex flex-col gap-5">
      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} aoFechar={() => download.setErro(null)} />
      )}

      <section className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-4">
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Ressarcimento apurado</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-sucesso">{valor(resumo.ressarcimento)}</p>
          <p className="m-0 text-xs text-texto-fraco">
            Diferença positiva entre o suportado baixado e o valor de confronto, saída a saída — só nas
            fichas válidas.
            {(resumo.retiradas?.fichas ?? 0) > 0 &&
              ` ${numero(resumo.retiradas?.fichas ?? 0)} fichas com estoque negativo ficaram fora até os dados chegarem.`}
          </p>
        </Cartao>
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Complemento</Rotulo>
          <p className={cn("m-0 font-mono text-[32px] leading-none", zero(resumo.complemento) ? "text-texto-fraco" : "text-atencao")}>
            {valor(resumo.complemento)}
          </p>
          <p className="m-0 text-xs text-texto-fraco">Só existe no enquadramento 1, consumidor final.</p>
        </Cartao>
        <Cartao className="flex flex-col gap-2">
          <Rotulo>Fichas válidas</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-texto">
            {numero((resumo.fichas ?? 0) - (resumo.retiradas?.fichas ?? 0))}
            <span className="ml-2 text-sm text-texto-fraco">de {numero(resumo.fichas ?? 0)}</span>
          </p>
          <p className="m-0 font-mono text-xs text-texto-fraco">
            {numero(resumo.codigos_com_st ?? 0)} mercadorias com saída CST 60 · {numero(resumo.estabelecimentos ?? 0)}{" "}
            estabelecimentos · {numero(resumo.linhas ?? 0)} linhas
          </p>
          <p className="m-0 text-xs text-texto-fraco">
            {resumo.periodo_inicio && resumo.periodo_fim
              ? `${mesAno(resumo.periodo_inicio.slice(0, 7))} a ${mesAno(resumo.periodo_fim.slice(0, 7))}`
              : ""}
            {resumo.abertura_em ? ` · abertura do inventário de ${resumo.abertura_em.split("-").reverse().join("/")}` : " · sem inventário de abertura"}
          </p>
        </Cartao>
      </section>

      {pendencias.length > 0 && (
        <section className="rounded-cartao border border-atencao/25 border-l-[3px] border-l-atencao bg-atencao-fundo px-5 py-4.5">
          <p className="m-0 text-sm font-extrabold text-atencao">O que ainda falta para o número valer</p>
          <ul className="m-0 mt-2.5 flex list-none flex-col gap-1.5 p-0">
            {pendencias.map((x) => (
              <li key={x.texto} className="flex gap-3 text-[13px] leading-relaxed">
                <span className={cn("min-w-[84px] text-right font-mono", x.tom === "atencao" ? "text-atencao" : "text-texto-suave")}>
                  {numero(x.n)}
                </span>
                <span className="text-texto">{x.texto}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <Conferencia resumo={resumo} acao={par("conferencia", "Baixar a conferência")} />

      <PorEnquadramento resumo={resumo} acao={par("ficha3", "Baixar a Ficha 3", true)} />

      <PorCompetencia resumo={resumo} />

      <Fichas execucaoId={execucao.id} total={resumo.fichas ?? 0} rodape={par("fichas", "Baixar o resumo por ficha")} />

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
          <p className="m-0 text-sm font-extrabold text-texto">Próxima etapa: apurar ressarcimento e complemento</p>
          <p className="m-0 mt-1 text-xs leading-relaxed text-texto-suave">
            Com as fichas montadas, o confronto por enquadramento fecha o valor do pedido e confere o saldo
            final contra o inventário.
          </p>
        </div>
        <BotaoLink para={ROTAS.projeto(execucao.projeto_id)} variante="secundario">
          Ver as etapas
        </BotaoLink>
      </section>
    </div>
  );
}

/** O juiz da unidade e da completude: o saldo da ficha fecha com o bloco H? */
function Conferencia({ resumo, acao }: { resumo: ResumoDoRazao; acao: ReactNode }) {
  const c = resumo.conferencia_inventario;
  if (!c || !("com_estoque" in c)) return null;
  const base = Math.max(1, c.com_estoque);
  const fecham = c.batem + c.proximas;
  const conv = resumo.conversao;
  return (
    <Cartao className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="m-0 flex-1 text-base font-extrabold text-texto">Conferência com o inventário</h2>
        <span className="text-xs text-texto-fraco">
          {numero(c.datas)} datas de bloco H · {numero(c.com_estoque)} comparações com estoque
        </span>
        {acao}
      </div>
      <p className="m-0 max-w-[820px] text-xs leading-relaxed text-texto-suave">
        O saldo de cada ficha em cada data de inventário contra o estoque que a empresa declarou. É o juiz da
        unidade e da completude: entrada em caixa com venda em unidade, ou um tipo de saída que faltou, não
        fecha aqui.
      </p>
      <div className="flex items-baseline gap-2.5">
        <span className={cn("font-mono text-[34px] leading-none", fecham / base >= 0.9 ? "text-sucesso" : "text-atencao")}>
          {((fecham / base) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%
        </span>
        <span className="text-[13px] text-texto-suave">fecham (exato ou até 2%)</span>
      </div>
      <BarraFina fracao={fecham / base} classe={fecham / base >= 0.9 ? "bg-sucesso" : "bg-atencao"} />
      <div className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">
        {[
          { rotulo: "Batem", valor: c.batem, classe: "text-sucesso" },
          { rotulo: "Até 2%", valor: c.proximas, classe: "text-sucesso" },
          { rotulo: "Divergem", valor: c.divergentes, classe: "text-atencao" },
          { rotulo: "Suspeita de unidade", valor: c.suspeita_unidade, classe: "text-erro" },
        ].map((x) => (
          <div key={x.rotulo} className="rounded-[11px] border border-borda bg-superficie-vidro px-3.5 py-3">
            <Rotulo>{x.rotulo}</Rotulo>
            <p className={cn("m-0 mt-1.5 font-mono text-[17px]", x.valor ? x.classe : "text-texto-fraco")}>{numero(x.valor)}</p>
          </div>
        ))}
      </div>
      {conv && (
        <p className="m-0 text-xs text-texto-fraco">
          Conversão de unidade: {numero(conv.linhas_convertidas)} linhas convertidas pelo 0220 ·{" "}
          {numero(conv.linhas_sem_fator)} com unidade diferente e sem fator, mantidas como vieram.
        </p>
      )}
    </Cartao>
  );
}

function PorEnquadramento({ resumo, acao }: { resumo: ResumoDoRazao; acao: ReactNode }) {
  const linhas = resumo.por_enquadramento ?? [];
  const colunas = "grid-cols-[1.6fr_.7fr_.9fr_1fr_1fr_1fr_1fr_1fr]";
  return (
    <section className="overflow-hidden rounded-cartao border border-borda bg-superficie shadow-cat">
      <div className="flex flex-wrap items-center gap-3.5 border-b border-borda px-5.5 py-4.5">
        <div className="min-w-[280px] flex-1">
          <h2 className="m-0 text-lg font-extrabold text-texto">Saídas por enquadramento legal</h2>
          <p className="m-0 mt-1 text-xs text-texto-fraco">
            O enquadramento decide contra o quê a saída é confrontada. Venda de PDV é consumidor final pelo tipo do
            documento; o que não dá para saber fica indefinido, não suposto.
          </p>
        </div>
        {acao}
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[900px]">
          <div className={cn("grid gap-3 bg-tabela-cabecalho-fundo px-5.5 py-3", colunas)}>
            {["Enquadramento", "Linhas", "Quantidade", "Suportado baixado", "Confronto", "Ressarcimento", "Complemento", "Crédito art. 271"].map(
              (c, i) => (
                <span
                  key={c}
                  className={cn(
                    "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                    i > 0 && "text-right",
                  )}
                >
                  {c}
                </span>
              ),
            )}
          </div>
          {linhas.map((e) => (
            <div key={e.codigo} className={cn("grid gap-3 border-t border-borda-sutil px-5.5 py-3", colunas)}>
              <span className="text-[13px] font-bold text-texto">
                <code className="mr-2 font-mono text-xs text-laranja-700 escuro:text-laranja-300">
                  {e.codigo === "indefinido" ? "?" : e.codigo}
                </code>
                {e.rotulo}
              </span>
              <span className="text-right font-mono text-[13px] text-texto-suave">{numero(e.linhas)}</span>
              <span className="text-right font-mono text-[13px] text-texto-suave">{qtd(e.quantidade)}</span>
              <span className="text-right font-mono text-[13px] text-texto">{valor(e.suportado)}</span>
              <span className={cn("text-right font-mono text-[13px]", zero(e.confronto) ? "text-texto-fraco" : "text-texto")}>
                {valor(e.confronto)}
              </span>
              <span className={cn("text-right font-mono text-[13px]", zero(e.ressarcimento) ? "text-texto-fraco" : "text-sucesso")}>
                {valor(e.ressarcimento)}
              </span>
              <span className={cn("text-right font-mono text-[13px]", zero(e.complemento) ? "text-texto-fraco" : "text-atencao")}>
                {valor(e.complemento)}
              </span>
              <span className={cn("text-right font-mono text-[13px]", zero(e.credito ?? "0") ? "text-texto-fraco" : "text-sucesso")}>
                {valor(e.credito ?? "0")}
              </span>
            </div>
          ))}
          {linhas.length === 0 && (
            <p className="m-0 border-t border-borda-sutil px-5.5 py-8 text-center text-[13px] text-texto-fraco">
              Nenhuma saída lançada.
            </p>
          )}
        </div>
      </div>
      <p className="m-0 border-t border-borda-sutil px-5.5 py-3 text-xs text-texto-fraco">
        Saídas lançadas por origem:{" "}
        {Object.entries(resumo.saidas_por_origem ?? {})
          .map(([k, n]) => `${k === "efd" ? "EFD" : k === "xml" ? "XML" : k === "relatorio" ? "relatório do cliente" : k} ${numero(n)}`)
          .join(" · ") || "nenhuma"}
        . A Ficha 3 inteira sai em CSV quando passa do que o Excel aguenta.
      </p>
    </section>
  );
}

function PorCompetencia({ resumo }: { resumo: ResumoDoRazao }) {
  const linhas = resumo.por_competencia ?? [];
  if (linhas.length === 0) return null;
  const maior = Math.max(1, ...linhas.map((m) => Number(m.ressarcimento)));
  return (
    <Cartao className="flex flex-col gap-3.5">
      <h2 className="m-0 text-base font-extrabold text-texto">Ressarcimento por competência</h2>
      <div className="flex max-h-[380px] flex-col gap-2 overflow-y-auto pr-1">
        {linhas.map((m) => (
          <div key={m.competencia} className="flex items-center gap-3">
            <code className="min-w-[58px] font-mono text-xs text-texto-suave">{mesAno(m.competencia)}</code>
            <div className="flex-1">
              <BarraFina fracao={Number(m.ressarcimento) / maior} classe="bg-sucesso" />
            </div>
            <span className="min-w-[112px] text-right font-mono text-xs text-texto">{valor(m.ressarcimento)}</span>
            <span className="min-w-[90px] text-right font-mono text-[11px] text-texto-fraco">{numero(m.linhas)} lin.</span>
          </div>
        ))}
      </div>
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function Fichas({ execucaoId, total, rodape }: { execucaoId: number; total: number; rodape: ReactNode }) {
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [recorte, setRecorte] = useState<Recorte>("validas");
  const [pagina, setPagina] = useState(1);
  const [aberta, setAberta] = useState<string | null>(null);
  const [dados, setDados] = useState<Pagina<Ficha> | null>(null);
  const leitura = useAcao();
  const { executar } = leitura;

  useEffect(() => {
    const t = window.setTimeout(() => setBuscaAplicada(busca), ESPERA_DA_BUSCA_MS);
    return () => window.clearTimeout(t);
  }, [busca]);

  const chaveDoRecorte = `${recorte}|${buscaAplicada}`;
  const [recorteDaPagina, setRecorteDaPagina] = useState(chaveDoRecorte);
  const paginaAtual = recorteDaPagina === chaveDoRecorte ? pagina : 1;
  useEffect(() => {
    setRecorteDaPagina(chaveDoRecorte);
    setPagina(1);
    setAberta(null);
  }, [chaveDoRecorte]);

  useEffect(() => {
    let vivo = true;
    executar((sinal) =>
      fichasDoRazao(execucaoId, { busca: buscaAplicada, recorte, pagina: paginaAtual, porPagina: POR_PAGINA }, sinal),
    ).then((r) => {
      if (vivo && r) setDados(r);
    });
    return () => {
      vivo = false;
    };
  }, [execucaoId, buscaAplicada, recorte, paginaAtual, executar]);

  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  const colunas = "grid-cols-[26px_1.1fr_1.6fr_.6fr_.9fr_.9fr_1fr_.9fr]";

  return (
    <section className="overflow-hidden rounded-cartao border border-borda bg-superficie shadow-cat">
      <div className="flex flex-wrap items-center gap-3.5 border-b border-borda px-5.5 py-4.5">
        <div className="min-w-[280px] flex-1">
          <h2 className="m-0 text-lg font-extrabold text-texto">Fichas</h2>
          <p className="m-0 mt-1 text-xs text-texto-fraco">
            {dados
              ? `Maior ressarcimento primeiro. Clique para abrir a ficha. ${numero(dados.total)} neste recorte · ${numero(total)} no total`
              : "Carregando…"}
          </p>
        </div>
        <Busca valor={busca} aoMudar={setBusca} placeholder="Buscar mercadoria, descrição ou CNPJ…" className="max-w-[320px]" />
        <Segmentado<Recorte>
          rotulo="Recorte das fichas"
          valor={recorte}
          aoMudar={setRecorte}
          opcoes={[
            { chave: "validas", rotulo: "Válidas" },
            { chave: "retiradas", rotulo: "Retiradas" },
            { chave: "sem_aliquota", rotulo: "Sem alíquota" },
            { chave: "indefinidas", rotulo: "Indefinidas" },
            { chave: "divergentes", rotulo: "Divergem do inventário" },
            { chave: "suspeita_unidade", rotulo: "Suspeita de unidade" },
            { chave: "sem_fator", rotulo: "Sem fator" },
            { chave: "todas", rotulo: "Todas" },
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
            {["", "Estabelecimento", "Mercadoria", "Linhas", "Saldo", "Saldo em ICMS", "Ressarcimento", "Atenção"].map((c, i) => (
              <span
                key={i}
                className={cn(
                  "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                  i >= 3 && i <= 6 && "text-right",
                )}
              >
                {c}
              </span>
            ))}
          </div>
          {dados?.linhas.map((f) => {
            const chave = `${f.cnpj}|${f.codigo}`;
            const aberto = aberta === chave;
            return (
              <Fragment key={chave}>
                <button
                  type="button"
                  aria-expanded={aberto}
                  onClick={() => setAberta(aberto ? null : chave)}
                  className={cn(
                    "grid w-full cursor-pointer items-center gap-3 border-0 border-t border-borda-sutil px-5.5 py-3 text-left transition-colors hover:bg-tabela-linha-hover",
                    colunas,
                    aberto ? "bg-superficie-alt" : "bg-transparent",
                  )}
                >
                  <IconeExpandir size={13} strokeWidth={2} aria-hidden className={cn("text-texto-fraco transition-transform", aberto && "rotate-90")} />
                  <span className="min-w-0">
                    <span className="block font-mono text-xs text-texto">{cnpjFormatado(f.cnpj)}</span>
                    <span className={cn("mt-0.5 block text-[11px]", f.uf && f.uf !== "SP" ? "text-atencao" : "text-texto-fraco")}>
                      {f.uf || "UF ?"}
                      {f.uf && f.uf !== "SP" ? " · fora da CAT 42" : ""}
                    </span>
                  </span>
                  <span className="min-w-0">
                    <span className="block font-mono text-[13px] text-texto">{f.codigo}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-texto-fraco" title={f.descricao}>
                      {f.descricao || "Sem descrição no cadastro"}
                    </span>
                  </span>
                  <span className="text-right font-mono text-[13px] text-texto-suave">{numero(f.linhas)}</span>
                  <span className={cn("text-right font-mono text-[13px]", f.ficou_negativo ? "text-atencao" : "text-texto-suave")}>
                    {qtd(f.saldo_quantidade)}
                  </span>
                  <span className="text-right font-mono text-[13px] text-texto-suave">{valor(f.saldo_valor)}</span>
                  <span
                    className={cn(
                      "text-right font-mono text-[13px]",
                      f.retirada ? "text-texto-fraco line-through" : zero(f.ressarcimento) ? "text-texto-fraco" : "text-sucesso",
                    )}
                    title={f.retirada ? "Fora do total: com estoque negativo o custo médio não vale" : undefined}
                  >
                    {valor(f.ressarcimento)}
                  </span>
                  <span className="flex flex-wrap gap-1">
                    {(f.retirada ?? f.ficou_negativo) && <Marca>retirada · estoque negativo</Marca>}
                    {f.abertura_sem_valor && <Marca>abertura s/ ICMS</Marca>}
                    {f.abertura_parcial && <Marca>abertura em parte</Marca>}
                    {f.saidas_sem_aliquota > 0 && <Marca>s/ alíquota</Marca>}
                    {f.saidas_indefinidas > 0 && <Marca>indefinida</Marca>}
                    {f.suspeita_de_unidade && <Marca>suspeita de unidade</Marca>}
                    {!f.suspeita_de_unidade && (f.inventarios_divergentes ?? 0) > 0 && <Marca>diverge do inventário</Marca>}
                    {(f.linhas_sem_fator ?? 0) > 0 && <Marca>unidade s/ fator</Marca>}
                  </span>
                </button>
                {aberto && <LinhasDaFicha execucaoId={execucaoId} ficha={f} />}
              </Fragment>
            );
          })}
          {dados && dados.linhas.length === 0 && (
            <p className="m-0 border-t border-borda-sutil px-5.5 py-10 text-center text-[13px] text-texto-fraco">
              Nenhuma ficha neste recorte.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-borda bg-superficie-vidro px-5.5 py-3.5">
        <Paginacao pagina={paginaAtual} paginas={paginas} ocupado={leitura.carregando} aoIr={setPagina} />
        <span className="min-w-[200px] flex-1 text-[11px] text-texto-fraco">
          Uma página por vez, montada no servidor. A lista inteira sai pelo download.
        </span>
        {rodape}
      </div>
    </section>
  );
}

function Marca({ children }: { children: ReactNode }) {
  return (
    <span className="whitespace-nowrap rounded-full border border-atencao/35 bg-atencao-fundo px-2 py-0.5 text-[10px] font-bold text-atencao">
      {children}
    </span>
  );
}

function Paginacao({
  pagina,
  paginas,
  ocupado,
  aoIr,
}: {
  pagina: number;
  paginas: number;
  ocupado: boolean;
  aoIr: (n: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Botao variante="secundario" tamanho="sm" onClick={() => aoIr(Math.max(1, pagina - 1))} disabled={pagina <= 1 || ocupado}>
        Anterior
      </Botao>
      <span className="font-mono text-xs text-texto-fraco">
        {numero(pagina)} / {numero(paginas)}
      </span>
      <Botao variante="secundario" tamanho="sm" onClick={() => aoIr(Math.min(paginas, pagina + 1))} disabled={pagina >= paginas || ocupado}>
        Próxima
      </Botao>
    </div>
  );
}

function conversaoDaLinha(l: LinhaDaFicha): string | undefined {
  if (l.unidade_sem_fator) return `Veio em ${l.unidade_origem}, que não é a unidade do inventário, e a EFD não trouxe 0220: quantidade mantida.`;
  const fator = Number(l.fator_conversao ?? 1);
  if (fator === 1) return undefined;
  const origem = Number(l.quantidade) / fator;
  return `Veio ${origem.toLocaleString("pt-BR")} ${l.unidade_origem} × ${fator.toLocaleString("pt-BR")} (0220)`;
}

function LinhasDaFicha({ execucaoId, ficha }: { execucaoId: number; ficha: Ficha }) {
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<Pagina<LinhaDaFicha> | null>(null);
  const leitura = useAcao();
  const { executar } = leitura;

  useEffect(() => {
    let vivo = true;
    executar((sinal) => linhasDaFicha(execucaoId, ficha, pagina, sinal)).then((r) => {
      if (vivo && r) setDados(r);
    });
    return () => {
      vivo = false;
    };
  }, [execucaoId, ficha, pagina, executar]);

  const colunas = "grid-cols-[.45fr_.8fr_1.1fr_.6fr_.8fr_.9fr_.9fr_.9fr_.9fr_.9fr]";
  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;

  return (
    <div className="animate-entrada border-t border-borda-sutil bg-superficie-alt/60 px-5.5 pb-4 pl-12 pt-1">
      <div className="flex items-center gap-3 pb-2 pt-3">
        <Rotulo>Ficha 3 · {numero(dados?.total ?? ficha.linhas)} linhas</Rotulo>
        {Number(ficha.abertura_quantidade) !== 0 && (
          <span className="text-[11px] text-texto-fraco">
            abre com {qtd(ficha.abertura_quantidade)} un do inventário, sem ICMS suportado
          </span>
        )}
      </div>
      {leitura.erro && <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />}
      <div className={cn("grid gap-2 py-1.5", colunas)}>
        {["Nº", "Data", "Operação", "Enq.", "Quantidade", "Suportado", "Confronto", "Saldo", "Saldo ICMS", "Ressarc."].map((c, i) => (
          <span key={c} className={cn("text-[10px] font-extrabold uppercase tracking-[0.1em] text-texto-fraco", i >= 4 && "text-right")}>
            {c}
          </span>
        ))}
      </div>
      {dados?.linhas.map((l) => (
        <div key={l.numero} className={cn("grid items-center gap-2 border-t border-borda-sutil py-2", colunas)}>
          <span className="font-mono text-xs text-texto-fraco">{l.numero}</span>
          <span className="font-mono text-xs text-texto-suave">{l.data.split("-").reverse().join("/")}</span>
          <span className="min-w-0 text-xs">
            <span className={l.especie === "entrada" ? "text-info" : "text-texto"}>
              {l.devolucao ? (l.especie === "entrada" ? "Devolução de compra" : "Devolução de venda") : l.especie === "entrada" ? "Entrada" : "Saída"}
            </span>
            <span className="ml-1.5 font-mono text-[11px] text-texto-fraco">
              {l.cfop} · {l.origem === "relatorio" ? "relatório" : l.origem.toUpperCase()}
            </span>
          </span>
          <span className={cn("font-mono text-xs", l.enquadramento_indefinido ? "text-atencao" : "text-texto-suave")}>
            {l.enquadramento_indefinido ? "?" : (l.enquadramento ?? "—")}
          </span>
          <span className="text-right font-mono text-xs text-texto" title={conversaoDaLinha(l)}>
            {qtd(l.quantidade)}
            {l.unidade_sem_fator ? (
              <span className="ml-1 text-[10px] text-atencao">{l.unidade_origem} s/ fator</span>
            ) : Number(l.fator_conversao ?? 1) !== 1 ? (
              <span className="ml-1 text-[10px] text-texto-fraco">
                ×{Number(l.fator_conversao).toLocaleString("pt-BR")}
              </span>
            ) : null}
          </span>
          <span className="text-right font-mono text-xs text-texto">{valor(l.icms_suportado)}</span>
          <span className="text-right font-mono text-xs text-texto-suave">{l.icms_efetivo === null ? "—" : valor(l.icms_efetivo)}</span>
          <span className={cn("text-right font-mono text-xs", Number(l.saldo_quantidade) < 0 ? "text-atencao" : "text-texto-suave")}>
            {qtd(l.saldo_quantidade)}
          </span>
          <span className="text-right font-mono text-xs text-texto-suave">{valor(l.saldo_valor)}</span>
          <span className={cn("text-right font-mono text-xs", zero(l.ressarcimento) ? "text-texto-fraco" : "text-sucesso")}>
            {valor(l.ressarcimento)}
          </span>
        </div>
      ))}
      {paginas > 1 && (
        <div className="pt-3">
          <Paginacao pagina={pagina} paginas={paginas} ocupado={leitura.carregando} aoIr={setPagina} />
        </div>
      )}
    </div>
  );
}

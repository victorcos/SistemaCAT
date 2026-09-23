import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Rotulo } from "@/components/shared/Rodada";
import { Aviso } from "@/components/ui/Aviso";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import { Botao } from "@/components/ui/Botao";
import { Carregando } from "@/components/ui/Carregando";
import { Busca, Segmentado, Toolbar } from "@/components/ui/Filtros";
import { CabecalhoDePagina, Vazio, Voltar } from "@/components/ui/Pagina";
import { IconeExpandir } from "@/constants/icons";
import { ROTAS } from "@/constants/routes";
import { useAcao } from "@/hooks/useAcao";
import { cn } from "@/lib/cn";
import { comoErro } from "@/lib/errors";
import { dinheiro, numero } from "@/lib/format";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import type { Formato } from "@/services/conferencia";
import {
  SEM_REFERENCIAL,
  baixarPlanilhaDaApuracao,
  contasDoRazaoContabil,
  estabelecimentosDoRazaoContabil,
  lancamentosDaConta,
  listarApuracoes,
  type ContaContabil,
  type EstabelecimentoDoRazao,
  type GalhoDoPlano,
  type PaginaDeContas,
  type ExecucaoDaApuracao,
  type PaginaDeLancamentos,
  type RecorteDeConta,
} from "@/services/apuracaoPisCofins";
import type { ErroApi } from "@/types/erro";

/**
 * Razão contábil da ECD — escolher a conta, depois ver os lançamentos.
 *
 * O razão inteiro sai pelo download da quebra. Esta tela existe para o outro
 * gesto, que o download não atende: **procurar uma conta**. Quem confronta a
 * EFD com a contabilidade não quer o arquivo de três milhões de partidas —
 * quer a 3.1.1 de junho, e quer vê-la com o saldo correndo.
 *
 * Por isso o seletor vem primeiro e ocupa a tela, e os lançamentos abrem
 * embaixo da conta escolhida. Nenhuma página é montada aqui: tudo vem
 * paginado do servidor, porque a lista inteira nunca coube no navegador.
 */

const PELA_CONTA: { chave: RecorteDeConta; rotulo: string }[] = [
  { chave: "todas", rotulo: "Todas" },
  { chave: "devedoras", rotulo: "Devedoras" },
  { chave: "credoras", rotulo: "Credoras" },
  { chave: "zeradas", rotulo: "Zeradas" },
];

const POR_PAGINA = 100;

const cnpjFormatado = (c: string) =>
  c.length === 14
    ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}`
    : c;

/** A data do SPED já vem em aaaa-mm-dd; aqui só vira o jeito de ler daqui. */
const data = (iso: string) => (iso?.length === 10 ? iso.split("-").reverse().join("/") : iso || "—");

/** Saldo devedor e credor não são "positivo e negativo": são D e C. */
function Saldo({ valor: v, forte }: { valor: string; forte?: boolean }) {
  const n = Number(v);
  const lado = n === 0 ? "" : n > 0 ? "D" : "C";
  return (
    <span className={cn("font-mono tabular-nums", forte ? "text-texto" : "text-texto-suave")}>
      {dinheiro(String(Math.abs(n)))}
      {lado && <span className="ml-1 text-[11px] font-bold text-texto-fraco">{lado}</span>}
    </span>
  );
}

export default function RazaoContabil() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [quebra, setQuebra] = useState<ExecucaoDaApuracao | null>(null);
  const [carregado, setCarregado] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);

  useEffect(() => {
    let vivo = true;
    detalharProjeto(projetoId)
      .then((p) => vivo && setProjeto(p))
      .catch(() => undefined);
    listarApuracoes(projetoId)
      .then((lista) => {
        if (!vivo) return;
        setQuebra(lista.find((e) => e.situacao === "concluida") ?? null);
      })
      .catch((x) => vivo && setErro(comoErro(x)))
      .finally(() => vivo && setCarregado(true));
    return () => {
      vivo = false;
    };
  }, [projetoId]);

  return (
    <>
      <Voltar para={ROTAS.apuracaoPisCofins(projetoId)}>Apuração de PIS/COFINS</Voltar>
      <CabecalhoDePagina
        eyebrow={projeto?.projeto.nome ? `PIS/COFINS · ${projeto.projeto.nome}` : "PIS/COFINS"}
        titulo="Razão contábil"
        sub="As partidas das contas analíticas da ECD, em ordem de data e com o saldo correndo. Marque as contas e extraia — é a planilha que se compara com a Consulta de Entradas (037)."
      />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}

      {!carregado && <Carregando />}

      {carregado && !quebra && (
        <Vazio
          titulo="Nenhuma apuração de PIS/COFINS concluída neste trabalho"
          acao={
            <Link to={ROTAS.apuracaoPisCofins(projetoId)}>
              <Botao variante="secundario">Ir para a apuração</Botao>
            </Link>
          }
        >
          O razão contábil sai da apuração. Rode a etapa com pelo menos uma ECD no lote e volte aqui.
        </Vazio>
      )}

      {carregado && quebra && (quebra.resumo?.linhas_do_razao ?? 0) === 0 && (
        <Vazio titulo="A apuração não encontrou nenhuma ECD">
          Esta execução leu só EFD-Contribuições. Importe a ECD do período e rode a apuração de novo.
        </Vazio>
      )}

      {carregado && quebra && (quebra.resumo?.linhas_do_razao ?? 0) > 0 && (
        <SeletorDeConta execucaoId={quebra.id} />
      )}
    </>
  );
}

/**
 * O seletor: navegar pelo plano, marcar contas, extrair.
 *
 * O gesto principal é **marcar e extrair**: quem confronta a contabilidade com
 * a Consulta de Entradas (037) escolhe meia dúzia de contas e leva as partidas
 * delas para comparar por fora. O sistema não cruza as duas pontas sozinho, e é
 * de propósito: casar lançamento contábil com item de nota exige critério que
 * muda de cliente para cliente.
 *
 * **A lista é uma árvore.** Numa rede de supermercado são dez mil contas — cem
 * páginas, e ninguém acha nada virando cem páginas. Os galhos são a conta
 * referencial que a própria ECD declara (I051), então três cliques fecham a
 * lista: 3 raízes, 6, 13, 36. Quem já sabe o nome digita na busca, e aí a
 * árvore se desfaz: vem a conta, não o caminho até ela.
 *
 * Onde a árvore não resolve, a tela não finge que resolve: o cliente abre uma
 * conta analítica por fornecedor, e um galho só pendura 5.659 delas. Ali vale a
 * busca — e, para percorrer, "mostrar mais" em vez de trocar de página, que é
 * o que faz perder o lugar.
 *
 * A marcação é **pelo código da conta**, não pelo par CNPJ+conta: a 3.1.1 é a
 * mesma conta do plano em todo estabelecimento, e quem a escolhe quer as
 * partidas de todos. Com mais de um CNPJ na base a tela diz isso.
 *
 * A seleção atravessa galhos, buscas e páginas de propósito: procura-se uma
 * conta, marca-se, procura-se outra.
 */
export function SeletorDeConta({ execucaoId }: { execucaoId: number }) {
  const [busca, setBusca] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [recorte, setRecorte] = useState<RecorteDeConta>("todas");
  const [estabelecimentos, setEstabelecimentos] = useState<EstabelecimentoDoRazao[]>([]);
  const [aberta, setAberta] = useState<string | null>(null);
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [baixando, setBaixando] = useState<Formato | null>(null);
  const download = useAcao();

  useEffect(() => {
    let vivo = true;
    estabelecimentosDoRazaoContabil(execucaoId)
      .then((r) => vivo && setEstabelecimentos(r.linhas))
      .catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, [execucaoId]);

  const procurando = busca.trim().length > 0;

  const alternar = (conta: string) =>
    setMarcadas((antes) => {
      const agora = new Set(antes);
      if (agora.has(conta)) agora.delete(conta);
      else agora.add(conta);
      return agora;
    });

  const marcarVarias = (contas: string[], marcar: boolean) =>
    setMarcadas((antes) => {
      const agora = new Set(antes);
      for (const c of contas) {
        if (marcar) agora.add(c);
        else agora.delete(c);
      }
      return agora;
    });

  async function extrair(formato: Formato) {
    setBaixando(formato);
    await download.executar((sinal) =>
      baixarPlanilhaDaApuracao(execucaoId, "razao-contabil", formato, [...marcadas], sinal),
    );
    setBaixando(null);
  }

  const lista: PropsDaLista = {
    execucaoId,
    busca,
    cnpj,
    recorte,
    marcadas,
    alternar,
    marcarVarias,
    aberta,
    setAberta,
  };

  return (
    <section className="overflow-hidden rounded-raio-g border border-borda bg-superficie">
      <Toolbar>
        <Busca valor={busca} aoMudar={setBusca} placeholder="Conta, nome ou conta referencial" />
        {estabelecimentos.length > 1 && (
          <select
            value={cnpj}
            onChange={(e) => setCnpj(e.target.value)}
            aria-label="Estabelecimento"
            className="rounded-raio-g border border-borda-forte bg-superficie-vidro px-3 py-2.5 font-mono text-[12px] text-texto"
          >
            <option value="">Todos os estabelecimentos</option>
            {estabelecimentos.map((e) => (
              <option key={e.cnpj} value={e.cnpj}>
                {cnpjFormatado(e.cnpj)} · {numero(e.contas)} contas
              </option>
            ))}
          </select>
        )}
        <Segmentado opcoes={PELA_CONTA} valor={recorte} aoMudar={setRecorte} rotulo="Recorte pelo saldo" />
        <span className="ml-auto text-[11px] text-texto-fraco">
          {procurando ? "buscando em todo o plano" : "plano de contas referencial"}
        </span>
      </Toolbar>

      {/* a barra da extração: o que está marcado, e o que sai daqui */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5 border-t border-borda-sutil bg-superficie-vidro px-5.5 py-3">
        <span className="flex items-baseline gap-2">
          <span
            data-testid="quantas-marcadas"
            className="font-mono text-[17px] font-extrabold leading-none text-texto"
          >
            {marcadas.size}
          </span>
          <span className="text-[12px] text-texto-suave">
            {marcadas.size === 1 ? "conta marcada" : "contas marcadas"}
          </span>
        </span>

        {marcadas.size > 0 && (
          <Botao variante="fantasma" tamanho="sm" onClick={() => setMarcadas(new Set())}>
            Limpar
          </Botao>
        )}

        {marcadas.size === 0 && (
          <span className="text-[12px] text-texto-fraco">
            Abra os galhos para achar a conta, ou busque pelo nome — o que você marcar fica marcado.
          </span>
        )}

        {marcadas.size > 0 && estabelecimentos.length > 1 && (
          <span className="text-[12px] text-texto-fraco">
            Sai a conta nos {numero(estabelecimentos.length)} estabelecimentos.
          </span>
        )}

        <div className="ml-auto">
          <BaixarPlanilha
            aoBaixar={extrair}
            desabilitado={marcadas.size === 0}
            rotulo="Extrair as contas marcadas"
            destaque
            baixando={baixando}
            aoCancelar={download.cancelar}
          />
        </div>
      </div>

      {download.erro && (
        <div className="px-5.5 pt-4">
          <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} />
        </div>
      )}

      <div className="overflow-x-auto">
        <div className="min-w-[980px]">
          <div className="grid grid-cols-[30px_1fr] items-center gap-3 bg-tabela-cabecalho-fundo px-5.5 py-3">
            <span />
            <div className={cn("grid gap-3", COLUNAS)}>
              {["", "Conta", "Descrição", "Partidas", "Débitos", "Créditos", "Saldo"].map((c, i) => (
                <span
                  key={i}
                  className={cn(
                    "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                    i >= 3 && "text-right",
                  )}
                >
                  {c}
                </span>
              ))}
            </div>
          </div>

          {/* a raiz da árvore, ou o resultado da busca: os dois saem da mesma
              rota, e o que muda é só quem manda paginar */}
          <Nivel {...lista} pai={null} nivel={0} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-borda bg-superficie-vidro px-5.5 py-3.5 text-[11px] text-texto-fraco">
        {procurando
          ? "Busca em todo o plano, montada no servidor."
          : "Os galhos são a conta referencial declarada pela ECD (I051)."}{" "}
        Sem conta marcada, o razão inteiro continua saindo pelo download da apuração.
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */

const COLUNAS = "grid-cols-[28px_1.1fr_1.6fr_.7fr_1fr_1fr_1fr]";

interface PropsDaLista {
  execucaoId: number;
  busca: string;
  cnpj: string;
  recorte: RecorteDeConta;
  marcadas: Set<string>;
  alternar: (conta: string) => void;
  marcarVarias: (contas: string[], marcar: boolean) => void;
  aberta: string | null;
  setAberta: (chave: string | null) => void;
}

/**
 * Um nível da árvore: os galhos filhos e as contas que param aqui.
 *
 * Busca o seu próprio conteúdo, e só quando é aberto — abrir o plano inteiro de
 * uma vez seria a lista chapada de novo, com mais passos. Quem pagina é a
 * conta, não o galho: galho nenhum passa de uma centena.
 */
function Nivel({ pai, nivel, ...p }: PropsDaLista & { pai: string | null; nivel: number }) {
  const [dados, setDados] = useState<PaginaDeContas | null>(null);
  const [contas, setContas] = useState<ContaContabil[]>([]);
  const [pagina, setPagina] = useState(1);
  const leitura = useAcao();
  const { executar } = leitura;
  const procurando = p.busca.trim().length > 0;

  // busca, estabelecimento ou recorte novos desfazem o que já se leu: o que
  // está na tela deixou de ser resposta para a pergunta que está sendo feita
  useEffect(() => {
    setPagina(1);
    setContas([]);
  }, [p.busca, p.cnpj, p.recorte]);

  useEffect(() => {
    let vivo = true;
    const espera = window.setTimeout(() => {
      executar((sinal) =>
        contasDoRazaoContabil(
          p.execucaoId,
          {
            busca: p.busca,
            cnpj: p.cnpj,
            recorte: p.recorte,
            pagina,
            porPagina: POR_PAGINA,
            pai,
            arvore: true,
          },
          sinal,
        ),
      ).then((r) => {
        if (!vivo || !r) return;
        setDados(r);
        setContas((antes) => (r.pagina === 1 ? r.linhas : [...antes, ...r.linhas]));
      });
    }, p.busca ? 250 : 0);
    return () => {
      vivo = false;
      window.clearTimeout(espera);
    };
  }, [p.execucaoId, p.busca, p.cnpj, p.recorte, pagina, pai, executar]);

  if (leitura.erro) {
    return (
      <div className="px-5.5 py-4">
        <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />
      </div>
    );
  }

  if (!dados) {
    return (
      <p className="m-0 border-t border-borda-sutil px-5.5 py-6 text-center text-[12px] text-texto-fraco">
        Lendo…
      </p>
    );
  }

  const faltam = dados.total - contas.length;
  const vazio = dados.nos.length === 0 && contas.length === 0;

  return (
    <>
      {dados.nos.map((galho) => (
        <Galho key={galho.codigo} galho={galho} nivel={nivel} {...p} />
      ))}

      {contas.map((c) => (
        <LinhaDeConta key={`${c.cnpj}|${c.conta}`} conta={c} nivel={nivel} {...p} />
      ))}

      {faltam > 0 && (
        <div
          className="border-t border-borda-sutil px-5.5 py-3"
          style={{ paddingLeft: 22 + nivel * 18 }}
        >
          <Botao
            variante="secundario"
            tamanho="sm"
            onClick={() => setPagina((n) => n + 1)}
            disabled={leitura.carregando}
          >
            {leitura.carregando
              ? "Lendo…"
              : `Mostrar mais ${numero(Math.min(faltam, POR_PAGINA))} de ${numero(faltam)}`}
          </Botao>
        </div>
      )}

      {vazio && (
        <p className="m-0 border-t border-borda-sutil px-5.5 py-10 text-center text-[13px] text-texto-fraco">
          {procurando ? "Nenhuma conta com esse texto." : "Nada neste galho."}
        </p>
      )}
    </>
  );
}

/** Um galho fechado; abrir busca o que há dentro. */
function Galho({
  galho,
  nivel,
  ...p
}: PropsDaLista & { galho: GalhoDoPlano; nivel: number }) {
  const [aberto, setAberto] = useState(false);
  const semMapa = galho.codigo === SEM_REFERENCIAL;

  return (
    <>
      <div className="grid grid-cols-[30px_1fr] items-center gap-3 border-t border-borda-sutil px-5.5">
        <span />
        <button
          type="button"
          aria-expanded={aberto}
          // sem rótulo, o nome do botão vira o amontoado de código, contagem e
          // três valores — impronunciável em leitor de tela
          aria-label={semMapa ? "Contas sem conta referencial" : `Conta referencial ${galho.codigo}`}
          onClick={() => setAberto((x) => !x)}
          className={cn(
            "grid w-full cursor-pointer items-center gap-3 border-0 bg-transparent py-3 text-left hover:bg-tabela-linha-hover",
            COLUNAS,
          )}
          style={{ paddingLeft: nivel * 18 }}
        >
          <IconeExpandir
            size={14}
            strokeWidth={2.5}
            aria-hidden
            className={cn("text-texto-suave transition-transform", aberto && "rotate-90")}
          />
          <span className="min-w-0">
            <span className="block font-mono text-[13px] font-bold text-texto">
              {semMapa ? "—" : galho.codigo}
            </span>
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[13px] text-texto-suave">
              {semMapa ? "Contas sem conta referencial na ECD" : "Conta referencial"}
            </span>
            <span className="mt-0.5 block text-[11px] text-texto-fraco">
              {numero(galho.contas)} {galho.contas === 1 ? "conta" : "contas"}
            </span>
          </span>
          <span className="text-right font-mono text-[13px] tabular-nums text-texto-fraco">
            {numero(galho.lancamentos)}
          </span>
          <span className="text-right text-[13px] text-texto-suave">{dinheiro(galho.debitos)}</span>
          <span className="text-right text-[13px] text-texto-suave">{dinheiro(galho.creditos)}</span>
          <span className="text-right text-[13px]">
            <Saldo valor={galho.saldo} />
          </span>
        </button>
      </div>

      {aberto && <Nivel {...p} pai={galho.codigo} nivel={nivel + 1} />}
    </>
  );
}

/** Uma conta: marcar para extrair, ou abrir para ver as partidas. */
function LinhaDeConta({
  conta: c,
  nivel,
  ...p
}: PropsDaLista & { conta: ContaContabil; nivel: number }) {
  const chave = `${c.cnpj}|${c.conta}`;
  const abertoAgora = p.aberta === chave;
  const marcada = p.marcadas.has(c.conta);

  return (
    <>
      <div
        className={cn(
          "grid grid-cols-[30px_1fr] items-center gap-3 border-t border-borda-sutil px-5.5 transition-colors",
          abertoAgora
            ? "bg-superficie-alt"
            : marcada
              ? "bg-laranja-500/8"
              : "bg-transparent hover:bg-tabela-linha-hover",
        )}
      >
        <input
          type="checkbox"
          aria-label={`Marcar a conta ${c.conta}`}
          checked={marcada}
          onChange={() => p.alternar(c.conta)}
        />
        <button
          type="button"
          aria-expanded={abertoAgora}
          aria-label={`Partidas da conta ${c.conta}`}
          onClick={() => p.setAberta(abertoAgora ? null : chave)}
          className={cn(
            "grid w-full cursor-pointer items-center gap-3 border-0 bg-transparent py-3 text-left",
            COLUNAS,
          )}
          style={{ paddingLeft: nivel * 18 }}
        >
          <IconeExpandir
            size={13}
            strokeWidth={2}
            aria-hidden
            className={cn("text-texto-fraco transition-transform", abertoAgora && "rotate-90")}
          />
          <span className="min-w-0">
            <span className="block font-mono text-[13px] text-texto">{c.conta}</span>
            <span className="mt-0.5 block font-mono text-[11px] text-texto-fraco">
              {cnpjFormatado(c.cnpj)}
            </span>
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[13px] text-texto" title={c.descricao}>
              {c.descricao || "Sem nome no plano de contas"}
            </span>
            <span className="mt-0.5 block text-[11px] text-texto-fraco">
              {c.conta_referencial ? `referencial ${c.conta_referencial} · ` : ""}
              {data(c.de)} a {data(c.ate)}
              {c.arquivos > 1 ? ` · ${numero(c.arquivos)} ECD` : ""}
            </span>
          </span>
          <span className="text-right font-mono text-[13px] tabular-nums text-texto-suave">
            {numero(c.lancamentos)}
          </span>
          <span className="text-right text-[13px]">{dinheiro(c.debitos)}</span>
          <span className="text-right text-[13px]">{dinheiro(c.creditos)}</span>
          <span className="text-right text-[13px]">
            <Saldo valor={c.saldo} forte />
          </span>
        </button>
      </div>
      {abertoAgora && <Lancamentos execucaoId={p.execucaoId} conta={c} />}
    </>
  );
}

function Lancamentos({ execucaoId, conta }: { execucaoId: number; conta: ContaContabil }) {
  const [pagina, setPagina] = useState(1);
  const [busca, setBusca] = useState("");
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [dados, setDados] = useState<PaginaDeLancamentos | null>(null);
  const leitura = useAcao();
  const { executar } = leitura;

  useEffect(() => setPagina(1), [busca, de, ate]);

  const chave = `${conta.cnpj}|${conta.conta}`;
  const ler = useCallback(
    (sinal: AbortSignal) =>
      lancamentosDaConta(execucaoId, { cnpj: conta.cnpj, conta: conta.conta }, { busca, de, ate, pagina }, sinal),
    [execucaoId, conta.cnpj, conta.conta, busca, de, ate, pagina],
  );

  useEffect(() => {
    let vivo = true;
    const espera = window.setTimeout(
      () => {
        executar(ler).then((r) => {
          if (vivo && r) setDados(r);
        });
      },
      busca ? 250 : 0,
    );
    return () => {
      vivo = false;
      window.clearTimeout(espera);
    };
  }, [ler, executar, busca]);

  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  const colunas = "grid-cols-[.65fr_.5fr_2fr_.75fr_.9fr_.9fr]";

  return (
    <div key={chave} className="animate-entrada border-t border-borda-sutil bg-superficie-alt/60 px-5.5 pb-4 pl-12 pt-1">
      <div className="flex flex-wrap items-center gap-3 pb-2 pt-3">
        <Rotulo>
          {numero(dados?.total ?? conta.lancamentos)} {(dados?.total ?? conta.lancamentos) === 1 ? "partida" : "partidas"}
        </Rotulo>
        <Busca valor={busca} aoMudar={setBusca} placeholder="Histórico, número ou participante" className="max-w-[300px]" />
        <label className="flex items-center gap-2 text-[11px] text-texto-fraco">
          de
          <input
            type="date"
            value={de}
            onChange={(e) => setDe(e.target.value)}
            className="rounded-raio border border-borda-forte bg-superficie-vidro px-2 py-1 font-mono text-[12px] text-texto"
          />
        </label>
        <label className="flex items-center gap-2 text-[11px] text-texto-fraco">
          até
          <input
            type="date"
            value={ate}
            onChange={(e) => setAte(e.target.value)}
            className="rounded-raio border border-borda-forte bg-superficie-vidro px-2 py-1 font-mono text-[12px] text-texto"
          />
        </label>
        {dados && (
          <span className="ml-auto flex flex-wrap items-center gap-4 text-[11px] text-texto-fraco">
            {dados.recortado && <span className="text-atencao">totais do recorte, não da conta</span>}
            <span>
              débitos <span className="font-mono text-texto-suave">{dinheiro(dados.totais.debitos)}</span>
            </span>
            <span>
              créditos <span className="font-mono text-texto-suave">{dinheiro(dados.totais.creditos)}</span>
            </span>
            <span>
              saldo <Saldo valor={dados.totais.saldo} forte />
            </span>
          </span>
        )}
      </div>

      {leitura.erro && <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />}

      {/* cada ECD começa o saldo do zero: com duas, a coluna volta ao início no
          meio da lista. Dizer isso é melhor que esconder a conta ou somar o que
          o arquivo não somou */}
      {conta.arquivos > 1 && (
        <p className="m-0 pb-1 text-[11px] text-atencao">
          Esta conta aparece em {numero(conta.arquivos)} arquivos de ECD. O saldo corre dentro de cada
          arquivo e recomeça no próximo — os totais acima somam os dois.
        </p>
      )}

      <div className={cn("overflow-x-auto transition-opacity", leitura.carregando && "opacity-60")}>
        <div className="min-w-[820px]">
          <div className={cn("grid gap-3 border-y border-borda-sutil py-2", colunas)}>
            {["Data", "Lançamento", "Histórico", "D/C", "Valor", "Saldo"].map((c, i) => (
              <span
                key={i}
                className={cn(
                  "text-[10px] font-extrabold uppercase tracking-[0.14em] text-texto-fraco",
                  i >= 4 && "text-right",
                )}
              >
                {c}
              </span>
            ))}
          </div>
          {dados?.linhas.map((l, i) => (
            <div key={`${l.numero}-${l.data}-${i}`} className={cn("grid items-center gap-3 border-b border-borda-sutil py-2", colunas)}>
              <span className="font-mono text-[12px] text-texto-suave">{data(l.data)}</span>
              <span className="min-w-0">
                <span className="block font-mono text-[12px] text-texto-suave">{l.numero || "—"}</span>
                {l.tipo && <span className="mt-0.5 block truncate text-[10px] text-texto-fraco">{l.tipo}</span>}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[12px] text-texto" title={l.historico}>
                  {l.historico || "Sem histórico"}
                </span>
                {(l.participante || l.centro_de_custo) && (
                  <span className="mt-0.5 block text-[10px] text-texto-fraco">
                    {[l.participante && `participante ${l.participante}`, l.centro_de_custo && `centro ${l.centro_de_custo}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                )}
              </span>
              <span className={cn("text-[12px] font-bold", l.debito_ou_credito === "D" ? "text-texto" : "text-texto-suave")}>
                {l.debito_ou_credito || "?"}
              </span>
              <span className="text-right font-mono text-[12px] tabular-nums text-texto-suave">{dinheiro(l.valor)}</span>
              <span className="text-right text-[12px]">
                <Saldo valor={l.saldo} />
              </span>
            </div>
          ))}
          {dados && dados.linhas.length === 0 && (
            <p className="m-0 py-8 text-center text-[12px] text-texto-fraco">
              Nenhuma partida neste recorte.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 pt-3">
        <Paginacao pagina={pagina} paginas={paginas} ocupado={leitura.carregando} aoIr={setPagina} />
        <span className="text-[11px] text-texto-fraco">
          O saldo corre na ordem de data do razão — que não é a ordem do arquivo.
        </span>
      </div>
    </div>
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
      <Botao
        variante="secundario"
        tamanho="sm"
        onClick={() => aoIr(Math.min(paginas, pagina + 1))}
        disabled={pagina >= paginas || ocupado}
      >
        Próxima
      </Botao>
    </div>
  );
}

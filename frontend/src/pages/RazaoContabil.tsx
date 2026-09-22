import { Fragment, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Rotulo } from "@/components/shared/Rodada";
import { Aviso } from "@/components/ui/Aviso";
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
import {
  contasDoRazaoContabil,
  estabelecimentosDoRazaoContabil,
  lancamentosDaConta,
  listarQuebras,
  type ContaContabil,
  type EstabelecimentoDoRazao,
  type ExecucaoDaQuebra,
  type Pagina,
  type PaginaDeLancamentos,
  type RecorteDeConta,
} from "@/services/quebraDeSped";
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
  const [quebra, setQuebra] = useState<ExecucaoDaQuebra | null>(null);
  const [carregado, setCarregado] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);

  useEffect(() => {
    let vivo = true;
    detalharProjeto(projetoId)
      .then((p) => vivo && setProjeto(p))
      .catch(() => undefined);
    listarQuebras(projetoId)
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
      <Voltar para={ROTAS.quebraDeSped(projetoId)}>Quebra de SPED</Voltar>
      <CabecalhoDePagina
        eyebrow={projeto?.projeto.nome ? `PIS/COFINS · ${projeto.projeto.nome}` : "PIS/COFINS"}
        titulo="Razão contábil"
        sub="As partidas das contas analíticas da ECD, em ordem de data e com o saldo correndo. Escolha a conta para ver os lançamentos dela."
      />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}

      {!carregado && <Carregando />}

      {carregado && !quebra && (
        <Vazio
          titulo="Nenhuma quebra de SPED concluída neste trabalho"
          acao={
            <Link to={ROTAS.quebraDeSped(projetoId)}>
              <Botao variante="secundario">Ir para a quebra</Botao>
            </Link>
          }
        >
          O razão contábil sai da quebra. Rode a etapa com pelo menos uma ECD no lote e volte aqui.
        </Vazio>
      )}

      {carregado && quebra && (quebra.resumo?.linhas_do_razao ?? 0) === 0 && (
        <Vazio titulo="A quebra não encontrou nenhuma ECD">
          Esta execução leu só EFD-Contribuições. Importe a ECD do período e rode a quebra de novo.
        </Vazio>
      )}

      {carregado && quebra && (quebra.resumo?.linhas_do_razao ?? 0) > 0 && (
        <SeletorDeConta execucaoId={quebra.id} />
      )}
    </>
  );
}

function SeletorDeConta({ execucaoId }: { execucaoId: number }) {
  const [busca, setBusca] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [recorte, setRecorte] = useState<RecorteDeConta>("todas");
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<Pagina<ContaContabil> | null>(null);
  const [estabelecimentos, setEstabelecimentos] = useState<EstabelecimentoDoRazao[]>([]);
  const [aberta, setAberta] = useState<string | null>(null);
  const leitura = useAcao();
  const { executar } = leitura;

  useEffect(() => {
    let vivo = true;
    estabelecimentosDoRazaoContabil(execucaoId)
      .then((r) => vivo && setEstabelecimentos(r.linhas))
      .catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, [execucaoId]);

  // a busca troca a lista inteira: voltar para a primeira página é o certo,
  // senão a pessoa digita e cai numa página 7 que o novo recorte não tem
  useEffect(() => setPagina(1), [busca, cnpj, recorte]);

  useEffect(() => {
    let vivo = true;
    const espera = window.setTimeout(() => {
      executar((sinal) =>
        contasDoRazaoContabil(execucaoId, { busca, cnpj, recorte, pagina, porPagina: POR_PAGINA }, sinal),
      ).then((r) => {
        if (vivo && r) setDados(r);
      });
    }, busca ? 250 : 0);
    return () => {
      vivo = false;
      window.clearTimeout(espera);
    };
  }, [execucaoId, busca, cnpj, recorte, pagina, executar]);

  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  const colunas = "grid-cols-[28px_1.1fr_1.6fr_.7fr_1fr_1fr_1fr]";

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
          {dados ? `${numero(dados.total)} ${dados.total === 1 ? "conta" : "contas"}` : ""}
        </span>
      </Toolbar>

      {leitura.erro && (
        <div className="px-5.5 pt-4">
          <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />
        </div>
      )}

      <div className={cn("overflow-x-auto transition-opacity", leitura.carregando && "opacity-60")}>
        <div className="min-w-[940px]">
          <div className={cn("grid gap-3 bg-tabela-cabecalho-fundo px-5.5 py-3", colunas)}>
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

          {dados?.linhas.map((c) => {
            const chave = `${c.cnpj}|${c.conta}`;
            const abertoAgora = aberta === chave;
            return (
              <Fragment key={chave}>
                <button
                  type="button"
                  aria-expanded={abertoAgora}
                  onClick={() => setAberta(abertoAgora ? null : chave)}
                  className={cn(
                    "grid w-full cursor-pointer items-center gap-3 border-0 border-t border-borda-sutil px-5.5 py-3 text-left transition-colors hover:bg-tabela-linha-hover",
                    colunas,
                    abertoAgora ? "bg-superficie-alt" : "bg-transparent",
                  )}
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
                {abertoAgora && <Lancamentos execucaoId={execucaoId} conta={c} />}
              </Fragment>
            );
          })}

          {dados && dados.linhas.length === 0 && (
            <p className="m-0 border-t border-borda-sutil px-5.5 py-10 text-center text-[13px] text-texto-fraco">
              Nenhuma conta neste recorte.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-borda bg-superficie-vidro px-5.5 py-3.5">
        <Paginacao pagina={pagina} paginas={paginas} ocupado={leitura.carregando} aoIr={setPagina} />
        <span className="min-w-[220px] flex-1 text-[11px] text-texto-fraco">
          Uma página por vez, montada no servidor. O razão inteiro sai pelo download da quebra.
        </span>
      </div>
    </section>
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

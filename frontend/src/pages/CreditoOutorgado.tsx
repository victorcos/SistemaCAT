import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import { BarraFina, Cartao, Faixa, ListaDoLog, Rotulo, quando } from "@/components/shared/Rodada";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Busca, Chip, Segmentado, Toolbar } from "@/components/ui/Filtros";
import { Modal } from "@/components/ui/Modal";
import { CabecalhoDePagina, Vazio, Voltar } from "@/components/ui/Pagina";
import { Celula, Linha, Tabela } from "@/components/ui/Tabela";
import { IconeApagar, IconeParar, IconeTentarDeNovo } from "@/constants/icons";
import { INTERVALO_POLL_MS } from "@/constants/polling";
import { ROTAS } from "@/constants/routes";
import { aceitaProcessamento } from "@/constants/status";
import { useAcao } from "@/hooks/useAcao";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/cn";
import { comoErro } from "@/lib/errors";
import { numero } from "@/lib/format";
import { EM_CURSO, type Formato } from "@/services/conferencia";
import {
  baixarPlanilhaDoOutorgado,
  cancelarOutorgado,
  detalharOutorgado,
  gravarFiltroDoOutorgado,
  iniciarOutorgado,
  itensDoOutorgado,
  lerFiltroDoOutorgado,
  listarOutorgados,
  produtosDoOutorgado,
  type ExecucaoDoOutorgado,
  type FiltroDoOutorgado,
  type ItemDoOutorgado,
  type PlanilhaDoOutorgado,
  type ProdutoDoOutorgado,
  type ResumoDoOutorgado,
} from "@/services/creditoOutorgado";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/**
 * Crédito outorgado — quais itens vendidos são produto beneficiado.
 *
 * A tela tem dois tempos, e eles não são etapas de um assistente: são duas
 * coisas que se alternam pela vida do trabalho.
 *
 * 1. **O filtro** — os termos de descrição e as NCM que definem o benefício
 *    nesta empresa. Fica gravado no trabalho e vale para todas as rodadas.
 * 2. **A revisão** — a lista de **produtos** que o filtro capturou. É por aqui
 *    que se descobre o "PÃO DE VELA" que entrou por engano e o item que ficou
 *    de fora; ninguém revisa um benefício lendo três milhões de linhas.
 *
 * A regra é do motor, e a tela não a repete: a descrição manda, a NCM confirma.
 * O que a tela faz é dizer isso em palavras, no lugar em que a pessoa escreve o
 * termo — não num manual que ninguém abre.
 */

const ESPERA_PARA_CANCELAR_MS = 400;

const reais = (texto: string | undefined) =>
  Number(texto ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

const reaisDeCentavos = (centavos: number | undefined) =>
  ((centavos ?? 0) / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

const mesmaLista = (a: string[], b: string[]) =>
  a.length === b.length && a.every((x, i) => x === b[i]);

export default function CreditoOutorgado() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);
  const { podeEscrever } = useAuth();

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [filtro, setFiltro] = useState<FiltroDoOutorgado | null>(null);
  const [atual, setAtual] = useState<ExecucaoDoOutorgado | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDoOutorgado | null>(null);
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
      const e = await detalharOutorgado(execucaoId);
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
    lerFiltroDoOutorgado(projetoId).then(setFiltro).catch((x) => setErro(comoErro(x)));
    listarOutorgados(projetoId)
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
      const nova = await iniciarOutorgado(projetoId);
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
      const e = await cancelarOutorgado(atual.id);
      setAtual(e);
      if (!EM_CURSO.includes(e.situacao)) parar();
    } catch (x) {
      setErro(comoErro(x));
    }
  }

  const anda = !projeto || aceitaProcessamento(projeto.projeto.status);
  const resumo = resultado?.resumo ?? null;
  const p = projeto?.projeto;
  // sem termo e sem a chave geral nada seria elegível — e o servidor recusa
  const julga = filtro !== null && (filtro.sem_filtro || filtro.termos.length > 0);

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
        <Botao carregando>Varrendo…</Botao>
      );
  } else {
    acao = (
      <Botao
        icone={IconeTentarDeNovo}
        onClick={comecar}
        carregando={ocupado}
        disabled={!anda || !julga || !podeEscrever}
        title={julga ? undefined : "Cadastre ao menos um termo de descrição antes de rodar."}
        className="shadow-acao"
      >
        {resultado ? "Varrer de novo" : "Varrer os XML"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="ICMS · Crédito outorgado"
        titulo="Crédito outorgado"
        sub="Varre os XML de saída e separa, item a item, o que é produto beneficiado. A descrição manda e a NCM confirma — bater só a NCM não basta, porque a NCM é declarada pelo emitente e erra, enquanto a descrição é o produto que o dono do negócio reconhece."
        acao={
          <div className="flex flex-col items-end gap-2.5">
            {acao}
            {resultado && !rodando && (
              <p className="m-0 text-right text-[11px] leading-normal text-texto-fraco">
                Varrido em {quando(resultado.terminada_em)}
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

      {filtro && (
        <EditorDoFiltro
          projetoId={projetoId}
          filtro={filtro}
          aoGravar={setFiltro}
          podeEscrever={podeEscrever}
        />
      )}

      {atual?.situacao === "falhou" && (
        <Aviso titulo="A varredura falhou">
          <span className="block">{atual.erro}</span>
          <code className="mt-2 inline-block rounded-lg border border-dashed border-erro/40 bg-erro/5 px-2.5 py-1.5 font-mono text-xs">
            execução #{atual.id}
          </code>
        </Aviso>
      )}

      {atual?.situacao === "cancelada" && (
        <Faixa titulo="A última rodada foi cancelada">
          Parou a pedido. O que ficou pela metade não vale.
          {resultado ? " Abaixo, a última varredura que concluiu." : " Rode de novo quando quiser."}
        </Faixa>
      )}

      {rodando && atual && <EmCurso e={atual} />}

      {!rodando && !atual && (
        <Faixa titulo="Nada varrido ainda">
          Cadastre os termos que descrevem os produtos beneficiados e rode a varredura. Ela lê os
          XML do lote direto — nenhuma outra etapa precisa vir antes.
        </Faixa>
      )}

      {!rodando && resultado && resumo && (
        <Concluido execucao={resultado} resumo={resumo} filtroDeHoje={filtro} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

/**
 * O filtro do trabalho.
 *
 * Dois campos que aceitam vários de uma vez: quem já tem a lista de produtos
 * numa planilha cola tudo separado por vírgula ou por linha, em vez de digitar
 * item a item. Cada termo vira uma pílula, e some com um clique.
 */
function EditorDoFiltro({
  projetoId,
  filtro,
  aoGravar,
  podeEscrever,
}: {
  projetoId: number;
  filtro: FiltroDoOutorgado;
  aoGravar: (f: FiltroDoOutorgado) => void;
  podeEscrever: boolean;
}) {
  const [termos, setTermos] = useState(filtro.termos);
  const [ncms, setNcms] = useState(filtro.ncms);
  const [semFiltro, setSemFiltro] = useState(filtro.sem_filtro);
  const [guardar, setGuardar] = useState(filtro.guardar_descartados);
  const gravacao = useAcao();

  useEffect(() => {
    setTermos(filtro.termos);
    setNcms(filtro.ncms);
    setSemFiltro(filtro.sem_filtro);
    setGuardar(filtro.guardar_descartados);
  }, [filtro]);

  const mudou =
    !mesmaLista(termos, filtro.termos) ||
    !mesmaLista(ncms, filtro.ncms) ||
    semFiltro !== filtro.sem_filtro ||
    guardar !== filtro.guardar_descartados;

  async function salvar() {
    const novo = await gravacao.executar(() =>
      gravarFiltroDoOutorgado(projetoId, {
        ncms,
        termos,
        sem_filtro: semFiltro,
        guardar_descartados: guardar,
      }),
    );
    if (novo) aoGravar(novo);
  }

  return (
    <Cartao className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-[280px] flex-1">
          <h2 className="m-0 text-base font-extrabold text-texto">O filtro deste trabalho</h2>
          <p className="m-0 mt-1 max-w-[760px] text-[13px] leading-relaxed text-texto-suave">
            Quais produtos têm o benefício aqui. A lista é deste trabalho — ela muda com o estado,
            com o período e com o que a empresa vende.
          </p>
        </div>
        {podeEscrever && (
          <Botao
            onClick={salvar}
            disabled={!mudou}
            carregando={gravacao.carregando}
            variante={mudou ? "principal" : "secundario"}
          >
            {mudou ? "Salvar o filtro" : "Filtro salvo"}
          </Botao>
        )}
      </div>

      {gravacao.erro && (
        <Aviso titulo={gravacao.erro.message} codigo={gravacao.erro.requisicaoId} aoFechar={() => gravacao.setErro(null)} />
      )}

      <ListaDeTermos
        rotulo="Termos de descrição"
        ajuda="Quem decide. Casa por pedaço e não diferencia maiúscula de minúscula — mas o acento conta: quem escreve PAO não acha PÃO."
        exemplo="PÃO, FARINHA DE TRIGO, LEITE"
        valores={termos}
        aoMudar={setTermos}
        somenteLeitura={!podeEscrever}
      />

      <ListaDeTermos
        rotulo="NCM (confirmação)"
        ajuda="Não elege sozinha: serve para marcar, entre os itens que a descrição pegou, quais também batem na classificação. Casa por prefixo — 190590 pega 19059090."
        exemplo="190590, 1101"
        valores={ncms}
        aoMudar={setNcms}
        somenteLeitura={!podeEscrever}
        mono
      />

      <div className="flex flex-wrap gap-2.5">
        <Chip marcado={semFiltro} aoAlternar={() => podeEscrever && setSemFiltro(!semFiltro)}>
          Rodar sem filtro
        </Chip>
        <Chip marcado={guardar} aoAlternar={() => podeEscrever && setGuardar(!guardar)}>
          Guardar os descartados
        </Chip>
      </div>

      {semFiltro && (
        <p className="m-0 rounded-raio-g border border-atencao/35 bg-atencao-fundo px-3.5 py-2.5 text-[12px] leading-relaxed text-texto-suave">
          <strong className="font-bold text-atencao">Sem filtro</strong> lista todos os itens de
          todas as notas, marcados <code className="font-mono">SEM FILTRO</code>. Serve para ver o
          universo antes de escrever o primeiro termo — não é apuração de benefício.
        </p>
      )}

      {!semFiltro && termos.length === 0 && (
        <p className="m-0 rounded-raio-g border border-atencao/35 bg-atencao-fundo px-3.5 py-2.5 text-[12px] leading-relaxed text-texto-suave">
          Sem nenhum termo, nada seria elegível — e a varredura não roda. Cadastre ao menos um.
        </p>
      )}

      {guardar && (
        <p className="m-0 text-[12px] leading-relaxed text-texto-fraco">
          Os descartados são como se revisa o filtro: o produto que devia ter entrado e não entrou
          só aparece nessa lista. Numa base grande, eles são a maioria esmagadora das linhas.
        </p>
      )}
    </Cartao>
  );
}

/** Um campo que vira pílulas. Aceita vários de uma vez, separados por vírgula
 *  ou por quebra de linha — colar a coluna de uma planilha tem de funcionar. */
function ListaDeTermos({
  rotulo,
  ajuda,
  exemplo,
  valores,
  aoMudar,
  somenteLeitura,
  mono,
}: {
  rotulo: string;
  ajuda: string;
  exemplo: string;
  valores: string[];
  aoMudar: (v: string[]) => void;
  somenteLeitura: boolean;
  mono?: boolean;
}) {
  const [texto, setTexto] = useState("");

  function acrescentar() {
    const novos = texto
      .split(/[,;\n\t]/)
      .map((t) => t.trim())
      .filter(Boolean);
    if (novos.length === 0) return;
    const juntos = [...valores];
    for (const n of novos) if (!juntos.some((v) => v.toLowerCase() === n.toLowerCase())) juntos.push(n);
    aoMudar(juntos);
    setTexto("");
  }

  return (
    <div className="flex flex-col gap-2">
      <div>
        <Rotulo>{rotulo}</Rotulo>
        <p className="m-0 mt-1 max-w-[760px] text-[12px] leading-relaxed text-texto-fraco">{ajuda}</p>
      </div>

      {!somenteLeitura && (
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                acrescentar();
              }
            }}
            placeholder={`Ex.: ${exemplo}`}
            aria-label={rotulo}
            className={cn(
              "min-w-[260px] max-w-[460px] flex-1 rounded-raio-g border border-borda-forte bg-superficie-vidro px-3.5 py-2.5",
              "text-[13px] text-texto placeholder:text-texto-fraco transition-colors",
              "focus:border-laranja-500/55 focus:bg-laranja-500/6 focus:outline-none",
              mono && "font-mono",
            )}
          />
          <Botao variante="secundario" tamanho="sm" onClick={acrescentar} disabled={!texto.trim()}>
            Acrescentar
          </Botao>
        </div>
      )}

      {valores.length > 0 ? (
        <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
          {valores.map((v) => (
            <li key={v}>
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border border-borda-forte bg-superficie-vidro py-1 pl-3 pr-1.5",
                  "text-[12px] font-semibold text-texto",
                  mono && "font-mono",
                )}
              >
                {v}
                {!somenteLeitura && (
                  <button
                    type="button"
                    onClick={() => aoMudar(valores.filter((x) => x !== v))}
                    aria-label={`Tirar ${v}`}
                    className="flex h-5 w-5 items-center justify-center rounded-full text-texto-fraco transition-colors hover:bg-erro/12 hover:text-erro"
                  >
                    <IconeApagar size={11} strokeWidth={2.2} aria-hidden />
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="m-0 text-[12px] text-texto-fraco">Nenhum cadastrado.</p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function EmCurso({ e }: { e: ExecucaoDoOutorgado }) {
  const a = e.resumo?.andamento;
  return (
    <Cartao className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <h2 className="m-0 flex-1 text-base font-extrabold text-texto">{e.passo ?? "Varrendo"}</h2>
        <code className="font-mono text-[11px] text-texto-fraco">execução #{e.id}</code>
      </div>
      <BarraFina fracao={e.fracao} classe="bg-marca-laranja" />
      <p className="m-0 font-mono text-xs text-texto-fraco">
        {numero(e.arquivos_lidos ?? 0)} de {numero(e.arquivos_totais ?? 0)} XML
        {a ? ` · ${numero(a.elegiveis)} itens elegíveis` : ""}
      </p>
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

function Concluido({
  execucao,
  resumo,
  filtroDeHoje,
}: {
  execucao: ExecucaoDoOutorgado;
  resumo: ResumoDoOutorgado;
  filtroDeHoje: FiltroDoOutorgado | null;
}) {
  const [descartados, setDescartados] = useState(false);
  const [busca, setBusca] = useState("");
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<{
    linhas: ProdutoDoOutorgado[];
    total: number;
    itens: number;
    valor: string;
    por_pagina: number;
  } | null>(null);
  const [aberto, setAberto] = useState<ProdutoDoOutorgado | null>(null);
  const leitura = useAcao();
  const download = useAcao();
  const [baixando, setBaixando] = useState<{ qual: PlanilhaDoOutorgado; formato: Formato } | null>(null);

  useEffect(() => {
    setPagina(1);
  }, [descartados, busca]);

  useEffect(() => {
    let vivo = true;
    const t = window.setTimeout(async () => {
      const pagina_ = await leitura.executar((sinal) =>
        produtosDoOutorgado(execucao.id, { descartados, busca, pagina }, sinal),
      );
      if (vivo && pagina_) setDados(pagina_);
    }, busca ? 300 : 0);
    return () => {
      vivo = false;
      window.clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [execucao.id, descartados, busca, pagina]);

  async function baixar(qual: PlanilhaDoOutorgado, formato: Formato) {
    setBaixando({ qual, formato });
    await download.executar((sinal) => baixarPlanilhaDoOutorgado(execucao.id, qual, formato, sinal));
    setBaixando(null);
  }

  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  // o filtro de hoje pode não ser o que produziu esta lista
  const doResumo = resumo.filtro;
  const envelheceu =
    doResumo !== undefined &&
    filtroDeHoje !== null &&
    (!mesmaLista(doResumo.termos, filtroDeHoje.termos) ||
      !mesmaLista(doResumo.ncms, filtroDeHoje.ncms) ||
      doResumo.sem_filtro !== filtroDeHoje.sem_filtro);

  return (
    <div className="flex flex-col gap-4">
      <section className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-3">
        <Numero rotulo="Documentos lidos" valor={numero(resumo.documentos ?? 0)} />
        <Numero rotulo="Itens lidos" valor={numero(resumo.itens ?? 0)} />
        <Numero
          rotulo="Itens elegíveis"
          valor={numero(resumo.elegiveis ?? 0)}
          destaque
          nota={`${numero(resumo.descartados ?? 0)} descartados`}
        />
        <Numero
          rotulo="Valor elegível"
          valor={reaisDeCentavos(resumo.centavos_elegiveis)}
          destaque
          nota="soma dos itens que entraram"
        />
      </section>

      {envelheceu && (
        <Aviso tom="atencao" titulo="O filtro mudou depois desta varredura">
          Esta lista saiu com {doResumo.termos.length} termo(s) e {doResumo.ncms.length} NCM. O
          filtro do trabalho já é outro — rode de novo para a lista refletir o que está gravado.
        </Aviso>
      )}

      {resumo.nao_autorizados ? (
        <Faixa titulo={`${numero(resumo.nao_autorizados)} nota(s) com uso denegado ficaram de fora`}>
          O protocolo da SEFAZ não autorizou: a operação não existiu, e nada dela entra na conta.
        </Faixa>
      ) : null}

      <Cartao className="flex flex-col gap-3.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-[260px]">
            <h2 className="m-0 text-base font-extrabold text-texto">Os produtos capturados</h2>
            <p className="m-0 mt-1 max-w-[720px] text-[12px] leading-relaxed text-texto-suave">
              Um produto por linha, do maior valor para o menor. É aqui que se revisa o filtro —
              o que não devia estar nesta lista salta aos olhos.
            </p>
          </div>
          <BaixarPlanilha
            destaque
            rotulo="Baixar a lista"
            aoBaixar={(formato) => baixar(descartados ? "descartados" : "elegiveis", formato)}
            desabilitado={download.carregando}
            baixando={baixando?.qual === (descartados ? "descartados" : "elegiveis") ? baixando.formato : null}
            aoCancelar={download.podeCancelar ? download.cancelar : undefined}
          />
        </div>

        <Toolbar>
          <Segmentado
            opcoes={[
              { chave: "elegiveis", rotulo: "Elegíveis" },
              { chave: "descartados", rotulo: "Descartados" },
            ]}
            valor={descartados ? "descartados" : "elegiveis"}
            aoMudar={(v) => setDescartados(v === "descartados")}
            rotulo="Qual lista"
          />
          <Busca valor={busca} aoMudar={setBusca} placeholder="Buscar por descrição, código ou NCM" />
          {dados && (
            <span className="font-mono text-xs text-texto-fraco">
              {numero(dados.total)} produto(s) · {numero(dados.itens)} item(ns) · {reais(dados.valor)}
            </span>
          )}
        </Toolbar>

        {leitura.erro && (
          <Aviso
            tom={descartados ? "atencao" : "erro"}
            titulo={leitura.erro.message}
            codigo={leitura.erro.requisicaoId}
            aoFechar={() => leitura.setErro(null)}
          />
        )}

        {dados && dados.linhas.length === 0 && !leitura.carregando && (
          <Vazio titulo="Nenhum produto nesta lista">
            {busca
              ? "Nada casa com a busca. Tente outro pedaço da descrição."
              : "Confira a grafia dos termos — a comparação é por pedaço da descrição, mas não ignora acento."}
          </Vazio>
        )}

        {dados && dados.linhas.length > 0 && (
          <>
            <Tabela
              colunas={["Código", "Descrição", "NCM", "Por quê", "Itens", "Quantidade", "Valor", ""]}
            >
              {dados.linhas.map((l) => (
                <Linha key={`${l.codigo}|${l.descricao}|${l.ncm}`}>
                  <Celula mono>{l.codigo}</Celula>
                  <Celula>{l.descricao}</Celula>
                  <Celula mono>{l.ncm}</Celula>
                  <Celula>
                    <MotivoDoProduto motivo={l.motivo} />
                  </Celula>
                  <Celula mono className="text-right">{numero(l.itens)}</Celula>
                  <Celula mono className="text-right">
                    {Number(l.quantidade).toLocaleString("pt-BR", { maximumFractionDigits: 3 })}
                  </Celula>
                  <Celula mono className="text-right font-bold">{reais(l.valor)}</Celula>
                  <Celula>
                    <Botao variante="fantasma" tamanho="sm" onClick={() => setAberto(l)}>
                      Ver notas
                    </Botao>
                  </Celula>
                </Linha>
              ))}
            </Tabela>

            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-mono text-xs text-texto-fraco">
                página {numero(pagina)} de {numero(paginas)}
              </span>
              <div className="flex items-center gap-2">
                <Botao
                  variante="secundario"
                  tamanho="sm"
                  onClick={() => setPagina((n) => Math.max(1, n - 1))}
                  disabled={pagina <= 1 || leitura.carregando}
                >
                  Anterior
                </Botao>
                <Botao
                  variante="secundario"
                  tamanho="sm"
                  onClick={() => setPagina((n) => Math.min(paginas, n + 1))}
                  disabled={pagina >= paginas || leitura.carregando}
                >
                  Próxima
                </Botao>
              </div>
            </div>
          </>
        )}
      </Cartao>

      {resumo.log && resumo.log.length > 0 && <ListaDoLog log={resumo.log} />}

      <NotasDoProduto
        execucaoId={execucao.id}
        produto={aberto}
        descartados={descartados}
        aoFechar={() => setAberto(null)}
      />
    </div>
  );
}

function Numero({
  rotulo,
  valor,
  nota,
  destaque,
}: {
  rotulo: string;
  valor: string;
  nota?: string;
  destaque?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-cartao border border-borda bg-superficie-vidro px-4 py-3.5",
        destaque && "border-laranja-500/35 bg-laranja-500/8",
      )}
    >
      <p className="m-0 text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
        {rotulo}
      </p>
      <p className="m-0 mt-1 font-mono text-[20px] font-extrabold leading-none text-texto">{valor}</p>
      {nota && <p className="m-0 mt-1.5 text-[11px] text-texto-fraco">{nota}</p>}
    </div>
  );
}

/** O motivo, dito em duas palavras e explicado no `title`. */
function MotivoDoProduto({ motivo }: { motivo: string }) {
  if (!motivo) return <span className="text-texto-fraco">—</span>;
  const ajuda: Record<string, string> = {
    "DESCRIÇÃO": "A descrição casou com um termo cadastrado. A NCM deste item não está na lista — confira se deveria estar.",
    "NCM+DESCRIÇÃO": "A descrição casou e a NCM confirma: é o caso em que as duas pistas concordam.",
    "SEM FILTRO": "Rodada sem filtro: este item não foi julgado por critério nenhum.",
  };
  return (
    <span
      title={ajuda[motivo]}
      className={cn(
        "inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold",
        motivo === "NCM+DESCRIÇÃO"
          ? "bg-sucesso-fundo text-sucesso"
          : motivo === "SEM FILTRO"
            ? "bg-atencao-fundo text-atencao"
            : "bg-laranja-500/12 text-laranja-800 escuro:text-laranja-300",
      )}
    >
      {motivo}
    </span>
  );
}

/** As notas de um produto. Quem revisa quer ver de onde saiu o item antes de
 *  decidir se ele entra ou não. */
function NotasDoProduto({
  execucaoId,
  produto,
  descartados,
  aoFechar,
}: {
  execucaoId: number;
  produto: ProdutoDoOutorgado | null;
  descartados: boolean;
  aoFechar: () => void;
}) {
  const [linhas, setLinhas] = useState<ItemDoOutorgado[]>([]);
  const [total, setTotal] = useState(0);
  const leitura = useAcao();

  useEffect(() => {
    if (!produto) return;
    let vivo = true;
    leitura
      .executar((sinal) =>
        itensDoOutorgado(execucaoId, { descartados, codigo: produto.codigo }, sinal),
      )
      .then((p) => {
        if (vivo && p) {
          setLinhas(p.linhas);
          setTotal(p.total);
        }
      });
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [execucaoId, produto?.codigo, descartados]);

  return (
    <Modal
      aberto={produto !== null}
      aoFechar={aoFechar}
      titulo={produto ? produto.descricao : ""}
      sub={
        produto ? (
          <>
            Código <code className="font-mono">{produto.codigo}</code> · NCM{" "}
            <code className="font-mono">{produto.ncm}</code> · {numero(total)} item(ns)
          </>
        ) : undefined
      }
    >
      {leitura.erro && <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} />}
      {linhas.length === 0 && !leitura.carregando && !leitura.erro && (
        <p className="m-0 text-[13px] text-texto-fraco">Nada a mostrar.</p>
      )}
      {linhas.length > 0 && (
        <Tabela colunas={["Emissão", "Documento", "CFOP", "Quantidade", "Valor", "CST ICMS"]}>
          {linhas.map((l) => (
            <Linha key={`${l.chave}-${l.numero_item}`}>
              <Celula mono>{l.emissao ?? "—"}</Celula>
              <Celula mono nota={l.destinatario_nome || undefined}>
                {l.numero_documento}/{l.serie}
              </Celula>
              <Celula mono>{l.cfop}</Celula>
              <Celula mono className="text-right">
                {Number(l.quantidade).toLocaleString("pt-BR", { maximumFractionDigits: 3 })}
              </Celula>
              <Celula mono className="text-right font-bold">{reais(l.valor)}</Celula>
              <Celula mono>{l.cst_icms || "—"}</Celula>
            </Linha>
          ))}
        </Tabela>
      )}
      {total > linhas.length && (
        <p className="m-0 mt-3 text-[12px] text-texto-fraco">
          Mostrando as {numero(linhas.length)} primeiras de {numero(total)}. A lista inteira sai na
          planilha.
        </p>
      )}
    </Modal>
  );
}

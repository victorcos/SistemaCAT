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
import { numero } from "@/lib/format";
import { EM_CURSO, type Formato } from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import {
  baixarItensDoXml,
  camposDoXml,
  cancelarQuebraDeXml,
  detalharQuebraDeXml,
  iniciarQuebraDeXml,
  listarQuebrasDeXml,
  type CatalogoDoXml,
  type ExecucaoDaQuebraDeXml,
  type ResumoDaQuebraDeXml,
} from "@/services/quebraXml";
import type { ErroApi } from "@/types/erro";

/**
 * Quebra de XML — as notas do lote, item a item.
 *
 * A tela entrega **uma planilha sob medida**: são 57 colunas possíveis e quase
 * ninguém quer as 57. Quem confere ICMS não olha ISSQN; quem confere PIS/COFINS
 * não olha ST. Por isso o seletor de campos ocupa o lugar de destaque depois da
 * rodada, com atalhos para o caso comum e liberdade para o raro.
 *
 * **O catálogo vem do servidor.** A tela não inventa coluna: pede a lista do
 * que a planilha sabe produzir. Escrever a lista aqui daria duas verdades, e a
 * primeira coluna nova do outro lado ficaria invisível.
 */

const ESPERA_PARA_CANCELAR_MS = 400;

const ROTULO_DO_ATALHO: Record<string, string> = {
  icms: "ICMS",
  piscofins: "PIS/COFINS",
  descontos: "Descontos",
  tudo: "Tudo",
};

/**
 * Os atalhos que a barra mostra, na ordem, para o módulo do trabalho.
 *
 * O do outro tributo fica de fora: num trabalho de PIS/COFINS, um botão "ICMS"
 * ao lado do "PIS/COFINS" convida ao clique errado — e quem realmente quiser a
 * coluna de ICMS ali tem o bloco, um clique adiante.
 */
function atalhosDoModulo(modulo: string | undefined): string[] {
  const proprio = modulo === "piscofins" ? "piscofins" : "icms";
  return [proprio, "descontos", "tudo"];
}

export default function QuebraXml() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDaQuebraDeXml | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDaQuebraDeXml | null>(null);
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
      const e = await detalharQuebraDeXml(execucaoId);
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
    listarQuebrasDeXml(projetoId)
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
      const nova = await iniciarQuebraDeXml(projetoId);
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
      const e = await cancelarQuebraDeXml(atual.id);
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
        <Botao carregando>Lendo…</Botao>
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
        {resultado ? "Quebrar de novo" : "Quebrar os XML"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow={`${p?.modulo_rotulo ?? ""} · Quebra de XML`}
        titulo="Quebrar os XML"
        sub="Abre as notas do lote item a item — NF-e, NFC-e e CF-e SAT, soltas ou em zip — e monta a planilha com as colunas que você escolher. É o item que a EFD não traz na saída própria, e o CST que o C170 consolidado esconde."
        acao={
          <div className="flex flex-col items-end gap-2.5">
            {acao}
            {resultado && !rodando && (
              <p className="m-0 text-right text-[11px] leading-normal text-texto-fraco">
                Lido em {quando(resultado.terminada_em)}
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
        <Aviso titulo="A quebra dos XML falhou">
          <span className="block">{atual.erro}</span>
          <code className="mt-2 inline-block rounded-lg border border-dashed border-erro/40 bg-erro/5 px-2.5 py-1.5 font-mono text-xs">
            execução #{atual.id}
          </code>
        </Aviso>
      )}

      {rodando && atual && <EmCurso e={atual} />}

      {!rodando && !resultado && atual === null && (
        <Faixa titulo="Os XML deste trabalho ainda não foram abertos">
          Clique em <strong>Quebrar os XML</strong>. Zip do portal entra inteiro — as notas são
          lidas de dentro dele, sem descompactar em disco.
        </Faixa>
      )}

      {resultado && resumo && (
        <Concluido execucao={resultado} resumo={resumo} modulo={p?.modulo} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function EmCurso({ e }: { e: ExecucaoDaQuebraDeXml }) {
  const a = e.resumo?.andamento;
  return (
    <Cartao>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <Rotulo>{e.passo || "Lendo"}</Rotulo>
        <span className="font-mono text-[13px] text-texto-suave">
          {numero(a?.notas ?? e.documentos ?? 0)} notas · {numero(a?.itens ?? 0)} itens
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
  modulo,
}: {
  execucao: ExecucaoDaQuebraDeXml;
  resumo: ResumoDaQuebraDeXml;
  /** o tributo do trabalho: decide o que vem marcado e o que fica guardado */
  modulo: string | undefined;
}) {
  const [catalogo, setCatalogo] = useState<CatalogoDoXml | null>(null);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [baixando, setBaixando] = useState<Formato | null>(null);
  const download = useAcao();

  useEffect(() => {
    let vivo = true;
    camposDoXml()
      .then((c) => {
        if (!vivo) return;
        setCatalogo(c);
        // começa marcado no atalho **do tributo do trabalho**. Tudo marcado
        // assusta, nada marcado obriga a escolher 57 vezes antes do primeiro
        // download — e o atalho do outro tributo seria a escolha errada por
        // padrão, que é pior que as duas
        const doModulo = atalhosDoModulo(modulo)[0];
        setMarcados(new Set(c.atalhos[doModulo] ?? c.campos.map((x) => x.campo)));
      })
      .catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, []);

  const foraDaConta: [string, number][] = [
    ["cópias repetidas da mesma nota", resumo.repetidos ?? 0],
    ["arquivos que não são documento de mercadoria", resumo.nao_sao_documento ?? 0],
    ["arquivos que não deram para ler", resumo.ilegiveis ?? 0],
    ["notas sem item", resumo.sem_item ?? 0],
    ["notas com protocolo que não autoriza", resumo.nao_autorizados ?? 0],
  ];
  const descartes = foraDaConta.filter(([, q]) => q > 0);

  async function baixar(formato: Formato) {
    setBaixando(formato);
    await download.executar((sinal) =>
      baixarItensDoXml(execucao.id, formato, [...marcados], sinal),
    );
    setBaixando(null);
  }

  return (
    <>
      <section className="flex flex-wrap items-center gap-x-8 gap-y-4 rounded-cartao border border-borda bg-superficie p-6 shadow-cat">
        <Numero rotulo="Notas" valor={numero(resumo.notas ?? 0)} destaque />
        <Numero rotulo="Itens" valor={numero(resumo.itens ?? 0)} destaque />
        <Numero rotulo="Arquivos lidos" valor={numero(resumo.arquivos ?? 0)} />
        {resumo.segundos ? <Numero rotulo="Tempo" valor={duracao(resumo.segundos)} /> : null}
        {(resumo.cancelamentos ?? 0) > 0 && (
          <Numero rotulo="Cancelamentos no meio" valor={numero(resumo.cancelamentos ?? 0)} />
        )}
      </section>

      {descartes.length > 0 && (
        <section className="rounded-cartao border border-borda bg-superficie-vidro p-5">
          <Rotulo>O que não entrou</Rotulo>
          <ul className="m-0 mt-2.5 flex list-none flex-col gap-1.5 p-0">
            {descartes.map(([o_que, quantas]) => (
              <li key={o_que} className="flex items-baseline gap-3 text-[13px]">
                <span className="min-w-[70px] text-right font-mono font-bold text-texto">
                  {numero(quantas)}
                </span>
                <span className="text-texto-suave">{o_que}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {download.erro && <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} />}

      <SeletorDeCampos
        modulo={modulo}
        catalogo={catalogo}
        marcados={marcados}
        aoMudar={setMarcados}
        aoBaixar={baixar}
        baixando={baixando}
        aoCancelar={download.cancelar}
      />
    </>
  );
}

function Numero({
  rotulo,
  valor,
  destaque,
}: {
  rotulo: string;
  valor: string;
  destaque?: boolean;
}) {
  return (
    <div>
      <p className="m-0 text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
        {rotulo}
      </p>
      <p
        className={cn(
          "m-0 mt-0.5 font-mono font-extrabold leading-none text-texto",
          destaque ? "text-[26px]" : "text-[17px]",
        )}
      >
        {valor}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */

/**
 * O seletor: os blocos do tributo do trabalho, e o resto guardado.
 *
 * Num trabalho de PIS/COFINS, ICMS-ST e ISSQN não são escolha — são ruído: seis
 * blocos abertos com o mesmo peso fazem a pessoa procurar os dois que interessam.
 * Então os blocos do próprio tributo ficam à vista, e os outros atrás de um
 * clique, **sem sumir**: cruzar a nota com o ICMS destacado é trabalho legítimo,
 * e quem precisa dele não deveria ter de mudar de tela.
 */
function SeletorDeCampos({
  modulo,
  catalogo,
  marcados,
  aoMudar,
  aoBaixar,
  baixando,
  aoCancelar,
}: {
  modulo: string | undefined;
  catalogo: CatalogoDoXml | null;
  marcados: Set<string>;
  aoMudar: (c: Set<string>) => void;
  aoBaixar: (formato: Formato) => void;
  baixando: Formato | null;
  aoCancelar: () => void;
}) {
  const [mostrarOutros, setMostrarOutros] = useState(false);

  if (!catalogo) {
    return (
      <section className="rounded-cartao border border-borda bg-superficie p-6 text-[13px] text-texto-fraco">
        Lendo as colunas disponíveis…
      </section>
    );
  }

  const atalhos = atalhosDoModulo(modulo);
  const doTributo = new Set(
    (catalogo.atalhos[atalhos[0]] ?? []).map(
      (campo) => catalogo.campos.find((c) => c.campo === campo)?.bloco ?? "",
    ),
  );
  const principais = catalogo.blocos.filter((b) => doTributo.has(b));
  const outros = catalogo.blocos.filter((b) => !doTributo.has(b));
  const marcadosNosOutros = catalogo.campos.filter(
    (c) => !doTributo.has(c.bloco) && marcados.has(c.campo),
  ).length;

  const alternar = (campo: string) => {
    const agora = new Set(marcados);
    if (agora.has(campo)) agora.delete(campo);
    else agora.add(campo);
    aoMudar(agora);
  };

  const alternarBloco = (bloco: string, marcar: boolean) => {
    const agora = new Set(marcados);
    for (const c of catalogo.campos.filter((x) => x.bloco === bloco)) {
      if (marcar) agora.add(c.campo);
      else agora.delete(c.campo);
    }
    aoMudar(agora);
  };

  const Bloco = ({ bloco }: { bloco: string }) => {
    const doBloco = catalogo.campos.filter((c) => c.bloco === bloco);
    const todos = doBloco.every((c) => marcados.has(c.campo));
    const algum = doBloco.some((c) => marcados.has(c.campo));
    return (
      <div>
        <label className="flex cursor-pointer items-center gap-2.5 border-b border-borda-sutil pb-2">
          <input
            type="checkbox"
            aria-label={`Marcar o bloco ${bloco}`}
            checked={todos}
            ref={(el) => {
              // meio marcado: o bloco tem campo escolhido, mas não todos
              if (el) el.indeterminate = algum && !todos;
            }}
            onChange={(e) => alternarBloco(bloco, e.target.checked)}
          />
          <span className="text-[12px] font-extrabold uppercase tracking-[0.12em] text-texto">
            {bloco}
          </span>
          <span className="ml-auto font-mono text-[11px] text-texto-fraco">
            {doBloco.filter((c) => marcados.has(c.campo)).length}/{doBloco.length}
          </span>
        </label>

        <ul className="m-0 mt-2 flex list-none flex-col gap-1 p-0">
          {doBloco.map((c) => (
            <li key={c.campo}>
              <label className="flex cursor-pointer items-center gap-2.5 py-0.5 text-[13px] text-texto-suave">
                <input
                  type="checkbox"
                  aria-label={`Marcar ${c.titulo}`}
                  checked={marcados.has(c.campo)}
                  onChange={() => alternar(c.campo)}
                />
                {c.titulo}
              </label>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  return (
    <section className="overflow-hidden rounded-cartao border border-borda bg-superficie">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-borda px-6 py-4">
        <div className="min-w-[220px]">
          <Rotulo>Colunas da planilha</Rotulo>
          <p className="m-0 mt-0.5 text-[13px] text-texto-suave">
            <span className="font-mono font-bold text-texto">{numero(marcados.size)}</span> de{" "}
            {numero(catalogo.campos.length)} campos
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {atalhos
            .filter((chave) => catalogo.atalhos[chave])
            .map((chave) => (
              <Botao
                key={chave}
                variante="secundario"
                tamanho="sm"
                onClick={() => aoMudar(new Set(catalogo.atalhos[chave]))}
              >
                {ROTULO_DO_ATALHO[chave] ?? chave}
              </Botao>
            ))}
          <Botao variante="fantasma" tamanho="sm" onClick={() => aoMudar(new Set())}>
            Limpar
          </Botao>
        </div>

        <div className="ml-auto">
          <BaixarPlanilha
            aoBaixar={aoBaixar}
            desabilitado={marcados.size === 0}
            rotulo="Baixar a planilha"
            destaque
            baixando={baixando}
            aoCancelar={aoCancelar}
          />
        </div>
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-x-8 gap-y-5 p-6">
        {principais.map((bloco) => (
          <Bloco key={bloco} bloco={bloco} />
        ))}
      </div>

      {outros.length > 0 && (
        <div className="border-t border-borda-sutil">
          <button
            type="button"
            aria-expanded={mostrarOutros}
            onClick={() => setMostrarOutros((x) => !x)}
            className="flex w-full cursor-pointer items-center gap-3 border-0 bg-transparent px-6 py-3.5 text-left hover:bg-tabela-linha-hover"
          >
            <span className="text-[13px] font-bold text-texto-suave">
              {mostrarOutros ? "Esconder" : "Mostrar"} os outros tributos
            </span>
            <span className="text-[12px] text-texto-fraco">{outros.join(" · ")}</span>
            {marcadosNosOutros > 0 && (
              <span className="rounded-full bg-laranja-500/14 px-2 py-0.5 font-mono text-[11px] font-bold text-marca-laranja">
                {numero(marcadosNosOutros)} marcados
              </span>
            )}
          </button>

          {mostrarOutros && (
            <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-x-8 gap-y-5 border-t border-borda-sutil bg-superficie-vidro p-6">
              {outros.map((bloco) => (
                <Bloco key={bloco} bloco={bloco} />
              ))}
            </div>
          )}
        </div>
      )}

      <p className="m-0 border-t border-borda bg-superficie-vidro px-6 py-3 text-[11px] leading-relaxed text-texto-fraco">
        A ordem das colunas é sempre a mesma, independente da ordem em que você marcar — duas
        planilhas do mesmo trabalho se comparam lado a lado.
      </p>
    </section>
  );
}

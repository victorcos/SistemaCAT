import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import {
  BarraFina,
  Cartao,
  ListaDoLog,
  Rotulo,
  duracao,
  mesAno,
  quando,
} from "@/components/shared/Rodada";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { CabecalhoDePagina, Metrica, Metricas, Voltar } from "@/components/ui/Pagina";
import { IconeParar, IconeTentarDeNovo } from "@/constants/icons";
import { INTERVALO_POLL_MS } from "@/constants/polling";
import { ROTAS } from "@/constants/routes";
import { aceitaProcessamento } from "@/constants/status";
import { useAcao } from "@/hooks/useAcao";
import { cn } from "@/lib/cn";
import { comoErro } from "@/lib/errors";
import { numero } from "@/lib/format";
import { EM_CURSO, type Formato } from "@/services/conferencia";
import {
  baixarPlanilhaDaGestao,
  cancelarGestao,
  detalharGestao,
  iniciarGestao,
  listarGestoes,
  type ExecucaoDaGestao,
  type ResumoDaGestao,
} from "@/services/gestao";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/**
 * Apuração das contribuições — a Gestão Fiscal no padrão do MA.
 *
 * A tela entrega **uma planilha**, com os quatro tributos em abas: PIS e COFINS
 * da EFD-Contribuições, IRPJ e CSLL da ECF. O resto dela serve para responder
 * duas perguntas antes de alguém abrir o número:
 *
 * 1. **as duas fontes entraram?** Um trabalho sem ECF tem PIS e COFINS e mais
 *    nada, e isso não pode ser descoberto depois, na planilha;
 * 2. **quanto vale o que saiu?** PIS e COFINS foram conferidos contra o export
 *    real do MA em 59 competências. IRPJ e CSLL **nunca passaram por gabarito**
 *    — e a tela diz isso em cima do card, não num rodapé.
 */

const ESPERA_PARA_CANCELAR_MS = 400;

/** O que cada tributo é, e de onde veio. */
const TRIBUTOS: Record<string, { fonte: string; conferido: boolean }> = {
  PIS: { fonte: "EFD-Contribuições", conferido: true },
  COFINS: { fonte: "EFD-Contribuições", conferido: true },
  IRPJ: { fonte: "ECF", conferido: false },
  CSLL: { fonte: "ECF", conferido: false },
};

export default function Gestao() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDaGestao | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDaGestao | null>(null);
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
      const e = await detalharGestao(execucaoId);
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
      acompanhar(execucaoId);
      relogio.current = window.setInterval(() => acompanhar(execucaoId), INTERVALO_POLL_MS);
    },
    [acompanhar],
  );

  useEffect(() => {
    if (!projetoId) return;
    detalharProjeto(projetoId).then(setProjeto).catch((x) => setErro(comoErro(x)));
    listarGestoes(projetoId)
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
      const nova = await iniciarGestao(projetoId);
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
      const e = await cancelarGestao(atual.id);
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
        {resultado ? "Apurar de novo" : "Apurar as contribuições"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="PIS/COFINS · Etapa 2"
        titulo="Apurar as contribuições"
        sub="Monta a Gestão Fiscal no padrão do MA: da EFD-Contribuições saem PIS e COFINS, nos 36 quadros; da ECF saem IRPJ e CSLL do Lucro Real. Cada quadro é uma lista de linhas, e cada linha um valor por competência."
        acao={
          <div className="flex flex-col items-end gap-2.5">
            {acao}
            {resultado && !rodando && (
              <p className="m-0 text-right text-[11px] leading-normal text-texto-fraco">
                última em {quando(resultado.terminada_em)}
                {resumo?.segundos ? ` · ${duracao(resumo.segundos)}` : ""}
              </p>
            )}
          </div>
        }
      >
        {p && (
          <div className="flex flex-wrap items-center gap-2.5">
            <strong className="text-sm text-texto">{p.empresa}</strong>
            {p.cnpj_matriz_formatado && (
              <code className="font-mono text-xs text-texto-fraco">{p.cnpj_matriz_formatado}</code>
            )}
          </div>
        )}
      </CabecalhoDePagina>

      <TrabalhoParado status={p?.status} projetoId={projetoId} />
      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}
      {atual?.situacao === "falhou" && atual.erro && (
        <Aviso titulo="A apuração falhou" codigo={String(atual.id)}>
          {atual.erro}
        </Aviso>
      )}

      {rodando && atual && <EmCurso e={atual} />}
      {resultado && resumo && !rodando && <Concluida execucao={resultado} resumo={resumo} />}

      {resumo?.log && resumo.log.length > 0 && !rodando && (
        <Cartao className="flex flex-col gap-3">
          <Rotulo>O que aconteceu na rodada</Rotulo>
          <ListaDoLog log={resumo.log ?? []} />
        </Cartao>
      )}
    </div>
  );
}

function EmCurso({ e }: { e: ExecucaoDaGestao }) {
  const a = e.resumo?.andamento;
  return (
    <Cartao className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="m-0 flex-1 text-base font-extrabold text-texto">{e.passo ?? "Apurando"}</h2>
        <code className="font-mono text-[11px] text-texto-fraco">execução #{e.id}</code>
      </div>
      <BarraFina fracao={e.fracao} classe="bg-marca-laranja" />
      <p className="m-0 font-mono text-xs text-texto-fraco">
        {numero(e.arquivos_lidos ?? 0)} de {numero(e.arquivos_totais ?? 0)} arquivos
        {a ? ` · ${numero(a.linhas)} linhas de quadro` : ""}
      </p>
    </Cartao>
  );
}

function Concluida({
  execucao,
  resumo,
}: {
  execucao: ExecucaoDaGestao;
  resumo: ResumoDaGestao;
}) {
  const download = useAcao();
  const [baixando, setBaixando] = useState<Formato | null>(null);

  async function baixar(formato: Formato) {
    setBaixando(formato);
    await download.executar((sinal) => baixarPlanilhaDaGestao(execucao.id, formato, sinal));
    setBaixando(null);
  }

  const tributos = resumo.tributos ?? [];
  const competencias = resumo.competencias ?? [];
  const semGabarito = tributos.filter((t) => TRIBUTOS[t]?.conferido === false);

  return (
    <div className="flex flex-col gap-5">
      {download.erro && (
        <Aviso
          titulo={download.erro.message}
          codigo={download.erro.requisicaoId}
          aoFechar={() => download.setErro(null)}
        />
      )}

      {/* a planilha é a entrega da etapa: vem primeiro e em destaque */}
      <Cartao className="flex flex-col gap-3">
        <Rotulo>Gestão Fiscal</Rotulo>
        <p className="m-0 font-mono text-[32px] leading-none text-texto">
          {numero(resumo.quadros ?? 0)}
        </p>
        <p className="m-0 max-w-[70ch] text-xs leading-relaxed text-texto-fraco">
          Quadros montados, em {numero(competencias.length)}{" "}
          {competencias.length === 1 ? "competência" : "competências"}. A planilha sai com um
          tributo por aba e uma coluna por mês — o mesmo formato do export do MA, que é o que se
          compara linha a linha.
        </p>
        <BaixarPlanilha
          destaque
          aoBaixar={baixar}
          desabilitado={download.carregando || (resumo.quadros ?? 0) === 0}
          baixando={baixando}
          aoCancelar={download.podeCancelar ? download.cancelar : undefined}
          rotulo="Baixar a Gestão"
        />
      </Cartao>

      {/* o que entrou de cada fonte: descobrir que faltava a ECF só ao abrir a
          planilha é tarde demais */}
      <section className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-4">
        <Cartao className="flex flex-col gap-2">
          <Rotulo>EFD-Contribuições</Rotulo>
          <p className="m-0 font-mono text-[26px] leading-none text-texto">
            {numero(resumo.contribuicoes ?? 0)}
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            {(resumo.contribuicoes ?? 0) > 0
              ? "Arquivos lidos. Daqui saem PIS e COFINS, nos 36 quadros."
              : "Nenhuma no lote — sem ela não há PIS nem COFINS."}
          </p>
        </Cartao>
        <Cartao className="flex flex-col gap-2">
          <Rotulo>ECF</Rotulo>
          <p className="m-0 font-mono text-[26px] leading-none text-texto">
            {numero(resumo.ecf ?? 0)}
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            {(resumo.ecf ?? 0) > 0
              ? "Arquivos lidos. Daqui saem IRPJ e CSLL do Lucro Real."
              : "Nenhuma no lote — sem ela não há IRPJ nem CSLL."}
          </p>
        </Cartao>
      </section>

      {semGabarito.length > 0 && (
        <Aviso tom="atencao" titulo={`${semGabarito.join(" e ")} ainda sem gabarito`}>
          As regras de {semGabarito.join(" e ")} foram portadas mas <strong>nunca foram
          conferidas contra o export real do MA</strong> — o arquivo de referência é de outra
          empresa. PIS e COFINS foram, em 59 competências. Confira antes de entregar:{" "}
          <code className="font-mono text-[11px]">tools/validar_gestao.py</code>.
        </Aviso>
      )}

      <Metricas>
        <Metrica rotulo="Tributos" valor={numero(tributos.length)} nota={tributos.join(" · ") || "nenhum"} />
        <Metrica rotulo="Linhas de quadro" valor={numero(resumo.linhas ?? 0)} />
        <Metrica
          rotulo="Competências"
          valor={numero(competencias.length)}
          nota={
            competencias.length
              ? `${mesAno(competencias[0])} a ${mesAno(competencias[competencias.length - 1])}`
              : ""
          }
        />
        <Metrica
          rotulo="Não deram para ler"
          valor={numero(resumo.ilegiveis ?? 0)}
          nota={resumo.ilegiveis ? "veja o log da rodada" : "nenhum"}
          tom={(resumo.ilegiveis ?? 0) > 0 ? "atencao" : "neutro"}
        />
      </Metricas>

      {tributos.length > 0 && (
        <Cartao className="flex flex-col gap-3">
          <Rotulo>De onde veio cada tributo</Rotulo>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {tributos.map((t) => (
              <li key={t} className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="min-w-[72px] font-extrabold text-texto">{t}</span>
                <span className="text-texto-fraco">{TRIBUTOS[t]?.fonte ?? "—"}</span>
                <span
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-[10px] font-bold",
                    TRIBUTOS[t]?.conferido
                      ? "border-sucesso/35 bg-sucesso-fundo text-sucesso"
                      : "border-atencao/35 bg-atencao-fundo text-atencao",
                  )}
                >
                  {TRIBUTOS[t]?.conferido ? "conferido contra o MA" : "sem gabarito"}
                </span>
              </li>
            ))}
          </ul>
        </Cartao>
      )}
    </div>
  );
}

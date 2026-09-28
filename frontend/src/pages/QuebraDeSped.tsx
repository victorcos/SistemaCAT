import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import { ExtrairDoSped } from "@/components/shared/ExtrairDoSped";
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
import { numero } from "@/lib/format";
import { EM_CURSO, type Formato } from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import {
  baixarPlanilhaDaQuebra,
  cancelarQuebra,
  detalharQuebra,
  iniciarQuebra,
  listarQuebras,
  type ExecucaoDaQuebra,
  type PlanilhaDaQuebra,
  type ResumoDaQuebra,
} from "@/services/quebraDeSped";
import type { ErroApi } from "@/types/erro";

/**
 * Quebrar os SPED — abrir os arquivos e dizer o que há dentro.
 *
 * Duas planilhas: **o que foi lido** (um arquivo por linha, com empresa,
 * período e tamanho) e **o que há dentro** (quantos de cada registro em cada
 * arquivo). O índice fica em disco, e é dele que sai a extração de um registro
 * qualquer — sem reler o arquivo.
 *
 * A Consulta de Entradas e o razão contábil saíram daqui em 23/09/2026 e viraram
 * a apuração de PIS/COFINS. Não eram quebra: eram o confronto entre o fiscal e
 * o contábil.
 */

const ESPERA_PARA_CANCELAR_MS = 400;

const tamanho = (bytes: number | undefined) => {
  const b = bytes ?? 0;
  if (b >= 1 << 30) return `${(b / (1 << 30)).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} GB`;
  if (b >= 1 << 20) return `${(b / (1 << 20)).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`;
  return `${Math.ceil(b / 1024).toLocaleString("pt-BR")} KB`;
};

const cnpjFormatado = (c: string) =>
  c.length === 14
    ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}`
    : c;

export default function QuebraDeSped() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDaQuebra | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDaQuebra | null>(null);
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
      const e = await detalharQuebra(execucaoId);
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
    listarQuebras(projetoId)
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
      const nova = await iniciarQuebra(projetoId);
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
      const e = await cancelarQuebra(atual.id);
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
        <Botao carregando>Quebrando…</Botao>
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
        {resultado ? "Quebrar de novo" : "Quebrar os SPED"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="PIS/COFINS · Etapa 1"
        titulo="Quebrar os SPED"
        sub="Abre os SPED do lote: quantos de cada registro cada arquivo tem, e o índice com a posição de cada um — que é o que permite extrair qualquer registro depois sem reler o arquivo."
        acao={
          <div className="flex flex-col items-end gap-2.5">
            {acao}
            {resultado && !rodando && (
              <p className="m-0 text-right text-[11px] leading-normal text-texto-fraco">
                Quebrado em {quando(resultado.terminada_em)}
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
        <Aviso titulo="A quebra falhou">
          <span className="block">{atual.erro}</span>
          <code className="mt-2 inline-block rounded-lg border border-dashed border-erro/40 bg-erro/5 px-2.5 py-1.5 font-mono text-xs">
            execução #{atual.id}
          </code>
        </Aviso>
      )}

      {atual?.situacao === "cancelada" && (
        <Faixa titulo="A última rodada foi cancelada">
          Parou a pedido. O que ficou pela metade não vale.
          {resultado ? " Abaixo, a última quebra que concluiu." : " Rode de novo quando quiser."}
        </Faixa>
      )}

      {rodando && atual && <EmCurso e={atual} />}

      {!rodando && !atual && (
        <Faixa titulo="Nada quebrado ainda">
          Importe a pasta com a EFD-Contribuições e a ECD que o cliente transmitiu à Receita e rode
          a quebra. Nenhuma outra etapa precisa vir antes.
        </Faixa>
      )}

      {!rodando && resultado && resumo && <Concluido execucao={resultado} resumo={resumo} />}
    </div>
  );
}

function EmCurso({ e }: { e: ExecucaoDaQuebra }) {
  const a = e.resumo?.andamento;
  return (
    <Cartao className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <h2 className="m-0 flex-1 text-base font-extrabold text-texto">{e.passo ?? "Quebrando"}</h2>
        <code className="font-mono text-[11px] text-texto-fraco">execução #{e.id}</code>
      </div>
      <BarraFina fracao={e.fracao} classe="bg-marca-laranja" />
      <p className="m-0 font-mono text-xs text-texto-fraco">
        {numero(e.arquivos_lidos ?? 0)} de {numero(e.arquivos_totais ?? 0)} arquivos
        {a ? ` · ${numero(a.registros)} registros indexados` : ""}
      </p>
    </Cartao>
  );
}

function Concluido({ execucao, resumo }: { execucao: ExecucaoDaQuebra; resumo: ResumoDaQuebra }) {
  const download = useAcao();
  const [baixando, setBaixando] = useState<{ qual: PlanilhaDaQuebra; formato: Formato } | null>(null);

  async function baixar(qual: PlanilhaDaQuebra, formato: Formato) {
    setBaixando({ qual, formato });
    await download.executar((sinal) => baixarPlanilhaDaQuebra(execucao.id, qual, formato, sinal));
    setBaixando(null);
  }

  const par = (qual: PlanilhaDaQuebra, rotulo: string, destaque?: boolean, vazio?: boolean) => (
    <BaixarPlanilha
      destaque={destaque}
      aoBaixar={(formato) => baixar(qual, formato)}
      desabilitado={download.carregando || (vazio ?? false)}
      baixando={baixando?.qual === qual ? baixando.formato : null}
      aoCancelar={download.podeCancelar ? download.cancelar : undefined}
      rotulo={rotulo}
    />
  );

  const competencias = resumo.competencias ?? [];

  return (
    <div className="flex flex-col gap-5">
      {download.erro && (
        <Aviso
          titulo={download.erro.message}
          codigo={download.erro.requisicaoId}
          aoFechar={() => download.setErro(null)}
        />
      )}

      {/* o que a quebra entrega: o inventário do que foi lido */}
      <section className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-4">
        <Cartao className="flex flex-col gap-3">
          <Rotulo>Arquivos abertos</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-texto">
            {numero(resumo.arquivos ?? 0)}
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Um por linha, com empresa, período, tamanho e o que rendeu. É por aqui que se
            confere se a base está inteira antes de olhar qualquer número.
          </p>
          {par("arquivos", "Baixar o que foi lido", true, (resumo.arquivos ?? 0) === 0)}
        </Cartao>

        <Cartao className="flex flex-col gap-3">
          <Rotulo>Registros distintos</Rotulo>
          <p className="m-0 font-mono text-[32px] leading-none text-texto">
            {numero(resumo.registros ?? 0)}
          </p>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Quantos de cada registro cada arquivo tem — C100, C170, M200, I250. O índice com a
            posição de cada um fica em disco, para extrair qualquer bloco depois.
          </p>
          {par("contagens", "Baixar as contagens", true, (resumo.arquivos ?? 0) === 0)}
        </Cartao>
      </section>

      <section className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-3">
        <Metrica rotulo="Arquivos lidos" valor={numero(resumo.arquivos ?? 0)}
                 nota={`${numero(resumo.contribuicoes ?? 0)} EFD-Contribuições · ${numero(resumo.ecd ?? 0)} ECD`} />
        <Metrica rotulo="Linhas lidas" valor={numero(resumo.linhas ?? 0)} nota={tamanho(resumo.bytes)} />
        <Metrica rotulo="Estabelecimentos" valor={numero((resumo.estabelecimentos ?? []).length)}
                 nota={(resumo.estabelecimentos ?? []).slice(0, 2).map(cnpjFormatado).join(" · ")} />
        <Metrica
          rotulo="Competências"
          valor={numero(competencias.length)}
          nota={competencias.length
            ? `${mesAno(competencias[0])} a ${mesAno(competencias[competencias.length - 1])}`
            : ""}
        />
        <Metrica
          rotulo="Não deram para ler"
          valor={numero(resumo.ilegiveis ?? 0)}
          nota={resumo.ilegiveis ? "veja os avisos abaixo" : "nenhum"}
          atencao={(resumo.ilegiveis ?? 0) > 0}
        />
      </section>

      {/* A extração vem antes do que foi lido: ler os arquivos é o meio, e
          extrair o registro é o fim. Enterrá-la depois da tabela de 58 linhas
          obrigava a rolar a tela inteira para chegar ao que se veio fazer. */}
      <ExtrairDoSped execucaoId={execucao.id} />

      {(resumo.avisos ?? []).length > 0 && (
        <section className="rounded-cartao border border-atencao/25 border-l-[3px] border-l-atencao bg-atencao-fundo px-5 py-4.5">
          <p className="m-0 text-sm font-extrabold text-atencao">Arquivos que não deram para quebrar</p>
          <ul className="m-0 mt-2.5 flex list-none flex-col gap-1.5 p-0">
            {(resumo.avisos ?? []).map((aviso) => (
              <li key={aviso} className="text-[13px] leading-relaxed text-texto">
                {aviso}
              </li>
            ))}
          </ul>
        </section>
      )}

      <Cartao className="flex flex-wrap items-center gap-3.5">
        <div className="min-w-[240px] flex-1">
          <p className="m-0 text-sm font-extrabold text-texto">O que foi lido</p>
          <p className="m-0 mt-1 text-xs leading-relaxed text-texto-suave">
            Um arquivo por linha, com o que cada um rendeu, e a contagem de cada tipo de registro.
            Serve para conferir a base antes de olhar o número.
          </p>
        </div>
        {par("arquivos", "Baixar os arquivos")}
        {par("contagens", "Baixar as contagens")}
      </Cartao>

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

function Metrica({
  rotulo,
  valor,
  nota,
  atencao,
}: {
  rotulo: string;
  valor: string;
  nota?: string;
  atencao?: boolean;
}) {
  return (
    <div className="rounded-cartao border border-borda bg-superficie-vidro px-4 py-3.5">
      <Rotulo>{rotulo}</Rotulo>
      <p className={cn("m-0 mt-1.5 font-mono text-2xl leading-none",
                       atencao ? "text-atencao" : "text-texto")}>
        {valor}
      </p>
      {nota && <p className="m-0 mt-1.5 text-[11px] leading-normal text-texto-fraco">{nota}</p>}
    </div>
  );
}

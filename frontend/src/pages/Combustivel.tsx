import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import {
  BarraFina,
  Cartao,
  ListaDoLog,
  Rotulo,
  duracao,
  quando,
  valor,
} from "@/components/shared/Rodada";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { CabecalhoDePagina, Metrica, Metricas, Voltar } from "@/components/ui/Pagina";
import { IconeParar, IconeTentarDeNovo } from "@/constants/icons";
import { INTERVALO_POLL_MS } from "@/constants/polling";
import { ROTAS } from "@/constants/routes";
import { aceitaProcessamento } from "@/constants/status";
import { comoErro } from "@/lib/errors";
import { dia, numero } from "@/lib/format";
import {
  cancelarCombustivel,
  detalharCombustivel,
  iniciarCombustivel,
  listarCombustiveis,
  rotuloDoMotivo,
  type ExecucaoDoCombustivel,
  type ResumoDoCombustivel,
} from "@/services/combustivel";
import { EM_CURSO } from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/**
 * Crédito de ICMS sobre combustível.
 *
 * A tela de uma etapa que **audita** além de apurar: além de dizer quanto o
 * cliente pode recuperar, ela mostra o que ficou de fora e por quê. Três
 * números governam a leitura, e nenhum deles pode sumir:
 *
 * * **o crédito**, que é o que entra no pedido;
 * * **quanto dele é estimativa** — a era da substituição tributária usa o valor
 *   do item como base, porque o arquivo do destinatário não traz a do ST;
 * * **o que foi recusado**, por motivo, com uma frase de exemplo de cada.
 *
 * O terceiro é o que distingue esta etapa. Competência sem ad rem conferida não
 * vira zero: vira linha fora do total, com o porquê — e alguns motivos se
 * resolvem cadastrando tabela, outros são crédito que o documento já deu.
 * Esconder isso num rodapé faria alguém somar o número errado.
 */

const ESPERA_PARA_CANCELAR_MS = 1500;

export default function Combustivel() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDoCombustivel | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDoCombustivel | null>(null);
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
      const e = await detalharCombustivel(execucaoId);
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
    listarCombustiveis(projetoId)
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
      const nova = await iniciarCombustivel(projetoId);
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
      const e = await cancelarCombustivel(atual.id);
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
        {resultado ? "Apurar de novo" : "Apurar o crédito"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="ICMS · Combustível"
        titulo="Crédito de combustível"
        sub="Quanto de ICMS a empresa pode recuperar do combustível que queimou como insumo, e quanto ela já recuperou por conta própria. Lê a EFD ICMS/IPI do lote: no regime monofásico a conta é litro × ad rem × fator de correção do volume; antes dele, base × alíquota interna do estado."
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
      {resultado && resumo && !rodando && <Concluida resumo={resumo} />}

      {resumo?.log && resumo.log.length > 0 && !rodando && (
        <Cartao className="flex flex-col gap-3">
          <Rotulo>O que aconteceu na rodada</Rotulo>
          <ListaDoLog log={resumo.log ?? []} />
        </Cartao>
      )}
    </div>
  );
}

function EmCurso({ e }: { e: ExecucaoDoCombustivel }) {
  const a = (e.resumo as { andamento?: { arquivos: number; linhas: number } } | null)?.andamento;
  return (
    <Cartao className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="m-0 flex-1 text-base font-extrabold text-texto">{e.passo ?? "Apurando"}</h2>
        <code className="font-mono text-[11px] text-texto-fraco">execução #{e.id}</code>
      </div>
      <BarraFina fracao={e.fracao} classe="bg-marca-laranja" />
      <p className="m-0 font-mono text-xs text-texto-fraco">
        {numero(e.arquivos_lidos ?? 0)} de {numero(e.arquivos_totais ?? 0)} arquivos
        {a ? ` · ${numero(a.linhas)} itens de compra` : ""}
      </p>
    </Cartao>
  );
}

/** Exportado para o teste: as três coisas que não podem sumir do resultado são
 *  marcação, não estado — e marcação só se cobra renderizando. */
export function Concluida({ resumo }: { resumo: ResumoDoCombustivel }) {
  const estimado = Number(resumo.credito_estimado ?? 0);
  const recusas = Object.entries(resumo.recusas_com_exemplo ?? {}).sort(
    (a, b) => b[1].linhas - a[1].linhas,
  );

  return (
    <div className="flex flex-col gap-5">
      <Cartao className="flex flex-col gap-4">
        <Rotulo>O que foi apurado</Rotulo>
        <Metricas>
          <Metrica rotulo="Crédito apurado" valor={`R$ ${valor(resumo.credito)}`} />
          <Metrica rotulo="Competências" valor={numero(resumo.competencias ?? 0)} />
          <Metrica rotulo="Estabelecimentos" valor={numero(resumo.estabelecimentos ?? 0)} />
          <Metrica rotulo="Itens de compra lidos" valor={numero(resumo.linhas ?? 0)} />
        </Metricas>

        {estimado > 0 && (
          <Aviso tom="atencao" titulo={`R$ ${valor(resumo.credito_estimado)} do total são estimativa`}>
            Na era da substituição tributária o arquivo do destinatário não traz a base do ST — ela
            foi retida lá atrás, e é justamente essa ausência que cria o direito ao crédito. A base
            usada aqui é o valor do item. A conferência é pelo XML, nos campos{" "}
            <code className="font-mono text-[11px]">vICMSSTRet</code> e{" "}
            <code className="font-mono text-[11px]">vBCSTRet</code>.
          </Aviso>
        )}

        {(resumo.primeira_emissao || resumo.ultima_emissao) && (
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Documentos emitidos entre <strong>{dia(resumo.primeira_emissao)}</strong> e{" "}
            <strong>{dia(resumo.ultima_emissao)}</strong>. O ICMS prescreve em cinco anos contados da
            emissão — esta etapa não corta nada por prazo, mostra o intervalo para você decidir.
          </p>
        )}
      </Cartao>

      {(resumo.a_revisar ?? 0) > 0 && (
        <Cartao className="flex flex-col gap-3">
          <Rotulo>O que pede olho humano</Rotulo>
          <p className="m-0 text-sm leading-relaxed text-texto">
            <strong>{numero(resumo.a_revisar ?? 0)}</strong> linha(s) o classificador marcou para
            revisão: item sem NCM, em que só a descrição decide, ou descrição que discorda da NCM.
            Ele nunca recusa — emite tudo com o motivo, e quem decide o que o produto é continua
            sendo gente.
          </p>
        </Cartao>
      )}

      {recusas.length > 0 && (
        <Cartao className="flex flex-col gap-3">
          <Rotulo>Fora do total, e por quê</Rotulo>
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            {numero(resumo.linhas_recusadas ?? 0)} linha(s) de combustível não entraram no crédito.
            Elas aparecem aqui, e não como zero: alguns motivos se resolvem cadastrando tabela,
            outros são crédito que o documento já deu.
          </p>
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {recusas.map(([motivo, r]) => (
              <li key={motivo} className="flex flex-col gap-1 border-l-2 border-borda pl-3">
                <div className="flex flex-wrap items-baseline gap-2">
                  <strong className="text-sm text-texto">{rotuloDoMotivo(motivo)}</strong>
                  <span className="font-mono text-xs text-texto-fraco">
                    {numero(r.linhas)} linha(s)
                  </span>
                </div>
                <p className="m-0 text-xs leading-relaxed text-texto-fraco">{r.exemplo}</p>
              </li>
            ))}
          </ul>
        </Cartao>
      )}

      <Cartao className="flex flex-col gap-3">
        <Rotulo>O que foi lido</Rotulo>
        <Metricas>
          <Metrica rotulo="Arquivos no lote" valor={numero(resumo.arquivos_no_lote ?? 0)} />
          <Metrica rotulo="Arquivos lidos" valor={numero(resumo.arquivos_lidos ?? 0)} />
          <Metrica
            rotulo="Repetidos, fora"
            valor={numero(resumo.ignorados_por_duplicidade ?? 0)}
          />
          <Metrica rotulo="Linhas de monofásico" valor={numero(resumo.linhas_de_monofasico ?? 0)} />
        </Metricas>
        {(resumo.ignorados_por_duplicidade ?? 0) > 0 && (
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            Um arquivo por estabelecimento e competência entra na conta, e a retificadora vence a
            original. Ver arquivos repetidos é o esperado quando o lote aponta a pasta-mãe: o mesmo
            mês costuma estar em mais de uma subpasta.
          </p>
        )}
      </Cartao>
    </div>
  );
}

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import {
  BarraFina,
  Cartao,
  ListaDoLog,
  Rotulo,
  duracao,
  mesAno,
  pct,
  quando,
  valor,
} from "@/components/shared/Rodada";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { CabecalhoDePagina, Metrica, Metricas, Voltar } from "@/components/ui/Pagina";
import { Celula, Linha, Tabela } from "@/components/ui/Tabela";
import { IconeBaixar, IconeParar, IconeTentarDeNovo } from "@/constants/icons";
import { INTERVALO_POLL_MS } from "@/constants/polling";
import { ROTAS } from "@/constants/routes";
import { aceitaProcessamento } from "@/constants/status";
import { useAcao } from "@/hooks/useAcao";
import { cn } from "@/lib/cn";
import { comoErro } from "@/lib/errors";
import { numero } from "@/lib/format";
import { EM_CURSO } from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import {
  baixarSimulacao,
  cancelarSimulacao,
  detalharSimulacao,
  iniciarSimulacao,
  listarSimulacoes,
  type AnoDaSimulacao,
  type ExecucaoDaSimulacao,
  type LinhaDaVisao,
  type ResumoDaSimulacao,
} from "@/services/simulacaoReforma";
import type { ErroApi } from "@/types/erro";

/**
 * Simulação da reforma tributária do consumo.
 *
 * A mesma tela nos módulos CBS e IBS: a conta põe ICMS, PIS/COFINS, CBS, IBS e
 * Imposto Seletivo lado a lado, de 2025 a 2033, e mede o que acontece com a
 * margem.
 *
 * **As premissas vêm antes dos números.** Pedido do revisor e do cliente: quem
 * olha uma margem de 4,8% em 2027 precisa ler primeiro que o preço e o volume
 * são constantes, e que as alíquotas do IS e a referência de 26,5% são
 * hipóteses. O resultado mede o tamanho do efeito; não é previsão de preço.
 *
 * **O que ficou fora da conta não some.** Pendência de cadastro — item sem
 * classificação — aparece com a receita que deixou de ser simulada, porque
 * deveria ser zero antes de apresentar. A exclusão (linha sem custo de compra)
 * é método, e aparece também, porque muda a leitura da margem.
 */

const ESPERA_PARA_CANCELAR_MS = 1500;
const DESTAQUE = ["2025", "2027", "2033"];

export default function SimulacaoReforma() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [atual, setAtual] = useState<ExecucaoDaSimulacao | null>(null);
  const [resultado, setResultado] = useState<ExecucaoDaSimulacao | null>(null);
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
      const e = await detalharSimulacao(execucaoId);
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
    listarSimulacoes(projetoId)
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
      const nova = await iniciarSimulacao(projetoId);
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
      const e = await cancelarSimulacao(atual.id);
      setAtual(e);
      if (!EM_CURSO.includes(e.situacao)) parar();
    } catch (x) {
      setErro(comoErro(x));
    }
  }

  const anda = !projeto || aceitaProcessamento(projeto.projeto.status);
  const resumo = resultado?.resumo ?? null;
  const p = projeto?.projeto;

  let acao: ReactNode;
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
        <Botao carregando>Simulando…</Botao>
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
        {resultado ? "Simular de novo" : "Simular a reforma"}
      </Botao>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="Reforma · CBS e IBS"
        titulo="Simulação da reforma tributária"
        sub="O que a transição de 2025 a 2033 faz com a margem: cada linha de venda projetada com ICMS, PIS/COFINS, CBS, IBS e Imposto Seletivo lado a lado. Lê do lote as saídas já custeadas e a classificação dos itens (NCM revisada e cClassTrib)."
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
        <Aviso titulo="A simulação falhou" codigo={String(atual.id)}>
          {atual.erro}
        </Aviso>
      )}

      {rodando && atual && <EmCurso e={atual} />}
      {resultado && resumo && !rodando && <Concluida execucaoId={resultado.id} resumo={resumo} />}

      {resumo?.log && resumo.log.length > 0 && !rodando && (
        <Cartao className="flex flex-col gap-3">
          <Rotulo>O que aconteceu na rodada</Rotulo>
          <ListaDoLog log={resumo.log ?? []} />
        </Cartao>
      )}
    </div>
  );
}

function EmCurso({ e }: { e: ExecucaoDaSimulacao }) {
  const a = e.resumo?.andamento;
  return (
    <Cartao className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="m-0 flex-1 text-base font-extrabold text-texto">{e.passo ?? "Simulando"}</h2>
        <code className="font-mono text-[11px] text-texto-fraco">execução #{e.id}</code>
      </div>
      <BarraFina fracao={e.fracao} classe="bg-marca-laranja" />
      <p className="m-0 font-mono text-xs text-texto-fraco">
        {numero(e.arquivos_lidos ?? 0)} de {numero(e.arquivos_totais ?? 0)} arquivos
        {a ? ` · ${numero(a.linhas)} linhas de venda lidas` : ""}
      </p>
    </Cartao>
  );
}

/* ------------------------------------------------------------------ */

const milhoes = (n: number | undefined) =>
  `R$ ${((n ?? 0) / 1e6).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} mi`;

const percentual = (f: number | null | undefined) => (f === null || f === undefined ? "—" : pct(f));

/** Margem negativa em vermelho: é o SKU que passa a dar prejuízo. */
const corDaMargem = (f: number | null | undefined) =>
  f !== null && f !== undefined && f < 0 ? "text-erro" : "";

/** Exportado para o teste: premissas antes dos números, e o que ficou fora da
 *  conta sempre à vista — marcação, e marcação só se cobra renderizando. */
export function Concluida({ execucaoId, resumo }: { execucaoId: number; resumo: ResumoDaSimulacao }) {
  const download = useAcao();
  const anos = resumo.por_ano ?? [];
  const base = resumo.base;
  const primeiro = anos[0];
  const ultimo = anos[anos.length - 1];
  const doAno = (a: number) => anos.find((x) => x.ano === a);
  const pendencias = resumo.pendencias ?? [];
  const exclusoes = resumo.exclusoes ?? [];
  const receitaPendente = pendencias.reduce((s, p) => s + p.receita_bruta, 0);

  return (
    <div className="flex flex-col gap-5">
      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} aoFechar={() => download.setErro(null)} />
      )}

      <Aviso tom="info" titulo="Simulação preliminar, sujeita à validação de premissas">
        Preço e volume constantes: a receita bruta do período-base vale para todos os anos, e a
        variação de imposto recai sobre a margem. Mede o tamanho do efeito — não é previsão de preço
        nem de venda. As alíquotas do Imposto Seletivo e a referência de 26,5% (CBS 8,8% + IBS
        17,7%) são hipóteses; o cronograma é o da LC 214/2025.
        {resumo.cenario && (
          <span className="mt-1 block text-xs text-texto-fraco">Cenário: {resumo.cenario.nome}</span>
        )}
      </Aviso>

      {pendencias.length > 0 && (
        <Aviso tom="atencao" titulo={`${milhoes(receitaPendente)} de receita ficaram fora por falta de cadastro`}>
          Item vendido sem classificação, ou com cClassTrib que o cenário não conhece, não entra com
          alíquota padrão chutada: fica fora da conta. Deveria ser zero antes de apresentar —
          classifique os itens abaixo e rode de novo.
        </Aviso>
      )}

      {base && base.competencias.length === 1 && (
        <Aviso tom="atencao" titulo={`Base de um mês só (${mesAno(base.competencias[0])})`}>
          A sazonalidade impede extrapolar um mês para o ano. Para a leitura anual, importe o
          ano-calendário inteiro: cada competência entra como uma visão própria.
        </Aviso>
      )}

      <Cartao className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex-1">
            <Rotulo>O que a transição faz com a margem</Rotulo>
          </div>
          <Botao
            variante="secundario"
            icone={IconeBaixar}
            carregando={download.carregando}
            onClick={() => download.executar((sinal) => baixarSimulacao(execucaoId, sinal))}
          >
            Baixar a planilha
          </Botao>
        </div>
        <Metricas>
          <Metrica rotulo="Receita bruta simulada" valor={milhoes(base?.receita_bruta)} />
          {primeiro && (
            <Metrica
              rotulo={`Lucro bruto ${primeiro.ano}`}
              valor={milhoes(primeiro.lucro_bruto)}
              nota={`margem ${percentual(primeiro.margem)}`}
            />
          )}
          {doAno(2027) && (
            <Metrica
              rotulo="Lucro bruto 2027"
              valor={milhoes(doAno(2027)!.lucro_bruto)}
              nota={`margem ${percentual(doAno(2027)!.margem)}`}
              tom={doAno(2027)!.lucro_bruto < (primeiro?.lucro_bruto ?? 0) ? "atencao" : "neutro"}
            />
          )}
          {ultimo && ultimo !== primeiro && (
            <Metrica
              rotulo={`Lucro bruto ${ultimo.ano}`}
              valor={milhoes(ultimo.lucro_bruto)}
              nota={`margem ${percentual(ultimo.margem)}`}
            />
          )}
        </Metricas>
        {base && (
          <p className="m-0 text-xs leading-relaxed text-texto-fraco">
            {numero(base.linhas_consideradas)} de {numero(base.linhas_lidas)} linhas de venda ·{" "}
            {numero(base.skus)} SKUs · {numero(base.lojas)} lojas · competência(s){" "}
            {base.competencias.map(mesAno).join(", ")}
          </p>
        )}
      </Cartao>

      <Cartao className="flex flex-col gap-3">
        <Rotulo>Trajetória, ano a ano (R$ do período-base)</Rotulo>
        <Trajetoria anos={anos} />
      </Cartao>

      <Visao titulo="Por grupo de alíquota (cClassTrib)" linhas={resumo.por_grupo} total={base?.receita_bruta} />
      <Visao titulo="Por UF" linhas={resumo.por_uf} total={base?.receita_bruta} />
      <Visao
        titulo="Imposto Seletivo, por categoria (hipótese)"
        linhas={resumo.por_seletivo}
        total={base?.receita_bruta}
        mostrarSeletivo
      />
      <Visao
        titulo="Os 15 maiores capítulos da NCM"
        linhas={resumo.por_capitulo}
        total={base?.receita_bruta}
        nota="A planilha traz todos os capítulos, as posições (4 dígitos), as famílias e cada SKU."
      />

      {(pendencias.length > 0 || exclusoes.length > 0) && (
        <Cartao className="flex flex-col gap-3">
          <Rotulo>Fora da conta, e por quê</Rotulo>
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {pendencias.map((p) => (
              <li key={p.motivo} className="flex flex-col gap-1 border-l-2 border-atencao pl-3">
                <div className="flex flex-wrap items-baseline gap-2">
                  <strong className="text-sm text-texto">{p.motivo}</strong>
                  <span className="font-mono text-xs text-texto-fraco">
                    {numero(p.skus)} SKU(s) · {numero(p.linhas)} linha(s) · R$ {valor(p.receita_bruta)} de receita bruta
                  </span>
                </div>
                {p.exemplos.length > 0 && (
                  <p className="m-0 font-mono text-[11px] leading-relaxed text-texto-fraco">
                    {p.exemplos.slice(0, 6).join(" · ")}
                  </p>
                )}
              </li>
            ))}
            {exclusoes.map((x) => (
              <li key={x.motivo} className="flex flex-col gap-1 border-l-2 border-borda pl-3">
                <div className="flex flex-wrap items-baseline gap-2">
                  <strong className="text-sm text-texto">Sem custo de compra: {x.motivo}</strong>
                  <span className="font-mono text-xs text-texto-fraco">
                    {numero(x.linhas)} linha(s) · R$ {valor(x.receita_liquida)} de receita líquida
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </Cartao>
      )}
    </div>
  );
}

/** As linhas da DRE resumida, com o ano nas colunas. */
const INDICADORES: { rotulo: string; v: (a: AnoDaSimulacao) => number | null; pct?: boolean; forte?: boolean }[] = [
  { rotulo: "Receita bruta", v: (a) => a.receita_bruta },
  { rotulo: "(−) ICMS", v: (a) => a.icms },
  { rotulo: "(−) PIS/COFINS", v: (a) => a.pis_cofins },
  { rotulo: "(−) CBS", v: (a) => a.cbs },
  { rotulo: "(−) IBS", v: (a) => a.ibs },
  { rotulo: "Receita líquida", v: (a) => a.receita_liquida, forte: true },
  { rotulo: "(−) CMV", v: (a) => a.cmv },
  { rotulo: "  dos quais Imposto Seletivo", v: (a) => a.seletivo },
  { rotulo: "Lucro bruto", v: (a) => a.lucro_bruto, forte: true },
  { rotulo: "Margem bruta", v: (a) => a.margem, pct: true, forte: true },
  { rotulo: "Créditos recuperáveis", v: (a) => a.creditos },
  { rotulo: "Tributo líquido a recolher", v: (a) => a.a_recolher },
  { rotulo: "Carga com IS", v: (a) => a.carga_com_seletivo, pct: true },
  { rotulo: "Variação teórica de preço", v: (a) => a.variacao_teorica, pct: true },
];

function Trajetoria({ anos }: { anos: AnoDaSimulacao[] }) {
  return (
    <>
      <Tabela colunas={["", ...anos.map((a) => String(a.ano))]}>
        {INDICADORES.map((ind) => (
          <Linha key={ind.rotulo}>
            <Celula className={cn("whitespace-pre", ind.forte && "font-extrabold")}>{ind.rotulo}</Celula>
            {anos.map((a) => {
              const v = ind.v(a);
              return (
                <Celula
                  key={a.ano}
                  mono
                  className={cn("whitespace-nowrap text-right", ind.forte && "font-extrabold", ind.pct && corDaMargem(v))}
                >
                  {ind.pct ? percentual(v) : milhoes(v ?? 0)}
                </Celula>
              );
            })}
          </Linha>
        ))}
      </Tabela>
      <p className="m-0 text-xs leading-relaxed text-texto-fraco">
        Variação teórica de preço: quanto a receita bruta teria de variar para preservar o lucro bruto
        em reais do ano-base. Não é recomendação de reajuste. O CMV é líquido dos créditos: eles estão
        no valor bruto das compras, e não se subtraem do custo.
      </p>
    </>
  );
}

function Visao({
  titulo,
  linhas,
  total,
  nota,
  mostrarSeletivo,
}: {
  titulo: string;
  linhas?: LinhaDaVisao[];
  total?: number;
  nota?: string;
  mostrarSeletivo?: boolean;
}) {
  if (!linhas || linhas.length === 0) return null;
  return (
    <Cartao className="flex flex-col gap-3">
      <Rotulo>{titulo}</Rotulo>
      <Tabela
        colunas={[
          "",
          "SKUs",
          "Receita bruta",
          "% da receita",
          ...(mostrarSeletivo ? ["IS pleno/mês"] : []),
          ...DESTAQUE.map((a) => `Margem ${a}`),
          "Var. teórica 2033",
        ]}
      >
        {linhas.map((l) => (
          <Linha key={l.chave || "vazio"}>
            <Celula nota={l.rotulo !== l.chave && l.chave ? l.chave : undefined}>{l.rotulo || l.chave}</Celula>
            <Celula mono className="text-right">{numero(l.skus)}</Celula>
            <Celula mono className="whitespace-nowrap text-right">{milhoes(l.receita_bruta)}</Celula>
            <Celula mono className="text-right">{total ? pct(l.receita_bruta / total) : "—"}</Celula>
            {mostrarSeletivo && (
              <Celula mono className="whitespace-nowrap text-right">{milhoes(l.seletivo_pleno)}</Celula>
            )}
            {DESTAQUE.map((a) => (
              <Celula key={a} mono className={cn("text-right", corDaMargem(l.anos[a]?.margem))}>
                {percentual(l.anos[a]?.margem)}
              </Celula>
            ))}
            <Celula mono className="text-right">{percentual(l.anos["2033"]?.variacao_teorica)}</Celula>
          </Linha>
        ))}
      </Tabela>
      {nota && <p className="m-0 text-xs leading-relaxed text-texto-fraco">{nota}</p>}
    </Cartao>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Andamento } from "@/components/ui/Andamento";
import { Aviso } from "@/components/ui/Aviso";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import { Botao } from "@/components/ui/Botao";
import { GrupoDeChips, Pilula } from "@/components/ui/Filtros";
import {
  Barra,
  CabecalhoDePagina,
  Metrica,
  Metricas,
  Numerao,
  Secao,
  Vazio,
  Voltar,
} from "@/components/ui/Pagina";
import { IconeTentarDeNovo } from "@/constants/icons";
import { ROTAS } from "@/constants/routes";
import { aceitaProcessamento } from "@/constants/status";
import { useAcao } from "@/hooks/useAcao";
import { comoErro } from "@/lib/errors";
import { dinheiro, numero } from "@/lib/format";
import { EM_CURSO, type Fatia, type Formato } from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import {
  baixarPlanilhaDeMovimentos,
  detalharMovimentos,
  iniciarMovimentos,
  listarMovimentos,
  type ExecucaoDeMovimentos,
  type PlanilhaDeMovimentos,
  type ResumoDaMovimentacao,
} from "@/services/movimentos";
import type { ErroApi } from "@/types/erro";
import { Filtro } from "./Conferencia";

const INTERVALO_MS = 2000;

/**
 * Etapa 3 — histórico de movimentação.
 *
 * Lê os itens de cada documento da EFD (C170), o analítico (C190/C850), o
 * cadastro (0200) e o inventário (bloco H), e marca cada movimento com o que
 * a conferência achou. A tela diz também o que a EFD não tem: NF-e própria e
 * cupom SAT vêm sem item, e esse detalhe virá do XML.
 */
export default function Movimentos() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [execucao, setExecucao] = useState<ExecucaoDeMovimentos | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState(false);
  // o download tem vida própria: carrega, erra e é cancelável por conta
  const download = useAcao();
  const [baixando, setBaixando] = useState<{
    qual: PlanilhaDeMovimentos;
    formato: Formato;
  } | null>(null);
  const [classes, setClasses] = useState<string[]>([]);
  const relogio = useRef<number | null>(null);

  const acompanhar = useCallback(async (execucaoId: number) => {
    try {
      const atual = await detalharMovimentos(execucaoId);
      setExecucao(atual);
      if (!EM_CURSO.includes(atual.situacao) && relogio.current !== null) {
        window.clearInterval(relogio.current);
        relogio.current = null;
      }
    } catch (e) {
      setErro(comoErro(e));
    }
  }, []);

  useEffect(() => {
    if (!projetoId) return;
    detalharProjeto(projetoId).then(setProjeto).catch((e) => setErro(comoErro(e)));
    listarMovimentos(projetoId)
      .then((lista) => {
        const ultima = lista[0] ?? null;
        setExecucao(ultima);
        if (ultima && EM_CURSO.includes(ultima.situacao)) {
          relogio.current = window.setInterval(() => acompanhar(ultima.id), INTERVALO_MS);
        }
      })
      .catch((e) => setErro(comoErro(e)));

    return () => {
      if (relogio.current !== null) window.clearInterval(relogio.current);
    };
  }, [projetoId, acompanhar]);

  async function comecar() {
    setOcupado(true);
    setErro(null);
    try {
      const nova = await iniciarMovimentos(projetoId);
      setExecucao(nova);
      setClasses([]);
      relogio.current = window.setInterval(() => acompanhar(nova.id), INTERVALO_MS);
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  async function baixar(qual: PlanilhaDeMovimentos, formato: Formato) {
    if (!execucao) return;
    setErro(null);
    setBaixando({ qual, formato });
    await download.executar((sinal) =>
      baixarPlanilhaDeMovimentos(
        execucao.id,
        qual,
        [],
        qual === "movimentos" ? classes : [],
        formato,
        sinal,
      ),
    );
    setBaixando(null);
  }

  const rodando = execucao !== null && EM_CURSO.includes(execucao.situacao);
  const resumo = execucao?.situacao === "concluida" ? execucao.resumo : null;
  const anda = !projeto || aceitaProcessamento(projeto.projeto.status);

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="Etapa 3"
        titulo="Extrair movimentos"
        sub={
          projeto ? (
            <>
              Lê os itens de cada documento da EFD de{" "}
              <strong className="text-texto">{projeto.projeto.empresa}</strong> (C170), o
              analítico, o cadastro de item e o inventário — e marca cada movimento com o que a
              conferência achou. É a matéria-prima do razão.
            </>
          ) : (
            "Carregando…"
          )
        }
        acao={
          <Botao
            icone={IconeTentarDeNovo}
            onClick={comecar}
            carregando={ocupado || rodando}
            disabled={!anda}
            className="shadow-acao"
          >
            {rodando ? "Extraindo…" : execucao ? "Extrair de novo" : "Extrair"}
          </Botao>
        }
      />

      <TrabalhoParado status={projeto?.projeto.status} projetoId={projetoId} />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} />}
      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} />
      )}

      {!execucao && (
        <Vazio titulo="Nenhuma extração ainda">
          Precisa de uma conferência concluída: é a lista de conferidos dela que marca cada
          movimento. Lê toda a EFD do trabalho — numa base grande leva minutos, e continua rodando
          se você sair desta tela.
        </Vazio>
      )}

      {rodando && execucao && <Andamento e={execucao} />}

      {execucao?.situacao === "falhou" && (
        <Aviso titulo="A extração falhou.">
          <span className="font-mono text-xs">{execucao.erro}</span>
        </Aviso>
      )}

      {resumo && (
        <Resultado
          resumo={resumo}
          execucao={execucao}
          classes={classes}
          aoAlternarClasse={(codigo) =>
            setClasses((atuais) =>
              atuais.includes(codigo) ? atuais.filter((c) => c !== codigo) : [...atuais, codigo],
            )
          }
          aoBaixar={baixar}
          ocupado={ocupado || download.carregando}
          baixando={baixando}
          aoCancelar={download.podeCancelar ? download.cancelar : undefined}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function Resultado({
  resumo,
  execucao,
  classes,
  aoAlternarClasse,
  aoBaixar,
  ocupado,
  baixando,
  aoCancelar,
}: {
  resumo: ResumoDaMovimentacao;
  execucao: ExecucaoDeMovimentos | null;
  classes: string[];
  aoAlternarClasse: (codigo: string) => void;
  aoBaixar: (qual: PlanilhaDeMovimentos, formato: Formato) => void;
  ocupado: boolean;
  baixando: { qual: PlanilhaDeMovimentos; formato: Formato } | null;
  aoCancelar?: () => void;
}) {
  const cobertura = Math.round(resumo.cobertura_de_item * 100);

  return (
    <>
      <Secao
        titulo="Resultado"
        sub={
          execucao?.terminada_em
            ? `Concluída em ${new Date(execucao.terminada_em).toLocaleString("pt-BR")}`
            : undefined
        }
      >
        <div className="mt-4">
          <Metricas>
            <Metrica rotulo="Documentos na EFD" valor={resumo.documentos} />
            <Metrica
              rotulo="Com item na EFD"
              valor={resumo.documentos_com_item}
              nota={`${cobertura}% dos documentos`}
              tom="sucesso"
            />
            <Metrica
              rotulo="Movimentos"
              valor={resumo.movimentos}
              nota={`${dinheiro(resumo.valor_entradas)} em entradas`}
              tom="info"
            />
            <Metrica
              rotulo="Saídas sem item na EFD"
              valor={resumo.saidas_sem_item}
              nota={
                resumo.saidas_completadas_pelo_xml
                  ? `${numero(resumo.saidas_completadas_pelo_xml)} completadas pelo XML`
                  : `${dinheiro(resumo.valor_saidas_sem_item_st)} com CST 60`
              }
              tom="atencao"
            />
          </Metricas>
        </div>

        {(resumo.xml_arquivos ?? 0) > 0 && (
          <Aviso tom="info" titulo="Itens do XML" className="mt-4">
            {numero(resumo.xml_documentos ?? 0)} documento(s) lidos de{" "}
            {numero(resumo.xml_arquivos ?? 0)} XML, com {numero(resumo.xml_itens ?? 0)} item(ns).
            O XML completou {numero(resumo.saidas_completadas_pelo_xml ?? 0)} saída(s) e{" "}
            {numero(resumo.entradas_completadas_pelo_xml ?? 0)} entrada(s) escrituradas sem item
            ({numero(resumo.movimentos_do_xml ?? 0)} movimentos), e ficou ao lado de{" "}
            {numero(resumo.itens_pareados_com_xml ?? 0)} item(ns) do C170, onde os valores dele
            vencem na apuração do suportado.
            {(resumo.xml_repetidos ?? 0) +
              (resumo.xml_nao_sao_documento ?? 0) +
              (resumo.xml_nao_autorizados ?? 0) >
              0 &&
              ` Fora da conta: ${numero(resumo.xml_repetidos ?? 0)} repetido(s)${
                resumo.xml_copias_trocadas
                  ? ` (em ${numero(resumo.xml_copias_trocadas)}, a cópia autorizada ficou no lugar da sem protocolo)`
                  : ""
              }, ${numero(resumo.xml_nao_sao_documento ?? 0)} que não são documento (evento, inutilização) e ${numero(
                resumo.xml_nao_autorizados ?? 0,
              )} de uso denegado.`}
          </Aviso>
        )}

        <Barra de={cobertura} para={100} tom="sucesso" className="mt-4" />

        <div className="mt-4 flex flex-col gap-2">
          {resumo.avisos.map((a) => (
            <Aviso key={a} tom="atencao">
              {a}
            </Aviso>
          ))}
          {resumo.recusados.length > 0 && (
            <Aviso tom="atencao" titulo="Arquivos com problema na leitura">
              O que está aqui não entrou:
              <ul className="m-0 mt-2 list-disc pl-5 text-[13px] leading-relaxed">
                {resumo.recusados.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </Aviso>
          )}
          {(resumo.observacoes ?? []).length > 0 && (
            <Aviso tom="info" titulo="Fora do confronto, e está certo assim">
              Linha que não é documento não tem o que conferir. Fica aqui para
              a conta fechar, não porque houve erro de leitura:
              <ul className="m-0 mt-2 list-disc pl-5 text-[13px] leading-relaxed">
                {(resumo.observacoes ?? []).map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ul>
            </Aviso>
          )}
        </div>
      </Secao>

      <Secao
        destaque
        titulo="Movimentos"
        sub="Cada item de documento com o cadastro (descrição, NCM, CEST) e a marca da conferência. Ordenado por estabelecimento, item e data — é a ordem em que a ficha se lê."
      >
        <Numerao
          tom="destaque"
          nota={`${dinheiro(resumo.st_nas_entradas)} de ICMS-ST nas entradas.`}
        >
          {numero(resumo.movimentos)}
        </Numerao>

        <Recortes titulo="Por CST das entradas" fatias={resumo.por_cst} />
        <Filtro
          titulo="Por marca da conferência"
          explicacao="Sem escolher nenhuma, a planilha traz todos os movimentos."
          fatias={resumo.por_classificacao}
          escolhidos={classes}
          aoAlternar={aoAlternarClasse}
        />

        <div className="mt-6">
          <BaixarPlanilha
            destaque
            aoBaixar={(formato) => aoBaixar("movimentos", formato)}
            desabilitado={ocupado || resumo.movimentos === 0}
            baixando={baixando?.qual === "movimentos" ? baixando.formato : null}
            aoCancelar={aoCancelar}
            rotulo={classes.length ? "Baixar planilha filtrada" : "Baixar planilha"}
          />
        </div>
      </Secao>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-4">
        <Secao
          titulo="Cadastro de itens"
          sub={
            <>
              O 0200 que vale: por estabelecimento e código, o do período mais recente.{" "}
              {numero(resumo.itens_movimentados)} códigos movimentados
              {resumo.itens_sem_cadastro > 0 &&
                `, ${numero(resumo.itens_sem_cadastro)} sem cadastro`}
              .
            </>
          }
        >
          <Numerao>{numero(resumo.itens_cadastrados)}</Numerao>
          <div className="mt-5">
            <BaixarPlanilha
              aoBaixar={(formato) => aoBaixar("itens", formato)}
              desabilitado={ocupado || resumo.itens_cadastrados === 0}
              baixando={baixando?.qual === "itens" ? baixando.formato : null}
              aoCancelar={aoCancelar}
            />
          </div>
        </Secao>

        <Secao
          titulo="Inventário"
          sub={
            <>
              O bloco H: o saldo de abertura da ficha, item a item.{" "}
              {numero(resumo.inventarios)} inventário(s), {dinheiro(resumo.valor_em_estoque)} em
              estoque.
            </>
          }
        >
          <Numerao>{numero(resumo.itens_em_estoque)}</Numerao>
          <div className="mt-5">
            <BaixarPlanilha
              aoBaixar={(formato) => aoBaixar("inventario", formato)}
              desabilitado={ocupado || resumo.itens_em_estoque === 0}
              baixando={baixando?.qual === "inventario" ? baixando.formato : null}
              aoCancelar={aoCancelar}
            />
          </div>
        </Secao>
      </div>

      <Secao
        titulo="Analítico por documento"
        sub="C190 e C850: o total por CST e CFOP de cada documento, com a marca de quem tem item na EFD e quem não tem. É por aqui que se vê o que o XML terá de detalhar."
        acao={
          <BaixarPlanilha
            aoBaixar={(formato) => aoBaixar("analitico", formato)}
            desabilitado={ocupado || resumo.analiticos === 0}
            baixando={baixando?.qual === "analitico" ? baixando.formato : null}
            aoCancelar={aoCancelar}
          />
        }
      >
        <Numerao
          nota={`${dinheiro(resumo.valor_saidas_sem_item)} em saídas sem item detalhado.`}
        >
          {numero(resumo.analiticos)}
        </Numerao>
        <Recortes
          titulo="Saídas sem item, por modelo"
          fatias={resumo.saidas_sem_item_por_modelo}
        />
      </Secao>

      {resumo.multa_nao_escrituradas_entradas !== undefined && (
        <Secao
          titulo="Notas não escrituradas"
          sub="XML do estabelecimento, de mês com EFD, que a EFD não tem e que não está cancelado. Não entra na ficha. A contingência é a multa do art. 527 do RICMS/SP — 10% do valor nas entradas, 75% do ICMS nas saídas —, sem SELIC. A base é a do XML; sem ela, o valor por unidade da nota mais próxima do mesmo produto."
          acao={
            <BaixarPlanilha
              aoBaixar={(formato) => aoBaixar("contingencia", formato)}
              desabilitado={
                ocupado ||
                (resumo.nao_escrituradas_entradas ?? 0) + (resumo.nao_escrituradas_saidas ?? 0) === 0
              }
              baixando={baixando?.qual === "contingencia" ? baixando.formato : null}
              aoCancelar={aoCancelar}
            />
          }
        >
          <Numerao
            nota={`${numero(resumo.nao_escrituradas_entradas ?? 0)} entrada(s), ${dinheiro(
              resumo.valor_nao_escriturado_entradas ?? "0",
            )} em valor, ${dinheiro(resumo.multa_nao_escrituradas_entradas ?? "0")} de multa · ${numero(
              resumo.nao_escrituradas_saidas ?? 0,
            )} saída(s), ${dinheiro(resumo.icms_nao_escriturado_saidas ?? "0")} de ICMS, ${dinheiro(
              resumo.multa_nao_escrituradas_saidas ?? "0",
            )} de multa.`}
          >
            {dinheiro(
              (
                Number(resumo.multa_nao_escrituradas_entradas ?? 0) +
                Number(resumo.multa_nao_escrituradas_saidas ?? 0)
              ).toFixed(2),
            )}
          </Numerao>
          <Recortes titulo="Multa por ano de emissão" fatias={resumo.contingencia_por_ano ?? []} />
        </Secao>
      )}
    </>
  );
}

/** Recortes só para ler: não filtram nada, mostram a composição. */
function Recortes({ titulo, fatias }: { titulo: string; fatias: Fatia[] }) {
  if (fatias.length === 0) return null;
  return (
    <GrupoDeChips titulo={titulo}>
      {fatias.map((f) => (
        <Pilula key={f.codigo || f.rotulo}>
          {f.rotulo}
          <span className="font-mono text-xs text-texto-fraco">
            {numero(f.documentos)} · {dinheiro(f.valor)}
          </span>
        </Pilula>
      ))}
    </GrupoDeChips>
  );
}

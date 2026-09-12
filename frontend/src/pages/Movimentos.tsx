import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Andamento } from "@/components/ui/Andamento";
import { Aviso } from "@/components/ui/Aviso";
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
import { IconeBaixar, IconeTentarDeNovo } from "@/constants/icons";
import { ROTAS } from "@/constants/routes";
import { comoErro } from "@/lib/errors";
import { dinheiro, numero } from "@/lib/format";
import { EM_CURSO, type Fatia } from "@/services/conferencia";
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

  async function baixar(qual: PlanilhaDeMovimentos) {
    if (!execucao) return;
    setOcupado(true);
    setErro(null);
    try {
      await baixarPlanilhaDeMovimentos(
        execucao.id,
        qual,
        [],
        qual === "movimentos" ? classes : [],
      );
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  const rodando = execucao !== null && EM_CURSO.includes(execucao.situacao);
  const resumo = execucao?.situacao === "concluida" ? execucao.resumo : null;

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
            className="shadow-acao"
          >
            {rodando ? "Extraindo…" : execucao ? "Extrair de novo" : "Extrair"}
          </Botao>
        }
      />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} />}

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
          ocupado={ocupado}
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
}: {
  resumo: ResumoDaMovimentacao;
  execucao: ExecucaoDeMovimentos | null;
  classes: string[];
  aoAlternarClasse: (codigo: string) => void;
  aoBaixar: (qual: PlanilhaDeMovimentos) => void;
  ocupado: boolean;
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
              nota={`${dinheiro(resumo.valor_saidas_sem_item_st)} com CST 60`}
              tom="atencao"
            />
          </Metricas>
        </div>

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
          <Botao
            icone={IconeBaixar}
            onClick={() => aoBaixar("movimentos")}
            disabled={ocupado || resumo.movimentos === 0}
            className="shadow-acao"
          >
            {classes.length ? "Baixar planilha filtrada" : "Baixar planilha"}
          </Botao>
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
            <Botao
              variante="secundario"
              icone={IconeBaixar}
              onClick={() => aoBaixar("itens")}
              disabled={ocupado || resumo.itens_cadastrados === 0}
            >
              Baixar planilha
            </Botao>
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
            <Botao
              variante="secundario"
              icone={IconeBaixar}
              onClick={() => aoBaixar("inventario")}
              disabled={ocupado || resumo.itens_em_estoque === 0}
            >
              Baixar planilha
            </Botao>
          </div>
        </Secao>
      </div>

      <Secao
        titulo="Analítico por documento"
        sub="C190 e C850: o total por CST e CFOP de cada documento, com a marca de quem tem item na EFD e quem não tem. É por aqui que se vê o que o XML terá de detalhar."
        acao={
          <Botao
            variante="secundario"
            icone={IconeBaixar}
            onClick={() => aoBaixar("analitico")}
            disabled={ocupado || resumo.analiticos === 0}
          >
            Baixar planilha
          </Botao>
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

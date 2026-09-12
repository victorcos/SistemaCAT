import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import { TrabalhoParado } from "@/components/shared/TrabalhoParado";
import { Andamento } from "@/components/ui/Andamento";
import { Aviso } from "@/components/ui/Aviso";
import { Botao, BotaoLink } from "@/components/ui/Botao";
import { Chip, GrupoDeChips } from "@/components/ui/Filtros";
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
import {
  baixarPlanilha,
  type Formato,
  detalharConferencia,
  EM_CURSO,
  iniciarConferencia,
  listarConferencias,
  type Execucao,
  type Fatia,
  type Planilha,
  type ResumoDaConferencia,
} from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

const INTERVALO_MS = 2000;

/**
 * Etapa 2 — conferir documentos.
 *
 * Cruza o que a EFD escriturou (C100 e C800) com o XML e o relatório do
 * cliente, e entrega as três listas do trabalho: o que casou (segue para a
 * apuração), o que está na pasta e não foi escriturado (sai da análise) e o
 * que foi escriturado sem documento (é o que se cobra).
 */
export default function Conferencia() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [execucao, setExecucao] = useState<Execucao | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState(false);
  // o download tem vida própria: carrega, erra e é cancelável por conta
  const download = useAcao();
  const [baixando, setBaixando] = useState<{
    qual: Planilha;
    formato: Formato;
  } | null>(null);
  const [modelos, setModelos] = useState<string[]>([]);
  const [classes, setClasses] = useState<string[]>([]);
  const relogio = useRef<number | null>(null);

  const acompanhar = useCallback(async (execucaoId: number) => {
    try {
      const atual = await detalharConferencia(execucaoId);
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
    listarConferencias(projetoId)
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
      const nova = await iniciarConferencia(projetoId);
      setExecucao(nova);
      setModelos([]);
      setClasses([]);
      relogio.current = window.setInterval(() => acompanhar(nova.id), INTERVALO_MS);
    } catch (e) {
      setErro(comoErro(e));
    } finally {
      setOcupado(false);
    }
  }

  async function baixar(qual: Planilha, formato: Formato) {
    if (!execucao) return;
    setErro(null);
    setBaixando({ qual, formato });
    await download.executar((sinal) =>
      baixarPlanilha(
        execucao.id,
        qual,
        qual === "a-cobrar" ? modelos : [],
        qual === "a-cobrar" ? classes : [],
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
        eyebrow="Etapa 2"
        titulo="Conferir documentos"
        sub={
          projeto ? (
            <>
              Cruza o que a EFD de{" "}
              <strong className="text-texto">{projeto.projeto.empresa}</strong> escriturou (C100 e
              C800) com o XML e o relatório do cliente. O que está na pasta e não foi escriturado
              sai da análise; o que foi escriturado sem documento é o que se cobra.
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
            {rodando ? "Conferindo…" : execucao ? "Conferir de novo" : "Conferir"}
          </Botao>
        }
      />

      <TrabalhoParado status={projeto?.projeto.status} projetoId={projetoId} />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} />}
      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} />
      )}

      {!execucao && (
        <Vazio titulo="Nenhuma conferência ainda">
          A conferência lê toda a EFD do trabalho. Numa base grande isso leva minutos — pode sair
          desta tela, que ela continua rodando.
        </Vazio>
      )}

      {rodando && execucao && <Andamento e={execucao} />}

      {execucao?.situacao === "falhou" && (
        <Aviso titulo="A conferência falhou.">
          <span className="font-mono text-xs">{execucao.erro}</span>
        </Aviso>
      )}

      {resumo && (
        <Resultado
          resumo={resumo}
          execucao={execucao}
          modelos={modelos}
          classes={classes}
          aoAlternarModelo={(codigo) => setModelos(alternar(codigo))}
          aoAlternarClasse={(codigo) => setClasses(alternar(codigo))}
          aoBaixar={baixar}
          ocupado={ocupado || download.carregando}
          baixando={baixando}
          aoCancelar={download.podeCancelar ? download.cancelar : undefined}
          projetoId={projetoId}
        />
      )}
    </div>
  );
}

/** Liga ou desliga um código na lista de filtros. */
const alternar = (codigo: string) => (atuais: string[]) =>
  atuais.includes(codigo) ? atuais.filter((c) => c !== codigo) : [...atuais, codigo];

/* ------------------------------------------------------------------ */

function Resultado({
  resumo,
  execucao,
  modelos,
  classes,
  aoAlternarModelo,
  aoAlternarClasse,
  aoBaixar,
  ocupado,
  baixando,
  aoCancelar,
  projetoId,
}: {
  resumo: ResumoDaConferencia;
  execucao: Execucao | null;
  modelos: string[];
  classes: string[];
  aoAlternarModelo: (codigo: string) => void;
  aoAlternarClasse: (codigo: string) => void;
  aoBaixar: (qual: Planilha, formato: Formato) => void;
  ocupado: boolean;
  baixando: { qual: Planilha; formato: Formato } | null;
  aoCancelar?: () => void;
  projetoId: number;
}) {
  const cobertura = Math.round(resumo.cobertura * 100);
  const filtrada = modelos.length > 0 || classes.length > 0;

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
            <Metrica rotulo="Escrituradas na EFD" valor={resumo.escriturados} />
            <Metrica
              rotulo="Com documento"
              valor={resumo.conferidos}
              nota={`${cobertura}% de cobertura`}
              tom="sucesso"
            />
            <Metrica
              rotulo="Sem documento"
              valor={resumo.sem_documento}
              nota={dinheiro(resumo.valor_sem_documento)}
              tom="destaque"
            />
            <Metrica
              rotulo="Não escrituradas"
              valor={resumo.nao_escrituradas}
              nota="saíram da análise"
            />
          </Metricas>
        </div>

        <Barra de={cobertura} para={100} tom="sucesso" className="mt-4" />

        <div className="mt-4 flex flex-col gap-2">
          {resumo.comparou && (
            <Aviso tom="sucesso" titulo="Desde a conferência anterior">
              {resumo.andou}
            </Aviso>
          )}
          {resumo.avisos.map((a) => (
            <Aviso key={a} tom="atencao">
              {a}
            </Aviso>
          ))}
          {resumo.recusados.length > 0 && (
            <Aviso tom="atencao" titulo="Arquivos com problema na leitura">
              O que está aqui não entrou no confronto:
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
        titulo="Notas conferidas"
        sub="Estão na EFD e o documento veio — XML da pasta ou linha do relatório do cliente. É o resultado positivo: o que segue para a apuração."
        acao={
          <BaixarPlanilha
            aoBaixar={(formato) => aoBaixar("conferidas", formato)}
            desabilitado={ocupado || resumo.conferidos === 0}
            baixando={baixando?.qual === "conferidas" ? baixando.formato : null}
            aoCancelar={aoCancelar}
          />
        }
      >
        <Numerao nota={`${dinheiro(resumo.valor_conferido)} em documentos conferidos.`}>
          {numero(resumo.conferidos)}
        </Numerao>
      </Secao>

      <Secao
        titulo="Notas não escrituradas"
        sub="Estão na pasta do cliente e não estão na EFD. Ficam fora da análise: ressarcimento se pede sobre o que foi declarado ao fisco."
        acao={
          <BaixarPlanilha
            aoBaixar={(formato) => aoBaixar("nao-escrituradas", formato)}
            desabilitado={ocupado || resumo.nao_escrituradas === 0}
            baixando={baixando?.qual === "nao-escrituradas" ? baixando.formato : null}
            aoCancelar={aoCancelar}
          />
        }
      >
        <Numerao>{numero(resumo.nao_escrituradas)}</Numerao>
      </Secao>

      <Secao
        destaque
        titulo="Notas a cobrar do cliente"
        sub="Foram escrituradas e o documento não veio. Sem o XML não há como saber o ICMS-ST retido daquela nota. A planilha sai inteira: nada é excluído, e o que não se espera cobrar vai marcado do que é."
      >
        <Numerao
          tom="destaque"
          nota={`${numero(resumo.sem_documento_cobravel)} esperam documento do cliente.`}
        >
          {numero(resumo.sem_documento)}
        </Numerao>

        <Filtro
          titulo="Por classificação"
          explicacao="Sem escolher nenhuma, a planilha traz todas — inclusive as canceladas e as sem chave, cada uma marcada."
          fatias={resumo.por_classificacao}
          escolhidos={classes}
          aoAlternar={aoAlternarClasse}
        />
        <Filtro
          titulo="Por modelo de documento"
          explicacao="Cupom de consumidor costuma dominar o volume, e não é XML que se peça um a um."
          fatias={resumo.por_modelo}
          escolhidos={modelos}
          aoAlternar={aoAlternarModelo}
        />

        <div className="mt-6">
          <BaixarPlanilha
            destaque
            aoBaixar={(formato) => aoBaixar("a-cobrar", formato)}
            desabilitado={ocupado || resumo.sem_documento === 0}
            baixando={baixando?.qual === "a-cobrar" ? baixando.formato : null}
            aoCancelar={aoCancelar}
            rotulo={filtrada ? "Baixar planilha filtrada" : "Baixar planilha"}
          />
        </div>
      </Secao>

      <Secao
        titulo="O cliente mandou o que faltava?"
        sub="Importe os arquivos novos na base de dados e rode a conferência de novo. A próxima rodada compara com esta e diz quantas pendências saíram, quantas continuam e quantas apareceram — por isso nada é excluído da lista."
        acao={
          <BotaoLink variante="secundario" para={ROTAS.arquivos(projetoId)}>
            Importar mais arquivos
          </BotaoLink>
        }
      >
        <span className="sr-only">Etapa 1</span>
      </Secao>
    </>
  );
}

/** Um grupo de filtros da planilha, com a contagem de cada recorte. */
export function Filtro({
  titulo,
  explicacao,
  fatias,
  escolhidos,
  aoAlternar,
}: {
  titulo: string;
  explicacao: string;
  fatias: Fatia[];
  escolhidos: string[];
  aoAlternar: (codigo: string) => void;
}) {
  if (fatias.length === 0) return null;
  return (
    <GrupoDeChips titulo={titulo} explicacao={explicacao}>
      {fatias.map((f) => (
        <Chip
          key={f.codigo}
          marcado={escolhidos.includes(f.codigo)}
          aoAlternar={() => aoAlternar(f.codigo)}
          contagem={numero(f.documentos)}
        >
          {f.rotulo}
        </Chip>
      ))}
    </GrupoDeChips>
  );
}

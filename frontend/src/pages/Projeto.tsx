import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { BarraDeFuncionalidades } from "@/components/shared/BarraDeFuncionalidades";
import { PainelDoTrabalho } from "@/components/shared/PainelDoTrabalho";
import { Aviso } from "@/components/ui/Aviso";
import { Botao, BotaoLink } from "@/components/ui/Botao";
import { Campo, CampoSenha } from "@/components/ui/Campo";
import { Carregando } from "@/components/ui/Carregando";
import { Etiqueta, type TomDeEtiqueta } from "@/components/ui/Etiqueta";
import { Modal } from "@/components/ui/Modal";
import { EditarCadastro } from "@/components/shared/EditarCadastro";
import {
  Barra,
  CabecalhoDePagina,
  Secao,
  Voltar,
} from "@/components/ui/Pagina";
import { IconeApagar, IconeArquivoDigital, IconeConfirma, IconeEditar, IconeHistorico } from "@/constants/icons";
import { ROTAS } from "@/constants/routes";
import {
  TOM_DO_STATUS,
  aceitaProcessamento,
  avisoDeTrabalhoParado,
  type Status,
} from "@/constants/status";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/cn";
import { periodo } from "@/lib/competencia";
import { comoErro } from "@/lib/errors";
import { numero } from "@/lib/format";
import {
  detalharProjeto,
  excluirProjeto,
  previaDaExclusao,
  type Etapa,
  type OQueSeraApagado,
  type ProjetoDetalhe,
} from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/* ------------------------------------------------------------------ */

/** Para onde cada funcionalidade leva, e com que palavras.
 *
 *  A tela não decide o que está disponível — isso vem do domínio, em
 *  `etapa.acessivel`. Chave sem entrada aqui aparece na barra e no cartão sem
 *  botão, o que é o certo para uma funcionalidade ainda sem tela. */
const DESTINOS: Record<
  string,
  { rota: (id: number) => string; rotulos: Record<string, string> }
> = {
  importar: {
    rota: ROTAS.arquivos,
    rotulos: {
      concluida: "Importar mais arquivos",
      padrao: "Importar a base de dados",
    },
  },
  conferencia: {
    rota: ROTAS.conferencia,
    rotulos: {
      concluida: "Ver o resultado e baixar as planilhas",
      em_andamento: "Acompanhar a conferência",
      padrao: "Conferir documentos",
    },
  },
  movimentos: {
    rota: ROTAS.movimentos,
    rotulos: {
      concluida: "Ver o histórico e baixar as planilhas",
      em_andamento: "Acompanhar a extração",
      padrao: "Extrair movimentos",
    },
  },
  st_suportado: {
    rota: ROTAS.suportado,
    rotulos: {
      concluida: "Ver de onde veio cada real e baixar a planilha",
      em_andamento: "Acompanhar a apuração",
      padrao: "Apurar o ICMS suportado",
    },
  },
  credito_outorgado: {
    rota: ROTAS.creditoOutorgado,
    rotulos: {
      concluida: "Ver os produtos capturados e baixar a lista",
      em_andamento: "Acompanhar a varredura",
      padrao: "Triar os itens beneficiados",
    },
  },
  // o histórico não está aqui de propósito: o caminho dele é o botão do canto
  // superior, e não uma funcionalidade da barra — ver `funcionalidades` abaixo
  quebra_de_sped: {
    rota: ROTAS.quebraDeSped,
    rotulos: {
      concluida: "Ver o que foi lido e baixar as contagens",
      em_andamento: "Acompanhar a quebra",
      padrao: "Quebrar os SPED",
    },
  },
  apuracao_piscofins: {
    rota: ROTAS.apuracaoPisCofins,
    rotulos: {
      concluida: "Ver o par que se confronta e baixar as planilhas",
      em_andamento: "Acompanhar a apuração",
      padrao: "Apurar PIS/COFINS",
    },
  },
  apuracao_contribuicoes: {
    rota: ROTAS.gestao,
    rotulos: {
      concluida: "Ver os quadros e baixar a Gestão",
      em_andamento: "Acompanhar a apuração",
      padrao: "Apurar as contribuições",
    },
  },
  razao: {
    rota: ROTAS.razao,
    rotulos: {
      concluida: "Ver as fichas e baixar a Ficha 3",
      em_andamento: "Acompanhar a montagem",
      padrao: "Montar o razão",
    },
  },
  apuracao: {
    rota: ROTAS.apuracao,
    rotulos: {
      concluida: "Ver o que dá para pedir e o que trava",
      em_andamento: "Acompanhar a apuração",
      padrao: "Apurar ressarcimento e complemento",
    },
  },
  arquivo_digital: {
    rota: ROTAS.arquivoDigital,
    rotulos: {
      concluida: "Baixar os arquivos e ver a pré-validação",
      em_andamento: "Acompanhar a geração",
      padrao: "Gerar o arquivo digital",
    },
  },
  entrega: {
    rota: ROTAS.entrega,
    rotulos: {
      concluida: "Ver a entrega aprovada e baixar o pacote",
      // montada e à espera do revisor também aparece em andamento
      em_andamento: "Acompanhar, conferir e aprovar a entrega",
      padrao: "Montar a entrega",
    },
  },
};

const TOM_DA_SITUACAO: Record<string, TomDeEtiqueta> = {
  concluida: "sucesso",
  em_andamento: "info",
  pendente: "atencao",
  bloqueada: "neutro",
  nao_disponivel: "neutro",
};

/* ------------------------------------------------------------------ */

export default function Projeto() {
  const { podeExcluirTrabalho, administraUsuarios, podeEscrever } = useAuth();
  const [editando, setEditando] = useState(false);
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<ProjetoDetalhe | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [aExcluir, setAExcluir] = useState<OQueSeraApagado | null>(null);

  useEffect(() => {
    if (!id) return;
    detalharProjeto(Number(id))
      .then(setD)
      .catch((e) => setErro(comoErro(e)));
  }, [id]);

  if (erro) {
    return (
      <div className="mx-auto flex max-w-[1240px] flex-col gap-4">
        <Voltar para={ROTAS.inicio}>Trabalhos</Voltar>
        <Aviso titulo={erro.message} codigo={erro.requisicaoId} />
      </div>
    );
  }

  if (!d) return <Carregando texto="Carregando o trabalho…" />;

  const p = d.projeto;
  /* O histórico sai da barra e dos cards: o caminho dele é o botão do canto
     superior, que está sempre ali. Repetir o mesmo destino em três lugares
     fazia o trabalho parecer ter uma funcionalidade a mais do que tem — e o
     histórico não é etapa: ele nunca conclui, que é por isso que o servidor já
     o deixa fora do progresso (`DefinicaoEtapa.Conta`). 23/09/2026. */
  const funcionalidades = d.etapas.filter((e) => e.chave !== "historico");
  const status = p.status as Status;
  // trabalho parado não roda etapa — a API recusa, e a tela diz antes
  const anda = aceitaProcessamento(status);
  const parado = avisoDeTrabalhoParado(status);

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4">
      <Voltar para={ROTAS.inicio}>Trabalhos</Voltar>

      <CabecalhoDePagina
        eyebrow={p.frente_rotulo}
        titulo={p.empresa}
        sub={
          <span className="flex flex-wrap items-center gap-2 font-mono">
            {p.cnpj_matriz_formatado ?? "CNPJ não informado"}
            {p.uf && (
              <span className="rounded border border-borda px-1.5 py-0.5 text-[11px] font-sans font-bold text-texto-fraco">
                {p.uf}
              </span>
            )}
          </span>
        }
        acao={
          <div className="flex flex-col items-end gap-3">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Etiqueta tom={TOM_DO_STATUS[status] ?? "neutro"} pulso={status === "em_andamento"}>
                {p.status_rotulo || status}
              </Etiqueta>
              <BotaoLink
                para={ROTAS.historico(p.id)}
                tamanho="sm"
                variante="secundario"
                icone={IconeHistorico}
              >
                Histórico do projeto
              </BotaoLink>
            </div>
            <dl className="m-0 grid gap-2 text-right">
            <div>
              <dt className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
                Projeto
              </dt>
              <dd className="m-0 text-sm font-semibold text-texto">{p.nome}</dd>
            </div>
            <div>
              <dt className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
                Competências
              </dt>
              <dd className="m-0 font-mono text-sm text-texto-suave">
                {periodo(p.competencia_ini, p.competencia_fim)}
              </dd>
            </div>
            {podeEscrever && (
              <div>
                <Botao variante="fantasma" tamanho="sm" icone={IconeEditar} onClick={() => setEditando(true)}>
                  Editar cadastro
                </Botao>
              </div>
            )}
            {administraUsuarios && p.criado_por && (
              <div>
                <dt className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
                  Criado por
                </dt>
                <dd className="m-0 text-sm text-texto-suave">{p.criado_por}</dd>
              </div>
            )}
            </dl>
          </div>
        }
      >
        {/* o progresso é o do servidor (`Etapas.Progresso`): ele já ignora o que
            não foi construído e o que não conclui. Recontar aqui dava uma
            segunda verdade — e ela discordava, somando o histórico. */}
        <div className="flex flex-wrap items-center gap-3">
          <Barra de={p.etapas_feitas} para={p.etapas_totais} className="min-w-[200px] flex-1" />
          <span className="text-[13px] font-semibold text-texto-suave">
            {p.etapas_feitas} de {p.etapas_totais} etapas concluídas
          </span>
        </div>
      </CabecalhoDePagina>

      {d.base && d.base.fora_do_periodo > 0 && (
        <Aviso
          tom="atencao"
          titulo={`${numero(d.base.fora_do_periodo)} de ${numero(d.base.efds)} EFD importadas estão fora do período do trabalho`}
          acao={
            podeEscrever ? (
              <Botao tamanho="sm" variante="secundario" icone={IconeEditar} onClick={() => setEditando(true)}>
                Editar cadastro
              </Botao>
            ) : undefined
          }
        >
          A base vai de {periodo(d.base.primeira, d.base.ultima)} e o trabalho está cadastrado para{" "}
          {periodo(p.competencia_ini, p.competencia_fim)}. Confira o cadastro ou a base importada: o relatório da entrega
          sai com os dois períodos.
        </Aviso>
      )}

      {editando && (
        <EditarCadastro
          projeto={p}
          aberto={editando}
          aoFechar={() => setEditando(false)}
          aoSalvar={() => detalharProjeto(p.id).then(setD).catch((x) => setErro(comoErro(x)))}
        />
      )}

      {parado && (
        <Aviso
          tom={status === "cancelado" ? "erro" : "atencao"}
          titulo={parado.titulo}
          acao={
            <BotaoLink para={ROTAS.historico(p.id)} tamanho="sm" variante="secundario">
              Abrir o histórico
            </BotaoLink>
          }
        >
          {parado.texto}
        </Aviso>
      )}

      <BarraDeFuncionalidades
        etapas={funcionalidades}
        rota={(chave: string) => {
          const destino = DESTINOS[chave];
          return destino ? destino.rota(Number(id)) : null;
        }}
      />

      {/* Em PIS/COFINS as funcionalidades são independentes, e a grade diz isso:
          cada uma é um card, com os leiautes da base em cima. Na CAT 42 a ordem
          é dependência real — sem movimentos não há razão —, e ali a lista
          numerada continua sendo a leitura certa. */}
      {p.modulo === "piscofins" ? (
        <PainelDoTrabalho
          projetoId={Number(id)}
          etapas={funcionalidades}
          rota={(chave: string) => {
            const destino = DESTINOS[chave];
            return destino ? destino.rota(Number(id)) : null;
          }}
          bloqueio={anda ? undefined : parado?.titulo}
        />
      ) : (
        <Secao
          titulo="As funcionalidades, em detalhe"
          sub="A barra acima leva direto a cada uma. Aqui vai o que cada uma faz, em que pé está e o que ela produz."
        >
          <ol className="m-0 mt-4 flex list-none flex-col gap-2.5 p-0">
            {funcionalidades.map((e, i) => (
              <LinhaDeEtapa
                key={e.chave}
                e={e}
                numero={i + 1}
                projetoId={Number(id)}
                bloqueada={!anda}
                motivo={parado?.titulo ?? ""}
              />
            ))}
          </ol>
        </Secao>
      )}

      <section className="flex flex-wrap items-center gap-4 rounded-cartao border border-borda bg-superficie-vidro p-6">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] border border-laranja-500/30 bg-laranja-500/14 text-laranja-700 escuro:text-laranja-300">
          <IconeArquivoDigital size={18} strokeWidth={1.8} aria-hidden />
        </div>
        <div className="min-w-[240px] flex-1">
          <h2 className="m-0 text-base font-extrabold text-texto">Auditoria do que o cliente já transmitiu</h2>
          <p className="m-0 mt-1.5 max-w-[680px] text-[13px] leading-relaxed text-texto-suave">
            Pré-validar os arquivos da CAT 42 que o cliente gerou com outra ferramenta, soltos no lote ou em
            zip. Não depende das etapas acima.
          </p>
        </div>
        <BotaoLink para={ROTAS.preValidacao(p.id)} variante="secundario">
          Pré-validar os arquivos do cliente
        </BotaoLink>
      </section>

      {podeExcluirTrabalho && (
        <section className="flex flex-wrap items-center justify-between gap-4 rounded-cartao border border-erro/30 border-l-[3px] border-l-erro bg-erro-fundo p-6">
          <div className="min-w-0">
            <h2 className="m-0 text-base font-extrabold text-erro">Excluir este trabalho</h2>
            <p className="m-0 mt-1.5 max-w-[620px] text-[13px] leading-relaxed text-texto-suave">
              Some o projeto, os lotes importados e as conferências já feitas. Não há como
              desfazer, e não há lixeira. Os arquivos do cliente em disco não são tocados.
            </p>
          </div>
          <Botao
            variante="perigo"
            icone={IconeApagar}
            onClick={() =>
              previaDaExclusao(Number(id))
                .then(setAExcluir)
                .catch((e) => setErro(comoErro(e)))
            }
          >
            Excluir trabalho
          </Botao>
        </section>
      )}

      <ConfirmarExclusao
        projetoId={Number(id)}
        alvo={aExcluir}
        aoFechar={() => setAExcluir(null)}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */

function LinhaDeEtapa({
  e,
  numero: n,
  projetoId,
  bloqueada,
  motivo,
}: {
  e: Etapa;
  numero: number;
  projetoId: number;
  /** o trabalho está pausado ou cancelado: a etapa não roda */
  bloqueada: boolean;
  motivo: string;
}) {
  const concluida = e.situacao === "concluida";
  const atual = e.acessivel && !concluida;
  const destino = DESTINOS[e.chave];
  const rotulo = destino
    ? destino.rotulos[e.situacao] ?? destino.rotulos.padrao
    : null;

  return (
    <li
      className={cn(
        "flex gap-3.5 rounded-[14px] border border-l-[3px] p-4 transition-colors",
        concluida && "border-sucesso/25 border-l-sucesso bg-sucesso-fundo",
        atual && "border-laranja-500/35 border-l-marca-laranja bg-laranja-500/8",
        !concluida && !atual && "border-borda border-l-borda-forte bg-superficie-vidro opacity-70",
      )}
    >
      <div
        aria-hidden
        className={cn(
          "flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full text-[13px] font-extrabold",
          concluida && "bg-sucesso text-marca-branco",
          atual && "bg-marca-laranja text-acao-texto",
          !concluida && !atual && "border border-borda-forte text-texto-fraco",
        )}
      >
        {concluida ? <IconeConfirma size={15} strokeWidth={3} /> : n}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="m-0 text-[15px] font-bold text-texto">{e.nome}</h3>
          <Etiqueta tom={TOM_DA_SITUACAO[e.situacao] ?? "neutro"} pulso={e.situacao === "em_andamento"}>
            {e.situacao_rotulo}
          </Etiqueta>
        </div>
        <p className="m-0 mt-1.5 max-w-[720px] text-[13px] leading-[1.6] text-texto-suave [text-wrap:pretty]">
          {e.descricao}
        </p>
        {rotulo && e.acessivel && (
          <div className="mt-3">
            {bloqueada ? (
              // botão morto, e não link escondido: some o caminho, fica o
              // motivo — quem chega aqui precisa saber por que não dá
              <Botao tamanho="sm" variante="secundario" disabled title={motivo}>
                {rotulo}
              </Botao>
            ) : (
              <BotaoLink
                para={destino.rota(projetoId)}
                tamanho="sm"
                variante={atual ? "principal" : "secundario"}
              >
                {rotulo}
              </BotaoLink>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

/* ------------------------------------------------------------------ */

/**
 * A confirmação da exclusão.
 *
 * Pede a senha de novo de propósito: a sessão fica aberta a jornada inteira, e
 * uma tela deixada em máquina destravada não pode bastar para desfazer meses
 * de apuração. É a única operação do sistema que exige isso.
 */
function ConfirmarExclusao({
  projetoId,
  alvo,
  aoFechar,
}: {
  projetoId: number;
  alvo: OQueSeraApagado | null;
  aoFechar: () => void;
}) {
  const navegar = useNavigate();
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    if (alvo) {
      setSenha("");
      setErro(null);
    }
  }, [alvo]);

  async function apagar(evento: FormEvent) {
    evento.preventDefault();
    setOcupado(true);
    setErro(null);
    try {
      await excluirProjeto(projetoId, senha);
      navegar(ROTAS.inicio, { replace: true });
    } catch (e) {
      setErro(comoErro(e));
      setSenha("");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal
      aberto={alvo !== null}
      aoFechar={aoFechar}
      tamanho="sm"
      titulo={`Apagar "${alvo?.projeto ?? ""}"?`}
      sub={<>De {alvo?.empresa}.</>}
      rodape={
        <>
          <Botao variante="fantasma" onClick={aoFechar} disabled={ocupado}>
            Cancelar
          </Botao>
          <Botao
            type="submit"
            form="form-excluir-trabalho"
            variante="perigo"
            carregando={ocupado}
            disabled={senha.length === 0}
          >
            Sim, apagar
          </Botao>
        </>
      }
    >
      <form id="form-excluir-trabalho" onSubmit={apagar} className="flex flex-col gap-4">
        <ul className="m-0 flex list-none flex-col gap-1.5 rounded-raio-g border border-borda bg-superficie-vidro p-3.5 text-[13px] text-texto-suave">
          <li>
            <strong className="font-mono text-texto">{numero(alvo?.lotes ?? 0)}</strong> lote(s)
            importado(s)
          </li>
          <li>
            <strong className="font-mono text-texto">{numero(alvo?.arquivos ?? 0)}</strong>{" "}
            arquivo(s) registrado(s)
          </li>
          <li>
            <strong className="font-mono text-texto">{numero(alvo?.execucoes ?? 0)}</strong>{" "}
            execução(ões)
          </li>
        </ul>

        <p className="m-0 text-[13px] leading-relaxed text-texto-suave">
          Não há como desfazer. Os arquivos do cliente em disco continuam onde estão — some o
          trabalho dentro do sistema.
        </p>

        {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} />}

        <Campo rotulo="Confirme com a sua senha de acesso">
          {(props) => (
            <CampoSenha
              {...props}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              autoComplete="current-password"
              autoFocus
            />
          )}
        </Campo>
      </form>
    </Modal>
  );
}

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { useParams } from "react-router-dom";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Carregando } from "@/components/ui/Carregando";
import { Combobox, type OpcaoDeCombobox } from "@/components/ui/Combobox";
import { Etiqueta } from "@/components/ui/Etiqueta";
import { Segmentado } from "@/components/ui/Filtros";
import { Modal } from "@/components/ui/Modal";
import { CabecalhoDePagina, Secao, Vazio, Voltar } from "@/components/ui/Pagina";
import {
  IconeArquivo,
  IconeComentario,
  IconeConfirma,
  IconeEnviar,
  IconeErro,
  IconeEstrela,
  IconeSucessao,
  IconeTrocar,
  type Icone,
} from "@/constants/icons";
import { PAPEIS } from "@/constants/roles";
import { ROTAS } from "@/constants/routes";
import { avisoDeTrabalhoParado, type Status } from "@/constants/status";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/useToast";
import { cn } from "@/lib/cn";
import { periodo } from "@/lib/competencia";
import { comoErro } from "@/lib/errors";
import { dataHora, numero, tamanho } from "@/lib/format";
import {
  comentar,
  daFamilia,
  lerHistorico,
  listarStatus,
  listarSucessores,
  mudarStatus,
  passarTrabalho,
  type EventoDoProjeto,
  type Familia,
  type StatusDisponivel,
  type Sucessor,
  type TipoDeEvento,
} from "@/services/historico";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import type { Papel } from "@/types/auth";
import type { ErroApi } from "@/types/erro";

const POR_PAGINA = 50;

const FILTROS: { chave: Familia; rotulo: string }[] = [
  { chave: "tudo", rotulo: "Tudo" },
  { chave: "comentarios", rotulo: "Comentários" },
  { chave: "situacao", rotulo: "Situação" },
  { chave: "arquivos", rotulo: "Arquivos" },
  { chave: "etapas", rotulo: "Etapas" },
];

/** Ícone e cor de cada tipo. Tipo novo do servidor cai no padrão em vez de
 *  sumir da linha do tempo. */
const APARENCIA: Record<TipoDeEvento, { icone: Icone; classe: string }> = {
  criado: { icone: IconeEstrela, classe: "bg-superficie-alt text-texto-suave" },
  comentario: { icone: IconeComentario, classe: "bg-superficie-alt text-texto" },
  status: {
    icone: IconeTrocar,
    classe: "bg-laranja-500/14 text-laranja-700 escuro:text-laranja-300",
  },
  sucessao: {
    icone: IconeSucessao,
    classe: "bg-laranja-500/14 text-laranja-700 escuro:text-laranja-300",
  },
  lote_importado: { icone: IconeEnviar, classe: "bg-info-fundo text-info" },
  lote_removido: { icone: IconeArquivo, classe: "bg-erro-fundo text-erro" },
  lote_reclassificado: { icone: IconeTrocar, classe: "bg-info-fundo text-info" },
  etapa_iniciada: { icone: IconeArquivo, classe: "bg-superficie-alt text-texto-suave" },
  etapa_concluida: { icone: IconeConfirma, classe: "bg-sucesso-fundo text-sucesso" },
  etapa_falhou: { icone: IconeErro, classe: "bg-erro-fundo text-erro" },
  planilha_baixada: { icone: IconeArquivo, classe: "bg-superficie-alt text-texto-suave" },
  parametro_alterado: {
    icone: IconeTrocar,
    classe: "bg-laranja-500/14 text-laranja-700 escuro:text-laranja-300",
  },
  entrega_aprovada: { icone: IconeConfirma, classe: "bg-sucesso-fundo text-sucesso" },
};

const PADRAO = { icone: IconeComentario, classe: "bg-superficie-alt text-texto-suave" };

/* ------------------------------------------------------------------ */

/**
 * Histórico do trabalho.
 *
 * Tudo que aconteceu, em ordem: o que o sistema fez e o que a equipe
 * escreveu, misturados de propósito. É também onde se muda a situação e onde
 * o gestor passa o trabalho para outra pessoa.
 */
export default function Historico() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);
  const { usuario, administraUsuarios } = useAuth();
  const toast = useToast();

  const [detalhe, setDetalhe] = useState<ProjetoDetalhe | null>(null);
  const [eventos, setEventos] = useState<EventoDoProjeto[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [temMais, setTemMais] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [filtro, setFiltro] = useState<Familia>("tudo");
  const [statusPossiveis, setStatusPossiveis] = useState<StatusDisponivel[]>([]);
  const [aConfirmar, setAConfirmar] = useState<StatusDisponivel | null>(null);
  const [sucessores, setSucessores] = useState<Sucessor[]>([]);
  const [sucessor, setSucessor] = useState("");
  const [aTransferir, setATransferir] = useState<Sucessor | null>(null);

  const recarregarProjeto = useCallback(
    () =>
      detalharProjeto(projetoId)
        .then(setDetalhe)
        .catch((e) => setErro(comoErro(e))),
    [projetoId],
  );

  useEffect(() => {
    if (!projetoId) return;
    recarregarProjeto();
    listarStatus().then(setStatusPossiveis).catch(() => setStatusPossiveis([]));
    lerHistorico(projetoId, { quantos: POR_PAGINA })
      .then((p) => {
        setEventos(p.eventos);
        setCursor(p.proximo_cursor);
        setTemMais(p.tem_mais);
      })
      .catch((e) => setErro(comoErro(e)))
      .finally(() => setCarregando(false));
  }, [projetoId, recarregarProjeto]);

  // a lista de quem pode receber só interessa a quem pode transferir
  useEffect(() => {
    if (!projetoId || !administraUsuarios) return;
    listarSucessores(projetoId).then(setSucessores).catch(() => setSucessores([]));
  }, [projetoId, administraUsuarios]);

  async function carregarMais() {
    if (!cursor) return;
    try {
      const p = await lerHistorico(projetoId, { antes_de: cursor, quantos: POR_PAGINA });
      setEventos((atuais) => [...atuais, ...p.eventos]);
      setCursor(p.proximo_cursor);
      setTemMais(p.tem_mais);
    } catch (e) {
      toast.erro(comoErro(e).message);
    }
  }

  async function enviarComentario(texto: string) {
    const novo = await comentar(projetoId, texto);
    setEventos((atuais) => [novo, ...atuais]);
    recarregarProjeto();
  }

  async function confirmarStatus(motivo: string) {
    if (!aConfirmar) return;
    await mudarStatus(projetoId, aConfirmar.valor, motivo);
    setAConfirmar(null);
    await recarregarTudo();
    toast.sucesso(`Situação: ${aConfirmar.rotulo}`);
  }

  async function confirmarSucessao(motivo: string) {
    if (!aTransferir) return;
    await passarTrabalho(projetoId, aTransferir.id, motivo);
    setATransferir(null);
    setSucessor("");
    await recarregarTudo();
    toast.sucesso(`${aTransferir.nome_exibicao} passa a responder por este trabalho.`);
  }

  async function recarregarTudo() {
    await recarregarProjeto();
    const p = await lerHistorico(projetoId, { quantos: POR_PAGINA });
    setEventos(p.eventos);
    setCursor(p.proximo_cursor);
    setTemMais(p.tem_mais);
  }

  const visiveis = useMemo(
    () => eventos.filter((e) => daFamilia(e, filtro)),
    [eventos, filtro],
  );

  const resumo = useMemo(() => {
    const conta = (f: Familia) => eventos.filter((e) => daFamilia(e, f)).length;
    return {
      comentarios: conta("comentarios"),
      situacao: eventos.filter((e) => e.tipo === "status" || e.tipo === "sucessao").length,
      arquivos: conta("arquivos"),
      etapas: eventos.filter((e) => e.tipo === "etapa_concluida").length,
    };
  }, [eventos]);

  if (erro && !detalhe) {
    return (
      <div className="mx-auto flex max-w-[1320px] flex-col gap-4">
        <Voltar para={ROTAS.inicio}>Trabalhos</Voltar>
        <Aviso titulo={erro.message} codigo={erro.requisicaoId} />
      </div>
    );
  }

  if (!detalhe) return <Carregando texto="Carregando o histórico…" />;

  const p = detalhe.projeto;
  const status = p.status as Status;
  const parado = avisoDeTrabalhoParado(status);
  const candidatos = sucessores.filter((s) => s.id !== p.responsavel_id);
  const opcoesDeSucessor: OpcaoDeCombobox<string>[] = candidatos.map((s) => ({
    valor: String(s.id),
    rotulo:
      `${s.nome_exibicao} — ${PAPEIS[s.papel as Papel]?.rotulo ?? s.papel}` +
      (s.precisa_de_acesso ? " · ganha acesso" : ""),
  }));
  const escolhido = candidatos.find((s) => String(s.id) === sucessor);

  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-4">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>

      <CabecalhoDePagina
        eyebrow="Histórico do projeto"
        titulo={p.nome}
        sub={
          <>
            <span className="font-semibold text-texto-suave">{p.empresa}</span>
            <span className="mx-2 text-texto-fraco">·</span>
            <span className="font-mono">{p.cnpj_matriz_formatado ?? "CNPJ não informado"}</span>
            {p.uf && (
              <span className="ml-2 rounded border border-borda px-1.5 py-0.5 text-[11px] font-bold text-texto-fraco">
                {p.uf}
              </span>
            )}
          </>
        }
        acao={
          <SeletorDeSituacao
            atual={status}
            opcoes={statusPossiveis}
            aoEscolher={setAConfirmar}
          />
        }
      >
        <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
          {administraUsuarios && (
            <Fato rotulo="Criado por" pessoa={p.criado_por} id={p.criado_por_id} />
          )}
          <Fato rotulo="Responsável atual" pessoa={p.responsavel} id={p.responsavel_id} />
          <Fato rotulo="Frente" valor={p.frente_rotulo} />
          <Fato
            rotulo="Competências"
            valor={periodo(p.competencia_ini, p.competencia_fim)}
            mono
            nota={`${p.etapas_feitas} de ${p.etapas_totais} etapas concluídas`}
          />
        </dl>
      </CabecalhoDePagina>

      {parado && (
        <Aviso tom={status === "cancelado" ? "erro" : "atencao"} titulo={parado.titulo}>
          {parado.texto}
        </Aviso>
      )}

      <div className="grid grid-cols-[repeat(auto-fit,minmax(420px,1fr))] items-start gap-4">
        <Secao
          className="min-w-0"
          titulo="Atividades e comentários"
          sub={`${numero(eventos.length)} registro(s) · mais recente primeiro`}
        >
          <div className="mt-3 flex flex-wrap gap-2">
            <Segmentado
              rotulo="Filtrar o histórico"
              opcoes={FILTROS}
              valor={filtro}
              aoMudar={setFiltro}
            />
          </div>

          <div className="mt-4 max-h-[620px] overflow-y-auto pr-1">
            {carregando ? (
              <Carregando />
            ) : visiveis.length === 0 ? (
              <Vazio titulo="Nada por aqui">
                Troque o filtro para ver outros registros.
              </Vazio>
            ) : (
              <ol className="m-0 flex list-none flex-col p-0">
                {visiveis.map((e, i) => (
                  <LinhaDoTempo key={e.id} e={e} ultima={i === visiveis.length - 1} />
                ))}
              </ol>
            )}

            {temMais && filtro === "tudo" && (
              <div className="mt-3 flex justify-center">
                <Botao tamanho="sm" variante="secundario" onClick={carregarMais}>
                  Carregar mais
                </Botao>
              </div>
            )}
          </div>

          <Composer
            autor={usuario?.nome_exibicao ?? ""}
            aoEnviar={enviarComentario}
            aoFalhar={(m) => toast.erro(m)}
          />
        </Secao>

        <div className="flex min-w-0 flex-col gap-4">
          <Secao titulo="Resumo">
            <dl className="m-0 mt-3 grid grid-cols-2 gap-3">
              <Contador rotulo="Comentários" valor={resumo.comentarios} />
              <Contador rotulo="Mudanças de situação" valor={resumo.situacao} tom="text-laranja-700 escuro:text-laranja-300" />
              <Contador rotulo="Importações" valor={resumo.arquivos} tom="text-info" />
              <Contador rotulo="Etapas concluídas" valor={resumo.etapas} tom="text-sucesso" />
            </dl>
          </Secao>

          {administraUsuarios && (
            <Secao
              destaque
              titulo="Sucessão do projeto"
              sub="Somente gestores. O responsável passa a responder pelo trabalho; o histórico e o nome de quem criou permanecem."
            >
              <div className="mt-4 rounded-raio-g border border-borda bg-superficie-vidro p-3.5">
                <p className="m-0 text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
                  Responsável atual
                </p>
                <div className="mt-2 flex items-center gap-2.5">
                  <Avatar nome={p.responsavel} id={p.responsavel_id} tamanho={30} />
                  <span className="text-sm font-bold text-texto">
                    {p.responsavel ?? "Sem responsável"}
                  </span>
                </div>
              </div>

              {candidatos.length === 0 ? (
                <p className="m-0 mt-4 text-[13px] leading-relaxed text-texto-fraco">
                  Não há mais ninguém para quem passar: você é a única pessoa ativa com papel
                  que escreve. Cadastre alguém em Usuários antes.
                </p>
              ) : (
                <>
                  <div className="mt-4">
                    <p className="mb-1.5 text-[13px] font-semibold text-texto-suave">
                      Passar para
                    </p>
                    <Combobox
                      valor={sucessor}
                      opcoes={opcoesDeSucessor}
                      aoMudar={setSucessor}
                      placeholderDaBusca="Buscar pessoa…"
                    />
                    {escolhido?.precisa_de_acesso && (
                      <p className="m-0 mt-1.5 text-xs leading-relaxed text-texto-fraco">
                        {escolhido.nome_exibicao} ainda não enxerga esta empresa. Transferir dá
                        o acesso, e isso fica registrado no histórico.
                      </p>
                    )}
                  </div>

                  <div className="mt-4">
                    <Botao
                      disabled={!sucessor}
                      onClick={() => setATransferir(escolhido ?? null)}
                      className="shadow-acao"
                    >
                      Transferir projeto
                    </Botao>
                  </div>
                </>
              )}
            </Secao>
          )}
        </div>
      </div>

      <ModalComJustificativa
        aberto={aConfirmar !== null}
        titulo={`Mudar a situação para ${aConfirmar?.rotulo.toLowerCase() ?? ""}?`}
        sub={aConfirmar?.explicacao}
        exigeMotivo={aConfirmar?.exige_motivo ?? false}
        rotuloConfirmar="Alterar situação"
        aoFechar={() => setAConfirmar(null)}
        aoConfirmar={confirmarStatus}
      />

      <ModalComJustificativa
        aberto={aTransferir !== null}
        titulo={`Passar o trabalho para ${aTransferir?.nome_exibicao ?? ""}?`}
        sub={
          aTransferir?.precisa_de_acesso
            ? "Quem criou o trabalho não muda — só quem responde por ele. Como esta pessoa ainda não enxerga a empresa, a transferência também lhe dá o acesso."
            : "Quem criou o trabalho não muda — só quem responde por ele daqui para a frente."
        }
        exigeMotivo={false}
        rotuloConfirmar="Transferir"
        aoFechar={() => setATransferir(null)}
        aoConfirmar={confirmarSucessao}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */

function SeletorDeSituacao({
  atual,
  opcoes,
  aoEscolher,
}: {
  atual: Status;
  opcoes: StatusDisponivel[];
  aoEscolher: (s: StatusDisponivel) => void;
}) {
  const escolhido = opcoes.find((o) => o.valor === atual);
  return (
    <div className="min-w-[250px]">
      <p className="mb-1.5 text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
        Situação do projeto
      </p>
      <Combobox
        valor={atual}
        opcoes={opcoes.map((o) => ({ valor: o.valor, rotulo: o.rotulo }))}
        aoMudar={(v) => {
          const alvo = opcoes.find((o) => o.valor === v);
          if (alvo && alvo.valor !== atual) aoEscolher(alvo);
        }}
        placeholderDaBusca="Buscar situação…"
      />
      {escolhido && (
        <p className="m-0 mt-1.5 max-w-[280px] text-xs leading-relaxed text-texto-fraco">
          {escolhido.explicacao}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function LinhaDoTempo({ e, ultima }: { e: EventoDoProjeto; ultima: boolean }) {
  const { icone: Ico, classe } = APARENCIA[e.tipo] ?? PADRAO;
  const delta = e.dados.frase;

  return (
    <li className="flex gap-3.5 py-4">
      <div className="flex flex-col items-center">
        <span
          className={cn(
            "flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-raio-g",
            classe,
          )}
        >
          <Ico size={16} strokeWidth={2} aria-hidden />
        </span>
        {!ultima && <span className="mt-1 w-px flex-1 bg-borda" aria-hidden />}
      </div>

      <div className="min-w-0 flex-1 border-b border-borda-sutil pb-4">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-sm font-bold text-texto">{e.autor}</span>
          <span className="text-xs text-texto-fraco">{e.rotulo_do_tipo.toLowerCase()}</span>
          <span className="ml-auto shrink-0 font-mono text-[11px] text-texto-fraco">
            {dataHora(e.quando)}
          </span>
        </div>

        {delta && (
          <p className="m-0 mt-2 text-[13px] font-semibold text-laranja-700 escuro:text-laranja-300">
            {delta}
          </p>
        )}

        {e.texto && (
          <p
            className={cn(
              "m-0 mt-1.5 text-[13px] leading-[1.6] [text-wrap:pretty]",
              e.e_comentario ? "text-texto" : "text-texto-suave",
            )}
          >
            {e.texto}
          </p>
        )}

        {(e.tipo === "lote_importado" || e.tipo === "lote_reclassificado") && (
          <div className="mt-2 flex flex-wrap gap-2">
            {typeof e.dados.arquivos === "number" && (
              <Etiqueta tom="info">{numero(e.dados.arquivos)} arquivos</Etiqueta>
            )}
            {typeof e.dados.uteis === "number" && (
              <Etiqueta tom="info">{numero(e.dados.uteis)} para a CAT</Etiqueta>
            )}
            {typeof e.dados.bytes === "number" && (
              <Etiqueta tom="neutro">{tamanho(e.dados.bytes)}</Etiqueta>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

/* ------------------------------------------------------------------ */

function Composer({
  autor,
  aoEnviar,
  aoFalhar,
}: {
  autor: string;
  aoEnviar: (texto: string) => Promise<void>;
  aoFalhar: (mensagem: string) => void;
}) {
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const campo = useRef<HTMLTextAreaElement>(null);

  async function enviar() {
    const limpo = texto.trim();
    if (!limpo || enviando) return;
    setEnviando(true);
    try {
      await aoEnviar(limpo);
      setTexto("");
    } catch (e) {
      aoFalhar(comoErro(e).message);
    } finally {
      setEnviando(false);
      campo.current?.focus();
    }
  }

  function aoTeclar(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Ctrl+Enter envia; Enter sozinho quebra linha, que é o que se espera de
    // um campo onde se escreve mais de uma frase
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      enviar();
    }
  }

  return (
    <div className="mt-4 border-t border-borda pt-4">
      <div className="flex gap-3">
        <Avatar nome={autor} id={null} tamanho={34} />
        <div className="min-w-0 flex-1">
          <textarea
            ref={campo}
            rows={2}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={aoTeclar}
            placeholder="Escreva um comentário para a equipe do projeto…"
            maxLength={2000}
            className="w-full resize-y rounded-raio border border-borda-forte bg-superficie px-3 py-2.5 text-[14px] text-texto placeholder:text-texto-fraco focus:border-borda-foco focus:outline-none"
          />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-texto-fraco">
              Ctrl + Enter envia. Comentários ficam no histórico com seu nome.
            </span>
            <Botao
              tamanho="sm"
              onClick={enviar}
              disabled={!texto.trim()}
              carregando={enviando}
            >
              Comentar
            </Botao>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function ModalComJustificativa({
  aberto,
  titulo,
  sub,
  exigeMotivo,
  rotuloConfirmar,
  aoFechar,
  aoConfirmar,
}: {
  aberto: boolean;
  titulo: string;
  sub?: ReactNode;
  exigeMotivo: boolean;
  rotuloConfirmar: string;
  aoFechar: () => void;
  aoConfirmar: (motivo: string) => Promise<void>;
}) {
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (aberto) {
      setMotivo("");
      setErro(null);
    }
  }, [aberto]);

  async function confirmar() {
    if (exigeMotivo && !motivo.trim()) {
      setErro("Diga o motivo — é o que responde a pergunta de daqui a três meses.");
      return;
    }
    setEnviando(true);
    setErro(null);
    try {
      await aoConfirmar(motivo.trim());
    } catch (e) {
      setErro(comoErro(e).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Modal
      aberto={aberto}
      aoFechar={aoFechar}
      tamanho="md"
      titulo={titulo}
      sub={sub}
      rodape={
        <>
          <p className={cn("m-0 mr-auto text-xs", erro ? "text-erro" : "text-texto-fraco")}>
            {erro ?? "Entra no histórico com o seu nome."}
          </p>
          <Botao variante="fantasma" onClick={aoFechar} disabled={enviando}>
            Cancelar
          </Botao>
          <Botao onClick={confirmar} carregando={enviando} className="shadow-acao">
            {rotuloConfirmar}
          </Botao>
        </>
      }
    >
      <label className="flex flex-col gap-1.5">
        <span className="text-[13px] font-semibold text-texto-suave">
          Justificativa{exigeMotivo ? "" : " (opcional)"}
        </span>
        <textarea
          rows={3}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          autoFocus
          maxLength={2000}
          placeholder={
            exigeMotivo
              ? "Por que o trabalho está mudando de situação?"
              : "O que motivou a transferência"
          }
          className="w-full resize-y rounded-raio border border-borda-forte bg-superficie px-3 py-2.5 text-[14px] text-texto placeholder:text-texto-fraco focus:border-borda-foco focus:outline-none"
        />
      </label>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */

function Fato({
  rotulo,
  valor,
  pessoa,
  id,
  mono,
  nota,
}: {
  rotulo: string;
  valor?: ReactNode;
  pessoa?: string | null;
  id?: number | null;
  mono?: boolean;
  nota?: string;
}) {
  return (
    <div className="rounded-raio-g border border-borda bg-superficie-vidro px-3.5 py-3">
      <dt className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
        {rotulo}
      </dt>
      {pessoa !== undefined ? (
        <dd className="m-0 mt-1.5 flex items-center gap-2">
          <Avatar nome={pessoa} id={id ?? null} tamanho={26} />
          <span className="truncate text-sm font-bold text-texto">{pessoa ?? "—"}</span>
        </dd>
      ) : (
        <dd className={cn("m-0 mt-1 text-[15px] font-bold text-texto", mono && "font-mono")}>
          {valor}
        </dd>
      )}
      {nota && <dd className="m-0 mt-0.5 text-xs text-texto-fraco">{nota}</dd>}
    </div>
  );
}

function Contador({
  rotulo,
  valor,
  tom = "text-texto",
}: {
  rotulo: string;
  valor: number;
  tom?: string;
}) {
  return (
    <div>
      <dt className="text-[11px] font-bold uppercase tracking-[0.1em] text-texto-fraco">
        {rotulo}
      </dt>
      <dd className={cn("m-0 mt-0.5 text-[15px] font-extrabold tabular-nums", tom)}>
        {numero(valor)}
      </dd>
    </div>
  );
}

// mesmas matizes dos avatares da tela de usuários: a mesma pessoa tem sempre
// a mesma cor em todo o sistema
const MATIZES = [222, 262, 32, 190, 300, 150];

function Avatar({
  nome,
  id,
  tamanho,
}: {
  nome: string | null | undefined;
  id: number | null;
  tamanho: number;
}) {
  const semente = id ?? (nome ?? "").length;
  const h = MATIZES[semente % MATIZES.length];
  const estilo: CSSProperties = {
    width: tamanho,
    height: tamanho,
    background: `linear-gradient(140deg, oklch(0.42 0.09 ${h}), oklch(0.28 0.06 ${h}))`,
    fontSize: Math.round(tamanho * 0.38),
  };
  const partes = (nome ?? "").trim().split(/\s+/).filter(Boolean);
  const iniciais = (partes[0]?.[0] ?? "?") + (partes[1]?.[0] ?? "");

  return (
    <span
      aria-hidden
      style={estilo}
      className="flex shrink-0 items-center justify-center rounded-raio-g border border-white/10 font-extrabold uppercase text-white"
    >
      {iniciais}
    </span>
  );
}

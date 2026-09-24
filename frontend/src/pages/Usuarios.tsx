import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type FormEvent,
  type ReactNode,
} from "react";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { BotaoIcone } from "@/components/ui/BotaoIcone";
import { Campo, Entrada } from "@/components/ui/Campo";
import type { Segmento } from "@/services/segmentos";
import {
  ChipsDeSegmento,
  PilulasDeSegmento,
  useCatalogoDeSegmentos,
} from "@/components/shared/SegmentosDoUsuario";
import { Carregando } from "@/components/ui/Carregando";
import { Combobox, type OpcaoDeCombobox } from "@/components/ui/Combobox";
import { Etiqueta, type TomDeEtiqueta } from "@/components/ui/Etiqueta";
import {
  Busca,
  Contador,
  Segmentado,
  Toolbar,
} from "@/components/ui/Filtros";
import { Modal } from "@/components/ui/Modal";
import {
  CabecalhoDePagina,
  Metrica,
  Metricas,
  Vazio,
} from "@/components/ui/Pagina";
import {
  IconeChave,
  IconeConfirma,
  IconeCopiar,
  IconeEmpresa,
  IconeDesativar,
  IconeDesbloquear,
  IconeEditar,
  IconeEnergia,
  IconeFechar,
  IconeNovo,
  IconeReativar,
} from "@/constants/icons";
import {
  CARGOS,
  ENXERGA_TODOS_OS_SEGMENTOS,
  enxergaTodasAsEmpresas,
  ORDEM_CARGOS,
  ORDEM_PAPEIS,
  PAPEIS,
} from "@/constants/roles";
import { definirSegmentos } from "@/services/segmentos";
import { useAuth } from "@/hooks/useAuth";
import { useConfirm } from "@/hooks/useConfirm";
import { useToast } from "@/hooks/useToast";
import { cn } from "@/lib/cn";
import { comoErro } from "@/lib/errors";
import { dataHora } from "@/lib/format";
import {
  alterarCargo,
  alterarDados,
  alterarPapel,
  criarUsuario,
  definirAcessoAEmpresas,
  definirSituacao,
  desbloquear,
  lerAcessoAEmpresas,
  listarUsuarios,
  redefinirSenha,
  type AcessoAEmpresa,
} from "@/services/usuarios";
import type { Cargo, Papel, UsuarioResumo } from "@/types/auth";
import type { ErroApi } from "@/types/erro";

/* ------------------------------------------------------------------ */
/* domínio da tela                                                     */
/* ------------------------------------------------------------------ */

type Filtro = "todos" | "ativos" | "provisorios" | "inativos";

const FILTROS: { chave: Filtro; rotulo: string }[] = [
  { chave: "todos", rotulo: "Todos" },
  { chave: "ativos", rotulo: "Ativos" },
  { chave: "provisorios", rotulo: "Provisórios" },
  { chave: "inativos", rotulo: "Inativos" },
];

const OPCOES_DE_PAPEL: OpcaoDeCombobox<Papel>[] = ORDEM_PAPEIS.map((p) => ({
  valor: p,
  rotulo: PAPEIS[p].rotulo,
}));
const OPCOES_DE_CARGO: OpcaoDeCombobox<Cargo>[] = ORDEM_CARGOS.map((c) => ({
  valor: c,
  rotulo: CARGOS[c],
}));

/** O que se diz da pessoa numa linha: uma situação só, na ordem de
 *  importância. Inativo prevalece; depois bloqueio; depois senha provisória. */
function situacaoDe(u: UsuarioResumo): { rotulo: string; tom: TomDeEtiqueta } {
  if (!u.ativo) return { rotulo: "Inativo", tom: "neutro" };
  if (u.bloqueado) return { rotulo: `Bloqueado · ${u.tentativas_falhas} tentativas`, tom: "erro" };
  if (u.senha_provisoria) return { rotulo: "Senha provisória", tom: "atencao" };
  return { rotulo: "Ativo", tom: "sucesso" };
}

function passaNoFiltro(u: UsuarioResumo, filtro: Filtro): boolean {
  switch (filtro) {
    case "ativos":
      return u.ativo && !u.senha_provisoria;
    case "provisorios":
      return u.ativo && u.senha_provisoria;
    case "inativos":
      return !u.ativo;
    default:
      return true;
  }
}

function passaNaBusca(u: UsuarioResumo, termo: string): boolean {
  if (!termo) return true;
  const t = termo.toLocaleLowerCase("pt-BR");
  return [u.usuario, u.nome_exibicao, u.email].some((c) =>
    c.toLocaleLowerCase("pt-BR").includes(t),
  );
}

/** Um recado no topo da tela: senha gerada, ação concluída. */
interface Flash {
  titulo: string;
  texto: string;
  segredo?: string;
}

/* ------------------------------------------------------------------ */
/* a tela                                                              */
/* ------------------------------------------------------------------ */

export default function Usuarios() {
  const { usuario: eu } = useAuth();
  const confirmar = useConfirm();
  const toast = useToast();

  const catalogo = useCatalogoDeSegmentos();
  const [usuarios, setUsuarios] = useState<UsuarioResumo[] | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [busca, setBusca] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [flash, setFlash] = useState<Flash | null>(null);
  const [criando, setCriando] = useState(false);
  const [editando, setEditando] = useState<UsuarioResumo | null>(null);
  const [dandoAcesso, setDandoAcesso] = useState<UsuarioResumo | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);

  const carregar = useCallback(async () => {
    try {
      setUsuarios(await listarUsuarios());
      setErro(null);
    } catch (e) {
      setErro(comoErro(e));
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const metricas = useMemo(() => {
    const lista = usuarios ?? [];
    return {
      total: lista.length,
      ativos: lista.filter((u) => u.ativo && !u.senha_provisoria).length,
      provisorios: lista.filter((u) => u.ativo && u.senha_provisoria).length,
      inativos: lista.filter((u) => !u.ativo).length,
    };
  }, [usuarios]);

  const visiveis = useMemo(
    () => (usuarios ?? []).filter((u) => passaNoFiltro(u, filtro) && passaNaBusca(u, busca)),
    [usuarios, filtro, busca],
  );

  /** Envolve toda ação de linha: marca ocupado, mostra erro, recarrega. */
  async function agir(u: UsuarioResumo, acao: () => Promise<Flash | void>) {
    setOcupado(u.id);
    try {
      const recado = await acao();
      if (recado) setFlash(recado);
      await carregar();
    } catch (e) {
      const err = comoErro(e);
      toast.mostrar({ tom: "erro", titulo: err.message, codigo: err.requisicaoId });
    } finally {
      setOcupado(null);
    }
  }

  async function aoRedefinir(u: UsuarioResumo) {
    const ok = await confirmar({
      icone: IconeChave,
      tom: "destaque",
      titulo: `Gerar nova senha provisória para ${u.nome_exibicao}?`,
      texto: "A senha atual deixa de funcionar na hora, e a nova aparece uma única vez.",
      rotuloConfirmar: "Gerar senha",
    });
    if (!ok) return;
    await agir(u, async () => {
      const r = await redefinirSenha(u.id);
      return {
        titulo: `Senha provisória de ${u.nome_exibicao}`,
        texto: "Entregue à pessoa. A troca é obrigatória no primeiro acesso, e a senha não é exibida de novo.",
        segredo: r.senha_provisoria,
      };
    });
  }

  async function aoAlternarSituacao(u: UsuarioResumo) {
    const ok = u.ativo
      ? await confirmar({
          icone: IconeDesativar,
          tom: "perigo",
          titulo: `Desativar ${u.nome_exibicao}?`,
          texto: "O acesso é bloqueado imediatamente. O histórico do usuário é preservado.",
          rotuloConfirmar: "Desativar",
          variante: "perigo",
        })
      : await confirmar({
          icone: IconeReativar,
          tom: "sucesso",
          titulo: `Reativar ${u.nome_exibicao}?`,
          texto: "O usuário volta a acessar o sistema com a senha que tinha — ou com uma provisória, se você redefinir.",
          rotuloConfirmar: "Reativar",
        });
    if (!ok) return;
    await agir(u, async () => {
      await definirSituacao(u.id, !u.ativo);
      return u.ativo
        ? { titulo: `${u.nome_exibicao} desativado`, texto: "O acesso foi bloqueado. Reative quando precisar." }
        : { titulo: `${u.nome_exibicao} reativado`, texto: "O acesso está liberado de novo." };
    });
  }

  async function aoDesbloquear(u: UsuarioResumo) {
    await agir(u, async () => {
      await desbloquear(u.id);
      return { titulo: `${u.nome_exibicao} desbloqueado`, texto: "As tentativas falhas foram zeradas." };
    });
  }

  // Depois dos hooks, de propósito: um return antes deles mudaria a quantidade
  // de hooks entre renders. A rota só chega aqui autenticada; o null é do tipo.
  if (!eu) return null;

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4">
      <CabecalhoDePagina
        eyebrow="Administração"
        titulo="Usuários"
        sub="Cadastro e redefinição de senha ficam com gestores. Não há autocadastro nem recuperação por e-mail."
        acao={
          <Botao icone={IconeNovo} onClick={() => setCriando(true)} className="shadow-acao">
            Novo usuário
          </Botao>
        }
      >
        <Metricas>
          <Metrica rotulo="Total" valor={metricas.total} />
          <Metrica rotulo="Ativos" valor={metricas.ativos} tom="sucesso" />
          <Metrica rotulo="Senha provisória" valor={metricas.provisorios} tom="atencao" />
          <Metrica rotulo="Inativos" valor={metricas.inativos} />
        </Metricas>
      </CabecalhoDePagina>

      {erro && (
        <Aviso
          titulo={erro.message}
          codigo={erro.requisicaoId}
          acao={
            <Botao tamanho="sm" variante="secundario" onClick={carregar}>
              Tentar de novo
            </Botao>
          }
        />
      )}

      {flash && <FlashBanner flash={flash} aoFechar={() => setFlash(null)} />}

      <section className="overflow-hidden rounded-cartao border border-borda bg-superficie shadow-cat">
        <Toolbar>
          <Busca
            valor={busca}
            aoMudar={setBusca}
            placeholder="Buscar por usuário, nome ou e-mail"
          />
          <Segmentado
            rotulo="Filtrar por situação"
            opcoes={FILTROS}
            valor={filtro}
            aoMudar={setFiltro}
          />
          <Contador quantos={visiveis.length} singular="usuário" plural="usuários" />
        </Toolbar>

        {!usuarios ? (
          <Carregando texto="Carregando usuários…" />
        ) : visiveis.length === 0 ? (
          <Vazio titulo="Nenhum usuário encontrado">
            Ajuste a busca ou o filtro de situação.
          </Vazio>
        ) : (
          <div className="overflow-x-auto">
            <div role="table" aria-label="Usuários">
              <div role="row" className={cn(GRADE, "border-b border-borda bg-tabela-cabecalho-fundo px-4 py-3")}>
                {["Nome", "Usuário", "Papel", "Cargo", "Segmentos", "Situação", "Último acesso", "Ações"].map(
                  (c, i) => (
                    <div
                      key={c}
                      role="columnheader"
                      className={cn(
                        "text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto",
                        i === 7 && "text-right",
                      )}
                    >
                      {c}
                    </div>
                  ),
                )}
              </div>
              {visiveis.map((u) => (
                <Linha
                  key={u.id}
                  u={u}
                  catalogo={catalogo}
                  souEu={u.id === eu.id}
                  ocupado={ocupado === u.id}
                  aoEditar={() => setEditando(u)}
                  aoDarAcesso={() => setDandoAcesso(u)}
                  aoRedefinir={() => aoRedefinir(u)}
                  aoAlternarSituacao={() => aoAlternarSituacao(u)}
                  aoDesbloquear={() => aoDesbloquear(u)}
                />
              ))}
            </div>
          </div>
        )}
      </section>

      <ModalNovo
        aberto={criando}
        aoFechar={() => setCriando(false)}
        aoCriado={(nome, senha) => {
          setCriando(false);
          setFlash({
            titulo: `${nome} criado`,
            texto: "Entregue a senha provisória à pessoa. A troca é obrigatória no primeiro acesso, e a senha não é exibida de novo.",
            segredo: senha,
          });
          carregar();
        }}
      />

      <ModalDeAcesso
        usuario={dandoAcesso}
        souEu={dandoAcesso?.id === eu.id}
        aoFechar={() => setDandoAcesso(null)}
        aoSalvo={(mudanca) => {
          setDandoAcesso(null);
          const partes = [
            mudanca.concedidas.length && `${mudanca.concedidas.length} concedida(s)`,
            mudanca.encerradas.length && `${mudanca.encerradas.length} encerrada(s)`,
          ].filter(Boolean);
          if (partes.length) toast.sucesso("Acesso atualizado", partes.join(" · "));
          carregar();
        }}
      />

      <ModalEditar
        usuario={editando}
        souEu={editando?.id === eu.id}
        aoFechar={() => setEditando(null)}
        aoSalvo={(u) => {
          setEditando(null);
          setFlash({
            titulo: `${u.nome_exibicao} atualizado`,
            texto: `Papel: ${PAPEIS[u.papel].rotulo} · Cargo: ${CARGOS[u.cargo]}. Alterações de papel valem no próximo acesso.`,
          });
          carregar();
        }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* flash                                                               */
/* ------------------------------------------------------------------ */

function FlashBanner({ flash, aoFechar }: { flash: Flash; aoFechar: () => void }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <div
      role="status"
      className={cn(
        "flex gap-3.5 rounded-[14px] border border-laranja-500/35 p-4 animate-entrada",
        "bg-[linear-gradient(100deg,color-mix(in_srgb,var(--marca-laranja)_14%,transparent),color-mix(in_srgb,var(--marca-laranja)_3%,transparent))]",
      )}
    >
      <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-raio-g bg-laranja-500/20 text-laranja-700 escuro:text-laranja-300">
        <IconeChave size={16} strokeWidth={2} aria-hidden />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <strong className="text-[13px] font-bold text-texto">{flash.titulo}</strong>
        <span className="text-[13px] text-texto-suave">{flash.texto}</span>
        {flash.segredo && (
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <code className="rounded-[9px] border border-dashed border-laranja-500/50 bg-black/40 px-3.5 py-2 font-mono text-[15px] tracking-[0.06em] text-laranja-200">
              {flash.segredo}
            </code>
            <Botao
              tamanho="sm"
              variante="secundario"
              icone={IconeCopiar}
              onClick={() =>
                navigator.clipboard.writeText(flash.segredo ?? "").then(
                  () => {
                    setCopiado(true);
                    window.setTimeout(() => setCopiado(false), 2000);
                  },
                  () => {
                    /* sem permissão de área de transferência: a senha está à vista */
                  },
                )
              }
            >
              {copiado ? "Copiado" : "Copiar"}
            </Botao>
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={aoFechar}
        title="Dispensar"
        aria-label="Dispensar"
        className="-mr-1 -mt-1 h-7 w-7 shrink-0 cursor-pointer rounded border-0 bg-transparent text-texto-fraco hover:text-texto"
      >
        <IconeFechar size={15} strokeWidth={2} className="mx-auto" aria-hidden />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* linha                                                               */
/* ------------------------------------------------------------------ */

/**
 * A grade da tabela: proporção para dividir a sobra, mínimo para não espremer.
 *
 * O mínimo está em cada coluna, e não numa largura fixa da tabela inteira.
 * Com `min-w-[1240px]` a barra de rolagem aparecia sempre que o card ficava um
 * pixel abaixo disso — e ela aparecia sem ter o que rolar, que é o pior tipo
 * de barra: ocupa espaço, chama atenção e não leva a lugar nenhum.
 *
 * Agora a largura mínima da tabela é a soma dos mínimos das colunas. Ela rola
 * quando não cabe de verdade — em janela estreita — e fica quieta quando cabe.
 *
 * A coluna de segmentos entra entre Cargo e Situação, como o handoff pede.
 */
// em uma linha só de propósito: o Tailwind lê o texto do arquivo, e classe
// montada por concatenação não chega a existir no CSS
// prettier-ignore
const GRADE = "grid items-center gap-3 grid-cols-[minmax(190px,1.4fr)_minmax(120px,.9fr)_minmax(80px,.7fr)_minmax(100px,.8fr)_minmax(110px,1.1fr)_minmax(95px,.9fr)_minmax(130px,.9fr)_minmax(160px,1.3fr)]";

// matizes que se revezam nos avatares; o id decide, então a mesma pessoa
// tem sempre a mesma cor
const MATIZES = [222, 262, 32, 190, 300, 150];

function estiloDoAvatar(id: number): CSSProperties {
  const h = MATIZES[id % MATIZES.length];
  return {
    background: `linear-gradient(140deg, oklch(0.42 0.09 ${h}), oklch(0.28 0.06 ${h}))`,
  };
}

function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/).filter(Boolean);
  return (partes[0]?.[0] ?? "") + (partes[1]?.[0] ?? "");
}

function Linha({
  u,
  catalogo,
  souEu,
  ocupado,
  aoEditar,
  aoDarAcesso,
  aoRedefinir,
  aoAlternarSituacao,
  aoDesbloquear,
}: {
  u: UsuarioResumo;
  catalogo: Segmento[];
  souEu: boolean;
  ocupado: boolean;
  aoEditar: () => void;
  aoDarAcesso: () => void;
  aoRedefinir: () => void;
  aoAlternarSituacao: () => void;
  aoDesbloquear: () => void;
}) {
  const situacao = situacaoDe(u);
  return (
    <div
      role="row"
      className={cn(
        GRADE,
        "border-b border-borda-sutil px-4 py-3.5 transition-colors hover:bg-tabela-linha-hover",
        !u.ativo && "opacity-60",
      )}
    >
      <div role="cell" className="flex min-w-0 items-center gap-3">
        <div
          aria-hidden
          style={estiloDoAvatar(u.id)}
          className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-raio-g border border-white/10 text-xs font-extrabold uppercase text-white"
        >
          {iniciais(u.nome_exibicao)}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-bold text-texto">{u.nome_exibicao}</div>
          <div className="truncate text-xs text-texto-fraco">{u.email}</div>
        </div>
      </div>

      <div role="cell" className="flex min-w-0 items-center gap-2">
        <code className="truncate font-mono text-[13px] text-texto-suave">{u.usuario}</code>
        {souEu && (
          <span className="shrink-0 rounded-[5px] border border-laranja-500/35 bg-laranja-500/16 px-1.5 py-0.5 text-[9px] font-extrabold tracking-[0.1em] text-laranja-800 escuro:text-laranja-300">
            VOCÊ
          </span>
        )}
      </div>

      <div role="cell" className="text-[13px] font-semibold text-texto" title={PAPEIS[u.papel].ajuda}>
        {PAPEIS[u.papel].rotulo}
      </div>
      <div role="cell" className="text-[13px] text-texto-suave">
        {CARGOS[u.cargo]}
      </div>
      <div role="cell" className="min-w-0">
        <PilulasDeSegmento segmentos={u.segmentos} catalogo={catalogo} papel={u.papel} />
      </div>
      <div role="cell">
        <Etiqueta tom={situacao.tom} pulso={u.ativo}>
          {situacao.rotulo}
        </Etiqueta>
      </div>
      <div role="cell" className="text-[13px] text-texto-suave">
        {dataHora(u.ultimo_acesso, "nunca entrou")}
      </div>

      <div role="cell" className="flex items-center justify-end gap-2">
        {u.bloqueado && (
          <BotaoIcone
            icone={IconeDesbloquear}
            rotulo="Desbloquear"
            tom="neutro"
            disabled={ocupado}
            onClick={aoDesbloquear}
          />
        )}
        <BotaoIcone
          icone={IconeEditar}
          rotulo="Editar"
          tom="destaque"
          disabled={ocupado}
          onClick={aoEditar}
        />
        <BotaoIcone
          icone={IconeEmpresa}
          rotulo={
            enxergaTodasAsEmpresas(u.papel)
              ? "Enxerga todas as empresas pelo papel"
              : u.empresas.length === 0
                ? "Sem acesso a nenhuma empresa — conceder"
                : `Acesso a ${u.empresas.length} empresa(s)`
          }
          // sem empresa a pessoa não enxerga trabalho nenhum: o botão chama
          // atenção em vez de esperar que alguém descubra. Para gestor e dev
          // a contagem não quer dizer nada — o papel já os deixa ver tudo
          tom={
            !enxergaTodasAsEmpresas(u.papel) && u.empresas.length === 0
              ? "perigo"
              : "neutro"
          }
          disabled={ocupado}
          onClick={aoDarAcesso}
        />
        <BotaoIcone
          icone={IconeChave}
          rotulo="Redefinir senha"
          tom="neutro"
          disabled={ocupado}
          carregando={ocupado}
          onClick={aoRedefinir}
        />
        <BotaoIcone
          icone={IconeEnergia}
          rotulo={souEu ? "Você não pode desativar a si mesmo" : u.ativo ? "Desativar" : "Reativar"}
          tom={u.ativo ? "perigo" : "sucesso"}
          disabled={ocupado || souEu}
          onClick={aoAlternarSituacao}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* modal: novo usuário                                                 */
/* ------------------------------------------------------------------ */

const RE_USUARIO = /^[a-z0-9._-]{3,}$/;
const RE_EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function ModalNovo({
  aberto,
  aoFechar,
  aoCriado,
}: {
  aberto: boolean;
  aoFechar: () => void;
  aoCriado: (nome: string, senha: string) => void;
}) {
  const catalogo = useCatalogoDeSegmentos();
  const [usuario, setUsuario] = useState("");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [papel, setPapel] = useState<Papel>("leitura");
  const [cargo, setCargo] = useState<Cargo>("analista");
  const [segmentos, setSegmentos] = useState<string[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  // cada abertura começa limpa: o formulário anterior não vaza para o próximo
  useEffect(() => {
    if (!aberto) return;
    setUsuario("");
    setNome("");
    setEmail("");
    setPapel("leitura");
    setCargo("analista");
    setSegmentos([]);
    setErro(null);
  }, [aberto]);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    const u = usuario.trim();
    if (!RE_USUARIO.test(u)) {
      setErro("Nome de usuário inválido: mínimo 3 caracteres, minúsculas, números, ponto, hífen ou sublinhado.");
      return;
    }
    if (!nome.trim()) {
      setErro("Informe o nome completo.");
      return;
    }
    if (!RE_EMAIL.test(email.trim())) {
      setErro("Informe um e-mail válido.");
      return;
    }
    // sem segmento a pessoa entra e não vê trabalho algum — e não saberia por
    // quê. Quem enxerga tudo pelo papel não tem escolha a fazer
    if (!ENXERGA_TODOS_OS_SEGMENTOS.includes(papel) && segmentos.length === 0) {
      setErro("Libere ao menos um segmento.");
      return;
    }
    setErro(null);
    setEnviando(true);
    try {
      const r = await criarUsuario({
        usuario: u,
        email: email.trim(),
        nome_exibicao: nome.trim(),
        papel,
        cargo,
      });
      // criar e liberar são dois recursos na API: o usuário nasce sem segmento
      // e recebe os dele em seguida
      if (segmentos.length > 0 && !ENXERGA_TODOS_OS_SEGMENTOS.includes(papel)) {
        await definirSegmentos(r.usuario.id, segmentos);
      }
      aoCriado(r.usuario.nome_exibicao, r.senha_provisoria);
    } catch (err) {
      setErro(comoErro(err).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Modal
      aberto={aberto}
      aoFechar={aoFechar}
      tamanho="lg"
      titulo="Novo usuário"
      sub="A senha é gerada pelo sistema e aparece uma única vez. A troca é obrigatória no primeiro acesso."
      rodape={
        <Rodape
          erro={erro}
          padrao="A senha provisória é exibida após a criação."
          enviando={enviando}
          aoCancelar={aoFechar}
          rotulo="Criar usuário"
          formulario="form-novo-usuario"
        />
      }
    >
      <form id="form-novo-usuario" onSubmit={enviar} noValidate className={GRADE_DO_FORMULARIO}>
        <Campo
          rotulo="Nome de usuário"
          dica="Não pode ser alterado depois. Minúsculas, números, ponto, hífen e sublinhado."
        >
          {(props) => (
            <Entrada
              {...props}
              mono
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              placeholder="ana.silva"
              autoCapitalize="none"
              autoComplete="off"
              spellCheck={false}
              autoFocus
            />
          )}
        </Campo>
        <Campo rotulo="Nome completo">
          {(props) => (
            <Entrada {...props} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ana Silva" />
          )}
        </Campo>
        <Campo rotulo="E-mail">
          {(props) => (
            <Entrada
              {...props}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ana.silva@bms.local"
              autoComplete="off"
            />
          )}
        </Campo>
        <Campo rotulo="Papel" dica={PAPEIS[papel].ajuda}>
          {(props) => <Combobox {...props} valor={papel} opcoes={OPCOES_DE_PAPEL} aoMudar={setPapel} />}
        </Campo>
        <Campo rotulo="Cargo" dica="Posição na empresa. Não define permissão.">
          {(props) => <Combobox {...props} valor={cargo} opcoes={OPCOES_DE_CARGO} aoMudar={setCargo} />}
        </Campo>
        <div className="sm:col-span-2">
          <Campo rotulo="Segmentos liberados">
            {() => (
              <ChipsDeSegmento
                catalogo={catalogo}
                escolhidos={segmentos}
                aoMudar={setSegmentos}
                papel={papel}
              />
            )}
          </Campo>
        </div>
      </form>
    </Modal>
  );
}

/** Dois conjuntos iguais, sem depender da ordem em que vieram. */
function mesmoConjunto(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((x) => b.includes(x));
}

/* ------------------------------------------------------------------ */
/* modal: editar usuário                                               */
/* ------------------------------------------------------------------ */

function ModalEditar({
  usuario,
  souEu,
  aoFechar,
  aoSalvo,
}: {
  usuario: UsuarioResumo | null;
  souEu: boolean;
  aoFechar: () => void;
  aoSalvo: (u: UsuarioResumo) => void;
}) {
  const catalogo = useCatalogoDeSegmentos();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [papel, setPapel] = useState<Papel>("leitura");
  const [cargo, setCargo] = useState<Cargo>("analista");
  const [segmentos, setSegmentos] = useState<string[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!usuario) return;
    setNome(usuario.nome_exibicao);
    setEmail(usuario.email);
    setPapel(usuario.papel);
    setCargo(usuario.cargo);
    setSegmentos(usuario.segmentos);
    setErro(null);
  }, [usuario]);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!usuario) return;
    if (!nome.trim()) {
      setErro("Informe o nome completo.");
      return;
    }
    if (!RE_EMAIL.test(email.trim())) {
      setErro("Informe um e-mail válido.");
      return;
    }
    // quem não enxerga tudo pelo papel precisa de ao menos um segmento: sem
    // nenhum, a pessoa entra e não vê trabalho algum — e não saberia por quê
    if (!ENXERGA_TODOS_OS_SEGMENTOS.includes(papel) && segmentos.length === 0) {
      setErro("Libere ao menos um segmento.");
      return;
    }
    setErro(null);
    setEnviando(true);
    try {
      // quatro recursos na API, um formulário na tela: só vai o que mudou
      let atual = usuario;
      if (nome.trim() !== usuario.nome_exibicao || email.trim() !== usuario.email) {
        atual = await alterarDados(usuario.id, { nome_exibicao: nome.trim(), email: email.trim() });
      }
      if (papel !== usuario.papel) atual = await alterarPapel(usuario.id, papel);
      if (cargo !== usuario.cargo) atual = await alterarCargo(usuario.id, cargo);
      if (!mesmoConjunto(segmentos, usuario.segmentos)) {
        await definirSegmentos(usuario.id, segmentos);
        atual = { ...atual, segmentos };
      }
      aoSalvo(atual);
    } catch (err) {
      setErro(comoErro(err).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Modal
      aberto={usuario !== null}
      aoFechar={aoFechar}
      tamanho="md"
      titulo="Editar usuário"
      sub={
        <>
          Nome de usuário <code className="font-mono">{usuario?.usuario}</code> não pode ser alterado.
        </>
      }
      rodape={
        <Rodape
          erro={erro}
          padrao="Alterações de papel valem no próximo acesso do usuário."
          enviando={enviando}
          aoCancelar={aoFechar}
          rotulo="Salvar alterações"
          formulario="form-editar-usuario"
        />
      }
    >
      <form id="form-editar-usuario" onSubmit={enviar} noValidate className={GRADE_DO_FORMULARIO}>
        <Campo rotulo="Nome completo">
          {(props) => <Entrada {...props} value={nome} onChange={(e) => setNome(e.target.value)} autoFocus />}
        </Campo>
        <Campo rotulo="E-mail">
          {(props) => (
            <Entrada {...props} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          )}
        </Campo>
        <Campo
          rotulo="Papel"
          dica={souEu ? "Você não pode alterar seu próprio papel." : PAPEIS[papel].ajuda}
        >
          {(props) => (
            <Combobox {...props} valor={papel} opcoes={OPCOES_DE_PAPEL} aoMudar={setPapel} disabled={souEu} />
          )}
        </Campo>
        <Campo rotulo="Cargo" dica="Posição na empresa. Não define permissão.">
          {(props) => <Combobox {...props} valor={cargo} opcoes={OPCOES_DE_CARGO} aoMudar={setCargo} />}
        </Campo>
        <div className="sm:col-span-2">
          <Campo rotulo="Segmentos liberados">
            {() => (
              <ChipsDeSegmento
                catalogo={catalogo}
                escolhidos={segmentos}
                aoMudar={setSegmentos}
                papel={papel}
              />
            )}
          </Campo>
        </div>
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* modal: acesso às empresas                                           */
/* ------------------------------------------------------------------ */

/**
 * A que empresas esta pessoa tem acesso.
 *
 * É daqui que sai o escopo de visibilidade do sistema: sem alocação, a
 * pessoa entra e não vê trabalho nenhum. Até esta tela existir, a alocação
 * só nascia de quem cadastrava a empresa pelo SPED.
 */
function ModalDeAcesso({
  usuario,
  souEu,
  aoFechar,
  aoSalvo,
}: {
  usuario: UsuarioResumo | null;
  souEu: boolean;
  aoFechar: () => void;
  aoSalvo: (mudanca: { concedidas: string[]; encerradas: string[] }) => void;
}) {
  const [empresas, setEmpresas] = useState<AcessoAEmpresa[] | null>(null);
  const [escolhidas, setEscolhidas] = useState<number[]>([]);
  const [busca, setBusca] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!usuario) return;
    setEmpresas(null);
    setBusca("");
    setErro(null);
    lerAcessoAEmpresas(usuario.id)
      .then((lista) => {
        setEmpresas(lista);
        setEscolhidas(lista.filter((e) => e.tem_acesso).map((e) => e.empresa_id));
      })
      .catch((e) => setErro(comoErro(e).message));
  }, [usuario]);

  const visiveis = (empresas ?? []).filter((e) =>
    e.razao_social.toLocaleLowerCase("pt-BR").includes(busca.toLocaleLowerCase("pt-BR")),
  );
  const originais = new Set(
    (empresas ?? []).filter((e) => e.tem_acesso).map((e) => e.empresa_id),
  );
  const todasMarcadas =
    visiveis.length > 0 && visiveis.every((e) => escolhidas.includes(e.empresa_id));
  const mudou =
    escolhidas.length !== originais.size ||
    escolhidas.some((id) => !originais.has(id));

  async function salvar() {
    if (!usuario) return;
    setEnviando(true);
    setErro(null);
    try {
      aoSalvo(await definirAcessoAEmpresas(usuario.id, escolhidas));
    } catch (e) {
      setErro(comoErro(e).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Modal
      aberto={usuario !== null}
      aoFechar={aoFechar}
      tamanho="md"
      titulo={`Acesso às empresas de ${usuario?.nome_exibicao ?? ""}`}
      sub="Sem empresa, a pessoa entra no sistema e não vê trabalho nenhum. Tirar o acesso não apaga o histórico: ele registra até quando ela teve."
      rodape={
        <>
          <p className={cn("m-0 mr-auto text-xs", erro ? "text-erro" : "text-texto-fraco")}>
            {erro ??
              (souEu
                ? "Você não pode tirar o seu próprio acesso — peça a outro gestor."
                : `${escolhidas.length} de ${empresas?.length ?? 0} empresa(s)`)}
          </p>
          <Botao variante="fantasma" onClick={aoFechar} disabled={enviando}>
            Cancelar
          </Botao>
          <Botao
            onClick={salvar}
            carregando={enviando}
            disabled={!mudou}
            className="shadow-acao"
          >
            Salvar acesso
          </Botao>
        </>
      }
    >
      {usuario && enxergaTodasAsEmpresas(usuario.papel) && (
        <Aviso tom="atencao" className="mb-4">
          Contas <strong>{PAPEIS[usuario.papel].rotulo.toLowerCase()}</strong> enxergam
          todas as empresas por definição do papel — alocação aqui não muda nada
          para elas.
        </Aviso>
      )}

      {empresas === null ? (
        <Carregando texto="Carregando empresas…" />
      ) : empresas.length === 0 ? (
        <Vazio titulo="Nenhuma empresa cadastrada ainda">
          O cadastro de empresa começa pelo SPED, na tela de Cadastro.
        </Vazio>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {empresas.length > 8 && (
              <Busca valor={busca} aoMudar={setBusca} placeholder="Buscar empresa" />
            )}
            {/* um controle só para os dois gestos: com busca ativa, vale
                para o que está à vista, que é o que a pessoa está olhando */}
            <Botao
              tamanho="sm"
              variante="secundario"
              className="ml-auto"
              disabled={visiveis.length === 0 || (todasMarcadas && souEu)}
              title={
                todasMarcadas && souEu
                  ? "Você não pode tirar o seu próprio acesso"
                  : undefined
              }
              onClick={() =>
                setEscolhidas((atuais) => {
                  const ids = visiveis.map((e) => e.empresa_id);
                  return todasMarcadas
                    ? atuais.filter((i) => !ids.includes(i))
                    : [...new Set([...atuais, ...ids])];
                })
              }
            >
              {todasMarcadas ? "Desmarcar todas" : "Marcar todas"}
              {busca && ` (${visiveis.length})`}
            </Botao>
          </div>
          <ul className="m-0 flex max-h-[340px] list-none flex-col gap-1.5 overflow-y-auto p-0">
            {visiveis.map((e) => {
              const marcada = escolhidas.includes(e.empresa_id);
              return (
                <li key={e.empresa_id}>
                  <label
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-raio-g border px-3.5 py-2.5",
                      "transition-colors focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-borda-foco",
                      marcada
                        ? "border-laranja-500/45 bg-laranja-500/10"
                        : "border-borda bg-superficie-vidro hover:border-texto-fraco",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={marcada}
                      onChange={() =>
                        setEscolhidas((atuais) =>
                          atuais.includes(e.empresa_id)
                            ? atuais.filter((i) => i !== e.empresa_id)
                            : [...atuais, e.empresa_id],
                        )
                      }
                      className="sr-only"
                    />
                    <span
                      aria-hidden
                      className={cn(
                        "flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border",
                        marcada
                          ? "border-marca-laranja bg-marca-laranja text-acao-texto"
                          : "border-texto-fraco",
                      )}
                    >
                      {marcada && <IconeConfirma size={11} strokeWidth={3} />}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-texto">
                      {e.razao_social}
                    </span>
                    {e.uf && (
                      <span className="shrink-0 rounded border border-borda px-1.5 py-0.5 text-[11px] font-bold text-texto-fraco">
                        {e.uf}
                      </span>
                    )}
                  </label>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Modal>
  );
}

const GRADE_DO_FORMULARIO = "grid grid-cols-[repeat(auto-fit,minmax(230px,1fr))] gap-[18px]";

/** Rodapé dos dois modais: mensagem à esquerda, botões à direita. O botão
 *  de enviar fica fora do <form> (está no rodapé do Modal), por isso o
 *  atributo `form`. */
function Rodape({
  erro,
  padrao,
  enviando,
  aoCancelar,
  rotulo,
  formulario,
}: {
  erro: string | null;
  padrao: ReactNode;
  enviando: boolean;
  aoCancelar: () => void;
  rotulo: string;
  formulario: string;
}) {
  return (
    <>
      <p
        role={erro ? "alert" : undefined}
        className={cn("m-0 mr-auto text-xs", erro ? "text-erro" : "text-texto-fraco")}
      >
        {erro ?? padrao}
      </p>
      <Botao variante="fantasma" onClick={aoCancelar} disabled={enviando}>
        Cancelar
      </Botao>
      <Botao type="submit" form={formulario} carregando={enviando} className="shadow-acao">
        {rotulo}
      </Botao>
    </>
  );
}

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Aviso } from "@/components/ui/Aviso";
import { Botao, BotaoLink } from "@/components/ui/Botao";
import { Campo, Entrada } from "@/components/ui/Campo";
import { Carregando } from "@/components/ui/Carregando";
import { Combobox, type OpcaoDeCombobox } from "@/components/ui/Combobox";
import { Etiqueta } from "@/components/ui/Etiqueta";
import { Busca, Contador, Segmentado, Toolbar } from "@/components/ui/Filtros";
import { Modal } from "@/components/ui/Modal";
import {
  Barra,
  CabecalhoDePagina,
  Metrica,
  Metricas,
  Vazio,
} from "@/components/ui/Pagina";
import { FRENTES, type Frente } from "@/constants/fronts";
import { meusSegmentos, type Segmento } from "@/services/segmentos";
import { IconeNovo } from "@/constants/icons";
import { ROTAS } from "@/constants/routes";
import { BARRA_DO_STATUS, TOM_DO_STATUS, type Status } from "@/constants/status";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/cn";
import { compara, mascarar, paraIso, periodo, valida } from "@/lib/competencia";
import { comoErro } from "@/lib/errors";
import {
  criarProjeto,
  listarEmpresas,
  listarProjetos,
  type Empresa,
  type Projeto,
} from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/* ------------------------------------------------------------------ */

/** Os filtros da listagem. Os quatro status, mais o pré-cadastro, que não é
 *  situação do trabalho e sim da empresa — por isso vem por último. */
type Filtro = Status | "todos" | "pre_cadastro";

const FILTROS: { chave: Filtro; rotulo: string }[] = [
  { chave: "todos", rotulo: "Todos" },
  { chave: "em_andamento", rotulo: "Em andamento" },
  { chave: "pausado", rotulo: "Pausados" },
  { chave: "cancelado", rotulo: "Cancelados" },
  { chave: "concluido", rotulo: "Concluídos" },
  { chave: "pre_cadastro", rotulo: "Pré-cadastro" },
];

function passaNoFiltro(p: Projeto, f: Filtro): boolean {
  if (f === "todos") return true;
  if (f === "pre_cadastro") return p.pre_cadastro;
  return p.status === f;
}

function passaNaBusca(p: Projeto, termo: string): boolean {
  if (!termo) return true;
  const t = termo.toLocaleLowerCase("pt-BR");
  return [p.empresa, p.nome, p.frente_rotulo, p.cnpj_matriz ?? "", p.cnpj_matriz_formatado ?? ""]
    .some((c) => c.toLocaleLowerCase("pt-BR").includes(t));
}

/* ------------------------------------------------------------------ */

export default function Inicio() {
  const { usuario } = useAuth();
  const [projetos, setProjetos] = useState<Projeto[] | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [busca, setBusca] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [uf, setUf] = useState("");
  const [criando, setCriando] = useState(false);

  function carregar() {
    listarProjetos()
      .then((lista) => {
        setProjetos(lista);
        setErro(null);
      })
      .catch((e) => setErro(comoErro(e)));
  }

  useEffect(carregar, []);

  const metricas = useMemo(() => {
    const lista = projetos ?? [];
    const quantos = (s: Status) => lista.filter((p) => p.status === s).length;
    return {
      total: lista.length,
      andamento: quantos("em_andamento"),
      concluidos: quantos("concluido"),
      parados: quantos("pausado") + quantos("cancelado"),
      pausados: quantos("pausado"),
      cancelados: quantos("cancelado"),
    };
  }, [projetos]);

  // só as UFs que existem nos trabalhos: filtro que oferece opção vazia é ruído
  const ufs = useMemo<OpcaoDeCombobox<string>[]>(() => {
    const achadas = [...new Set((projetos ?? []).map((p) => p.uf).filter(Boolean))].sort();
    return [{ valor: "", rotulo: "Todas as UFs" }, ...achadas.map((u) => ({ valor: u!, rotulo: u! }))];
  }, [projetos]);

  const visiveis = useMemo(
    () =>
      (projetos ?? []).filter(
        (p) => passaNoFiltro(p, filtro) && passaNaBusca(p, busca) && (!uf || p.uf === uf),
      ),
    [projetos, filtro, busca, uf],
  );

  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-4">
      <CabecalhoDePagina
        eyebrow="Trabalhos"
        titulo={`Olá, ${usuario?.nome_exibicao ?? ""}`}
        sub="Cada cartão é um trabalho de uma empresa. Abra para ver as etapas do processamento e continuar de onde parou."
        acao={
          <Botao icone={IconeNovo} onClick={() => setCriando(true)} className="shadow-acao">
            Novo trabalho
          </Botao>
        }
      >
        <Metricas>
          <Metrica rotulo="Trabalhos" valor={metricas.total} />
          <Metrica rotulo="Em andamento" valor={metricas.andamento} tom="info" />
          <Metrica rotulo="Concluídos" valor={metricas.concluidos} tom="sucesso" />
          <Metrica
            rotulo="Pausados / cancelados"
            valor={metricas.parados}
            nota={
              metricas.parados > 0
                ? `${metricas.pausados} pausado(s), ${metricas.cancelados} cancelado(s)`
                : undefined
            }
            tom="atencao"
          />
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

      <section className="overflow-hidden rounded-cartao border border-borda bg-superficie shadow-cat">
        <Toolbar>
          <Busca valor={busca} aoMudar={setBusca} placeholder="Buscar por empresa, CNPJ ou projeto" />
          <Segmentado rotulo="Filtrar por situação" opcoes={FILTROS} valor={filtro} aoMudar={setFiltro} />
          {ufs.length > 1 && (
            <Combobox valor={uf} opcoes={ufs} aoMudar={setUf} className="w-[150px]" />
          )}
          <Contador quantos={visiveis.length} singular="trabalho" plural="trabalhos" />
        </Toolbar>

        <div className="p-4">
          {!projetos ? (
            <Carregando texto="Carregando trabalhos…" />
          ) : projetos.length === 0 ? (
            <Vazio
              titulo="Nenhum trabalho ainda"
              acao={
                <Botao icone={IconeNovo} onClick={() => setCriando(true)}>
                  Cadastrar o primeiro
                </Botao>
              }
            >
              Comece cadastrando uma empresa pelo SPED: o sistema identifica CNPJ e razão social
              pelo próprio arquivo.
            </Vazio>
          ) : visiveis.length === 0 ? (
            <Vazio titulo="Nenhum trabalho encontrado">
              Ajuste a busca, o filtro de situação ou a UF.
            </Vazio>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
              {visiveis.map((p) => (
                <CartaoDeTrabalho key={p.id} p={p} />
              ))}
              <button
                type="button"
                onClick={() => setCriando(true)}
                className={cn(
                  "flex min-h-[220px] cursor-pointer flex-col items-center justify-center gap-2 rounded-cartao",
                  "border border-dashed border-borda-forte bg-transparent p-6 text-center transition-colors",
                  "hover:border-marca-laranja hover:bg-laranja-500/6",
                )}
              >
                <IconeNovo size={22} strokeWidth={2} className="text-texto-fraco" aria-hidden />
                <span className="text-sm font-bold text-texto-suave">Novo trabalho</span>
                <span className="max-w-[220px] text-xs text-texto-fraco">
                  Outra frente para uma empresa já cadastrada
                </span>
              </button>
            </div>
          )}
        </div>
      </section>

      <ModalNovoTrabalho
        aberto={criando}
        aoFechar={() => setCriando(false)}
        aoCriado={() => {
          setCriando(false);
          carregar();
        }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */

/** A faixa à esquerda do cartão, na cor da situação. É o que se lê de longe,
 *  antes de qualquer número. */
const FAIXA: Record<Status, string> = {
  em_andamento: "border-l-info",
  pausado: "border-l-atencao",
  cancelado: "border-l-erro",
  concluido: "border-l-sucesso",
};

function CartaoDeTrabalho({ p }: { p: Projeto }) {
  const status = p.status as Status;
  const tom = TOM_DO_STATUS[status] ?? "neutro";
  const cancelado = status === "cancelado";

  return (
    <Link
      to={ROTAS.projeto(p.id)}
      className={cn(
        "group flex flex-col gap-3 rounded-cartao border border-borda bg-superficie p-5 no-underline",
        "border-l-[3px] transition-all duration-150",
        FAIXA[status] ?? "border-l-borda-forte",
        // cancelado entra mais fraco: continua acessível, mas não disputa
        // atenção com o que está andando
        cancelado && "opacity-70",
        "hover:-translate-y-0.5 hover:border-laranja-500/40 hover:border-l-marca-laranja hover:shadow-cat-alta",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Etiqueta tom={tom} pulso={status === "em_andamento"}>
          {p.status_rotulo || status}
        </Etiqueta>
        {p.pre_cadastro && (
          <Etiqueta tom="destaque" title="Dados vieram do arquivo e ainda não foram conferidos">
            Pré-cadastro
          </Etiqueta>
        )}
      </div>

      <div className="min-w-0">
        <h2 className="m-0 truncate text-[17px] font-extrabold text-texto" title={p.empresa}>
          {p.empresa}
        </h2>
        <p className="m-0 mt-1 flex flex-wrap items-center gap-2 font-mono text-[13px] text-texto-suave">
          {p.cnpj_matriz_formatado ?? "CNPJ não informado"}
          {p.uf && (
            <span className="rounded border border-borda px-1.5 py-0.5 text-[11px] font-sans font-bold text-texto-fraco">
              {p.uf}
            </span>
          )}
        </p>
      </div>

      <div className="border-t border-borda pt-3">
        <p className="m-0 text-[11px] font-bold uppercase tracking-[0.1em] text-laranja-700 escuro:text-laranja-400">
          {p.frente_rotulo}
        </p>
        <p className="m-0 mt-0.5 text-[15px] font-semibold text-texto">{p.nome}</p>
      </div>

      <dl className="m-0 grid grid-cols-2 gap-3">
        <div>
          <dt className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
            Competências
          </dt>
          <dd className="m-0 mt-0.5 font-mono text-[13px] text-texto-suave">
            {periodo(p.competencia_ini, p.competencia_fim)}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] font-extrabold uppercase tracking-[0.13em] text-texto-fraco">
            Etapas
          </dt>
          <dd className="m-0 mt-0.5 font-mono text-[13px] text-texto-suave">
            {p.etapas_feitas} de {p.etapas_totais}
          </dd>
        </div>
      </dl>

      <Barra
        de={p.etapas_feitas}
        para={p.etapas_totais}
        tom={BARRA_DO_STATUS[status] ?? "destaque"}
        className="h-1.5"
      />

      {(p.responsavel || p.comentarios > 0) && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-borda pt-3 text-xs text-texto-fraco">
          {p.responsavel && <span>Responsável: {p.responsavel}</span>}
          {p.comentarios > 0 && (
            <span className="ml-auto">
              {p.comentarios === 1 ? "1 comentário" : `${p.comentarios} comentários`}
            </span>
          )}
        </div>
      )}
    </Link>
  );
}

/* ------------------------------------------------------------------ */

const OPCOES_DE_FRENTE: OpcaoDeCombobox<Frente>[] = (
  Object.keys(FRENTES) as Frente[]
).map((f) => ({ valor: f, rotulo: FRENTES[f] }));

/** O módulo padrão: ICMS quando a pessoa o enxerga, senão o primeiro que ela vê.
 *
 *  ICMS é o padrão porque é o que todo trabalho anterior à divisão por segmento
 *  é. Mas quem só enxerga PIS/COFINS não pode receber um padrão que o servidor
 *  vai recusar — daí o "senão". */
function moduloPadrao(segmentos: Segmento[]): string {
  const todos = segmentos.flatMap((s) => s.modulos);
  return todos.some((m) => m.chave === "icms") ? "icms" : (todos[0]?.chave ?? "icms");
}

/**
 * Novo trabalho para empresa **já cadastrada**.
 *
 * Empresa nova continua vindo pelo cadastro por SPED: é o arquivo que diz
 * CNPJ, razão social, IE e UF, e digitar isso à mão é como o cadastro erra.
 */
function ModalNovoTrabalho({
  aberto,
  aoFechar,
  aoCriado,
}: {
  aberto: boolean;
  aoFechar: () => void;
  aoCriado: () => void;
}) {
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [empresa, setEmpresa] = useState("");
  const [frente, setFrente] = useState<Frente>("cat42");
  // o módulo decide o roteiro de etapas do trabalho; sem ele tudo nascia ICMS
  const [segmentos, setSegmentos] = useState<Segmento[]>([]);
  const [modulo, setModulo] = useState("icms");
  const [nome, setNome] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!aberto) return;
    setEmpresa("");
    setFrente("cat42");
    setNome("");
    setIni("");
    setFim("");
    setErro(null);
    listarEmpresas()
      .then(setEmpresas)
      .catch((e) => setErro(comoErro(e).message));
    // só os módulos que a pessoa enxerga: criar trabalho num assunto que ela
    // não vê é criar algo que ela não encontraria depois
    meusSegmentos()
      .then((s) => {
        setSegmentos(s);
        setModulo(moduloPadrao(s));
      })
      .catch(() => undefined);
  }, [aberto]);

  const opcoesDeEmpresa = useMemo<OpcaoDeCombobox<string>[]>(
    () =>
      (empresas ?? []).map((e) => ({
        valor: String(e.id),
        rotulo: `${e.razao_social}${e.uf ? ` · ${e.uf}` : ""}`,
      })),
    [empresas],
  );

  async function enviar(e: FormEvent) {
    e.preventDefault();
    if (!empresa) {
      setErro("Escolha a empresa.");
      return;
    }
    if (!nome.trim()) {
      setErro("Informe o nome do trabalho.");
      return;
    }
    if (!valida(ini) || !valida(fim)) {
      setErro("Competências em MM/AAAA, como 05/2021.");
      return;
    }
    if (compara(ini, fim) > 0) {
      setErro("A competência inicial não pode ser depois da final.");
      return;
    }
    setErro(null);
    setEnviando(true);
    try {
      await criarProjeto({
        empresa_id: Number(empresa),
        frente,
        modulo,
        nome: nome.trim(),
        competencia_ini: paraIso(ini)!,
        competencia_fim: paraIso(fim, true)!,
        observacao: null,
      });
      aoCriado();
    } catch (err) {
      setErro(comoErro(err).message);
    } finally {
      setEnviando(false);
    }
  }

  const semEmpresas = empresas !== null && empresas.length === 0;

  return (
    <Modal
      aberto={aberto}
      aoFechar={aoFechar}
      tamanho="lg"
      titulo="Novo trabalho"
      sub="Para uma empresa já cadastrada. Empresa nova entra pelo cadastro por SPED, que lê CNPJ e razão social do próprio arquivo."
      rodape={
        <>
          <p className={cn("m-0 mr-auto text-xs", erro ? "text-erro" : "text-texto-fraco")}>
            {erro ?? "O trabalho nasce com as etapas pendentes."}
          </p>
          <Botao variante="fantasma" onClick={aoFechar} disabled={enviando}>
            Cancelar
          </Botao>
          <Botao
            type="submit"
            form="form-novo-trabalho"
            carregando={enviando}
            disabled={semEmpresas}
            className="shadow-acao"
          >
            Criar trabalho
          </Botao>
        </>
      }
    >
      {semEmpresas ? (
        <Vazio
          titulo="Nenhuma empresa cadastrada ainda"
          acao={<BotaoLink para={ROTAS.importar}>Cadastrar pelo SPED</BotaoLink>}
        >
          O cadastro começa por um arquivo do SPED Fiscal: é ele que traz CNPJ, razão social,
          inscrição estadual e UF sem ninguém digitar.
        </Vazio>
      ) : (
        <form
          id="form-novo-trabalho"
          onSubmit={enviar}
          noValidate
          className="grid grid-cols-[repeat(auto-fit,minmax(230px,1fr))] gap-[18px]"
        >
          <div className="col-span-full">
            <Campo rotulo="Empresa" dica="Só empresas já cadastradas aparecem aqui.">
              {(props) => (
                <Combobox
                  {...props}
                  valor={empresa}
                  opcoes={opcoesDeEmpresa}
                  aoMudar={setEmpresa}
                  placeholderDaBusca="Buscar empresa…"
                  disabled={empresas === null}
                />
              )}
            </Campo>
          </div>
          <Campo
            rotulo="Tributo"
            dica="Decide as etapas do trabalho: ICMS percorre a CAT 42; PIS/COFINS, a quebra de SPED."
          >
            {(props) => (
              <Combobox
                {...props}
                valor={modulo}
                opcoes={segmentos.flatMap((s) =>
                  s.modulos.map((m) => ({ valor: m.chave, rotulo: m.rotulo })),
                )}
                aoMudar={setModulo}
                disabled={segmentos.length === 0}
              />
            )}
          </Campo>
          <Campo rotulo="Frente de trabalho">
            {(props) => (
              <Combobox {...props} valor={frente} opcoes={OPCOES_DE_FRENTE} aoMudar={setFrente} />
            )}
          </Campo>
          <Campo rotulo="Nome do trabalho" dica="Como a equipe chama este trabalho.">
            {(props) => (
              <Entrada
                {...props}
                value={nome}
                onChange={(ev) => setNome(ev.target.value)}
                placeholder="Ressarcimento ST 2025"
              />
            )}
          </Campo>
          <Campo rotulo="Competência inicial">
            {(props) => (
              <Entrada
                {...props}
                mono
                value={ini}
                onChange={(ev) => setIni(mascarar(ev.target.value))}
                placeholder="01/2021"
                inputMode="numeric"
              />
            )}
          </Campo>
          <Campo rotulo="Competência final">
            {(props) => (
              <Entrada
                {...props}
                mono
                value={fim}
                onChange={(ev) => setFim(mascarar(ev.target.value))}
                placeholder="12/2025"
                inputMode="numeric"
              />
            )}
          </Campo>
        </form>
      )}
    </Modal>
  );
}

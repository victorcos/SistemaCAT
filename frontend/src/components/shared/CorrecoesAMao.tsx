import { useCallback, useEffect, useRef, useState } from "react";
import { Cartao, Rotulo, quando } from "@/components/shared/Rodada";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Celula, Linha, Tabela } from "@/components/ui/Tabela";
import { IconeApagar, IconeEnviar } from "@/constants/icons";
import { useAcao } from "@/hooks/useAcao";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/cn";
import { numero } from "@/lib/format";
import {
  comoCorrecao,
  conferirPlanilha,
  desfazerCorrecao,
  gravarCorrecoes,
  listarCorrecoes,
  type CorrecaoGravada,
  type MudancaDaPlanilha,
  type PlanilhaConferida,
  type ProblemaDaPlanilha,
} from "@/services/correcoes";

/**
 * Correção à mão do trabalho: a porta da planilha e a lista do que já foi
 * corrigido.
 *
 * O caminho é sempre o mesmo, e é o que separa corrigir de estragar: a pessoa
 * baixa a Ficha 3, edita no Excel o que o sistema deduziu errado, escreve o
 * motivo na última coluna e sobe o arquivo. A tela mostra **o que muda, de que
 * valor para que valor**, e só então grava. Subir e gravar no mesmo gesto é
 * como uma coluna arrastada sem querer viraria dez mil correções.
 *
 * A correção fica no banco e não some quando a etapa roda de novo: é o razão
 * que a aplica, a cada montagem. Por isso a tela diz, depois de gravar, que o
 * número só muda quando o razão rodar outra vez.
 */

const QUANTAS_MOSTRAR = 40;
const PROBLEMAS_NA_TELA = 12;

export function CorrecoesAMao({ projetoId, execucaoId }: { projetoId: number; execucaoId: number }) {
  // leitor vê o que foi corrigido e por quem; corrigir é de quem escreve
  const { podeEscrever } = useAuth();
  const [gravadas, setGravadas] = useState<CorrecaoGravada[]>([]);
  const [conferida, setConferida] = useState<PlanilhaConferida | null>(null);
  const [recado, setRecado] = useState<string | null>(null);
  const [todas, setTodas] = useState(false);
  const escolher = useRef<HTMLInputElement>(null);
  const leitura = useAcao();
  const envio = useAcao();
  const gravacao = useAcao();

  const recarregar = useCallback(async () => {
    const r = await leitura.executar(() => listarCorrecoes(projetoId, { todas }));
    if (r) setGravadas(r.correcoes);
  }, [leitura, projetoId, todas]);

  useEffect(() => {
    void recarregar();
    // recarregar muda a cada render do useAcao; o que importa aqui é o trabalho
    // e o recorte
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projetoId, todas]);

  async function subir(arquivo: File) {
    setRecado(null);
    setConferida(null);
    const r = await envio.executar((sinal) => conferirPlanilha(execucaoId, arquivo, sinal));
    if (r) setConferida(r);
  }

  async function gravar() {
    if (!conferida || conferida.correcoes.length === 0) return;
    const quantas = await gravacao.executar(() =>
      gravarCorrecoes(projetoId, conferida.correcoes.map(comoCorrecao)),
    );
    if (quantas === undefined) return;
    setConferida(null);
    setRecado(
      `${numero(quantas)} ${quantas === 1 ? "correção gravada" : "correções gravadas"}. ` +
        "Elas entram na conta na próxima montagem do razão — rode a etapa de novo para ver o efeito.",
    );
    await recarregar();
  }

  async function desfazer(c: CorrecaoGravada) {
    const r = await gravacao.executar(() => desfazerCorrecao(projetoId, c.id));
    if (!r) return;
    setRecado(`Correção desfeita: ${c.rotulo} (${c.onde}) volta ao que o sistema calcular.`);
    await recarregar();
  }

  const ativas = gravadas.filter((c) => c.situacao === "ativa");

  return (
    <Cartao className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-[280px] flex-1">
          <h2 className="m-0 text-base font-extrabold text-texto">Correção à mão</h2>
          <p className="m-0 mt-1 text-xs leading-relaxed text-texto-suave">
            Baixe a Ficha 3, corrija no Excel o que o sistema deduziu errado — alíquota, redução,
            enquadramento, quantidade, valor, ICMS suportado —, escreva o motivo na última coluna e
            suba o arquivo. Nada é gravado antes de você ver o que muda.
          </p>
        </div>
        {gravadas.length > 0 && (
          <Botao variante="secundario" tamanho="sm" onClick={() => setTodas((t) => !t)}>
            {todas ? "Só as ativas" : "Ver as desfeitas também"}
          </Botao>
        )}
      </div>

      {(leitura.erro ?? envio.erro ?? gravacao.erro) && (
        <Aviso
          titulo={(leitura.erro ?? envio.erro ?? gravacao.erro)!.message}
          codigo={(leitura.erro ?? envio.erro ?? gravacao.erro)!.requisicaoId}
          aoFechar={() => {
            leitura.setErro(null);
            envio.setErro(null);
            gravacao.setErro(null);
          }}
        />
      )}
      {recado && (
        <Aviso tom="sucesso" titulo={recado} aoFechar={() => setRecado(null)} />
      )}

      {podeEscrever && (
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={escolher}
            type="file"
            accept=".xlsx,.xlsm,.csv"
            className="hidden"
            onChange={(e) => {
              const arquivo = e.target.files?.[0];
              e.target.value = "";
              if (arquivo) void subir(arquivo);
            }}
          />
          <Botao
            icone={IconeEnviar}
            carregando={envio.carregando}
            aoCancelar={envio.podeCancelar ? envio.cancelar : undefined}
            onClick={() => escolher.current?.click()}
          >
            Subir a Ficha 3 corrigida
          </Botao>
          <span className="text-xs text-texto-fraco">
            xlsx ou csv, como o sistema gera. A ordem e o recorte das linhas não importam.
          </span>
        </div>
      )}

      {conferida && (
        <Proposta
          conferida={conferida}
          gravando={gravacao.carregando}
          aoGravar={gravar}
          aoDescartar={() => setConferida(null)}
        />
      )}

      <Gravadas ativas={ativas} todas={todas ? gravadas : ativas} podeDesfazer={podeEscrever}
                ocupado={gravacao.carregando} aoDesfazer={desfazer} />
    </Cartao>
  );
}

/** O que a planilha propõe, antes de gravar: de que valor para que valor. */
function Proposta({
  conferida,
  gravando,
  aoGravar,
  aoDescartar,
}: {
  conferida: PlanilhaConferida;
  gravando: boolean;
  aoGravar: () => void;
  aoDescartar: () => void;
}) {
  const [tudo, setTudo] = useState(false);
  const mostradas = tudo ? conferida.correcoes : conferida.correcoes.slice(0, QUANTAS_MOSTRAR);
  const nada = conferida.correcoes.length === 0;

  return (
    <section className="flex flex-col gap-3 rounded-cartao border border-info/25 border-l-[3px] border-l-info bg-info-fundo px-5 py-4.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="m-0 text-sm font-extrabold text-texto">
          {nada
            ? "A planilha não muda nada"
            : `${numero(conferida.correcoes.length)} ${conferida.correcoes.length === 1 ? "mudança" : "mudanças"} para gravar`}
        </p>
        <code className="font-mono text-[11px] text-texto-fraco">
          {conferida.arquivo} · {numero(conferida.linhas_lidas)} linhas lidas
          {conferida.abas.length > 1 ? ` · ${conferida.abas.length} abas` : ""}
        </code>
      </div>

      {nada && (
        <p className="m-0 text-xs leading-relaxed text-texto-suave">
          Todos os valores da planilha batem com os do razão. Corrija a célula do valor errado e
          escreva o motivo ao lado — linha sem motivo escrito não vira correção.
        </p>
      )}

      {conferida.truncado && (
        <Aviso tom="atencao" titulo={`A planilha passa do limite de ${numero(conferida.limite)} correções por envio.`}>
          Suba em partes: só as primeiras entram nesta lista.
        </Aviso>
      )}

      {mostradas.length > 0 && (
        <Tabela colunas={["Linha", "O que muda", "Onde", "De", "Para", "Motivo"]}>
          {mostradas.map((m) => (
            <MudancaNaLista key={`${m.campo}-${m.aba}-${m.linha_na_planilha}`} m={m} />
          ))}
        </Tabela>
      )}

      {conferida.correcoes.length > QUANTAS_MOSTRAR && (
        <Botao variante="secundario" tamanho="sm" onClick={() => setTudo((t) => !t)}>
          {tudo
            ? `Mostrar só as primeiras ${QUANTAS_MOSTRAR}`
            : `Ver as outras ${numero(conferida.correcoes.length - QUANTAS_MOSTRAR)}`}
        </Botao>
      )}

      <Problemas titulo="Não dá para gravar estas" tom="erro" lista={conferida.erros}
                 total={conferida.total_de_erros} />
      <Problemas titulo="Vale conferir" tom="atencao" lista={conferida.avisos} total={conferida.avisos.length} />

      <div className="flex flex-wrap items-center gap-3">
        <Botao carregando={gravando} disabled={nada} onClick={aoGravar}>
          {nada ? "Nada a gravar" : `Gravar ${numero(conferida.correcoes.length)}`}
        </Botao>
        <Botao variante="secundario" onClick={aoDescartar} disabled={gravando}>
          Descartar
        </Botao>
        {!nada && (
          <span className="text-xs text-texto-fraco">
            Depois de gravar, rode o razão de novo: é ele que aplica a correção na conta.
          </span>
        )}
      </div>
    </section>
  );
}

function MudancaNaLista({ m }: { m: MudancaDaPlanilha }) {
  return (
    <Linha>
      <Celula mono>{m.linha_na_planilha}</Celula>
      <Celula
        nota={
          m.alvo === "mercadoria"
            ? `vale para as ${numero(m.linhas_atingidas)} linhas da mercadoria`
            : "só nesta linha"
        }
      >
        {m.rotulo}
      </Celula>
      <Celula mono className="max-w-[260px] truncate" title={m.onde}>
        {m.onde}
      </Celula>
      <Celula mono className="text-texto-fraco line-through">
        {m.de || "—"}
      </Celula>
      <Celula mono className="font-[650] text-sucesso">
        {m.para}
      </Celula>
      <Celula className="max-w-[320px]">{m.motivo}</Celula>
    </Linha>
  );
}

function Problemas({
  titulo,
  tom,
  lista,
  total,
}: {
  titulo: string;
  tom: "erro" | "atencao";
  lista: ProblemaDaPlanilha[];
  total: number;
}) {
  if (lista.length === 0) return null;
  return (
    <div
      className={cn(
        "rounded-raio-g border-l-[3px] px-4 py-3",
        tom === "erro" ? "border-l-erro bg-erro-fundo" : "border-l-atencao bg-atencao-fundo",
      )}
    >
      <p className={cn("m-0 text-[13px] font-extrabold", tom === "erro" ? "text-erro" : "text-atencao")}>
        {titulo} ({numero(total)})
      </p>
      <ul className="m-0 mt-2 flex list-none flex-col gap-1 p-0">
        {lista.slice(0, PROBLEMAS_NA_TELA).map((p, i) => (
          <li key={`${p.aba}-${p.linha}-${p.campo ?? ""}-${i}`} className="flex gap-2.5 text-xs leading-relaxed">
            <span className="min-w-[56px] text-right font-mono text-texto-fraco">
              {p.linha > 0 ? `linha ${p.linha}` : p.aba}
            </span>
            <span className="text-texto">
              {p.rotulo ? <strong className="font-[650]">{p.rotulo}: </strong> : null}
              {p.mensagem}
            </span>
          </li>
        ))}
      </ul>
      {total > PROBLEMAS_NA_TELA && (
        <p className="m-0 mt-2 text-[11px] text-texto-fraco">
          e mais {numero(total - Math.min(lista.length, PROBLEMAS_NA_TELA))} — corrija estas primeiro e
          suba de novo.
        </p>
      )}
    </div>
  );
}

/** O que já foi corrigido neste trabalho, com quem fez e quando. */
function Gravadas({
  ativas,
  todas,
  podeDesfazer,
  ocupado,
  aoDesfazer,
}: {
  ativas: CorrecaoGravada[];
  todas: CorrecaoGravada[];
  podeDesfazer: boolean;
  ocupado: boolean;
  aoDesfazer: (c: CorrecaoGravada) => void;
}) {
  const [tudo, setTudo] = useState(false);
  if (todas.length === 0) {
    return (
      <p className="m-0 text-xs text-texto-fraco">
        Nenhuma correção à mão neste trabalho. Os números são todos do que os documentos trazem.
      </p>
    );
  }
  const mostradas = tudo ? todas : todas.slice(0, QUANTAS_MOSTRAR);
  return (
    <div className="flex flex-col gap-2.5">
      <Rotulo>
        {numero(ativas.length)} {ativas.length === 1 ? "correção ativa" : "correções ativas"}
        {todas.length > ativas.length ? ` · ${numero(todas.length - ativas.length)} desfeitas` : ""}
      </Rotulo>
      <Tabela colunas={["O que mudou", "Onde", "De", "Para", "Motivo", "Quem", ""]}>
        {mostradas.map((c) => (
          <Linha key={c.id} apagada={c.situacao !== "ativa"}>
            <Celula>{c.rotulo}</Celula>
            <Celula mono className="max-w-[260px] truncate" title={c.onde}>
              {c.onde}
            </Celula>
            <Celula mono className="text-texto-fraco line-through">
              {c.valor_anterior || "—"}
            </Celula>
            <Celula mono className={cn("font-[650]", c.situacao === "ativa" ? "text-sucesso" : "text-texto-fraco")}>
              {c.valor}
            </Celula>
            <Celula className="max-w-[300px]">{c.motivo}</Celula>
            <Celula nota={quando(c.criada_em)}>{c.autor}</Celula>
            <Celula>
              {c.situacao === "ativa" && podeDesfazer && (
                <Botao
                  variante="secundario"
                  tamanho="sm"
                  icone={IconeApagar}
                  disabled={ocupado}
                  onClick={() => aoDesfazer(c)}
                >
                  Desfazer
                </Botao>
              )}
            </Celula>
          </Linha>
        ))}
      </Tabela>
      {todas.length > QUANTAS_MOSTRAR && (
        <Botao variante="secundario" tamanho="sm" onClick={() => setTudo((t) => !t)}>
          {tudo ? `Mostrar só as primeiras ${QUANTAS_MOSTRAR}` : `Ver as outras ${numero(todas.length - QUANTAS_MOSTRAR)}`}
        </Botao>
      )}
    </div>
  );
}

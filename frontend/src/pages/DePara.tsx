import { useCallback, useEffect, useMemo, useState, type ChangeEvent } from "react";
import { useParams } from "react-router-dom";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Etiqueta, type TomDeEtiqueta } from "@/components/ui/Etiqueta";
import { Busca, Segmentado } from "@/components/ui/Filtros";
import { CabecalhoDePagina, Voltar } from "@/components/ui/Pagina";
import { Celula, Linha, Tabela } from "@/components/ui/Tabela";
import { ROTAS } from "@/constants/routes";
import { useAuth } from "@/hooks/useAuth";
import { comoErro } from "@/lib/errors";
import { numero } from "@/lib/format";
import {
  ROTULO_DO_MOTIVO,
  decidirDePara,
  decisaoDoPar,
  deparaDoTrabalho,
  lerPlanilhaDoCliente,
  planilhaParaOCliente,
  type DeParaDoTrabalho,
  type Decisao,
  type ParDoDePara,
  type SituacaoDoPar,
} from "@/services/depara";
import type { ErroApi } from "@/types/erro";

/**
 * De-para de códigos do trabalho.
 *
 * O sistema propõe os pares a partir da movimentação — mesmo GTIN, código de
 * compra = código de venda + sufixo, kit, descrição e NCM — e diz por quê. Quem
 * escreve aprova ou recusa; o que nada liga vai numa planilha para o cliente
 * dizer de onde veio. O razão aplica só o que foi aprovado.
 */

type Filtro = SituacaoDoPar | "todos";
const POR_PAGINA = 200;

const TOM: Record<SituacaoDoPar, TomDeEtiqueta> = { pendente: "atencao", aprovado: "sucesso", recusado: "neutro" };
const chave = (p: { cnpj: string; origem: string }) => `${p.cnpj}|${p.origem}`;

export default function DePara() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);
  const { podeEscrever } = useAuth();

  const [dados, setDados] = useState<DeParaDoTrabalho | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [gravando, setGravando] = useState(false);
  const [filtro, setFiltro] = useState<Filtro>("pendente");
  const [busca, setBusca] = useState("");
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [manual, setManual] = useState<Record<string, { destino: string; fator: string }>>({});
  const [nota, setNota] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setDados(await deparaDoTrabalho(projetoId));
      setErro(null);
    } catch (x) {
      setErro(comoErro(x));
    } finally {
      setCarregando(false);
    }
  }, [projetoId]);

  useEffect(() => {
    if (projetoId) void carregar();
  }, [projetoId, carregar]);

  const visiveis = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    return (dados?.pares ?? []).filter(
      (p) =>
        (filtro === "todos" || p.situacao === filtro) &&
        (!termo || `${p.origem} ${p.destino} ${p.explicacao}`.toLowerCase().includes(termo)),
    );
  }, [dados, filtro, busca]);

  async function gravar(decisoes: Decisao[], texto: string) {
    if (decisoes.length === 0) return;
    setGravando(true);
    try {
      const n = await decidirDePara(projetoId, decisoes);
      setNota(`${numero(n)} ${texto}. O razão aplica os pares aprovados na próxima montagem.`);
      setMarcados(new Set());
      await carregar();
    } catch (x) {
      setErro(comoErro(x));
    } finally {
      setGravando(false);
    }
  }

  const decidirMarcados = (situacao: "aprovado" | "recusado") =>
    gravar(
      visiveis.filter((p) => marcados.has(chave(p))).map((p) => decisaoDoPar(p, situacao)),
      situacao === "aprovado" ? "par(es) aprovado(s)" : "par(es) recusado(s)",
    );

  function baixarPlanilha() {
    if (!dados) return;
    const blob = new Blob([planilhaParaOCliente(dados.sem_par)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `depara_para_o_cliente_trabalho_${projetoId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function importarPlanilha(e: ChangeEvent<HTMLInputElement>) {
    const arquivo = e.target.files?.[0];
    e.target.value = "";
    if (!arquivo) return;
    const { decisoes, ignoradas } = lerPlanilhaDoCliente(await arquivo.text());
    if (decisoes.length === 0) {
      setNota(`Nenhuma linha preenchida na planilha (${numero(ignoradas)} sem o código do mesmo produto).`);
      return;
    }
    await gravar(decisoes, `par(es) informado(s) pelo cliente gravado(s)${ignoradas ? `, ${ignoradas} linha(s) em branco` : ""}`);
  }

  const r = dados?.resumo;
  return (
    <div className="flex flex-col gap-5">
      <Voltar para={ROTAS.projeto(projetoId)}>Voltar ao trabalho</Voltar>
      <CabecalhoDePagina
        eyebrow="Razão dos itens"
        titulo="De-para de códigos"
        sub="O mesmo produto escriturado com outro código na compra, no kit ou no marketplace vira uma ficha só. O sistema propõe e diz por quê; o razão aplica só o que for aprovado."
      />

      {erro && (
        <Aviso tom="erro" codigo={erro.requisicaoId}>
          {erro.message}
        </Aviso>
      )}
      {nota && (
        <Aviso tom="sucesso" aoFechar={() => setNota(null)}>
          {nota}
        </Aviso>
      )}

      {carregando && !dados && <p className="text-sm text-texto-suave">Lendo a movimentação…</p>}

      {r && (
        <div className="flex flex-wrap gap-2">
          <Etiqueta tom="atencao">{numero(r.pendentes)} pendentes</Etiqueta>
          <Etiqueta tom="sucesso">{numero(r.aprovados)} aprovados</Etiqueta>
          <Etiqueta>{numero(r.recusados)} recusados</Etiqueta>
          <Etiqueta tom="info">{numero(r.sem_par)} códigos sem par</Etiqueta>
          <span className="text-xs text-texto-fraco">
            sobre a movimentação #{dados?.movimentos_execucao_id}, {numero(r.estabelecimentos)} estabelecimento(s)
          </span>
        </div>
      )}

      {dados && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <Segmentado<Filtro>
              rotulo="Situação"
              valor={filtro}
              aoMudar={(v) => {
                setFiltro(v);
                setMarcados(new Set());
              }}
              opcoes={[
                { chave: "pendente", rotulo: "Pendentes" },
                { chave: "aprovado", rotulo: "Aprovados" },
                { chave: "recusado", rotulo: "Recusados" },
                { chave: "todos", rotulo: "Todos" },
              ]}
            />
            <Busca valor={busca} aoMudar={setBusca} placeholder="Buscar código ou motivo" />
            {podeEscrever && (
              <>
                <Botao
                  tamanho="sm"
                  disabled={gravando || marcados.size === 0}
                  onClick={() => decidirMarcados("aprovado")}
                >
                  Aprovar {marcados.size > 0 ? numero(marcados.size) : ""}
                </Botao>
                <Botao
                  tamanho="sm"
                  variante="secundario"
                  disabled={gravando || marcados.size === 0}
                  onClick={() => decidirMarcados("recusado")}
                >
                  Recusar
                </Botao>
              </>
            )}
          </div>

          {visiveis.length === 0 ? (
            <p className="text-sm text-texto-suave">Nenhum par nesta situação.</p>
          ) : (
            <Tabela
              colunas={[
                podeEscrever ? (
                  <input
                    type="checkbox"
                    aria-label="Marcar todos os visíveis"
                    checked={marcados.size > 0 && marcados.size === Math.min(visiveis.length, POR_PAGINA)}
                    onChange={(e) =>
                      setMarcados(e.target.checked ? new Set(visiveis.slice(0, POR_PAGINA).map(chave)) : new Set())
                    }
                  />
                ) : (
                  ""
                ),
                "Origem",
                "Vira",
                "Fator",
                "Por quê",
                "Situação",
              ]}
            >
              {visiveis.slice(0, POR_PAGINA).map((p) => (
                <LinhaDoPar
                  key={chave(p)}
                  par={p}
                  marcado={marcados.has(chave(p))}
                  podeEscrever={podeEscrever}
                  ocupado={gravando}
                  aoMarcar={(m) =>
                    setMarcados((atual) => {
                      const novo = new Set(atual);
                      if (m) novo.add(chave(p));
                      else novo.delete(chave(p));
                      return novo;
                    })
                  }
                  aoDecidir={(s) =>
                    gravar([decisaoDoPar(p, s)], s === "aprovado" ? "par aprovado" : "par recusado")
                  }
                />
              ))}
            </Tabela>
          )}
          {visiveis.length > POR_PAGINA && (
            <p className="text-xs text-texto-fraco">
              Mostrando {numero(POR_PAGINA)} de {numero(visiveis.length)}: decida estes e os próximos aparecem.
            </p>
          )}
        </section>
      )}

      {dados && dados.sem_par.length > 0 && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="m-0 text-base font-bold">Códigos sem par</h2>
              <p className="m-0 text-[13px] text-texto-suave">
                Têm saída e não têm entrada nem estoque, e nenhuma proposta os explica: são as fichas que ficam
                negativas. Informe o código do mesmo produto, ou mande a planilha para o cliente preencher.
              </p>
            </div>
            <div className="flex gap-2">
              <Botao tamanho="sm" variante="secundario" onClick={baixarPlanilha}>
                Planilha para o cliente
              </Botao>
              {podeEscrever && (
                <label className="inline-flex cursor-pointer items-center rounded-raio border border-borda px-3 py-1.5 text-xs font-semibold">
                  Importar preenchida
                  <input type="file" accept=".csv,text/csv" className="hidden" onChange={importarPlanilha} />
                </label>
              )}
            </div>
          </div>
          <Tabela colunas={["Código", "Descrição", "NCM", "Saídas", podeEscrever ? "Mesmo produto que" : ""]}>
            {dados.sem_par.slice(0, POR_PAGINA).map((s) => {
              const k = chave({ cnpj: s.cnpj, origem: s.codigo });
              const m = manual[k] ?? { destino: "", fator: "1" };
              return (
                <Linha key={k}>
                  <Celula mono nota={s.cnpj}>
                    {s.codigo}
                  </Celula>
                  <Celula>{s.descricao}</Celula>
                  <Celula mono>{s.ncm}</Celula>
                  <Celula mono>{numero(Number(s.saidas))}</Celula>
                  <Celula>
                    {podeEscrever && (
                      <div className="flex items-center gap-2">
                        <input
                          aria-label={`Código do mesmo produto que ${s.codigo}`}
                          className="w-28 rounded border border-borda px-2 py-1 font-mono text-xs"
                          value={m.destino}
                          onChange={(e) => setManual({ ...manual, [k]: { ...m, destino: e.target.value } })}
                        />
                        <input
                          aria-label="Unidades por item"
                          title="Unidades por item, se for kit"
                          className="w-12 rounded border border-borda px-2 py-1 font-mono text-xs"
                          value={m.fator}
                          onChange={(e) => setManual({ ...manual, [k]: { ...m, fator: e.target.value } })}
                        />
                        <Botao
                          tamanho="sm"
                          variante="fantasma"
                          disabled={gravando || !m.destino.trim()}
                          onClick={() =>
                            gravar(
                              [{ cnpj: s.cnpj, origem: s.codigo, destino: m.destino.trim(),
                                 fator: m.fator.replace(",", ".") || "1", motivo: "analista", situacao: "aprovado" }],
                              "par informado gravado",
                            )
                          }
                        >
                          Gravar
                        </Botao>
                      </div>
                    )}
                  </Celula>
                </Linha>
              );
            })}
          </Tabela>
        </section>
      )}
    </div>
  );
}

function LinhaDoPar({
  par,
  marcado,
  podeEscrever,
  ocupado,
  aoMarcar,
  aoDecidir,
}: {
  par: ParDoDePara;
  marcado: boolean;
  podeEscrever: boolean;
  ocupado: boolean;
  aoMarcar: (m: boolean) => void;
  aoDecidir: (s: "aprovado" | "recusado") => void;
}) {
  const decididoOutro = par.destino_decidido && par.destino_decidido !== par.destino;
  return (
    <Linha apagada={par.situacao === "recusado"}>
      <Celula>
        {podeEscrever && (
          <input
            type="checkbox"
            aria-label={`Marcar ${par.origem}`}
            checked={marcado}
            onChange={(e) => aoMarcar(e.target.checked)}
          />
        )}
      </Celula>
      <Celula mono nota={par.cnpj || "todos os estabelecimentos"}>
        {par.origem}
      </Celula>
      <Celula mono nota={decididoOutro ? `decidido: ${par.destino_decidido}` : undefined}>
        {par.destino}
      </Celula>
      <Celula mono>{par.fator}</Celula>
      <Celula nota={par.explicacao}>
        <div className="flex flex-wrap gap-1">
          {par.motivos.map((m) => (
            <Etiqueta key={m} tom={par.confianca === "media" ? "neutro" : "info"}>
              {ROTULO_DO_MOTIVO[m] ?? m}
            </Etiqueta>
          ))}
        </div>
      </Celula>
      <Celula nota={par.decidido_por ? `${par.decidido_por}` : undefined}>
        <div className="flex items-center gap-2">
          <Etiqueta tom={TOM[par.situacao]}>{par.situacao}</Etiqueta>
          {podeEscrever && par.situacao !== "aprovado" && (
            <Botao tamanho="sm" variante="fantasma" disabled={ocupado} onClick={() => aoDecidir("aprovado")}>
              Aprovar
            </Botao>
          )}
          {podeEscrever && par.situacao !== "recusado" && (
            <Botao tamanho="sm" variante="fantasma" disabled={ocupado} onClick={() => aoDecidir("recusado")}>
              Recusar
            </Botao>
          )}
        </div>
      </Celula>
    </Linha>
  );
}

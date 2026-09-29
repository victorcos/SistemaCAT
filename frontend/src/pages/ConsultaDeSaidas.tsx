import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import { Rotulo } from "@/components/shared/Rodada";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Carregando } from "@/components/ui/Carregando";
import { Busca, Chip, GrupoDeChips } from "@/components/ui/Filtros";
import { CabecalhoDePagina, Metrica, Metricas, Vazio, Voltar } from "@/components/ui/Pagina";
import { Celula, Linha, Tabela } from "@/components/ui/Tabela";
import { ROTAS } from "@/constants/routes";
import { useAcao } from "@/hooks/useAcao";
import { cn } from "@/lib/cn";
import { dinheiro, numero } from "@/lib/format";
import type { Formato } from "@/services/conferencia";
import { detalharProjeto, type ProjetoDetalhe } from "@/services/importacao";
import {
  RECORTE_DAS_SAIDAS_INTEIRO,
  baixarSaidas,
  filtrosDasSaidas,
  linhasDasSaidas,
  listarApuracoes,
  quantosFiltrosNasSaidas,
  type EscolhaDoFiltro,
  type ExecucaoDaApuracao,
  type FiltrosDasSaidas,
  type LinhaDaSaida,
  type PaginaDasSaidas,
  type RecorteDasSaidas,
} from "@/services/apuracaoPisCofins";
import type { ErroApi } from "@/types/erro";

/**
 * Consulta de Saídas (047) — recortar primeiro, olhar depois.
 *
 * A 047 de cinco anos de uma rede passa de **sete milhões de linhas**. O
 * download existe e continua valendo, mas não atende o gesto de quem confere:
 * o Excel não abre sete milhões de linhas, e quem está conferindo quer uma
 * competência, um CFOP, uma nota.
 *
 * Por isso o recorte vem primeiro e ocupa o alto da tela, e as linhas abrem
 * embaixo. Nenhuma página é montada aqui: tudo vem paginado do servidor.
 *
 * **Os filtros mostram o tamanho de cada escolha**, e cada lista é contada sem
 * o próprio filtro. Assim se vê o que *ganharia* ao marcar mais uma coisa, e
 * não só o que já está marcado — filtro que encolhe a própria lista vira
 * armadilha de mão única, porque quem marcou o 5102 nunca mais acha o 5405.
 *
 * **O download sai recortado igual à tela.** Quem está olhando outubro leva
 * outubro; o arquivo inteiro continua a um clique, no cartão da apuração.
 */

const POR_PAGINA = 100;

const cnpjFormatado = (c: string) =>
  c.length === 14
    ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}`
    : c;

/** "01/10/2025" vira "10/2025": o dia é sempre 1º e não diz nada. */
const competencia = (p: string) => (p.length === 10 ? p.slice(3) : p);

/** O ramo inteiro é longo demais para um chip; o código já identifica. */
const ramoCurto = (r: string) => r.split(" - ")[0] || r;

export default function ConsultaDeSaidas() {
  const { id } = useParams<{ id: string }>();
  const projetoId = Number(id);

  const [projeto, setProjeto] = useState<ProjetoDetalhe | null>(null);
  const [apuracao, setApuracao] = useState<ExecucaoDaApuracao | null>(null);
  const [carregado, setCarregado] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);

  useEffect(() => {
    let vivo = true;
    detalharProjeto(projetoId)
      .then((p) => vivo && setProjeto(p))
      .catch(() => undefined);
    listarApuracoes(projetoId)
      .then((lista) => {
        if (!vivo) return;
        setApuracao(lista.find((e) => e.situacao === "concluida") ?? null);
      })
      .catch((x) => vivo && setErro(comoErroApi(x)))
      .finally(() => vivo && setCarregado(true));
    return () => {
      vivo = false;
    };
  }, [projetoId]);

  const saidas = apuracao?.resumo?.saidas ?? 0;

  return (
    <>
      <Voltar para={ROTAS.apuracaoPisCofins(projetoId)}>Apuração de PIS/COFINS</Voltar>
      <CabecalhoDePagina
        eyebrow={projeto?.projeto.nome ? `PIS/COFINS · ${projeto.projeto.nome}` : "PIS/COFINS"}
        titulo="Consulta de Saídas (047)"
        sub="Tudo que saiu, pela EFD-Contribuições: nota fiscal item a item, o analítico da NFC-e, nota de serviço e os demais documentos. Recorte o que vai olhar — e o download sai do mesmo tamanho."
      />

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}

      {!carregado && <Carregando />}

      {carregado && !apuracao && (
        <Vazio
          titulo="Nenhuma apuração de PIS/COFINS concluída neste trabalho"
          acao={
            <Link to={ROTAS.apuracaoPisCofins(projetoId)}>
              <Botao variante="secundario">Ir para a apuração</Botao>
            </Link>
          }
        >
          A Consulta de Saídas sai da apuração. Rode a etapa com pelo menos uma EFD-Contribuições
          no lote e volte aqui.
        </Vazio>
      )}

      {carregado && apuracao && saidas === 0 && (
        <Vazio titulo="Esta apuração não produziu nenhuma linha de saída">
          A execução leu só ECD, ou as EFD-Contribuições do lote não têm documento de saída.
          Confira os arquivos do lote e rode a apuração de novo.
        </Vazio>
      )}

      {carregado && apuracao && saidas > 0 && <Consulta execucaoId={apuracao.id} />}
    </>
  );
}

/** O erro da API, sem importar o módulo inteiro só por isto. */
function comoErroApi(x: unknown): ErroApi {
  const e = x as ErroApi;
  return e?.message ? e : ({ message: String(x) } as ErroApi);
}

function Consulta({ execucaoId }: { execucaoId: number }) {
  const [recorte, setRecorte] = useState<RecorteDasSaidas>(RECORTE_DAS_SAIDAS_INTEIRO);
  const [busca, setBusca] = useState("");
  const [filtros, setFiltros] = useState<FiltrosDasSaidas | null>(null);
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<PaginaDasSaidas | null>(null);
  const [baixando, setBaixando] = useState<Formato | null>(null);
  const leituraDosFiltros = useAcao();
  const leitura = useAcao();
  const download = useAcao();

  // a busca livre varre as linhas; esperar o que se digita evita uma varredura
  // por tecla numa base de sete milhões
  useEffect(() => {
    const t = setTimeout(
      () => setRecorte((r) => (r.busca === busca ? r : { ...r, busca })),
      400,
    );
    return () => clearTimeout(t);
  }, [busca]);

  useEffect(() => setPagina(1), [recorte]);

  useEffect(() => {
    let vivo = true;
    leituraDosFiltros
      .executar((sinal) => filtrosDasSaidas(execucaoId, recorte, sinal))
      .then((f) => vivo && f && setFiltros(f));
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [execucaoId, recorte]);

  useEffect(() => {
    let vivo = true;
    leitura
      .executar((sinal) => linhasDasSaidas(execucaoId, recorte, pagina, POR_PAGINA, sinal))
      .then((p) => vivo && p && setDados(p));
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [execucaoId, recorte, pagina]);

  const alternar = useCallback(
    (campo: keyof Omit<RecorteDasSaidas, "busca">, valor: string) =>
      setRecorte((r) => {
        const atual = r[campo];
        return {
          ...r,
          [campo]: atual.includes(valor) ? atual.filter((v) => v !== valor) : [...atual, valor],
        };
      }),
    [],
  );

  const quantos = quantosFiltrosNasSaidas(recorte);
  const paginas = Math.max(1, Math.ceil((dados?.total ?? 0) / POR_PAGINA));

  async function baixar(formato: Formato) {
    setBaixando(formato);
    await download.executar((sinal) => baixarSaidas(execucaoId, recorte, formato, sinal));
    setBaixando(null);
  }

  return (
    <div className="flex flex-col gap-5">
      {(leitura.erro || download.erro) && (
        <Aviso
          titulo={(leitura.erro ?? download.erro)!.message}
          codigo={(leitura.erro ?? download.erro)!.requisicaoId}
          aoFechar={() => {
            leitura.setErro(null);
            download.setErro(null);
          }}
        />
      )}

      <Metricas>
        <Metrica
          rotulo="Linhas no recorte"
          valor={numero(dados?.total ?? 0)}
          nota={
            quantos === 0
              ? "a consulta inteira"
              : `de ${numero(filtros?.linhas_no_total ?? 0)} no total`
          }
        />
        <Metrica rotulo="Valor dos itens" valor={dinheiro(dados?.totais.valor ?? "0")} />
        <Metrica rotulo="PIS" valor={dinheiro(dados?.totais.pis ?? "0")} />
        <Metrica rotulo="COFINS" valor={dinheiro(dados?.totais.cofins ?? "0")} />
      </Metricas>

      <Recorte
        filtros={filtros}
        recorte={recorte}
        busca={busca}
        quantos={quantos}
        carregando={leituraDosFiltros.carregando}
        aoBuscar={setBusca}
        aoAlternar={alternar}
        aoLimpar={() => {
          setBusca("");
          setRecorte(RECORTE_DAS_SAIDAS_INTEIRO);
        }}
      />

      <div className="flex flex-wrap items-center gap-3">
        <BaixarPlanilha
          destaque
          rotulo={quantos === 0 ? "Baixar tudo" : "Baixar o recorte"}
          aoBaixar={baixar}
          desabilitado={download.carregando || (dados?.total ?? 0) === 0}
          baixando={baixando}
          aoCancelar={download.podeCancelar ? download.cancelar : undefined}
        />
        <span className="text-[12px] text-texto-suave">
          {quantos === 0
            ? "A consulta inteira, como o MA exporta: 53 colunas."
            : `Sai só o que está no recorte — ${numero(dados?.total ?? 0)} linha${(dados?.total ?? 0) === 1 ? "" : "s"}, 53 colunas.`}
        </span>
      </div>

      {(dados?.total ?? 0) === 0 && !leitura.carregando ? (
        <Vazio titulo="Nenhuma linha com este recorte">
          Nenhuma saída casa com o que está marcado. Limpe um filtro e tente de novo.
        </Vazio>
      ) : (
        <>
          <AsLinhas linhas={dados?.linhas ?? []} carregando={leitura.carregando} />
          <div className="flex flex-wrap items-center gap-3">
            <Paginacao
              pagina={pagina}
              paginas={paginas}
              ocupado={leitura.carregando}
              aoIr={setPagina}
            />
            <span className="text-[11px] text-texto-fraco">
              Na ordem da escrituração — competência, estabelecimento, documento, item.
            </span>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * O painel de recorte.
 *
 * Os chips trazem a contagem do que cada escolha rende. É o que permite
 * decidir antes de pedir: "este CFOP são quatro milhões de linhas" é uma
 * informação que muda o clique seguinte.
 */
function Recorte({
  filtros,
  recorte,
  busca,
  quantos,
  carregando,
  aoBuscar,
  aoAlternar,
  aoLimpar,
}: {
  filtros: FiltrosDasSaidas | null;
  recorte: RecorteDasSaidas;
  busca: string;
  quantos: number;
  carregando: boolean;
  aoBuscar: (v: string) => void;
  aoAlternar: (campo: keyof Omit<RecorteDasSaidas, "busca">, valor: string) => void;
  aoLimpar: () => void;
}) {
  const [aberto, setAberto] = useState(true);

  const grupo = (
    campo: keyof Omit<RecorteDasSaidas, "busca">,
    titulo: string,
    escolhas: EscolhaDoFiltro[] | undefined,
    rotulo: (e: EscolhaDoFiltro) => string,
    explicacao?: string,
  ) => {
    if (!escolhas?.length || escolhas.length < 2) return null;
    return (
      <GrupoDeChips titulo={titulo} explicacao={explicacao}>
        {escolhas.map((e) => (
          <Chip
            key={e.valor || "(vazio)"}
            marcado={recorte[campo].includes(e.valor)}
            aoAlternar={() => aoAlternar(campo, e.valor)}
            contagem={numero(e.linhas)}
          >
            <span title={e.rotulo || undefined}>{rotulo(e)}</span>
          </Chip>
        ))}
      </GrupoDeChips>
    );
  };

  return (
    <div className="rounded-raio-g border border-borda bg-superficie-vidro">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <Botao variante="fantasma" tamanho="sm" onClick={() => setAberto(!aberto)}>
          {aberto ? "Esconder o recorte" : "Recortar"}
        </Botao>
        <span className="text-[12px] text-texto-suave">
          {quantos === 0
            ? "Sai tudo o que a apuração encontrou."
            : `${quantos} filtro${quantos === 1 ? "" : "s"} em uso.`}
          {carregando && " Contando…"}
        </span>
        {quantos > 0 && (
          <Botao variante="fantasma" tamanho="sm" onClick={aoLimpar}>
            Limpar
          </Botao>
        )}
      </div>

      {aberto && (
        <div className="border-t border-borda-sutil p-4">
          <Rotulo>Procurar</Rotulo>
          <div className="mt-2 max-w-[520px]">
            <Busca
              valor={busca}
              aoMudar={aoBuscar}
              placeholder="Chave, número da nota, código ou nome do produto, participante"
            />
          </div>
          {busca.trim() && filtros && !filtros.busca_conta_no_resumo && (
            <p className="m-0 mt-2 text-[11px] text-texto-fraco">
              As contagens dos chips abaixo não consideram a busca — ela varre as linhas, e os
              números vêm do resumo. O total do recorte, no alto, considera tudo.
            </p>
          )}

          {grupo("competencias", "Competência", filtros?.competencias, (e) =>
            competencia(e.valor),
          )}
          {grupo("cnpjs", "Estabelecimento", filtros?.cnpjs, (e) => cnpjFormatado(e.valor))}
          {grupo(
            "ramos",
            "Ramo do documento",
            filtros?.ramos,
            (e) => ramoCurto(e.valor),
            "Cada ramo é um caminho de escrituração: a nota item a item, o analítico da NFC-e, a nota de serviço, os demais documentos.",
          )}
          {grupo(
            "cfops",
            "CFOP",
            filtros?.cfops,
            (e) => e.valor || "(sem CFOP)",
            "Sem CFOP são as notas canceladas e os documentos que não têm operação — o bloco F e a nota de serviço.",
          )}
          {grupo("cst_pis", "CST do PIS", filtros?.cst_pis, (e) => e.valor || "(vazio)")}
        </div>
      )}
    </div>
  );
}

/**
 * As linhas.
 *
 * São 53 colunas, e 53 colunas não cabem na tela de ninguém. Aqui ficam as que
 * identificam a linha e as que se conferem; as demais estão na planilha, que é
 * onde se confere coluna a coluna. A ordem é a do relatório.
 */
function AsLinhas({ linhas, carregando }: { linhas: LinhaDaSaida[]; carregando: boolean }) {
  const colunas = useMemo(
    () => [
      "Competência",
      "Documento",
      "Item",
      "Produto",
      "CFOP",
      "Natureza",
      "Valor",
      "CST",
      "PIS",
      "COFINS",
    ],
    [],
  );

  return (
    <div className={cn("transition-opacity", carregando && "opacity-60")}>
      <Tabela colunas={colunas}>
        {linhas.map((l, i) => (
          <Linha key={`${l.chave}-${l.numero_do_item}-${l.cfop}-${l.cst_pis}-${i}`}>
            <Celula nota={l.cnpj ? cnpjFormatado(l.cnpj) : undefined}>
              {competencia(l.periodo)}
            </Celula>
            <Celula nota={l.nome_do_participante || ramoCurto(l.registros)}>
              <span className="font-mono text-[12px]">{l.numero_do_documento || "—"}</span>
              {l.serie && <span className="ml-1 text-[11px] text-texto-fraco">/{l.serie}</span>}
            </Celula>
            <Celula mono className="text-right">
              {l.numero_do_item || "—"}
            </Celula>
            <Celula nota={l.ncm ? `NCM ${l.ncm}` : undefined}>
              <span title={l.descricao_do_item || undefined}>
                {l.descricao_do_item || l.descricao_complementar || "—"}
              </span>
            </Celula>
            <Celula mono nota={l.descricao_do_cfop || undefined}>
              {l.cfop || "—"}
            </Celula>
            <Celula nota={l.faturamento || undefined}>{l.natureza || "—"}</Celula>
            <Celula mono className="text-right">
              {l.valor_do_item || "—"}
            </Celula>
            <Celula mono className="text-right">
              {l.cst_pis || "—"}
            </Celula>
            <Celula mono className="text-right">
              {l.pis || "—"}
            </Celula>
            <Celula mono className="text-right">
              {l.cofins || "—"}
            </Celula>
          </Linha>
        ))}
      </Tabela>
    </div>
  );
}

function Paginacao({
  pagina,
  paginas,
  ocupado,
  aoIr,
}: {
  pagina: number;
  paginas: number;
  ocupado: boolean;
  aoIr: (n: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Botao
        variante="secundario"
        tamanho="sm"
        onClick={() => aoIr(Math.max(1, pagina - 1))}
        disabled={pagina <= 1 || ocupado}
      >
        Anterior
      </Botao>
      <span className="font-mono text-xs text-texto-fraco">
        {numero(pagina)} / {numero(paginas)}
      </span>
      <Botao
        variante="secundario"
        tamanho="sm"
        onClick={() => aoIr(Math.min(paginas, pagina + 1))}
        disabled={pagina >= paginas || ocupado}
      >
        Próxima
      </Botao>
    </div>
  );
}

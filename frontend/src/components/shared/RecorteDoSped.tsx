import { useState } from "react";
import { Botao } from "@/components/ui/Botao";
import { Chip } from "@/components/ui/Filtros";
import { Rotulo } from "@/components/shared/Rodada";
import { cn } from "@/lib/cn";
import {
  RECORTE_INTEIRO,
  quantosFiltros,
  type RecorteDaExtracao,
} from "@/services/quebraDeSped";

/**
 * O recorte da extração: o que entra, e o que nem chega a ser lido.
 *
 * **Filtrar aqui não é conveniência, é viabilidade.** A extração de um C170 de
 * 59 competências passa de milhões de linhas; recortar depois, no Excel, exige
 * primeiro abrir o que o Excel não abre. Por isso o filtro vai ao servidor: o
 * arquivo fora do período nem é aberto, e a linha que não passa nem é gravada.
 *
 * **Dois níveis, e a tela diz qual é qual.** Estabelecimento e período são do
 * **arquivo** — pulam o SPED inteiro. O resto é da **linha**, e o campo é
 * procurado pelo nome em qualquer registro do recorte: `CST_PIS` acha o do
 * C170, o do C870 e o do C491, sem a pessoa precisar saber em qual deles está.
 *
 * Fica fechado por padrão. Quem chega aqui quer extrair; o recorte é o segundo
 * movimento, e ocupar a tela com dezenove campos antes disso atrapalharia o
 * primeiro.
 */
export function RecorteDoSped({
  recorte,
  aoMudar,
  estabelecimentos,
}: {
  recorte: RecorteDaExtracao;
  aoMudar: (r: RecorteDaExtracao) => void;
  estabelecimentos: { cnpj: string; empresa: string }[];
}) {
  const [aberto, setAberto] = useState(false);
  const quantos = quantosFiltros(recorte);

  const mudar = <C extends keyof RecorteDaExtracao>(campo: C, valor: RecorteDaExtracao[C]) =>
    aoMudar({ ...recorte, [campo]: valor });

  const lista = (campo: keyof RecorteDaExtracao) =>
    (recorte[campo] as string[]).join(", ");

  const mudarLista = (campo: keyof RecorteDaExtracao, texto: string) =>
    aoMudar({
      ...recorte,
      [campo]: texto.split(/[,;]/).map((t) => t.trim()).filter(Boolean),
    });

  return (
    <div className="rounded-raio-g border border-borda bg-superficie-vidro">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <Botao variante="fantasma" tamanho="sm" onClick={() => setAberto(!aberto)}>
          {aberto ? "Esconder o recorte" : "Recortar"}
        </Botao>
        <span className="text-[12px] text-texto-suave">
          {quantos === 0
            ? "Sai tudo o que há nos arquivos."
            : `${quantos} filtro${quantos === 1 ? "" : "s"} em uso — a extração sai só com o que passar.`}
        </span>
        {quantos > 0 && (
          <Botao variante="fantasma" tamanho="sm" onClick={() => aoMudar(RECORTE_INTEIRO)}>
            Limpar
          </Botao>
        )}
      </div>

      {aberto && (
        <div className="flex flex-col gap-5 border-t border-borda-sutil p-4">
          <section className="flex flex-col gap-3">
            <div>
              <Rotulo>No arquivo</Rotulo>
              <p className="m-0 mt-1 text-[12px] text-texto-fraco">
                O SPED que não passa aqui nem chega a ser aberto.
              </p>
            </div>

            {estabelecimentos.length > 1 && (
              <div className="flex flex-wrap gap-2">
                {estabelecimentos.map((e) => {
                  const marcado = recorte.cnpjs.includes(e.cnpj);
                  return (
                    <Chip
                      key={e.cnpj}
                      marcado={marcado}
                      aoAlternar={() =>
                        mudar(
                          "cnpjs",
                          marcado
                            ? recorte.cnpjs.filter((c) => c !== e.cnpj)
                            : [...recorte.cnpjs, e.cnpj],
                        )
                      }
                    >
                      <span title={e.empresa} className="font-mono text-[12px]">
                        {formatarCnpj(e.cnpj)}
                      </span>
                    </Chip>
                  );
                })}
              </div>
            )}

            <div className="flex flex-wrap gap-3">
              <Campo rotulo="Período de" tipo="date" valor={recorte.de}
                     aoMudar={(v) => mudar("de", v)} />
              <Campo rotulo="Período até" tipo="date" valor={recorte.ate}
                     aoMudar={(v) => mudar("ate", v)} />
            </div>
          </section>

          <section className="flex flex-col gap-3">
            <div>
              <Rotulo>Na linha</Rotulo>
              <p className="m-0 mt-1 text-[12px] text-texto-fraco">
                Vários valores separados por vírgula. O campo é procurado em qualquer registro do
                recorte — <code className="font-mono">CST_PIS</code> acha o do C170 e o do C870.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Campo rotulo="CST do PIS" valor={lista("cst_pis")} largo={false}
                     aoMudar={(v) => mudarLista("cst_pis", v)} dica="01, 50, 70" />
              <Campo rotulo="CST da COFINS" valor={lista("cst_cofins")} largo={false}
                     aoMudar={(v) => mudarLista("cst_cofins", v)} dica="01, 50" />
              <Campo rotulo="CFOP" valor={lista("cfop")} largo={false}
                     aoMudar={(v) => mudarLista("cfop", v)} dica="1102, 5102" />
              <Campo rotulo="Código do item" valor={lista("cod_item")}
                     aoMudar={(v) => mudarLista("cod_item", v)} dica="P01, P02" />
              <Campo rotulo="Natureza (COD_NAT)" valor={lista("cod_nat")} largo={false}
                     aoMudar={(v) => mudarLista("cod_nat", v)} dica="N01" />
              <Campo rotulo="Número do documento" valor={lista("num_doc")} largo={false}
                     aoMudar={(v) => mudarLista("num_doc", v)} dica="123, 124" />
              <Campo rotulo="Ajuste (COD_AJ)" valor={lista("cod_aj")} largo={false}
                     aoMudar={(v) => mudarLista("cod_aj", v)} dica="01, 02" />
              <Campo rotulo="Indicador do ajuste" valor={lista("ind_aj")} largo={false}
                     aoMudar={(v) => mudarLista("ind_aj", v)} dica="0 redução, 1 acréscimo" />
              <Campo rotulo="Descrição contém" valor={lista("descricao")}
                     aoMudar={(v) => mudarLista("descricao", v)} dica="pão, farinha" />
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <span className="text-[11px] font-bold text-texto-suave">Operação</span>
                <div className="flex gap-2">
                  {[
                    { valor: "", rotulo: "Todas" },
                    { valor: "0", rotulo: "Entrada" },
                    { valor: "1", rotulo: "Saída" },
                  ].map((o) => (
                    <Chip
                      key={o.valor || "todas"}
                      marcado={recorte.ind_oper === o.valor}
                      aoAlternar={() => mudar("ind_oper", o.valor)}
                    >
                      {o.rotulo}
                    </Chip>
                  ))}
                </div>
              </div>
              <Campo rotulo="Documento de" tipo="date" valor={recorte.doc_de}
                     aoMudar={(v) => mudar("doc_de", v)} />
              <Campo rotulo="Documento até" tipo="date" valor={recorte.doc_ate}
                     aoMudar={(v) => mudar("doc_ate", v)} />
            </div>

            <div className="flex flex-wrap gap-3">
              <Campo rotulo="Valor do item, de" valor={recorte.vl_item_min} largo={false}
                     aoMudar={(v) => mudar("vl_item_min", v)} dica="0,00" />
              <Campo rotulo="Valor do item, até" valor={recorte.vl_item_max} largo={false}
                     aoMudar={(v) => mudar("vl_item_max", v)} dica="1.000,00" />
              <Campo rotulo="Valor do PIS, de" valor={recorte.vl_pis_min} largo={false}
                     aoMudar={(v) => mudar("vl_pis_min", v)} dica="0,00" />
              <Campo rotulo="Valor do PIS, até" valor={recorte.vl_pis_max} largo={false}
                     aoMudar={(v) => mudar("vl_pis_max", v)} dica="100,00" />
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

/** Um campo do recorte. Pequeno de propósito: são dezenove deles na tela. */
function Campo({
  rotulo,
  valor,
  aoMudar,
  dica,
  tipo = "text",
  largo = true,
}: {
  rotulo: string;
  valor: string;
  aoMudar: (v: string) => void;
  dica?: string;
  tipo?: "text" | "date";
  largo?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] font-bold text-texto-suave">{rotulo}</span>
      <input
        type={tipo}
        value={valor}
        onChange={(e) => aoMudar(e.target.value)}
        placeholder={dica}
        className={cn(
          "rounded-raio border border-borda-forte bg-superficie px-3 py-2",
          "text-[13px] text-texto placeholder:text-texto-fraco transition-colors",
          "focus:border-laranja-500/55 focus:outline-none",
          largo ? "w-[220px]" : "w-[150px]",
        )}
      />
    </label>
  );
}

function formatarCnpj(c: string): string {
  return c.length === 14
    ? `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}`
    : c;
}

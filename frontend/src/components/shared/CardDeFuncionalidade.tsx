import { Link } from "react-router-dom";
import { Etiqueta, type TomDeEtiqueta } from "@/components/ui/Etiqueta";
import { cn } from "@/lib/cn";
import type { Etapa } from "@/services/importacao";

/**
 * Uma funcionalidade do trabalho, como card.
 *
 * É o card do hub (`CardDeEscolha`) um nível abaixo: lá se escolhe o tributo,
 * aqui se escolhe o que fazer dentro do trabalho. Mesma anatomia de propósito —
 * sigla, etiqueta, nome, o que aquilo é, e o chamado no rodapé —, porque quem
 * acabou de escolher PIS/COFINS na tela anterior não deveria precisar aprender
 * uma segunda gramática de tela.
 *
 * **A cor aqui é da situação, não do assunto.** No hub a cor separa ICMS de
 * PIS/COFINS; dentro do trabalho o assunto já é um só, e o que muda de card
 * para card é o andamento: verde concluída, laranja em curso, apagada a que
 * ainda não existe.
 *
 * **Nada some por estar bloqueado.** Sem destino, o card continua na tela,
 * apagado e com o motivo no `title` — some o caminho, fica a razão. Card que
 * desaparece faz a pessoa procurar a funcionalidade que ela sabe que existe.
 */

const TOM: Record<string, TomDeEtiqueta> = {
  concluida: "sucesso",
  em_andamento: "atencao",
  falhou: "erro",
  pendente: "neutro",
  nao_disponivel: "neutro",
};

/** A sigla do ícone, na mesma ideia das do hub (P/C, ICMS, IR/CS). */
const SIGLAS: Record<string, string> = {
  importar: "ARQ",
  conferencia: "CONF",
  movimentos: "MOV",
  st_suportado: "ST",
  razao: "RZ",
  apuracao: "APU",
  arquivo_digital: "AD",
  pre_validacao: "PV",
  entrega: "ENT",
  quebra_de_sped: "QSP",
  apuracao_piscofins: "037",
  apuracao_contribuicoes: "GES",
  quebra_xml: "XML",
  credito_outorgado: "OUT",
  combustivel: "CMB",
};

/** Sem entrada na tabela, as iniciais servem: "Razão contábil" vira "RC". */
function sigla(e: Etapa): string {
  const pronta = SIGLAS[e.chave];
  if (pronta) return pronta;
  const palavras = e.nome.split(/\s+/).filter((p) => p.length > 2);
  return (palavras.map((p) => p[0]).join("") || e.nome.slice(0, 3)).toUpperCase().slice(0, 4);
}

export interface Funcionalidade {
  etapa: Etapa;
  /** null quando não há para onde ir; o motivo explica por quê */
  destino: string | null;
  motivo?: string;
}

export function CardDeFuncionalidade({ etapa, destino, motivo }: Funcionalidade) {
  const concluida = etapa.situacao === "concluida";
  const emCurso = etapa.situacao === "em_andamento";
  const morto = destino === null;

  const moldura = cn(
    "group relative flex min-h-[210px] flex-col gap-3 overflow-hidden rounded-cartao border p-5 no-underline transition-all",
    morto && "cursor-default border-borda bg-superficie-vidro opacity-60",
    !morto && "border-borda bg-superficie shadow-cat hover:-translate-y-1 hover:shadow-lg",
    !morto && concluida && "hover:border-sucesso/55",
    !morto && !concluida && "hover:border-laranja-500/55",
    "focus-visible:outline-2 focus-visible:outline-borda-foco",
  );

  const corpo = (
    <>
      {/* o brilho do canto, na cor do andamento */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute -left-10 -top-10 h-36 w-36 rounded-full opacity-50 blur-2xl transition-opacity",
          !morto && "group-hover:opacity-90",
          concluida ? "bg-sucesso/14" : emCurso ? "bg-laranja-500/16" : "bg-texto-fraco/10",
        )}
      />

      <div className="relative flex items-start justify-between gap-3">
        <span
          aria-hidden
          className={cn(
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] font-mono text-[12px] font-extrabold",
            concluida && "bg-sucesso/14 text-sucesso",
            emCurso && "bg-laranja-500/14 text-marca-laranja",
            !concluida && !emCurso && "bg-texto-fraco/12 text-texto-suave",
          )}
        >
          {sigla(etapa)}
        </span>
        <Etiqueta tom={TOM[etapa.situacao] ?? "neutro"} pulso={emCurso}>
          {etapa.situacao_rotulo}
        </Etiqueta>
      </div>

      <div className="relative flex-1">
        <h3 className="m-0 text-[18px] font-extrabold leading-tight text-texto">{etapa.nome}</h3>
        <p className="m-0 mt-2 line-clamp-4 text-[13px] leading-relaxed text-texto-fraco [text-wrap:pretty]">
          {etapa.descricao}
        </p>
      </div>

      {/* Só o card indisponível tem rodapé, e o que vai nele é o motivo.
          O "Abrir →" saiu em 23/09/2026: o card inteiro é um `<Link>`, então a
          chamada repetia o que o cartão já é — e a etiqueta de situação, no
          topo, já diz em que pé a funcionalidade está. */}
      {morto && (
        <div className="relative border-t border-borda-sutil pt-3 text-[13px] font-bold text-texto-fraco">
          {motivo ?? "Indisponível"}
        </div>
      )}
    </>
  );

  if (morto) {
    return (
      <div className={moldura} title={motivo} aria-disabled>
        {corpo}
      </div>
    );
  }

  return (
    <Link to={destino} className={moldura}>
      {corpo}
    </Link>
  );
}

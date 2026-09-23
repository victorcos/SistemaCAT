import { Link } from "react-router-dom";
import { corDoAssunto } from "@/constants/assuntos";
import { cn } from "@/lib/cn";
import { numero } from "@/lib/format";

/**
 * O card das telas de entrada — segmentos e módulos.
 *
 * Os dois níveis mostram a mesma coisa com palavras diferentes: uma sigla, um
 * nome, o que aquilo é, quantos trabalhos há e para onde se vai. Ter um
 * componente só é o que garante que o segundo nível não vire uma cópia do
 * primeiro com três pixels de diferença.
 *
 * **A cor é do assunto, não do card.** Cada segmento tem a sua, e ela se repete
 * no ícone, na borda ao passar o mouse e no chamado do rodapé — é o que faz
 * alguém reconhecer "o azul é o ICMS" antes de ler o nome. A tabela mora em
 * `constants/assuntos`, com as pílulas que usam a mesma cor em outras telas.
 */

/** A sigla do ícone. Sem entrada, as três primeiras letras servem. */
const SIGLAS: Record<string, string> = {
  piscofins: "P/C",
  cbs: "CBS",
  icms: "ICMS",
  ibs: "IBS",
  irpj_csll: "IR/CS",
  usuarios: "USR",
};

export interface Escolha {
  chave: string;
  rotulo: string;
  descricao: string;
  para: string;
  /** o texto do canto do ícone: "2 frentes", "demandas", "só gestores" */
  etiqueta: string;
  /** o que o rodapé conta. Ausente some — melhor que mostrar zero inventado */
  contagem?: { quantos: number; rotulo: string };
  chamada: string;
}

export function CardDeEscolha({ escolha }: { escolha: Escolha }) {
  const tema = corDoAssunto(escolha.chave);
  const sigla = SIGLAS[escolha.chave] ?? escolha.rotulo.slice(0, 4).toUpperCase();

  return (
    <Link
      to={escolha.para}
      className={cn(
        "group relative flex min-h-[236px] flex-col gap-3 overflow-hidden rounded-cartao",
        "border border-borda bg-superficie p-6 no-underline shadow-cat transition-all",
        "hover:-translate-y-1 hover:shadow-lg focus-visible:outline-2 focus-visible:outline-borda-foco",
        tema.anel,
      )}
    >
      {/* o brilho do canto, na cor do assunto */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute -left-10 -top-10 h-40 w-40 rounded-full opacity-60 blur-2xl transition-opacity group-hover:opacity-100",
          tema.fundo,
        )}
      />

      <div className="relative flex items-start justify-between gap-3">
        <span
          aria-hidden
          className={cn(
            "flex h-12 w-12 shrink-0 items-center justify-center rounded-[14px] font-mono text-[13px] font-extrabold",
            tema.fundo,
            tema.texto,
          )}
        >
          {sigla}
        </span>
        <span className="rounded-full border border-borda px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.12em] text-texto-fraco">
          {escolha.etiqueta}
        </span>
      </div>

      <div className="relative flex-1">
        <h2 className="m-0 text-[22px] font-extrabold leading-tight text-texto">{escolha.rotulo}</h2>
        <p className="m-0 mt-2 text-[13px] leading-relaxed text-texto-fraco">{escolha.descricao}</p>
      </div>

      <div className="relative flex items-end justify-between gap-3 border-t border-borda-sutil pt-3.5">
        <span className="min-w-0">
          {escolha.contagem ? (
            <>
              <span className="block font-mono text-[26px] font-extrabold leading-none text-texto">
                {numero(escolha.contagem.quantos)}
              </span>
              <span className="mt-1 block text-[11px] text-texto-fraco">
                {escolha.contagem.rotulo}
              </span>
            </>
          ) : (
            <span className="block text-[11px] text-texto-fraco">&nbsp;</span>
          )}
        </span>
        <span className={cn("shrink-0 text-[13px] font-bold", tema.texto)}>
          {escolha.chamada} →
        </span>
      </div>
    </Link>
  );
}

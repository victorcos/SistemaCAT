import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { IconeAbrir, IconeBusca, IconeConfirma, IconeFechar2 } from "@/constants/icons";
import { cn } from "@/lib/cn";

export interface OpcaoDeCombobox<T extends string> {
  valor: T;
  rotulo: string;
}

interface Props<T extends string> {
  id?: string;
  "aria-describedby"?: string;
  valor: T;
  opcoes: OpcaoDeCombobox<T>[];
  aoMudar: (valor: T) => void;
  disabled?: boolean;
  /** texto do campo de busca dentro do painel */
  placeholderDaBusca?: string;
  className?: string;
}

/**
 * Seletor com busca, no lugar do `<select>` nativo.
 *
 * A spec da tela de usuários pede que nenhum dropdown seja nativo: o select
 * do navegador não segue o tema, não tem busca e some dentro de modal em
 * alguns navegadores. Este componente faz o que o protótipo mostrava —
 * painel com campo de busca focado ao abrir, filtro por substring, fecha ao
 * escolher e ao clicar fora — e o que o protótipo deixou para a
 * implementação real: teclado (↑ ↓ Enter Esc Home End), papéis ARIA de
 * combobox/listbox/option e `aria-activedescendant`.
 *
 * Abre para baixo; quando não há espaço abaixo, abre para cima. Sem
 * portal: o Modal do sistema não tem `overflow: hidden` justamente para o
 * painel não ser cortado.
 */
export function Combobox<T extends string>({
  id,
  "aria-describedby": describedBy,
  valor,
  opcoes,
  aoMudar,
  disabled,
  placeholderDaBusca = "Buscar…",
  className,
}: Props<T>) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const [ativo, setAtivo] = useState(0);
  const [paraCima, setParaCima] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLInputElement>(null);
  const lista = useRef<HTMLUListElement>(null);
  const idLista = useId();

  const filtradas = useMemo(() => {
    const termo = busca.trim().toLocaleLowerCase("pt-BR");
    return termo
      ? opcoes.filter((o) => o.rotulo.toLocaleLowerCase("pt-BR").includes(termo))
      : opcoes;
  }, [busca, opcoes]);

  const escolhida = opcoes.find((o) => o.valor === valor);

  function abrir() {
    if (disabled) return;
    setBusca("");
    setAtivo(Math.max(0, opcoes.findIndex((o) => o.valor === valor)));
    // painel de 260px (busca + lista): se não couber abaixo, vai para cima
    const caixa = raiz.current?.getBoundingClientRect();
    setParaCima(!!caixa && window.innerHeight - caixa.bottom < 260 && caixa.top > 260);
    setAberto(true);
    // o input só existe depois do render do painel
    window.setTimeout(() => campo.current?.focus(), 0);
  }

  function fechar(devolverFoco = true) {
    setAberto(false);
    setBusca("");
    if (devolverFoco) raiz.current?.querySelector("button")?.focus();
  }

  function escolher(o: OpcaoDeCombobox<T>) {
    aoMudar(o.valor);
    fechar();
  }

  // clique fora fecha — em captura, para ganhar de qualquer stopPropagation
  useEffect(() => {
    if (!aberto) return;
    function aoClicar(e: MouseEvent) {
      if (!raiz.current?.contains(e.target as Node)) fechar(false);
    }
    document.addEventListener("mousedown", aoClicar, true);
    return () => document.removeEventListener("mousedown", aoClicar, true);
  });

  // a opção ativa acompanha o teclado sem sair da área visível
  useEffect(() => {
    if (!aberto) return;
    lista.current
      ?.querySelector<HTMLElement>(`[data-indice="${ativo}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [ativo, aberto]);

  function aoTeclar(e: KeyboardEvent) {
    if (!aberto) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        abrir();
      }
      return;
    }
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setAtivo((i) => Math.min(i + 1, filtradas.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setAtivo((i) => Math.max(i - 1, 0));
        break;
      case "Home":
        e.preventDefault();
        setAtivo(0);
        break;
      case "End":
        e.preventDefault();
        setAtivo(filtradas.length - 1);
        break;
      case "Enter":
        e.preventDefault();
        if (filtradas[ativo]) escolher(filtradas[ativo]);
        break;
      case "Escape":
        e.preventDefault();
        fechar();
        break;
      case "Tab":
        fechar(false);
        break;
    }
  }

  const idAtiva = aberto && filtradas[ativo] ? `${idLista}-${ativo}` : undefined;
  const Caret = aberto ? IconeFechar2 : IconeAbrir;

  return (
    <div ref={raiz} className={cn("relative", className)} onKeyDown={aoTeclar}>
      <button
        type="button"
        id={id}
        role="combobox"
        aria-expanded={aberto}
        aria-controls={idLista}
        aria-haspopup="listbox"
        aria-activedescendant={idAtiva}
        aria-describedby={describedBy}
        disabled={disabled}
        onClick={() => (aberto ? fechar() : abrir())}
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-raio border px-3 py-2.5",
          "text-left text-[15px] font-semibold text-texto transition-colors",
          "bg-superficie hover:not-disabled:border-texto-fraco",
          "focus:outline-none focus-visible:border-borda-foco",
          aberto ? "border-borda-foco" : "border-borda-forte",
          "disabled:cursor-not-allowed disabled:bg-superficie-alt disabled:text-texto-fraco",
        )}
      >
        <span className="truncate">{escolhida?.rotulo ?? "—"}</span>
        <Caret size={15} strokeWidth={2} className="shrink-0 text-texto-fraco" aria-hidden />
      </button>

      {aberto && (
        <div
          className={cn(
            "absolute left-0 right-0 z-[90] overflow-hidden rounded-raio-g border border-borda-forte",
            "bg-superficie-elevada shadow-cat-alta animate-entrada",
            paraCima ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]",
          )}
        >
          <div className="relative border-b border-borda p-2">
            <IconeBusca
              size={13}
              strokeWidth={2}
              className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-texto-fraco"
              aria-hidden
            />
            <input
              ref={campo}
              type="text"
              value={busca}
              onChange={(e) => {
                setBusca(e.target.value);
                setAtivo(0);
              }}
              placeholder={placeholderDaBusca}
              aria-label={placeholderDaBusca}
              aria-autocomplete="list"
              aria-controls={idLista}
              className={cn(
                "w-full rounded-raio border border-borda bg-superficie py-2 pl-7 pr-2.5",
                "text-[13px] text-texto focus:outline-none focus:border-borda-foco",
              )}
            />
          </div>
          <ul
            ref={lista}
            id={idLista}
            role="listbox"
            className="m-0 max-h-[200px] list-none overflow-y-auto p-1.5"
          >
            {filtradas.length === 0 && (
              <li className="px-2.5 py-3 text-xs text-texto-fraco">Nenhum resultado</li>
            )}
            {filtradas.map((o, i) => {
              const selecionada = o.valor === valor;
              return (
                <li
                  key={o.valor}
                  id={`${idLista}-${i}`}
                  data-indice={i}
                  role="option"
                  aria-selected={selecionada}
                  onMouseEnter={() => setAtivo(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => escolher(o)}
                  className={cn(
                    "flex cursor-pointer items-center justify-between gap-2 rounded-raio px-2.5 py-2",
                    "text-[13px] font-semibold",
                    selecionada ? "bg-laranja-100 text-laranja-800 escuro:bg-laranja-900/40 escuro:text-laranja-300"
                                : "text-texto",
                    i === ativo && !selecionada && "bg-acao2-hover",
                  )}
                >
                  <span className="truncate">{o.rotulo}</span>
                  {selecionada && <IconeConfirma size={14} strokeWidth={2.2} aria-hidden />}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Tabela de dados.
 *
 * `<table>` de verdade, e não uma grade de divs: aqui há cabeçalho de coluna,
 * e leitor de tela precisa dele para dizer "Competência, 05/2021" em vez de
 * ler células soltas. (A de usuários é grade porque cada linha é um cartão
 * com avatar e ações, não uma matriz de valores.)
 *
 * A rolagem horizontal fica no invólucro: tabela larga não pode empurrar a
 * página inteira para o lado.
 */
export function Tabela({
  colunas,
  children,
  className,
}: {
  colunas: ReactNode[];
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("overflow-x-auto rounded-raio-g border border-borda", className)}>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="bg-tabela-cabecalho-fundo">
            {colunas.map((c, i) => (
              <th
                key={i}
                className="whitespace-nowrap px-3.5 py-2.5 text-left text-[10px] font-extrabold uppercase tracking-[0.14em] text-tabela-cabecalho-texto"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Linha({
  children,
  apagada,
  className,
}: {
  children: ReactNode;
  /** linha que não conta para o trabalho: entra mais fraca, mas não some */
  apagada?: boolean;
  className?: string;
}) {
  return (
    <tr
      className={cn(
        "border-t border-borda-sutil transition-colors hover:bg-tabela-linha-hover",
        apagada && "opacity-60",
        className,
      )}
    >
      {children}
    </tr>
  );
}

export function Celula({
  children,
  mono,
  nota,
  title,
  className,
}: {
  children?: ReactNode;
  mono?: boolean;
  /** segunda linha, menor: o motivo, o detalhe, o caminho */
  nota?: ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <td
      title={title}
      className={cn("px-3.5 py-2.5 align-top text-texto", mono && "font-mono", className)}
    >
      {children}
      {nota && <span className="mt-0.5 block text-xs text-texto-fraco">{nota}</span>}
    </td>
  );
}

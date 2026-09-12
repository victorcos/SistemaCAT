import type { ReactNode } from "react";
import {
  IconeAtencao,
  IconeErro,
  IconeFechar,
  IconeInfo,
  IconeSucesso,
  type Icone,
} from "@/constants/icons";
import { cn } from "@/lib/cn";

export type TomDeAviso = "erro" | "atencao" | "sucesso" | "info";

const TONS: Record<TomDeAviso, { classe: string; icone: Icone }> = {
  erro: { classe: "text-erro bg-erro-fundo border-l-erro", icone: IconeErro },
  atencao: {
    classe: "text-atencao bg-atencao-fundo border-l-atencao",
    icone: IconeAtencao,
  },
  sucesso: {
    classe: "text-sucesso bg-sucesso-fundo border-l-sucesso",
    icone: IconeSucesso,
  },
  info: { classe: "text-info bg-info-fundo border-l-info", icone: IconeInfo },
};

interface Props {
  tom?: TomDeAviso;
  titulo?: ReactNode;
  children?: ReactNode;
  /** X-Request-Id: é o que liga a mensagem na tela à linha exata no log */
  codigo?: string;
  acao?: ReactNode;
  aoFechar?: () => void;
  className?: string;
}

/**
 * Mensagem de erro, aviso ou confirmação.
 *
 * O bloco `<div className="aviso aviso--erro" role="alert">` aparecia 19 vezes
 * no projeto, quase sempre com o mesmo miolo: mensagem, código de suporte e às
 * vezes um "Tentar de novo". Isto é esse bloco.
 */
export function Aviso({
  tom = "erro",
  titulo,
  children,
  codigo,
  acao,
  aoFechar,
  className,
}: Props) {
  const { classe, icone: Ico } = TONS[tom];
  return (
    <div
      role={tom === "erro" ? "alert" : "status"}
      className={cn(
        "flex gap-3 rounded-raio border-l-[3px] px-3.5 py-3 text-sm",
        classe,
        className,
      )}
    >
      <Ico size={18} strokeWidth={2} className="mt-px shrink-0" aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {titulo && <strong className="font-[650]">{titulo}</strong>}
        {children && <div className="[text-wrap:pretty]">{children}</div>}
        {codigo && (
          <span className="font-mono text-xs opacity-85">
            Código para suporte: {codigo}
          </span>
        )}
        {acao && <div className="mt-1.5">{acao}</div>}
      </div>
      {aoFechar && (
        <button
          type="button"
          onClick={aoFechar}
          title="Dispensar"
          aria-label="Dispensar"
          className="-mr-1 -mt-1 h-7 w-7 shrink-0 rounded opacity-70 hover:opacity-100"
        >
          <IconeFechar size={15} strokeWidth={2} className="mx-auto" aria-hidden />
        </button>
      )}
    </div>
  );
}

import { IconeConfirma } from "@/constants/icons";
import { cn } from "@/lib/cn";

/**
 * Medidor de força e lista de requisitos da senha.
 *
 * A política é a mesma do domínio (`validar_senha`), repetida aqui para dar
 * retorno **enquanto** a pessoa digita em vez de só ao enviar. Quem decide
 * continua sendo o servidor: isto é ajuda, não autorização.
 */

export const MINIMO = 10;

export const REGRAS = [
  { texto: `Pelo menos ${MINIMO} caracteres`, testa: (s: string) => s.length >= MINIMO },
  {
    texto: "Maiúsculas e minúsculas",
    testa: (s: string) => s !== s.toLowerCase() && s !== s.toUpperCase(),
  },
  { texto: "Pelo menos um número", testa: (s: string) => /\d/.test(s) },
  { texto: "Sem espaço no início ou no fim", testa: (s: string) => s.trim() === s },
];

/** Quantas regras a senha cumpre. Zero a quatro. */
export const forcaDe = (senha: string) =>
  senha.length === 0 ? 0 : REGRAS.filter((r) => r.testa(senha)).length;

export const senhaServe = (senha: string) => forcaDe(senha) === REGRAS.length;

const NIVEIS = [
  { rotulo: "Muito fraca", cor: "bg-erro", texto: "text-erro" },
  { rotulo: "Fraca", cor: "bg-erro", texto: "text-erro" },
  { rotulo: "Razoável", cor: "bg-atencao", texto: "text-atencao" },
  { rotulo: "Boa", cor: "bg-atencao", texto: "text-atencao" },
  { rotulo: "Forte", cor: "bg-sucesso", texto: "text-sucesso" },
];

export function ForcaDaSenha({ senha }: { senha: string }) {
  const forca = forcaDe(senha);
  const nivel = NIVEIS[forca];

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center gap-2">
        <div className="flex flex-1 gap-1.5" aria-hidden>
          {REGRAS.map((_, i) => (
            <span
              key={i}
              className={cn(
                "h-1 flex-1 rounded-full transition-colors",
                i < forca ? nivel.cor : "bg-superficie-alt",
              )}
            />
          ))}
        </div>
        {senha.length > 0 && (
          <span className={cn("text-xs font-bold", nivel.texto)}>{nivel.rotulo}</span>
        )}
      </div>

      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {REGRAS.map((r) => {
          const ok = senha.length > 0 && r.testa(senha);
          return (
            <li
              key={r.texto}
              className={cn(
                "flex items-center gap-2 text-xs",
                ok ? "text-sucesso" : "text-texto-fraco",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full",
                  ok ? "bg-sucesso-fundo" : "bg-superficie-alt",
                )}
              >
                {ok && <IconeConfirma size={9} strokeWidth={3.5} />}
              </span>
              {r.texto}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

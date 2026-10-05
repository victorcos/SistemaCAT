/**
 * Formatação para leitura humana, em pt-BR.
 *
 * Estava espalhada: `numero` e `dinheiro` em services/conferencia.ts,
 * `tamanho` e `competencia` em services/lote.ts, `formatarData` dentro da
 * página de usuários. Nenhuma delas fala com a API — é apresentação, e
 * apresentação não mora na camada de transporte.
 */

export const numero = (n: number) => n.toLocaleString("pt-BR");

export const dinheiro = (texto: string) =>
  Number(texto).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });

/** Tamanho legível. Base de trabalho se mede em GB, não em bytes. */
export function tamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const unidades = ["KB", "MB", "GB", "TB"];
  let valor = bytes / 1024;
  let i = 0;
  while (valor >= 1024 && i < unidades.length - 1) {
    valor /= 1024;
    i += 1;
  }
  return `${valor.toFixed(valor >= 100 || i === 0 ? 0 : 1)} ${unidades[i]}`;
}

/** "2025-03-01" vira "03/2025". A competência é o mês. */
export function competencia(iso: string | null): string {
  if (!iso) return "—";
  const [ano, mes] = iso.split("-");
  return `${mes}/${ano}`;
}

/**
 * "2024-02-15" vira "15/02/2024". Data de calendário, não instante.
 *
 * Parte a string em vez de montar um `Date`: `new Date("2024-02-15")` é
 * meia-noite **UTC**, e em Brasília isso volta um dia — a emissão de 15/02
 * apareceria como 14/02. Data de emissão de documento não tem fuso: é o dia
 * que está escrito no arquivo.
 */
export function dia(iso: string | null | undefined, vazio = "—"): string {
  if (!iso) return vazio;
  const [ano, mes, d] = iso.split("-");
  return ano && mes && d ? `${d}/${mes}/${ano}` : iso;
}

/** Data e hora de um instante ISO. `vazio` é o que aparece quando não há
 *  valor — na tela de usuários, "nunca entrou" diz mais que um travessão. */
export function dataHora(iso: string | null, vazio = "—"): string {
  if (!iso) return vazio;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

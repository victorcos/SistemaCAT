/**
 * Competência é mês, não dia.
 *
 * O usuário escreve e lê `MM/AAAA`; a API fala ISO. A conversão vive aqui
 * porque estava escrita de três jeitos — `mes()` no Início, outra igual no
 * Projeto, e o wizard usando `type="date"` com um dia que ninguém escolheu e
 * que aparecia depois na tela.
 *
 * A inicial é sempre o dia 1; a final é o último dia do mês, que é o que a
 * apuração entende por "até 06/2024".
 */

const RE_COMPETENCIA = /^(0[1-9]|1[0-2])\/(\d{4})$/;

/** "2021-05-01" → "05/2021". Vazio vira travessão. */
export function paraTexto(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [ano, mes] = iso.split("-");
  return mes && ano ? `${mes}/${ano}` : "—";
}

/** "05/2021 a 06/2024", que é como se diz o período de um trabalho. */
export const periodo = (ini: string | null, fim: string | null) =>
  `${paraTexto(ini)} a ${paraTexto(fim)}`;

export const valida = (texto: string) => RE_COMPETENCIA.test(texto.trim());

/** "05/2021" → "2021-05-01" (ou o último dia do mês, quando `fimDoMes`). */
export function paraIso(texto: string, fimDoMes = false): string | null {
  const achado = RE_COMPETENCIA.exec(texto.trim());
  if (!achado) return null;
  const [, mes, ano] = achado;
  if (!fimDoMes) return `${ano}-${mes}-01`;
  // dia 0 do mês seguinte é o último dia deste — sem tabela de meses nem
  // regra de bissexto escrita à mão
  const ultimo = new Date(Number(ano), Number(mes), 0).getDate();
  return `${ano}-${mes}-${String(ultimo).padStart(2, "0")}`;
}

/** Compara duas competências em MM/AAAA. Negativo, zero ou positivo. */
export function compara(a: string, b: string): number {
  const ia = paraIso(a);
  const ib = paraIso(b);
  if (!ia || !ib) return 0;
  return ia < ib ? -1 : ia > ib ? 1 : 0;
}

/** Máscara de digitação: mantém só dígitos e põe a barra depois do mês. */
export function mascarar(bruto: string): string {
  const d = bruto.replace(/\D/g, "").slice(0, 6);
  return d.length <= 2 ? d : `${d.slice(0, 2)}/${d.slice(2)}`;
}

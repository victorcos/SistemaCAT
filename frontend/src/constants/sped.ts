/** Os tipos de SPED que o cadastro reconhece pelo registro 0000. As chaves são
 *  as de `TipoSped`, no motor; o rótulo é curto de propósito, porque aparece
 *  na composição da remessa ("1 EFD Contribuições"). */
export const TIPOS_DE_SPED: Record<string, string> = {
  efd_icms_ipi: "EFD ICMS/IPI",
  efd_contribuicoes: "EFD Contribuições",
  ecd: "ECD",
  ecf: "ECF",
};

/** "efd_contribuicoes" -> "EFD Contribuições"; tipo novo aparece pela chave. */
export const rotuloDoSped = (chave: string) => TIPOS_DE_SPED[chave] ?? chave;

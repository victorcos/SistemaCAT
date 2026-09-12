import type { Cargo, Papel } from "@/types/auth";

/** Rótulos e explicações vêm do domínio, não da tela. Mantidos juntos aqui
 *  para que nenhuma tela invente um nome diferente para o mesmo papel. */
export const PAPEIS: Record<Papel, { rotulo: string; ajuda: string }> = {
  dev: {
    rotulo: "Dev",
    ajuda: "Manutenção do sistema. Enxerga toda empresa, com ou sem alocação.",
  },
  gestor: {
    rotulo: "Gestor",
    ajuda: "Administra usuários e alocações.",
  },
  analista: {
    rotulo: "Analista",
    ajuda: "Executa apuração e aprova de-para.",
  },
  revisor: {
    rotulo: "Revisor",
    ajuda: "Confere e aprova entrega.",
  },
  leitura: {
    rotulo: "Leitura",
    ajuda: "Só consulta.",
  },
};

export const CARGOS: Record<Cargo, string> = {
  diretor: "Diretor",
  gerente: "Gerente",
  coordenador: "Coordenador",
  analista: "Analista",
  estagiario: "Estagiário",
  outro: "Outro",
};

/** A ordem em que papel e cargo aparecem num seletor.
 *
 *  Existe porque as telas usavam Object.keys(PAPEIS), que depende da ordem de
 *  inserção do objeto — funciona hoje e quebra silenciosamente no dia em que
 *  alguém reordenar o dicionário acima. Aqui a ordem é dita, não deduzida. */
export const ORDEM_PAPEIS: Papel[] = [
  "gestor",
  "analista",
  "revisor",
  "leitura",
  "dev",
];

export const ORDEM_CARGOS: Cargo[] = [
  "diretor",
  "gerente",
  "coordenador",
  "analista",
  "estagiario",
  "outro",
];

/** Papéis que administram usuários. Espelha Papel.administra_usuarios no
 *  domínio — a tela usa isto só para esconder o que a API já recusaria. */
export const ADMINISTRA_USUARIOS: Papel[] = ["dev", "gestor"];

/** Papéis que apagam um trabalho inteiro. Espelha Papel.pode_excluir_trabalho
 *  no domínio. Analista e revisor escrevem, apuram e entregam — mas não
 *  desfazem meses de trabalho de uma vez. A tela usa isto só para esconder o
 *  botão; quem recusa de verdade é a API. */
export const PODE_EXCLUIR_TRABALHO: Papel[] = ["dev", "gestor"];

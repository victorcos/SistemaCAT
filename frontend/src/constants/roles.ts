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
    ajuda:
      "Responde pela carteira inteira: enxerga toda empresa e administra " +
      "usuários e alocações.",
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

/** Papéis que enxergam toda empresa, alocados ou não. Espelha
 *  Papel.ignora_escopo_de_empresa no domínio.
 *
 *  Gestor está aqui porque responde pela carteira inteira da casa — exigir
 *  que alguém o alocasse em cada empresa nova era trabalho que ninguém fazia,
 *  e o gestor entrava num sistema vazio. Dev, porque manutenção precisa
 *  reproduzir problema em qualquer cliente.
 *
 *  Para estes dois, a tela de alocação não muda nada, e "0 empresas" não é
 *  aviso de nada — é por isso que três telas consultam esta lista. */
export const IGNORA_ESCOPO_DE_EMPRESA: Papel[] = ["dev", "gestor"];

/** Quem enxerga todo segmento tributário, esteja o que estiver gravado.
 *
 *  Espelha `Papel.EnxergaTodosOsSegmentos` no servidor — que é quem decide.
 *  A tela repete para não oferecer uma escolha que a API ignoraria. */
export const ENXERGA_TODOS_OS_SEGMENTOS: Papel[] = ["dev", "gestor"];

export const enxergaTodasAsEmpresas = (papel: Papel) =>
  IGNORA_ESCOPO_DE_EMPRESA.includes(papel);

/** Papéis que apagam um trabalho inteiro. Espelha Papel.pode_excluir_trabalho
 *  no domínio. Analista e revisor escrevem, apuram e entregam — mas não
 *  desfazem meses de trabalho de uma vez. A tela usa isto só para esconder o
 *  botão; quem recusa de verdade é a API. */
export const PODE_EXCLUIR_TRABALHO: Papel[] = ["dev", "gestor"];

/** Papéis que aprovam a entrega. Espelha Papel.pode_aprovar_entrega no
 *  domínio: quem responde pelo que sai do escritório. Dev fica de fora — conta
 *  técnica não substitui responsável pelo negócio. A tela usa isto só para
 *  mostrar o botão; quem recusa de verdade é a API. */
export const PODE_APROVAR_ENTREGA: Papel[] = ["revisor", "gestor"];

/** Papéis que escrevem: criam e mudam trabalho, rodam etapa. Espelha
 *  Papel.pode_escrever no domínio; só "leitura" fica de fora. */
export const PODE_ESCREVER: Papel[] = ["dev", "gestor", "analista", "revisor"];

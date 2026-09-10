export type Papel = "dev" | "gestor" | "analista" | "revisor" | "leitura";

export type Cargo =
  | "diretor"
  | "gerente"
  | "coordenador"
  | "analista"
  | "estagiario"
  | "outro";

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

/** Papéis que administram usuários. Espelha Papel.administra_usuarios no
 *  domínio — a tela usa isto só para esconder o que a API já recusaria. */
export const ADMINISTRA_USUARIOS: Papel[] = ["dev", "gestor"];

/** Papéis que apagam um trabalho inteiro. Espelha Papel.pode_excluir_trabalho
 *  no domínio. Analista e revisor escrevem, apuram e entregam — mas não
 *  desfazem meses de trabalho de uma vez. A tela usa isto só para esconder o
 *  botão; quem recusa de verdade é a API. */
export const PODE_EXCLUIR_TRABALHO: Papel[] = ["dev", "gestor"];

export interface Usuario {
  id: number;
  usuario: string;
  email: string;
  nome_exibicao: string;
  papel: Papel;
  cargo: Cargo;
  empresas: number[];
  senha_provisoria: boolean;
  ultimo_acesso: string | null;
}

/** O que a listagem de gestão devolve, com os campos que só o gestor vê. */
export interface UsuarioResumo extends Usuario {
  ativo: boolean;
  bloqueado: boolean;
  tentativas_falhas: number;
}

export interface RespostaToken {
  access_token: string;
  token_type: string;
  expires_in: number;
  usuario: Usuario;
}

export interface UsuarioCriado {
  usuario: UsuarioResumo;
  senha_provisoria: string;
  aviso: string;
}

export interface SenhaRedefinida {
  senha_provisoria: string;
  aviso: string;
}

/** Erro com o identificador da requisição, para casar com o log do servidor. */
export class ErroApi extends Error {
  constructor(
    mensagem: string,
    readonly status: number,
    readonly requisicaoId?: string,
  ) {
    super(mensagem);
    this.name = "ErroApi";
  }
}

export type Papel = "dev" | "gestor" | "analista" | "revisor" | "leitura";

export type Cargo =
  | "diretor"
  | "gerente"
  | "coordenador"
  | "analista"
  | "estagiario"
  | "outro";

export interface Usuario {
  id: number;
  usuario: string;
  email: string;
  nome_exibicao: string;
  papel: Papel;
  cargo: Cargo;
  empresas: number[];
  /** os segmentos tributários que a pessoa enxerga; para gestor e dev, todos */
  segmentos: string[];
  /** para onde a tela inicial deve mandá-la, já resolvido no servidor.
   *  Nulo quando nenhum segmento foi liberado — aí a tela pede que procure o gestor. */
  entrada: string | null;
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

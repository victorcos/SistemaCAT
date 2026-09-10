export type Papel = "gestor" | "analista" | "revisor" | "leitura";

export interface Usuario {
  id: number;
  usuario: string;
  email: string;
  nome_exibicao: string;
  papel: Papel;
  empresas: number[];
  ultimo_acesso: string | null;
}

export interface RespostaToken {
  access_token: string;
  token_type: string;
  expires_in: number;
  usuario: Usuario;
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

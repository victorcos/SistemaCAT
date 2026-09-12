/** Erro com o identificador da requisição, para casar com o log do servidor.
 *
 *  Fica fora de auth.ts porque erro de API não é assunto de autenticação:
 *  toda tela e todo serviço levantam este erro, não só o login. */
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

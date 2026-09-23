/**
 * A cor de cada assunto tributário.
 *
 * "O azul é o ICMS" só vira reconhecimento se for **sempre o mesmo azul**, em
 * toda tela. Este arquivo existe porque a mesma tabela já estava escrita em
 * dois lugares — os cards do hub (`CardDeEscolha`) e as pílulas de segmento na
 * lista de usuários —, e a etiqueta do cartão de trabalho ia ser a terceira.
 * Três cópias da mesma verdade divergem no dia em que alguém mexer numa.
 *
 * **As chaves são as dos dois níveis do catálogo do servidor** (`Segmentos`):
 * segmento (`piscofins`, `icms`, `irpj_csll`) e módulo (`cbs`, `ibs`). Dá para
 * consultar por qualquer um dos dois sem saber de que nível é a chave.
 *
 * **O sucessor herda a cor de quem sucede** — a CBS é laranja como PIS/COFINS,
 * o IBS é azul como o ICMS. Na transição de 2027 a 2033 os dois aparecem lado
 * a lado por anos, e quem olha precisa ver na hora que são o mesmo assunto.
 */
export interface CorDoAssunto {
  /** a borda que acende ao passar o mouse, nos cards do hub */
  anel: string;
  /** o fundo do quadrado da sigla e do brilho do canto */
  fundo: string;
  /** a sigla, e o chamado do rodapé */
  texto: string;
  /** a pílula inteira: borda, fundo e texto */
  pilula: string;
}

/**
 * Assunto que este arquivo não conhece — um módulo novo no catálogo do
 * servidor, por exemplo. Cinza é o que se pode dizer com honestidade: não sei
 * o que é isto. Pintá-lo de laranja diria que é PIS/COFINS, que é pior do que
 * não dizer nada.
 */
const NEUTRO: CorDoAssunto = {
  anel: "hover:border-borda-forte",
  fundo: "bg-texto-fraco/12",
  texto: "text-texto-suave",
  pilula: "border-borda-forte bg-superficie-vidro text-texto-suave",
};

const LARANJA: CorDoAssunto = {
  anel: "hover:border-laranja-500/55",
  fundo: "bg-laranja-500/12",
  texto: "text-marca-laranja",
  pilula: "border-laranja-500/40 bg-laranja-500/12 text-laranja-800 escuro:text-laranja-300",
};

const AZUL: CorDoAssunto = {
  anel: "hover:border-azul-400/55",
  fundo: "bg-azul-400/12",
  texto: "text-azul-400",
  pilula: "border-azul-400/40 bg-azul-400/12 text-azul-700 escuro:text-azul-300",
};

const VERDE: CorDoAssunto = {
  anel: "hover:border-sucesso/55",
  fundo: "bg-sucesso/12",
  texto: "text-sucesso",
  pilula: "border-sucesso/40 bg-sucesso-fundo text-sucesso",
};

const CORES: Record<string, CorDoAssunto> = {
  piscofins: LARANJA,
  cbs: LARANJA,
  icms: AZUL,
  ibs: AZUL,
  irpj_csll: VERDE,
  // não é tributo: é o cartão de administração no mesmo hub, e ele não deve
  // disputar atenção com os assuntos
  usuarios: NEUTRO,
};

export const corDoAssunto = (chave?: string | null): CorDoAssunto => CORES[chave ?? ""] ?? NEUTRO;

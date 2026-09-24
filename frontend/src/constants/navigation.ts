import { IconeEnviar, IconePasta, IconeUsuarios, type Icone } from "./icons";
import { ROTAS } from "./routes";
import type { Papel } from "@/types/auth";
import { ADMINISTRA_USUARIOS } from "./roles";

export interface ItemDeMenu {
  para: string;
  rotulo: string;
  icone: Icone;
  /** Quando presente, o item só aparece para estes papéis. A tela usa isto
   *  para não oferecer o que a API recusaria — quem barra de verdade é ela. */
  papeis?: Papel[];
}

export const MENU: ItemDeMenu[] = [
  // o caminho de volta ao hub: sem ele, quem entrasse direto num módulo
  // ficaria preso nele até sair e entrar de novo
  { para: ROTAS.segmentos, rotulo: "Segmentos", icone: IconePasta },
  // "Todos os trabalhos" saiu daqui em 24/09/2026. A rota continua existindo
  // (`/`), e continua servindo a quem chega por link ou por engano — o que ela
  // não faz mais é ser um clique no menu de quem está dentro de um assunto:
  // ali ela misturava ICMS com PIS/COFINS e desfazia o recorte do hub. Para
  // ver os trabalhos de outro tributo, o caminho é Segmentos.
  { para: ROTAS.importar, rotulo: "Cadastro", icone: IconeEnviar },
  {
    para: ROTAS.usuarios,
    rotulo: "Usuários",
    icone: IconeUsuarios,
    papeis: ADMINISTRA_USUARIOS,
  },
];

export const podeVer = (item: ItemDeMenu, papel: Papel) =>
  !item.papeis || item.papeis.includes(papel);

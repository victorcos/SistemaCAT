import { IconeInicio, IconeEnviar, IconePasta, IconeUsuarios, type Icone } from "./icons";
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
  { para: ROTAS.inicio, rotulo: "Todos os trabalhos", icone: IconeInicio },
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

/**
 * Os ícones do sistema, em português e num lugar só.
 *
 * Duas razões para existir este arquivo em vez de cada tela importar do
 * lucide direto:
 *
 * 1. Disciplina. Ninguém inventa um ícone novo para "editar" sem passar por
 *    aqui, então a mesma ação tem o mesmo desenho em todas as telas.
 * 2. Troca de biblioteca. Se um dia o lucide não servir, muda-se este arquivo
 *    e nenhuma tela.
 *
 * Tamanho e espessura de traço ficam nos componentes (Botao, BotaoIcone),
 * nunca no ponto de uso.
 */
export {
  // ações de linha
  Plus as IconeNovo,
  Pencil as IconeEditar,
  KeyRound as IconeChave,
  Power as IconeEnergia,
  LockOpen as IconeDesbloquear,
  Trash2 as IconeApagar,
  Copy as IconeCopiar,
  Download as IconeBaixar,
  Upload as IconeEnviar,
  RefreshCw as IconeTentarDeNovo,

  // navegação e controles
  House as IconeInicio,
  Users as IconeUsuarios,
  Search as IconeBusca,
  ChevronDown as IconeAbrir,
  ChevronUp as IconeFechar2,
  ArrowLeft as IconeVoltar,
  X as IconeFechar,
  Check as IconeConfirma,
  LogOut as IconeSair,

  // estado e feedback
  LoaderCircle as IconeCarregando,
  CircleAlert as IconeErro,
  TriangleAlert as IconeAtencao,
  CircleCheck as IconeSucesso,
  Info as IconeInfo,
  Ban as IconeBloqueado,
  Play as IconeReativar,
  Pause as IconeDesativar,

  // senha
  Eye as IconeVer,
  EyeOff as IconeEsconder,

  // tema
  Sun as IconeClaro,
  Moon as IconeEscuro,
} from "lucide-react";

export type { LucideIcon as Icone } from "lucide-react";

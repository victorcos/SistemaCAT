import { PAPEIS, type Usuario } from "../tipos/auth";
import "./Inicio.css";

/** Provisória: a aplicação de verdade é a etapa 5 do roteiro. */
export default function Inicio({ usuario }: { usuario: Usuario }) {
  return (
    <div className="inicio">
      <h1 className="pagina__titulo">Olá, {usuario.nome_exibicao}</h1>
      <p className="pagina__sub">{PAPEIS[usuario.papel].ajuda}</p>

      <div className="inicio__aviso">
        <strong>Em construção.</strong> As telas de apuração da CAT entram na
        etapa 5 do roteiro. Por ora só o acesso está pronto.
      </div>
    </div>
  );
}

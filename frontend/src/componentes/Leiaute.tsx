import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { sair } from "../servicos/auth";
import { ADMINISTRA_USUARIOS, PAPEIS, type Usuario } from "../tipos/auth";
import logo from "../ativos/bms-branco.png";
import "./Leiaute.css";

interface Props {
  usuario: Usuario;
  aoSair: () => void;
}

interface Item {
  para: string;
  rotulo: string;
  soAdmin?: boolean;
}

const MENU: Item[] = [
  { para: "/", rotulo: "Início" },
  { para: "/importar", rotulo: "Cadastro" },
  { para: "/usuarios", rotulo: "Usuários", soAdmin: true },
];

export default function Leiaute({ usuario, aoSair }: Props) {
  const navegar = useNavigate();
  const admin = ADMINISTRA_USUARIOS.includes(usuario.papel);

  function encerrar() {
    sair();
    aoSair();
    navegar("/", { replace: true });
  }

  return (
    <div className="leiaute">
      {/* A moldura fica azul porque é a única superfície onde o logotipo que
          temos funciona — ver docs/IDENTIDADE.md seção 7. */}
      <aside className="leiaute__menu">
        <img src={logo} alt="BMS Consultoria Tributária" className="leiaute__logo" />

        <nav className="leiaute__nav">
          {MENU.filter((i) => !i.soAdmin || admin).map((i) => (
            <NavLink
              key={i.para}
              to={i.para}
              end={i.para === "/"}
              className={({ isActive }) =>
                `leiaute__link${isActive ? " leiaute__link--ativo" : ""}`
              }
            >
              {i.rotulo}
            </NavLink>
          ))}
        </nav>

        <div className="leiaute__rodape">Sistema CAT</div>
      </aside>

      <div className="leiaute__corpo">
        <header className="leiaute__topo">
          <div className="leiaute__quem">
            <strong>{usuario.nome_exibicao}</strong>
            <span
              className={`etiqueta etiqueta--${usuario.papel}`}
              title={PAPEIS[usuario.papel].ajuda}
            >
              {PAPEIS[usuario.papel].rotulo}
            </span>
            {/* dev enxerga toda empresa; mostrar "0 empresas" confundiria */}
            {usuario.papel !== "dev" && (
              <span className="leiaute__escopo">
                {usuario.empresas.length === 1
                  ? "1 empresa"
                  : `${usuario.empresas.length} empresas`}
              </span>
            )}
          </div>
          <button type="button" className="botao botao--secundario" onClick={encerrar}>
            Sair
          </button>
        </header>

        <main className="leiaute__conteudo">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

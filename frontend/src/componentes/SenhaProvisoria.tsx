import { useEffect, useRef, useState } from "react";
import "./SenhaProvisoria.css";

interface Props {
  senha: string;
  usuario: string;
  motivo: "criado" | "redefinido";
  aoFechar: () => void;
}

/**
 * Mostra a senha provisória uma única vez.
 *
 * Fica em destaque de propósito: se o gestor fechar sem anotar, a única saída é
 * gerar outra. O componente não guarda nada nem manda a senha a lugar nenhum.
 */
export default function SenhaProvisoria({
  senha,
  usuario,
  motivo,
  aoFechar,
}: Props) {
  const [copiada, setCopiada] = useState(false);
  const [confirmou, setConfirmou] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    caixa.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(senha);
      setCopiada(true);
      setTimeout(() => setCopiada(false), 2500);
    } catch {
      // navegador sem permissão de área de transferência: a senha continua
      // visível na tela, então dá para copiar à mão
      setCopiada(false);
    }
  }

  return (
    <div className="senha-nova" ref={caixa} role="alert">
      <h2 className="senha-nova__titulo">
        {motivo === "criado"
          ? `Usuário criado: ${usuario}`
          : `Senha redefinida: ${usuario}`}
      </h2>

      <p className="senha-nova__aviso">
        Esta senha <strong>não será exibida de novo</strong>. Entregue
        pessoalmente. A troca é obrigatória no primeiro acesso.
      </p>

      <div className="senha-nova__caixa">
        <code className="senha-nova__valor">{senha}</code>
        <button type="button" className="botao botao--secundario" onClick={copiar}>
          {copiada ? "Copiada" : "Copiar"}
        </button>
      </div>

      <label className="senha-nova__confirma">
        <input
          type="checkbox"
          checked={confirmou}
          onChange={(e) => setConfirmou(e.target.checked)}
        />
        <span>Já anotei ou entreguei a senha.</span>
      </label>

      <button
        type="button"
        className="botao botao--principal"
        disabled={!confirmou}
        onClick={aoFechar}
      >
        Fechar
      </button>
    </div>
  );
}

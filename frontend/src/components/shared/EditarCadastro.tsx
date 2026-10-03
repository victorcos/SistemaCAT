import { useState, type FormEvent } from "react";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Campo, Entrada } from "@/components/ui/Campo";
import { Modal } from "@/components/ui/Modal";
import { compara, mascarar, paraIso, paraTexto, valida } from "@/lib/competencia";
import { comoErro } from "@/lib/errors";
import { alterarCadastro, type Projeto } from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/**
 * Nome e período do trabalho.
 *
 * Existe porque o período muda de verdade: o trabalho da empresa V nasceu como
 * 2025 e a base que existia era de 2021. A mudança fica no histórico com o de
 * e o para — a API grava o evento, a tela só diz que vai gravar.
 */
export function EditarCadastro({
  projeto,
  aberto,
  aoFechar,
  aoSalvar,
}: {
  projeto: Projeto;
  aberto: boolean;
  aoFechar: () => void;
  aoSalvar: (p: Projeto) => void;
}) {
  const [nome, setNome] = useState(projeto.nome);
  const [ini, setIni] = useState(paraTexto(projeto.competencia_ini));
  const [fim, setFim] = useState(paraTexto(projeto.competencia_fim));
  const [erro, setErro] = useState<ErroApi | string | null>(null);
  const [salvando, setSalvando] = useState(false);

  async function salvar(e?: FormEvent) {
    e?.preventDefault();
    setErro(null);
    if (!valida(ini) || !valida(fim)) {
      setErro("Competência é mês e ano, no formato MM/AAAA.");
      return;
    }
    if (compara(ini, fim) > 0) {
      setErro("A competência final não pode ser anterior à inicial.");
      return;
    }
    setSalvando(true);
    try {
      aoSalvar(
        await alterarCadastro(projeto.id, {
          nome: nome.trim(),
          competencia_ini: paraIso(ini)!,
          competencia_fim: paraIso(fim, true)!,
        }),
      );
      aoFechar();
    } catch (x) {
      setErro(comoErro(x));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      aberto={aberto}
      aoFechar={() => !salvando && aoFechar()}
      tamanho="sm"
      titulo="Editar o cadastro do trabalho"
      sub="A mudança fica no histórico, com o antes e o depois."
      rodape={
        <>
          <Botao variante="fantasma" onClick={aoFechar} disabled={salvando}>
            Cancelar
          </Botao>
          <Botao onClick={() => salvar()} carregando={salvando} className="shadow-acao">
            Salvar
          </Botao>
        </>
      }
    >
      <form onSubmit={salvar} className="grid gap-3.5 sm:grid-cols-2">
        {erro && (
          <div className="col-span-full">
            <Aviso
              titulo={typeof erro === "string" ? erro : erro.message}
              codigo={typeof erro === "string" ? undefined : erro.requisicaoId}
              aoFechar={() => setErro(null)}
            />
          </div>
        )}
        <div className="col-span-full">
          <Campo rotulo="Nome do trabalho">
            {(props) => <Entrada {...props} value={nome} onChange={(e) => setNome(e.target.value)} required />}
          </Campo>
        </div>
        <Campo rotulo="Competência inicial">
          {(props) => (
            <Entrada
              {...props}
              mono
              value={ini}
              onChange={(e) => setIni(mascarar(e.target.value))}
              placeholder="01/2021"
              inputMode="numeric"
            />
          )}
        </Campo>
        <Campo rotulo="Competência final">
          {(props) => (
            <Entrada
              {...props}
              mono
              value={fim}
              onChange={(e) => setFim(mascarar(e.target.value))}
              placeholder="12/2021"
              inputMode="numeric"
            />
          )}
        </Campo>
        {/* Enter no campo salva */}
        <button type="submit" hidden aria-hidden />
      </form>
    </Modal>
  );
}

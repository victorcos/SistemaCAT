import { useEffect, useState } from "react";
import { Cartao, Rotulo } from "@/components/shared/Rodada";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Modal } from "@/components/ui/Modal";
import { cn } from "@/lib/cn";
import { comoErro } from "@/lib/errors";
import {
  definirVendaAConsumidor,
  opcoesDeVendaAConsumidor,
  type OpcaoDeVendaAConsumidor,
  type Projeto,
} from "@/services/importacao";
import type { ErroApi } from "@/types/erro";

/**
 * Como o trabalho enquadra a venda a consumidor final.
 *
 * É escolha do trabalho (decisão de 16/09/2026): o manual põe o cupom no
 * enquadramento 1, com ressarcimento e complemento; a empresa T o transmitiu no 0,
 * e só a perda gerou ressarcimento. As duas mudam o valor do pedido, então a
 * troca pede confirmação e a tela diz quando o razão montado usou a outra.
 */
export function EscolhaDaVendaAConsumidor({
  projeto,
  usadaNoRazao,
  bloqueada,
  aoMudar,
}: {
  projeto: Projeto;
  /** a escolha com que o último razão concluído foi montado, se já houve um */
  usadaNoRazao?: string;
  /** rodada em curso ou trabalho parado: mudar agora não valeria para ela */
  bloqueada: boolean;
  aoMudar: (projeto: Projeto) => void;
}) {
  const [opcoes, setOpcoes] = useState<OpcaoDeVendaAConsumidor[]>([]);
  const [alvo, setAlvo] = useState<OpcaoDeVendaAConsumidor | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<ErroApi | null>(null);

  useEffect(() => {
    opcoesDeVendaAConsumidor().then(setOpcoes).catch((x) => setErro(comoErro(x)));
  }, []);

  const atual = projeto.venda_a_consumidor;
  const rotuloDe = (valor: string) => opcoes.find((o) => o.valor === valor)?.rotulo ?? valor;
  const desatualizado = usadaNoRazao !== undefined && usadaNoRazao !== atual;

  async function confirmar() {
    if (!alvo) return;
    setOcupado(true);
    setErro(null);
    try {
      aoMudar(await definirVendaAConsumidor(projeto.id, alvo.valor));
      setAlvo(null);
    } catch (x) {
      setErro(comoErro(x));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Cartao className="flex flex-col gap-3.5">
      <div>
        <Rotulo>Escolha do trabalho</Rotulo>
        <h2 className="m-0 mt-1 text-base font-extrabold text-texto">Venda a consumidor final</h2>
        <p className="m-0 mt-1 max-w-[820px] text-xs leading-relaxed text-texto-suave">
          Decide o enquadramento do cupom e da NFC-e, e com ele o ressarcimento e o complemento. O
          arquivo digital leva o mesmo enquadramento que o razão usou.
        </p>
      </div>

      {erro && <Aviso titulo={erro.message} codigo={erro.requisicaoId} aoFechar={() => setErro(null)} />}

      <div role="radiogroup" aria-label="Venda a consumidor final" className="grid gap-3 md:grid-cols-2">
        {opcoes.map((o) => {
          const ativa = o.valor === atual;
          return (
            <button
              key={o.valor}
              type="button"
              role="radio"
              aria-checked={ativa}
              disabled={ativa || bloqueada}
              onClick={() => setAlvo(o)}
              className={cn(
                "flex flex-col gap-1.5 rounded-raio-g border px-4 py-3.5 text-left transition-colors",
                ativa
                  ? "border-laranja-500/60 bg-laranja-500/8"
                  : "border-borda bg-superficie-vidro hover:border-borda-forte disabled:opacity-60",
              )}
            >
              <span className="text-[13px] font-extrabold text-texto">
                {o.rotulo}
                {ativa && <span className="ml-2 text-[11px] font-bold text-laranja-700 escuro:text-laranja-300">· em uso</span>}
              </span>
              <span className="text-xs leading-relaxed text-texto-suave [text-wrap:pretty]">{o.explicacao}</span>
            </button>
          );
        })}
      </div>

      {desatualizado && (
        <p className="m-0 rounded-raio-g border border-atencao/25 border-l-[3px] border-l-atencao bg-atencao-fundo px-4 py-3 text-[13px] leading-relaxed text-texto">
          <strong className="text-atencao">O razão abaixo foi montado com a outra escolha</strong> ({rotuloDe(usadaNoRazao!).toLowerCase()}).
          Monte de novo para valer a escolha atual — a apuração e o arquivo digital vêm dele.
        </p>
      )}

      <Modal
        aberto={alvo !== null}
        aoFechar={() => setAlvo(null)}
        tamanho="sm"
        titulo="Mudar a venda a consumidor final?"
        sub={alvo?.rotulo}
        rodape={
          <>
            <Botao variante="fantasma" onClick={() => setAlvo(null)} disabled={ocupado}>
              Cancelar
            </Botao>
            <Botao onClick={confirmar} carregando={ocupado}>
              Sim, mudar
            </Botao>
          </>
        }
      >
        <p className="m-0 text-[13px] leading-relaxed text-texto-suave">
          Muda o valor do pedido. O razão, a apuração e o arquivo digital já feitos continuam com a
          escolha anterior até rodarem de novo, e a troca fica no histórico do trabalho.
        </p>
      </Modal>
    </Cartao>
  );
}

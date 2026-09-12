import { BotaoLink } from "@/components/ui/Botao";
import { IconeVoltar } from "@/constants/icons";
import { ROTAS } from "@/constants/routes";

/** 404 de verdade. Antes qualquer caminho desconhecido era redirecionado em
 *  silêncio para a raiz, o que esconde erro de link em vez de mostrar. */
export default function NaoEncontrada() {
  return (
    <div className="flex flex-col items-center gap-4 p-16 text-center">
      <h1 className="m-0 text-2xl font-extrabold">Página não encontrada</h1>
      <p className="m-0 max-w-[48ch] text-sm leading-relaxed text-texto-suave">
        O endereço não existe ou o item foi removido. Confira o link ou volte
        para o início.
      </p>
      <BotaoLink para={ROTAS.inicio} icone={IconeVoltar} variante="secundario">
        Voltar ao início
      </BotaoLink>
    </div>
  );
}

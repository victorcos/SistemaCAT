import { useEffect, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { CardDeEscolha, type Escolha } from "@/components/shared/CardDeEscolha";
import { Aviso } from "@/components/ui/Aviso";
import { Carregando } from "@/components/ui/Carregando";
import { Voltar } from "@/components/ui/Pagina";
import { ROTAS } from "@/constants/routes";
import { comoErro } from "@/lib/errors";
import {
  meusSegmentos,
  resumoDosModulos,
  type ResumoDoModulo,
  type Segmento,
} from "@/services/segmentos";
import type { ErroApi } from "@/types/erro";

/**
 * O segundo nível: dentro de um segmento, qual frente.
 *
 * PIS/COFINS e CBS; ICMS e IBS. A reforma mora ao lado do tributo que sucede
 * porque de 2027 a 2033 é a mesma equipe apurando os dois lado a lado — e quem
 * abre o ICMS num dia abre o IBS no outro, com a mesma empresa na cabeça.
 *
 * O caminho de volta só aparece para quem tem mais de um segmento. Para quem só
 * enxerga um, não há hub para onde voltar, e um "← Segmentos" que leva a uma
 * tela que redireciona de volta é um laço — então no lugar dele vai a frase que
 * explica por que a pessoa caiu aqui direto.
 */
export default function ModulosDoSegmento() {
  const { chave } = useParams<{ chave: string }>();
  const [segmentos, setSegmentos] = useState<Segmento[] | null>(null);
  const [resumo, setResumo] = useState<ResumoDoModulo[]>([]);
  const [erro, setErro] = useState<ErroApi | null>(null);

  useEffect(() => {
    let vivo = true;
    meusSegmentos()
      .then((s) => vivo && setSegmentos(s))
      .catch((x) => vivo && setErro(comoErro(x)));
    resumoDosModulos()
      .then((r) => vivo && setResumo(r))
      .catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, []);

  if (erro) return <Aviso titulo={erro.message} codigo={erro.requisicaoId} />;
  if (segmentos === null) return <Carregando />;

  const segmento = segmentos.find((s) => s.chave === chave);
  // segmento que a pessoa não enxerga (ou que não existe) não vira erro: volta
  // ao hub, que é onde ela escolhe entre o que pode abrir. Quem barra de
  // verdade é a API, em toda rota de trabalho
  if (segmento === undefined) return <Navigate to={ROTAS.segmentos} replace />;
  // segmento de um módulo só não tem escolha a fazer
  if (segmento.modulos.length === 1) {
    return <Navigate to={ROTAS.modulo(segmento.modulos[0].chave)} replace />;
  }

  const abertos = (modulo: string) => resumo.find((r) => r.modulo === modulo)?.abertos ?? 0;
  const temHub = segmentos.length > 1;

  const cards: Escolha[] = segmento.modulos.map((m, i) => ({
    chave: m.chave,
    rotulo: m.rotulo,
    descricao: m.descricao,
    para: ROTAS.modulo(m.chave),
    etiqueta: i === 0 ? "regime atual" : "reforma",
    contagem: { quantos: abertos(m.chave), rotulo: "trabalhos em aberto" },
    chamada: "Abrir os trabalhos",
  }));

  return (
    <>
      {temHub && <Voltar para={ROTAS.segmentos}>Segmentos</Voltar>}

      <header className="flex flex-col gap-2">
        <p className="m-0 text-[11px] font-extrabold uppercase tracking-[0.16em] text-texto-fraco">
          {segmento.rotulo}
        </p>
        <h1 className="m-0 text-[32px] font-extrabold leading-tight tracking-tight text-texto">
          Qual frente?
        </h1>
        <p className="m-0 max-w-[62ch] text-[15px] leading-relaxed text-texto-fraco">
          {segmento.descricao}
        </p>
      </header>

      {!temHub && (
        <p className="m-0 rounded-raio-g border border-borda bg-superficie-alt px-4 py-3 text-[12px] leading-relaxed text-texto-fraco">
          Você entrou direto aqui porque seu gestor liberou só {segmento.rotulo} para a sua
          conta.
        </p>
      )}

      <section className="grid grid-cols-[repeat(auto-fit,minmax(270px,1fr))] gap-[18px]">
        {cards.map((c) => (
          <CardDeEscolha key={c.chave} escolha={c} />
        ))}
      </section>
    </>
  );
}

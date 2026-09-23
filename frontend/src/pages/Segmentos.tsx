import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { CardDeEscolha, type Escolha } from "@/components/shared/CardDeEscolha";
import { Aviso } from "@/components/ui/Aviso";
import { Carregando } from "@/components/ui/Carregando";
import { Vazio } from "@/components/ui/Pagina";
import { ROTAS } from "@/constants/routes";
import { ADMINISTRA_USUARIOS } from "@/constants/roles";
import { useAuth } from "@/hooks/useAuth";
import { comoErro } from "@/lib/errors";
import {
  meusSegmentos,
  resumoDosModulos,
  type ResumoDoModulo,
  type Segmento,
} from "@/services/segmentos";
import type { ErroApi } from "@/types/erro";

/**
 * O hub: por onde se começa depois de entrar.
 *
 * Um card por segmento tributário que a pessoa enxerga — e, para quem
 * administra, o card de gestão de usuários ao lado. É a porta de entrada, então
 * não tem menu lateral: o que se escolhe aqui é justamente o contexto que o
 * menu passaria a mostrar.
 *
 * **Quem decide o que aparece é o servidor.** A lista vem de `/segmentos`, que
 * já devolve só o que a pessoa pode abrir. Repetir a regra aqui daria duas
 * fontes para a mesma verdade, e um dia a tela ofereceria um card que a API
 * recusa.
 *
 * Quem tem um único segmento não passa por aqui: o servidor resolve o destino
 * no login (`usuario.entrada`) e manda direto. Chegar nesta tela com um segmento
 * só é atalho digitado na barra de endereços — e aí ela redireciona, em vez de
 * mostrar um hub de um card, que não é escolha nenhuma.
 */
export default function Segmentos() {
  const { usuario } = useAuth();
  const [segmentos, setSegmentos] = useState<Segmento[] | null>(null);
  const [resumo, setResumo] = useState<ResumoDoModulo[]>([]);
  const [erro, setErro] = useState<ErroApi | null>(null);

  useEffect(() => {
    let vivo = true;
    meusSegmentos()
      .then((s) => vivo && setSegmentos(s))
      .catch((x) => vivo && setErro(comoErro(x)));
    // o resumo é enfeite: se falhar, os cards saem sem número em vez de a tela
    // inteira virar erro. O que importa aqui é conseguir escolher
    resumoDosModulos()
      .then((r) => vivo && setResumo(r))
      .catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, []);

  const administra = usuario !== null && ADMINISTRA_USUARIOS.includes(usuario.papel);

  if (erro) return <Aviso titulo={erro.message} codigo={erro.requisicaoId} />;
  if (segmentos === null) return <Carregando />;

  if (segmentos.length === 0) {
    return (
      <Vazio titulo="Nenhum segmento liberado para a sua conta">
        Peça ao seu gestor para liberar PIS/COFINS, ICMS ou IRPJ/CSLL. Sem pelo menos um, não
        há trabalho que você possa abrir.
      </Vazio>
    );
  }

  // um segmento só não é escolha: vai direto para onde o servidor mandaria
  if (segmentos.length === 1 && !administra) {
    return <Navigate to={destinoDe(segmentos[0])} replace />;
  }

  const abertos = (modulo: string) => resumo.find((r) => r.modulo === modulo)?.abertos ?? 0;

  const cards: Escolha[] = segmentos.map((s) => ({
    chave: s.chave,
    rotulo: s.rotulo,
    descricao: s.descricao,
    para: destinoDe(s),
    etiqueta: s.modulos.length > 1 ? `${s.modulos.length} frentes` : "trabalhos",
    contagem: {
      quantos: s.modulos.reduce((total, m) => total + abertos(m.chave), 0),
      rotulo: "trabalhos em aberto",
    },
    chamada: s.modulos.length > 1 ? "Escolher a frente" : "Abrir os trabalhos",
  }));

  if (administra) {
    cards.push({
      chave: "usuarios",
      rotulo: "Gestão de usuários",
      descricao:
        "Quem entra, com que papel, sobre quais empresas e em que segmentos. Também é daqui que se passa um trabalho de uma pessoa para outra.",
      para: ROTAS.usuarios,
      etiqueta: "só gestores",
      chamada: "Gerenciar",
    });
  }

  return (
    <>
      <header className="flex flex-col gap-2">
        <p className="m-0 text-[11px] font-extrabold uppercase tracking-[0.16em] text-texto-fraco">
          {administra ? "Painel do gestor" : "Seus segmentos"}
        </p>
        <h1 className="m-0 text-[32px] font-extrabold leading-tight tracking-tight text-texto">
          Olá, {primeiroNome(usuario?.nome_exibicao)}. Por onde vamos começar?
        </h1>
        <p className="m-0 max-w-[62ch] text-[15px] leading-relaxed text-texto-fraco">
          Cada segmento tem o próprio roteiro de etapas. O que você escolher aqui decide o que
          o sistema mostra daqui para a frente.
        </p>
      </header>

      <section className="grid grid-cols-[repeat(auto-fit,minmax(270px,1fr))] gap-[18px]">
        {cards.map((c) => (
          <CardDeEscolha key={c.chave} escolha={c} />
        ))}
      </section>

      <p className="m-0 text-[12px] leading-relaxed text-texto-fraco">
        {administra
          ? "Quem tem um segmento só não passa por esta tela: entra direto no dele."
          : "Precisa de outro segmento? Peça ao seu gestor."}
      </p>
    </>
  );
}

/** Segmento de um módulo só pula o segundo nível: não há o que escolher lá. */
function destinoDe(s: Segmento): string {
  return s.modulos.length === 1 ? ROTAS.modulo(s.modulos[0].chave) : ROTAS.segmento(s.chave);
}

function primeiroNome(nome: string | undefined): string {
  return (nome ?? "").trim().split(/\s+/)[0] || "tudo bem";
}

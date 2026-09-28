import { useEffect, useMemo, useState } from "react";
import { BaixarPlanilha } from "@/components/shared/BaixarPlanilha";
import { Cartao, Faixa } from "@/components/shared/Rodada";
import { Aviso } from "@/components/ui/Aviso";
import { Busca, Chip, Toolbar } from "@/components/ui/Filtros";
import { Vazio } from "@/components/ui/Pagina";
import { Celula, Linha, Tabela } from "@/components/ui/Tabela";
import { useAcao } from "@/hooks/useAcao";
import { cn } from "@/lib/cn";
import { numero } from "@/lib/format";
import type { Formato } from "@/services/conferencia";
import {
  alvosDaQuebra,
  baixarExtracao,
  type AlvoDaQuebra,
  type AlvosDaQuebra,
} from "@/services/quebraDeSped";

/**
 * Extrair um registro do SPED, consolidado de todos os arquivos.
 *
 * É o que a quebra sempre prometeu: ela abre os arquivos e diz o que há dentro
 * — aqui se pede o conteúdo. "Me dá todos os C170 desses 59 arquivos, numa
 * planilha só."
 *
 * **Só aparece o que está nos arquivos.** A lista vem do índice da própria
 * quebra; oferecer o C870 a quem não emite cupom seria oferecer planilha vazia.
 *
 * **A hierarquia vem primeiro, e marcada.** O C170 sozinho não diz de que nota
 * é — o SPED amarra o item ao documento pela *posição*, e quem precisa do par
 * quase sempre precisa do par. Quem quer o registro puro continua tendo, logo
 * abaixo.
 *
 * O filtro é por **bloco**, que é como o leiaute do SPED se organiza e como
 * quem trabalha com ele pensa: "o que eu preciso é do bloco M".
 */
export function ExtrairDoSped({ execucaoId }: { execucaoId: number }) {
  const [dados, setDados] = useState<AlvosDaQuebra | null>(null);
  const [bloco, setBloco] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [baixando, setBaixando] = useState<{ alvo: string; formato: Formato } | null>(null);
  const leitura = useAcao();
  const download = useAcao();

  useEffect(() => {
    let vivo = true;
    leitura.executar((sinal) => alvosDaQuebra(execucaoId, sinal)).then((d) => {
      if (vivo && d) setDados(d);
    });
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [execucaoId]);

  const visiveis = useMemo(() => {
    const termo = busca.trim().toLocaleUpperCase("pt-BR");
    return (dados?.linhas ?? []).filter(
      (l) =>
        (bloco === null || l.bloco === bloco) &&
        (!termo || l.alvo.includes(termo) || l.rotulo.toLocaleUpperCase("pt-BR").includes(termo)),
    );
  }, [dados, bloco, busca]);

  async function baixar(alvo: string, formato: Formato) {
    setBaixando({ alvo, formato });
    await download.executar((sinal) => baixarExtracao(execucaoId, alvo, formato, sinal));
    setBaixando(null);
  }

  if (leitura.erro) {
    return (
      <Aviso titulo={leitura.erro.message} codigo={leitura.erro.requisicaoId} aoFechar={() => leitura.setErro(null)} />
    );
  }
  if (!dados) return null;

  return (
    <Cartao className="flex flex-col gap-3.5">
      <div className="min-w-[260px]">
        <h2 className="m-0 text-base font-extrabold text-texto">Extrair um registro</h2>
        <p className="m-0 mt-1 max-w-[760px] text-[13px] leading-relaxed text-texto-suave">
          O conteúdo, e não só a contagem: as linhas do registro escolhido, de todos os arquivos
          desta quebra, numa planilha só. As colunas saem com o nome do leiaute, e cada linha diz
          de que arquivo veio.
        </p>
      </div>

      {dados.sem_indice > 0 && (
        <Faixa titulo={`${numero(dados.sem_indice)} arquivo(s) sem índice válido`}>
          O arquivo mudou em disco depois da quebra, ou o índice é de uma versão anterior. A
          extração sai sem eles — rode a quebra de novo para incluí-los.
        </Faixa>
      )}

      <Toolbar>
        <Busca valor={busca} aoMudar={setBusca} placeholder="Buscar registro (C170, M210…)" />
        <div className="flex flex-wrap gap-2">
          <Chip marcado={bloco === null} aoAlternar={() => setBloco(null)}>
            Todos
          </Chip>
          {dados.blocos.map((b) => (
            <Chip
              key={b}
              marcado={bloco === b}
              aoAlternar={() => setBloco(bloco === b ? null : b)}
              contagem={dados.linhas.filter((l) => l.bloco === b).length}
            >
              <span title={dados.rotulos_dos_blocos[b]}>Bloco {b}</span>
            </Chip>
          ))}
        </div>
      </Toolbar>

      {bloco !== null && dados.rotulos_dos_blocos[bloco] && (
        <p className="m-0 text-[12px] text-texto-fraco">{dados.rotulos_dos_blocos[bloco]}</p>
      )}

      {download.erro && (
        <Aviso titulo={download.erro.message} codigo={download.erro.requisicaoId} aoFechar={() => download.setErro(null)} />
      )}

      {visiveis.length === 0 ? (
        <Vazio titulo="Nada para extrair com este recorte">
          {busca
            ? "Nenhum registro casa com a busca."
            : "Nenhum registro deste bloco apareceu nos arquivos desta quebra."}
        </Vazio>
      ) : (
        <Tabela colunas={["Registro", "Linhas", "Colunas", ""]}>
          {visiveis.map((l) => (
            <LinhaDoAlvo
              key={l.alvo}
              alvo={l}
              ocupado={download.carregando}
              baixando={baixando?.alvo === l.alvo ? baixando.formato : null}
              aoBaixar={(formato) => baixar(l.alvo, formato)}
              aoCancelar={download.podeCancelar ? download.cancelar : undefined}
            />
          ))}
        </Tabela>
      )}
    </Cartao>
  );
}

function LinhaDoAlvo({
  alvo,
  ocupado,
  baixando,
  aoBaixar,
  aoCancelar,
}: {
  alvo: AlvoDaQuebra;
  ocupado: boolean;
  baixando: Formato | null;
  aoBaixar: (formato: Formato) => void;
  aoCancelar?: () => void;
}) {
  return (
    <Linha>
      <Celula
        nota={alvo.hierarquia ? alvo.rotulo : undefined}
        className={cn(alvo.hierarquia && "font-bold")}
      >
        <span className="flex flex-wrap items-center gap-2">
          <code className="font-mono text-[13px] text-texto">{alvo.alvo}</code>
          {alvo.hierarquia && (
            <span
              title="Sai com o registro pai junto: o SPED amarra os dois pela posição, e um item solto não diz de que documento é."
              className="whitespace-nowrap rounded-full bg-laranja-500/12 px-2 py-0.5 text-[10px] font-extrabold text-laranja-800 escuro:text-laranja-300"
            >
              com o pai
            </span>
          )}
        </span>
      </Celula>
      <Celula mono className="text-right">{numero(alvo.quantidade)}</Celula>
      <Celula mono className="text-right">{numero(alvo.colunas)}</Celula>
      <Celula>
        <BaixarPlanilha
          rotulo="Extrair"
          aoBaixar={aoBaixar}
          desabilitado={ocupado}
          baixando={baixando}
          aoCancelar={aoCancelar}
        />
      </Celula>
    </Linha>
  );
}

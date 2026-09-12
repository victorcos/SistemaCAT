import { Botao } from "@/components/ui/Botao";
import { EtiquetaDePapel } from "@/components/ui/Etiqueta";
import { enxergaTodasAsEmpresas } from "@/constants/roles";
import { IconeClaro, IconeEscuro, IconeSair } from "@/constants/icons";
import { useAuth } from "@/hooks/useAuth";
import { useTheme } from "@/hooks/useTheme";
import type { Usuario } from "@/types/auth";

export function BarraTopo({ usuario }: { usuario: Usuario }) {
  const { sair } = useAuth();

  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-borda bg-superficie/85 px-6 py-3 backdrop-blur-[10px]">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2.5">
        <strong className="truncate text-sm">{usuario.nome_exibicao}</strong>
        <EtiquetaDePapel papel={usuario.papel} />
        {/* quem enxerga toda empresa não tem contagem que faça sentido:
            mostrar "0 empresas" a um gestor era dizer o contrário da verdade */}
        {enxergaTodasAsEmpresas(usuario.papel) ? (
          <span className="text-[13px] text-texto-fraco">todas as empresas</span>
        ) : (
          <span className="text-[13px] text-texto-fraco">
            {usuario.empresas.length === 1
              ? "1 empresa"
              : `${usuario.empresas.length} empresas`}
          </span>
        )}
      </div>

      <AlternarTema />

      <Botao variante="secundario" tamanho="sm" icone={IconeSair} onClick={sair}>
        Sair
      </Botao>
    </header>
  );
}

/** O tema sempre esteve pronto em tokens.css e nunca teve como ser trocado —
 *  nenhum código lia `data-tema`. Este botão é o que faltava. */
function AlternarTema() {
  const { temaEfetivo, definirTema } = useTheme();
  const indoPara = temaEfetivo === "escuro" ? "claro" : "escuro";
  const Ico = temaEfetivo === "escuro" ? IconeClaro : IconeEscuro;
  return (
    <button
      type="button"
      onClick={() => definirTema(indoPara)}
      title={`Mudar para o tema ${indoPara}`}
      aria-label={`Mudar para o tema ${indoPara}`}
      className="rounded-raio border border-acao2-borda p-2 text-acao2-texto hover:bg-acao2-hover"
    >
      <Ico size={16} strokeWidth={2} aria-hidden />
    </button>
  );
}

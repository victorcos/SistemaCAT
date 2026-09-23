import { useCallback, useEffect, useState } from "react";
import { CHAVE_MENU_RECOLHIDO } from "@/constants/storage";

/**
 * Se o menu lateral está recolhido, e a escolha guardada.
 *
 * É preferência de quem usa, não estado de tela: quem recolhe o menu quer a
 * tela larga **sempre**, não só até o próximo F5. Por isso vai para o
 * `localStorage` e volta na abertura.
 *
 * Só vale no desktop. Em tela estreita o menu já é uma barra horizontal no
 * topo — não há largura a recuperar, e recolher ali não significaria nada.
 */
export function useMenuRecolhido(): [boolean, () => void] {
  const [recolhido, setRecolhido] = useState(() => {
    try {
      return localStorage.getItem(CHAVE_MENU_RECOLHIDO) === "1";
    } catch {
      // navegador com armazenamento bloqueado: abre expandido, que é o padrão
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(CHAVE_MENU_RECOLHIDO, recolhido ? "1" : "0");
    } catch {
      // não poder lembrar não pode impedir de usar
    }
  }, [recolhido]);

  return [recolhido, useCallback(() => setRecolhido((r) => !r), [])];
}

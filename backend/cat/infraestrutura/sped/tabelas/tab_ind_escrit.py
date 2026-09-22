"""Registro C010.IND_ESCRIT (indicador de tipo de escrituração) -> rótulo.

Só o código "2" está confirmado 1:1 contra o arquivo de referência real
"C100, C170, 0200 - Documento e Itens - Nota Fiscal" (empresa C, 43.497/43.497 linhas com esse código) — replicado
literalmente, inclusive a grafia truncada ("Individualiza" em vez de
"Individualizada") como o MA escreve. Os códigos "0" e "1" seguem o texto
oficial do Guia Prático (não confrontados com nenhum arquivo real).
"""

# Copiada do projeto Quebra de SPED em 22/09/2026, sem alteração de conteúdo.
# As marcas "# CONFIRMADO" indicam o que foi conferido contra arquivo de
# referência real — não as remova ao acrescentar entradas novas: elas são a
# diferença entre o que se sabe e o que se supõe.

from __future__ import annotations

_IND_ESCRIT: dict[str, str] = {
    "0": "0 - Consolidada",
    "1": "1 - Individualizada por Estabelecimento",
    "2": "2 – Apuração Individualiza - C100/C170 e C400",  # CONFIRMADO
}


def rotulo(codigo: str) -> str:
    codigo = (codigo or "").strip()
    return _IND_ESCRIT.get(codigo, codigo)

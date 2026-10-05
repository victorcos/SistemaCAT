"""Indicadores de C100/C170 (EFD Contribuições) -> rótulo "código - texto".

Domínios fixos e pequenos do Guia Prático EFD-Contribuições. Valores
marcados com # CONFIRMADO batem 1:1 com o arquivo de referência real
"C100, C170, 0200 - Documento e Itens - Nota Fiscal" (empresa 03, 43.497 linhas, out/2024) — inclusive a grafia
exata usada pelo MA (ex.: "Saida" sem acento). Os demais vêm do texto
oficial do Guia Prático e não foram confrontados com um arquivo real.
"""

# Copiada do projeto Quebra de SPED em 22/09/2026, sem alteração de conteúdo.
# As marcas "# CONFIRMADO" indicam o que foi conferido contra arquivo de
# referência real — não as remova ao acrescentar entradas novas: elas são a
# diferença entre o que se sabe e o que se supõe.

from __future__ import annotations

_TIPO_OPERACAO: dict[str, str] = {
    "0": "0 - Entrada",  # CONFIRMADO
    "1": "1 - Saida",  # CONFIRMADO
}

_INDICADOR_EMITENTE: dict[str, str] = {
    "0": "0 - Emissão própria",  # CONFIRMADO
    "1": "1 - Terceiros",  # CONFIRMADO
}

_INDICADOR_PAGAMENTO: dict[str, str] = {
    "0": "0 - À vista",  # CONFIRMADO
    "1": "1 - A prazo",
    "2": "2 - Outros",
}

_INDICADOR_FRETE: dict[str, str] = {
    "0": "0 - Contratação do frete por conta do remetente(CIF)",  # CONFIRMADO
    "1": "1 - Contratação do frete por conta do destinatário(FOB)",  # CONFIRMADO
    "2": "2 - Contratação do frete por conta de terceiros",  # CONFIRMADO
    "3": "3 - Transporte próprio por conta do remetente",  # CONFIRMADO
    "4": "4 - Transporte próprio por conta do destinatário",  # CONFIRMADO
    "9": "9 - Sem ocorrência de transporte",  # CONFIRMADO
}

_INDICADOR_MOVIMENTO_ITEM: dict[str, str] = {
    "0": "0 - Sim",
    "1": "1 - Não",  # CONFIRMADO
}


def _rotulo(tabela: dict[str, str], codigo: str) -> str:
    return tabela.get((codigo or "").strip(), (codigo or "").strip())


def tipo_operacao(codigo: str) -> str:
    return _rotulo(_TIPO_OPERACAO, codigo)


def indicador_emitente(codigo: str) -> str:
    return _rotulo(_INDICADOR_EMITENTE, codigo)


def indicador_pagamento(codigo: str) -> str:
    return _rotulo(_INDICADOR_PAGAMENTO, codigo)


def indicador_frete(codigo: str) -> str:
    return _rotulo(_INDICADOR_FRETE, codigo)


def indicador_movimento_item(codigo: str) -> str:
    return _rotulo(_INDICADOR_MOVIMENTO_ITEM, codigo)

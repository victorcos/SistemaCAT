"""Domínio do campo TIPO_ITEM (registro 0200 do EFD-Contribuições).

Códigos marcados com # CONFIRMADO foram extraídos diretamente do arquivo de
referência "037 - Entradas" (empresa A, jul-dez/2021). Os
demais vêm do Guia Prático e ainda não foram confrontados com um arquivo
de referência real.
"""

# Copiada do projeto Quebra de SPED em 22/09/2026, sem alteração de conteúdo.
# As marcas "# CONFIRMADO" indicam o que foi conferido contra arquivo de
# referência real — não as remova ao acrescentar entradas novas: elas são a
# diferença entre o que se sabe e o que se supõe.

from __future__ import annotations

TABELA: dict[str, str] = {
    "00": "Mercadoria para Revenda",  # CONFIRMADO
    "01": "Matéria-Prima",  # CONFIRMADO
    "02": "Embalagem",
    "03": "Produto em Processo",
    "04": "Produto Acabado",  # CONFIRMADO
    "05": "Subproduto",
    "06": "Produto Intermediário",
    "07": "Material de Uso e Consumo",  # CONFIRMADO
    "08": "Ativo Imobilizado",
    "09": "Serviços",
    "10": "Outros insumos",  # CONFIRMADO
    "99": "Outras",  # CONFIRMADO
}


def descricao(codigo: str) -> str:
    """Retorna a descrição do código, ou string vazia se desconhecido."""
    return TABELA.get((codigo or "").strip(), "")

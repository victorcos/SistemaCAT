"""Tabela 4.3.7 do Guia Prático EFD-Contribuições — Natureza da Base de
Cálculo dos Créditos (registros C170/C181/C185/C191/C195/C501/C505/D101/
D105/D501/D505/F100, campo NAT_BC_CRED).

Entradas marcadas com # CONFIRMADO foram extraídas diretamente do arquivo
de referência "037 - Entradas" (Tropical Supermercados, jul-dez/2021) —
valores garantidamente iguais aos usados pelo Sistema MA. As demais vêm do
texto oficial do Guia Prático e ainda não foram confrontadas com nenhum
arquivo de referência real — confirmar antes de tratar como definitivas.
"""

# Copiada do projeto Quebra de SPED em 22/09/2026, sem alteração de conteúdo.
# As marcas "# CONFIRMADO" indicam o que foi conferido contra arquivo de
# referência real — não as remova ao acrescentar entradas novas: elas são a
# diferença entre o que se sabe e o que se supõe.

from __future__ import annotations

TABELA: dict[str, str] = {
    "01": "Aquisição de bens para revenda",  # CONFIRMADO
    "02": "Aquisição de bens utilizados como insumo",
    "03": "Aquisição de serviços utilizados como insumo",  # CONFIRMADO
    "04": "Energia elétrica e térmica, inclusive sob a forma de vapor",  # CONFIRMADO
    "05": "Aluguéis de prédios",  # CONFIRMADO
    "06": "Aluguéis de máquinas e equipamentos",
    "07": "Armazenagem de mercadoria e frete na operação de venda",
    "08": "Contraprestações de arrendamento mercantil",
    "09": "Máquinas, equip. bens do ativo - Depreciação",  # CONFIRMADO
    "10": "Máquinas, equip. bens do ativo - Aquisição",  # CONFIRMADO
    "11": "Amortização e Depreciação de edificações e benfeitorias em imóveis",
    "12": "Devolução de vendas - Incidência Não-Cumulativa",  # CONFIRMADO
    "13": "Outras operações com direito a crédito",
    "14": "Atividade de Transporte de Cargas - Subcontratação",  # CONFIRMADO
    "15": "Atividade Imobiliária - Custo Incorrido de Unidade Imobiliária",
    "16": "Atividade Imobiliária - Custo Orçado de Unidade não Concluída",
    "17": "Atividade de Prestação de Serviços de Limpeza, Conservação e Manutenção",
    "18": "Estoque de Abertura de Bens",
    "19": "Fretes na Operação de Venda, Subcontratação de Serviços de Transporte",
}


def descricao(codigo: str) -> str:
    """Retorna a descrição do código, ou string vazia se desconhecido."""
    return TABELA.get((codigo or "").strip(), "")


def rotulo(codigo: str) -> str:
    """Retorna "código - descrição", ou string vazia se código vazio/desconhecido."""
    codigo = (codigo or "").strip()
    if not codigo:
        return ""
    desc = descricao(codigo)
    return f"{codigo} - {desc}" if desc else codigo

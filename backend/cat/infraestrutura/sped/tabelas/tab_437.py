"""Tabela 4.3.7 do Guia Prático EFD-Contribuições — Natureza da Base de
Cálculo dos Créditos (registros C170/C181/C185/C191/C195/C501/C505/D101/
D105/D501/D505/F100, campo NAT_BC_CRED).

Entradas marcadas com # CONFIRMADO foram extraídas diretamente do arquivo
de referência "037 - Entradas" (empresa A, jul-dez/2021) —
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


# ---------------------------------------------------------------------------
# a grafia do MA, que não é a da tabela oficial
# ---------------------------------------------------------------------------
# **O MA encurta o texto da 4.3.7.** Onde a tabela oficial diz "Energia
# elétrica e térmica, inclusive sob a forma de vapor", a 037 escreve "Energia
# elétrica e térmica"; onde diz "Amortização e Depreciação de edificações e
# benfeitorias em imóveis", escreve "Amortização e deprec. de edificações em
# imóveis". Não é truncamento por largura — o texto é reescrito, e o "Outras
# operações" vira "Outras Operações", com maiúscula.
#
# `TABELA` fica com o texto oficial, que é o da lei e o que a extração mostra;
# esta é a grafia de quem compara relatório com relatório. Mesmo arranjo de
# `tab_cfop`, e pelo mesmo motivo.
#
# Das 10 naturezas do gabarito do 037 da empresa F (458.792 linhas, 30/09/2026),
# 6 batem com a oficial e estas 4 não:
COMO_O_MA_ESCREVE: dict[str, str] = {
    "04": "Energia elétrica e térmica",
    "07": "Armazenagem e frete na operação de venda",
    "11": "Amortização e deprec. de edificações em imóveis",
    "13": "Outras Operações com direito a crédito",
}


def descricao_do_ma(codigo: str) -> str:
    """A descrição como o MA a escreve; na falta dela, a oficial."""
    limpo = (codigo or "").strip()
    return COMO_O_MA_ESCREVE.get(limpo) or descricao(limpo)


def rotulo_do_ma(codigo: str) -> str:
    """"código - descrição", na grafia do MA. Vazio continua vazio."""
    limpo = (codigo or "").strip()
    if not limpo:
        return ""
    desc = descricao_do_ma(limpo)
    return f"{limpo} - {desc}" if desc else limpo


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

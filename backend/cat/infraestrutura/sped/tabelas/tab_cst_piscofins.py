"""Tabela II do Anexo Único da IN RFB 1.009/2010 — CST PIS/COFINS.

Domínio padronizado e estável (não específico de nenhuma empresa). Os
códigos 50, 70, 71, 73, 98, 99 e 51 foram efetivamente observados no
arquivo de referência "037 - Entradas" (empresa A); os demais
completam a tabela oficial e não têm ocorrência confirmada nesse arquivo.

Não aparece como coluna própria no arquivo de referência (a saída só traz
o código cru de CST PIS / CST Cofins) — construída mesmo assim, por pedido
explícito, para uso em filtros/validações e em telas futuras.
"""

# Copiada do projeto Quebra de SPED em 22/09/2026, sem alteração de conteúdo.
# As marcas "# CONFIRMADO" indicam o que foi conferido contra arquivo de
# referência real — não as remova ao acrescentar entradas novas: elas são a
# diferença entre o que se sabe e o que se supõe.

from __future__ import annotations

TABELA: dict[str, str] = {
    "01": "Operação Tributável com Alíquota Básica",
    "02": "Operação Tributável com Alíquota Diferenciada",
    "03": "Operação Tributável com Alíquota por Unidade de Medida de Produto",
    "04": "Operação Tributável Monofásica - Revenda a Alíquota Zero",
    "05": "Operação Tributável por Substituição Tributária",
    "06": "Operação Tributável a Alíquota Zero",
    "07": "Operação Isenta da Contribuição",
    "08": "Operação sem Incidência da Contribuição",
    "09": "Operação com Suspensão da Contribuição",
    "49": "Outras Operações de Saída",
    "50": "Operação com Direito a Crédito - Vinculada Exclusivamente a Receita Tributada no Mercado Interno",
    "51": "Operação com Direito a Crédito - Vinculada Exclusivamente a Receita Não Tributada no Mercado Interno",
    "52": "Operação com Direito a Crédito - Vinculada Exclusivamente a Receita de Exportação",
    "53": "Operação com Direito a Crédito - Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno",
    "54": "Operação com Direito a Crédito - Vinculada a Receitas Tributadas no Mercado Interno e de Exportação",
    "55": "Operação com Direito a Crédito - Vinculada a Receitas Não-Tributadas no Mercado Interno e de Exportação",
    "56": "Operação com Direito a Crédito - Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno, e de Exportação",
    "60": "Crédito Presumido - Operação de Aquisição Vinculada Exclusivamente a Receita Tributada no Mercado Interno",
    "61": "Crédito Presumido - Operação de Aquisição Vinculada Exclusivamente a Receita Não-Tributada no Mercado Interno",
    "62": "Crédito Presumido - Operação de Aquisição Vinculada Exclusivamente a Receita de Exportação",
    "63": "Crédito Presumido - Operação de Aquisição Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno",
    "64": "Crédito Presumido - Operação de Aquisição Vinculada a Receitas Tributadas no Mercado Interno e de Exportação",
    "65": "Crédito Presumido - Operação de Aquisição Vinculada a Receitas Não-Tributadas no Mercado Interno e de Exportação",
    "66": "Crédito Presumido - Operação de Aquisição Vinculada a Receitas Tributadas e Não-Tributadas no Mercado Interno, e de Exportação",
    "67": "Crédito Presumido - Outras Operações",
    "70": "Operação de Aquisição sem Direito a Crédito",
    "71": "Operação de Aquisição com Isenção",
    "72": "Operação de Aquisição com Suspensão",
    "73": "Operação de Aquisição a Alíquota Zero",
    "74": "Operação de Aquisição sem Incidência da Contribuição",
    "75": "Operação de Aquisição por Substituição Tributária",
    "98": "Outras Operações de Entrada",
    "99": "Outras Operações",
}

# CSTs de entrada (50-56, 60-67) que geram direito a crédito de PIS/COFINS.
CSTS_GERAM_CREDITO: frozenset[str] = frozenset(
    {"50", "51", "52", "53", "54", "55", "56", "60", "61", "62", "63", "64", "65", "66", "67"}
)


def descricao(codigo: str) -> str:
    """Retorna a descrição do CST, ou string vazia se desconhecido."""
    return TABELA.get((codigo or "").strip(), "")


def gera_credito(codigo: str) -> bool:
    """True se o CST, por definição, gera direito a crédito de PIS/COFINS."""
    return (codigo or "").strip() in CSTS_GERAM_CREDITO

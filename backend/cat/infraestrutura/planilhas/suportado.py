"""A planilha da apuração do ICMS suportado.

Uma linha por item de entrada, com o valor e **de onde ele veio**. A coluna
Fonte é o motivo de a planilha existir: é por ela que se separa, na hora de
sustentar o pedido, o que está em documento do que foi reconstruído. E o
Motivo diz por que o item não apurou — sem ele, "não apurável" obrigaria a
abrir a nota para descobrir.

O filtro da tela é por fonte: pedir só "Não apurável" é a lista de providências.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

COLUNAS_SUPORTADO = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("competencia", "Competência", "data", 13),
    Coluna("modelo", "Modelo", "texto", 8),
    Coluna("numero_documento", "Número", "texto", 12),
    Coluna("chave", "Chave de acesso", "texto", 46),
    Coluna("participante", "Cód. participante", "texto", 16),
    Coluna("codigo", "Código do item", "texto", 16),
    Coluna("descricao", "Descrição (0200)", "texto", 40),
    Coluna("cst_icms", "CST ICMS", "texto", 9),
    Coluna("quantidade", "Quantidade", "quantidade", 14),
    Coluna("bc_st", "BC ICMS-ST", "numero", 14),
    Coluna("suportado", "ICMS suportado", "numero", 16),
    Coluna("fonte", "Fonte", "texto", 30),
    Coluna("pendencia", "Pendência", "texto", 18),
    Coluna("motivo", "Motivo", "texto", 60),
)


def gerar_suportado(parquet: str, destino: str,
                    modelos: frozenset[str] | None = None,
                    classificacoes: frozenset[str] | None = None,
                    formato: str = "xlsx") -> int:
    # `classificacoes`, aqui, são as fontes da cascata
    return gerar(parquet, destino, COLUNAS_SUPORTADO, "ICMS suportado",
                 modelos=modelos, classificacoes=classificacoes,
                 formato=formato, campo_da_classificacao="fonte")

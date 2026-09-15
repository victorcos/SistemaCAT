"""As planilhas do razão: a Ficha 3 inteira e o resumo por ficha.

A ficha é a lista grande — uma linha por lançamento, e numa base real são
dezenas de milhões. É a que se baixa em CSV. O resumo por ficha é o que se
abre no Excel para achar onde está o ressarcimento e o que pede atenção.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

COLUNAS_FICHA3 = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("codigo", "Código da mercadoria", "texto", 16),
    Coluna("numero", "Linha", "numero_inteiro", 8),
    Coluna("data", "Data", "data", 12),
    Coluna("especie", "Espécie", "texto", 10),
    Coluna("devolucao", "Devolução", "texto", 10),
    Coluna("cfop", "CFOP", "texto", 7),
    Coluna("documento", "Documento", "texto", 46),
    Coluna("origem", "Origem", "texto", 11),
    Coluna("enquadramento", "Enquadramento legal", "numero_inteiro", 12),
    Coluna("enquadramento_indefinido", "Enquadramento indefinido", "texto", 12),
    Coluna("quantidade", "Quantidade", "quantidade", 14),
    Coluna("icms_suportado", "ICMS suportado", "numero", 16),
    Coluna("valor_unitario_usado", "Unitário do saldo anterior", "quantidade", 16),
    Coluna("icms_efetivo", "Valor de confronto", "numero", 16),
    Coluna("saldo_quantidade", "Saldo em quantidade", "quantidade", 14),
    Coluna("saldo_unitario", "Saldo unitário", "quantidade", 16),
    Coluna("saldo_valor", "Saldo em valor", "numero", 16),
    Coluna("ressarcimento", "Ressarcimento", "numero", 14),
    Coluna("complemento", "Complemento", "numero", 14),
)

COLUNAS_FICHAS = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("uf", "UF", "texto", 5),
    Coluna("codigo", "Código da mercadoria", "texto", 16),
    Coluna("descricao", "Descrição (0200)", "texto", 40),
    Coluna("linhas", "Linhas", "numero_inteiro", 8),
    Coluna("abertura_quantidade", "Abertura (quantidade)", "quantidade", 14),
    Coluna("abertura_sem_valor", "Abertura sem ICMS suportado", "texto", 12),
    Coluna("entradas", "Entradas", "quantidade", 14),
    Coluna("saidas", "Saídas", "quantidade", 14),
    Coluna("saldo_quantidade", "Saldo final (quantidade)", "quantidade", 14),
    Coluna("saldo_valor", "Saldo final (ICMS suportado)", "numero", 16),
    Coluna("ressarcimento", "Ressarcimento", "numero", 14),
    Coluna("complemento", "Complemento", "numero", 14),
    Coluna("ficou_negativo", "Estoque ficou negativo", "texto", 12),
    Coluna("saidas_sem_aliquota", "Saídas sem alíquota", "numero_inteiro", 10),
    Coluna("saidas_indefinidas", "Saídas indefinidas", "numero_inteiro", 10),
)


def gerar_ficha3(parquet: str, destino: str, modelos=None, classificacoes=None,
                 formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_FICHA3, "Ficha 3", formato=formato)


def gerar_fichas(parquet: str, destino: str, modelos=None, classificacoes=None,
                 formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_FICHAS, "Fichas", formato=formato)

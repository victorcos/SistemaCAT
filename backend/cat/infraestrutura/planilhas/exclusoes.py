"""A planilha das exclusões da base do PIS/COFINS.

Uma linha por grupo — registro, CST e CFOP dentro da competência —, que é a
unidade em que a conta arredonda. Somar a coluna da diferença tem de dar o
total que a tela mostra: é por isso que o grupo aparece inteiro, com o que
havia e o que passa a haver, lado a lado.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

ONDE = "Onde"
ANTES = "Como está escriturado"
TESE = "Excluindo as contribuições da base"
VOLTA = "O que volta"

COLUNAS_DAS_EXCLUSOES = (
    Coluna("cnpj", "CNPJ do Estabelecimento", "texto", 20, ONDE),
    Coluna("competencia", "Competência", "texto", 12, ONDE),
    Coluna("registro", "Registro", "texto", 10, ONDE),
    Coluna("cst", "CST", "texto", 7, ONDE),
    Coluna("cfop", "CFOP", "texto", 8, ONDE),

    Coluna("base", "Base de Cálculo", "numero", 18, ANTES),
    Coluna("pis", "PIS", "numero", 15, ANTES),
    Coluna("cofins", "COFINS", "numero", 15, ANTES),

    Coluna("excluido", "PIS + COFINS Excluídos", "numero", 18, TESE),
    Coluna("base_nova_pis", "Base Nova do PIS", "numero", 18, TESE),
    Coluna("base_nova_cofins", "Base Nova da COFINS", "numero", 18, TESE),
    Coluna("pis_novo", "PIS Recalculado", "numero", 16, TESE),
    Coluna("cofins_novo", "COFINS Recalculada", "numero", 16, TESE),

    Coluna("diferenca_pis", "PIS", "numero", 15, VOLTA),
    Coluna("diferenca_cofins", "COFINS", "numero", 15, VOLTA),

    Coluna("tese", "Tese", "texto", 26, ONDE),
)


def gerar_exclusoes(parquet: str, destino: str, modelos=None, classificacoes=None,
                    formato: str = "xlsx") -> int:
    """Escreve a planilha das exclusões. Devolve quantas linhas gravou."""
    return gerar(parquet, destino, COLUNAS_DAS_EXCLUSOES, "Exclusões", formato=formato)

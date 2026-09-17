"""As planilhas do fechamento do período.

Duas saídas. A **apuração** é uma linha por estabelecimento e mês, com o que se
pede, o que se recolhe e o que trava — é a que se manda para quem decide. Os
**saldos** são uma linha por mercadoria e mês, no formato do registro 1050 do
arquivo digital: quantidade e ICMS suportado no início e no fim.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

COLUNAS_APURACAO = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("uf", "UF", "texto", 5),
    Coluna("competencia", "Competência", "texto", 12),
    Coluna("ressarcimento", "Ressarcimento a pedir", "numero", 16),
    Coluna("complemento", "Complemento a recolher", "numero", 16),
    Coluna("credito_operacao_propria", "Crédito da operação própria (art. 271)", "numero", 16),
    Coluna("apta", "Pronta para o arquivo digital", "texto", 12),
    Coluna("motivos", "O que trava", "texto", 60),
    Coluna("itens", "Mercadorias", "numero_inteiro", 10),
    Coluna("linhas", "Linhas da Ficha 3", "numero_inteiro", 12),
    Coluna("saldo_inicial_quantidade", "Saldo inicial (quantidade)", "quantidade", 14),
    Coluna("saldo_inicial_icms", "Saldo inicial (ICMS suportado)", "numero", 16),
    Coluna("saldo_final_quantidade", "Saldo final (quantidade)", "quantidade", 14),
    Coluna("saldo_final_icms", "Saldo final (ICMS suportado)", "numero", 16),
    Coluna("fichas_retiradas", "Fichas retiradas", "numero_inteiro", 10),
    Coluna("fichas_negativas", "Fichas abertas por estoque negativo", "numero_inteiro", 12),
    Coluna("confronto_pendente", "Saídas com confronto pendente", "numero_inteiro", 12),
    Coluna("sem_aliquota", "Saídas sem alíquota", "numero_inteiro", 10),
    Coluna("indefinidas", "Saídas indefinidas", "numero_inteiro", 10),
    Coluna("inventarios_conferidos", "Comparações com o inventário", "numero_inteiro", 12),
    Coluna("inventarios_divergentes", "Divergências com o inventário", "numero_inteiro", 12),
)

COLUNAS_SALDOS = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("competencia", "Competência", "texto", 12),
    Coluna("codigo", "Código da mercadoria", "texto", 16),
    Coluna("qtd_ini", "QTD_INI", "quantidade", 14),
    Coluna("icms_tot_ini", "ICMS_TOT_INI", "numero", 16),
    Coluna("qtd_fim", "QTD_FIM", "quantidade", 14),
    Coluna("icms_tot_fim", "ICMS_TOT_FIM", "numero", 16),
    Coluna("retirada", "Ficha retirada do total", "texto", 12),
)


def gerar_apuracao(parquet: str, destino: str, modelos=None, classificacoes=None,
                   formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_APURACAO, "Apuração", formato=formato)


def gerar_saldos(parquet: str, destino: str, modelos=None, classificacoes=None,
                 formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_SALDOS, "Saldos (1050)", formato=formato)

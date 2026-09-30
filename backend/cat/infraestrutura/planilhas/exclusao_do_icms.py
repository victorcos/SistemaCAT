"""A planilha do ICMS fora da base do PIS/COFINS — o relatório 903.

Uma linha por **item de nota fiscal**, nas quarenta colunas e na ordem em que o
MA exporta. Não é gosto: é para que o cliente que já tem o relatório do
escritório anterior consiga pôr as duas lado a lado e conferir coluna por
coluna. Foi assim que este motor foi validado — 138.358 linhas, 100%.

**As faixas contam a conta em quatro tempos**: onde a nota está, como ela foi
escriturada, o que o STF manda tirar, e quanto volta corrigido. Quem abre a
planilha no meio precisa saber em que etapa da conta está olhando.

A base recalculada e a base do STF ficam lado a lado de propósito: onde as
duas batem, a nota **já** excluiu o ICMS e não entra no pedido — e a linha
continua na planilha, com zero nas colunas do crédito, porque conferir que algo
foi feito certo também é trabalho.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

ONDE = "Onde"
ANTES = "Como está escriturado"
TESE = "Excluindo o ICMS da base (Tema 69)"
VOLTA = "O que volta, corrigido"

COLUNAS_DA_EXCLUSAO_DO_ICMS = (
    Coluna("cnpj", "CNPJ do Estabelecimento", "texto", 20, ONDE),
    Coluna("periodo", "Período", "texto", 12, ONDE),
    Coluna("codigo_do_participante", "Código Participante", "texto", 16, ONDE),
    Coluna("situacao", "Situação", "texto", 10, ONDE),
    Coluna("numero_do_documento", "Número Documento", "texto", 16, ONDE),
    # 44 dígitos: texto, sempre. Em número vira notação científica e parece certa
    Coluna("chave", "Chave NF-e", "texto", 46, ONDE),
    Coluna("data_do_documento", "Data Documento", "texto", 14, ONDE),
    Coluna("data_de_entrada_ou_saida", "Data Entrada/Saída", "texto", 16, ONDE),
    Coluna("numero_do_item", "Número Item", "texto", 11, ONDE),
    Coluna("codigo_do_item", "Código Item", "texto", 16, ONDE),
    Coluna("cfop", "CFOP", "texto", 8, ONDE),
    Coluna("cfop_faturamento", "CFOP Faturamento", "texto", 20, ONDE),
    Coluna("cst", "CST PIS/Cofins", "texto", 14, ONDE),

    Coluna("valor_do_item", "Vlr Item", "numero", 15, ANTES),
    Coluna("desconto_do_item", "Vlr Desconto Item", "numero", 16, ANTES),
    Coluna("base_do_icms", "Vlr Base Cálculo ICMS", "numero", 19, ANTES),
    Coluna("aliquota_do_icms", "Alíquota ICMS", "numero", 13, ANTES),
    Coluna("icms", "Vlr ICMS", "numero", 14, ANTES),
    Coluna("icms_com_pagamento", "Vlr ICMS C/ Pagamento PIS/Cofins", "numero", 22, ANTES),
    Coluna("rateio", "Vlr Rateio Frete/Seguro/DA", "numero", 20, ANTES),
    Coluna("ipi", "Valor IPI", "numero", 13, ANTES),
    Coluna("base", "Vlr Base Cálculo PIS/Cofins", "numero", 20, ANTES),

    Coluna("base_recalculada", "Vlr Base Cálculo Recalculada", "numero", 21, TESE),
    Coluna("diferenca_da_base_recalculada", "Vlr Diferença Base Recalculada",
           "numero", 22, TESE),
    Coluna("base_stf", "Vlr Base Cálculo - STF", "numero", 19, TESE),
    Coluna("diferenca_da_base", "Vlr Diferença Base", "numero", 17, TESE),
    Coluna("selic_acumulada", "SELIC Acumulada", "numero", 15, TESE),

    Coluna("aliquota_do_pis", "Alíquota PIS", "numero", 12, VOLTA),
    Coluna("pis", "Vlr PIS", "numero", 13, VOLTA),
    Coluna("pis_stf", "Vlr PIS - STF", "numero", 14, VOLTA),
    Coluna("diferenca_do_pis", "Vlr Diferença PIS", "numero", 16, VOLTA),
    Coluna("selic_sobre_o_pis", "Vlr SELIC S/PIS", "numero", 15, VOLTA),
    Coluna("total_do_pis_a_recuperar", "Vlr Total PIS Recuperar", "numero", 19, VOLTA),
    Coluna("aliquota_da_cofins", "Alíquota Cofins", "numero", 14, VOLTA),
    Coluna("cofins", "Vlr Cofins", "numero", 14, VOLTA),
    Coluna("cofins_stf", "Vlr Cofins - STF", "numero", 15, VOLTA),
    Coluna("diferenca_da_cofins", "Vlr Diferença Cofins", "numero", 18, VOLTA),
    Coluna("selic_sobre_a_cofins", "Vlr SELIC S/Cofins", "numero", 17, VOLTA),
    Coluna("total_da_cofins_a_recuperar", "Vlr Total Cofins Recuperar", "numero", 21, VOLTA),
    Coluna("total_a_recuperar_atualizado", "Vlr Total Recuperar Atualizado",
           "numero", 22, VOLTA),
)


def gerar_exclusao_do_icms(parquet: str, destino: str, modelos=None,
                           classificacoes=None, formato: str = "xlsx") -> int:
    """Escreve a planilha do Tema 69. Devolve quantas linhas gravou."""
    return gerar(parquet, destino, COLUNAS_DA_EXCLUSAO_DO_ICMS, "ICMS fora da base",
                 formato=formato)

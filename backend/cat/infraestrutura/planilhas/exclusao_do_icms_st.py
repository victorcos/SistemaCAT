"""A planilha do ICMS-ST fora da base do PIS/COFINS — o relatório 839.

Uma linha por **item de nota fiscal**, nas quarenta e seis colunas e na ordem em
que o MA exporta, para que o cliente ponha as duas lado a lado e confira. Foi
assim que este motor foi validado — 463.212 linhas, 100%.

**A faixa "Como o ST foi presumido" existe por honestidade.** Diferente do 903,
que exclui um imposto escrito na nota, aqui o ICMS-ST não existe em lugar
nenhum do arquivo: ele é reconstruído de uma base presumida e de uma alíquota.
Quem abrir a planilha precisa ver as duas colunas que geraram o número — a base
e a alíquota — ao lado do número, e não em outro lugar. Pedido que nasce de
arbitramento se defende mostrando a conta.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

ONDE = "Onde"
ANTES = "Como está escriturado"
PRESUMIDO = "Como o ST foi presumido"
TESE = "Excluindo o ICMS-ST da base"
VOLTA = "O que volta, corrigido"

COLUNAS_DA_EXCLUSAO_DO_ICMS_ST = (
    Coluna("cnpj", "CNPJ do Estabelecimento", "texto", 20, ONDE),
    Coluna("periodo", "Período", "texto", 12, ONDE),
    Coluna("uf", "UF Origem/Destino", "texto", 16, ONDE),
    Coluna("modelo", "Modelo", "texto", 9, ONDE),
    Coluna("codigo_do_participante", "Código Participante", "texto", 16, ONDE),
    Coluna("cnpj_do_participante", "CNPJ Participante", "texto", 20, ONDE),
    Coluna("cpf_do_participante", "CPF Participante", "texto", 16, ONDE),
    Coluna("nome_do_participante", "Nome Participante", "texto", 40, ONDE),
    Coluna("situacao", "Situação", "texto", 10, ONDE),
    Coluna("numero_do_documento", "Número Documento", "texto", 16, ONDE),
    # 44 dígitos: texto, sempre. Em número vira notação científica e parece certa
    Coluna("chave", "Chave NF-e", "texto", 46, ONDE),
    Coluna("data_do_documento", "Data Documento", "texto", 14, ONDE),
    Coluna("data_de_entrada_ou_saida", "Data Entrada/Saída", "texto", 16, ONDE),
    Coluna("numero_do_item", "Número Item", "texto", 11, ONDE),
    Coluna("codigo_do_item", "Código Item", "texto", 16, ONDE),
    Coluna("codigo_ean", "Código EAN", "texto", 18, ONDE),
    Coluna("descricao_do_item", "Descrição Item", "texto", 40, ONDE),
    Coluna("cfop", "CFOP", "texto", 8, ONDE),
    Coluna("cst_do_icms", "CST ICMS", "texto", 10, ONDE),
    Coluna("cst", "CST PIS/Cofins", "texto", 14, ONDE),

    Coluna("valor_do_documento", "Vlr Documento", "numero", 16, ANTES),
    Coluna("desconto_do_documento", "Vlr Desconto", "numero", 14, ANTES),
    Coluna("valor_do_item", "Vlr Item", "numero", 15, ANTES),
    Coluna("desconto_do_item", "Vlr Desconto Item", "numero", 16, ANTES),
    Coluna("rateio", "Vlr Rateio Frete/Seguro/DA", "numero", 20, ANTES),
    Coluna("base", "Vlr Base Cálculo PIS/Cofins", "numero", 20, ANTES),

    Coluna("base_do_icms_st_presumido", "Vlr Base Cálculo ICMS-ST Presumido",
           "numero", 24, PRESUMIDO),
    Coluna("aliquota_interna", "Alíquota Interna ICMS/UF Origem/Destino",
           "numero", 24, PRESUMIDO),
    Coluna("icms_st", "Vlr ICMS-ST", "numero", 14, PRESUMIDO),
    Coluna("icms_st_com_pagamento", "Vlr ICMS-ST C/ Pagamento PIS/Cofins",
           "numero", 24, PRESUMIDO),

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
    Coluna("total_da_cofins_a_recuperar", "Vlr Total Cofins Recuperar",
           "numero", 21, VOLTA),
    Coluna("total_a_recuperar_atualizado", "Vlr Total Recuperar Atualizado",
           "numero", 22, VOLTA),
)


def gerar_exclusao_do_icms_st(parquet: str, destino: str, modelos=None,
                              classificacoes=None, formato: str = "xlsx") -> int:
    """Escreve a planilha do ICMS-ST. Devolve quantas linhas gravou."""
    return gerar(parquet, destino, COLUNAS_DA_EXCLUSAO_DO_ICMS_ST,
                 "ICMS-ST fora da base", formato=formato)

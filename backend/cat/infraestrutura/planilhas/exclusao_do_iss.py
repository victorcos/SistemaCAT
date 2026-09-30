"""A planilha do ISS fora da base do PIS/COFINS — o relatório 933.

Uma linha por item de nota de serviço, nas trinta e duas colunas e na ordem em
que o MA exporta. Conferida 100% nas 33 linhas do arquivo de referência.

**A coluna do ISS sai em branco quando o cliente não a escriturou** — e não
zero. O `VL_ISS` do registro A100 é facultativo; em branco quer dizer "o valor
está na NFS-e e ainda não veio", e zero quer dizer "não houve ISS". Para quem
confere são coisas diferentes, e a planilha preserva a diferença como o MA
preserva.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

ONDE = "Onde"
ANTES = "Como está escriturado"
TESE = "Excluindo o ISS da base"
VOLTA = "O que volta, corrigido"

COLUNAS_DA_EXCLUSAO_DO_ISS = (
    Coluna("cnpj", "CNPJ do Estabelecimento", "texto", 20, ONDE),
    Coluna("periodo", "Período", "texto", 12, ONDE),
    Coluna("situacao", "Situação", "texto", 10, ONDE),
    Coluna("numero_do_documento", "Número Documento", "texto", 16, ONDE),
    Coluna("chave", "Chave/Código Verificação NFS-e", "texto", 46, ONDE),
    Coluna("data_do_documento", "Data Documento", "texto", 14, ONDE),
    Coluna("data_de_execucao_do_servico", "Data Execução Serviço", "texto", 18, ONDE),
    Coluna("cst", "CST PIS/Cofins", "texto", 14, ONDE),

    Coluna("valor_do_documento", "Vlr Documento", "numero", 16, ANTES),
    Coluna("desconto_do_documento", "Vlr Desconto Documento", "numero", 20, ANTES),
    Coluna("valor_do_item", "Vlr Item", "numero", 15, ANTES),
    Coluna("desconto_do_item", "Vlr Desconto Item", "numero", 16, ANTES),
    Coluna("base", "Vlr Base Cálculo PIS/Cofins", "numero", 20, ANTES),

    # fração, não porcentagem: vale 1 no documento de um item só
    Coluna("percentual_do_rateio", "Percentual Rateio", "numero", 15, TESE),
    Coluna("iss_rateado", "Vlr ISS - Rateio", "numero", 15, TESE),
    Coluna("base_recalculada", "Vlr Base Cálculo - Recalculada", "numero", 22, TESE),
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


def gerar_exclusao_do_iss(parquet: str, destino: str, modelos=None,
                          classificacoes=None, formato: str = "xlsx") -> int:
    """Escreve a planilha do ISS. Devolve quantas linhas gravou."""
    return gerar(parquet, destino, COLUNAS_DA_EXCLUSAO_DO_ISS,
                 "ISS fora da base", formato=formato)

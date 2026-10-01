"""A planilha das contribuições fora da própria base, item a item — o 680.

Uma linha por item, nas trinta e cinco colunas e na ordem em que o MA exporta.
Conferida **100%** nas 3.568.362 linhas do arquivo de referência.

É a frente detalhada da tese das contribuições; a outra é a consolidada, que sai
em `exclusoes.py` somada por grupo. A soma das duas difere em 0,06% **de
propósito** — ver a decisão de 24/09/2026 e o topo de
`sped/exclusao_piscofins_na_base.py`. Quem põe as duas lado a lado tem de
encontrar essa diferença escrita, e não descobri-la.

**Três colunas saem em branco onde o ramo não as tem**, e branco não é zero: só
o `C100/C170` traz ICMS, desconto e rateio; o `C100/C175` traz só o desconto; o
`A100/A170` e o `F100` não trazem nenhum dos três — nem quando o leiaute tem o
campo. Preencher com zero era errar 71.837 linhas de uma competência só.

**O ICMS e o rateio são informativos.** Vêm preenchidos e não entram em conta
nenhuma desta tese: a base do relatório é a base escriturada, não
`item − desconto + rateio − ICMS`. Estão ali porque o 680 é o detalhe geral da
receita.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

ONDE = "Onde"
ANTES = "Como está escriturado"
TESE = "Excluindo as contribuições da própria base"
VOLTA = "O que volta, corrigido"

COLUNAS_DA_EXCLUSAO_PISCOFINS = (
    Coluna("cnpj", "CNPJ", "texto", 20, ONDE),
    Coluna("periodo", "Período", "texto", 12, ONDE),
    # qual dos quatro ramos: C100/C170, C100/C175, A100/A170 ou F100
    Coluna("registro", "Registro Lançamento", "texto", 20, ONDE),
    Coluna("modelo", "Modelo Documento", "texto", 16, ONDE),
    Coluna("numero_do_documento", "Número Documento", "texto", 16, ONDE),
    Coluna("chave", "Chave Documento", "texto", 46, ONDE),
    Coluna("data_do_documento", "Data Documento", "texto", 14, ONDE),
    Coluna("numero_do_item", "Número Item", "texto", 12, ONDE),
    Coluna("codigo_do_item", "Código Item", "texto", 16, ONDE),
    Coluna("descricao_do_item", "Descrição Item", "texto", 42, ONDE),

    Coluna("valor_do_item", "Vlr Item", "numero", 15, ANTES),
    Coluna("desconto", "Vlr Desconto", "numero", 15, ANTES),
    # informativos, e vazios nos ramos que não os têm. Ver o topo do módulo
    Coluna("icms", "Vlr ICMS", "numero", 14, ANTES),
    Coluna("rateio", "Vlr Rateio Frete/Seguro/DA", "numero", 22, ANTES),
    # "S" — o sentido — nos registros que não têm CFOP no leiaute
    Coluna("cfop", "CFOP", "texto", 10, ANTES),
    Coluna("cfop_faturamento", "CFOP Faturamento", "texto", 20, ANTES),
    Coluna("cst", "CST PIS/Cofins", "texto", 14, ANTES),

    Coluna("selic_acumulada", "SELIC Acumulada", "numero", 15, TESE),
    Coluna("base_do_pis", "Vlr Base Cálculo PIS", "numero", 18, TESE),
    Coluna("base_do_pis_stf", "Vlr Base Cálculo PIS - STF", "numero", 22, TESE),

    Coluna("aliquota_do_pis", "Alíquota PIS", "numero", 12, VOLTA),
    Coluna("pis", "Vlr PIS", "numero", 13, VOLTA),
    Coluna("pis_stf", "Vlr PIS - STF", "numero", 14, VOLTA),
    Coluna("diferenca_do_pis", "Vlr Diferença PIS", "numero", 16, VOLTA),
    Coluna("selic_sobre_o_pis", "Vlr SELIC S/PIS", "numero", 15, VOLTA),
    Coluna("total_do_pis_a_recuperar", "Vlr Total PIS Recuperar", "numero", 19, VOLTA),
    Coluna("base_da_cofins", "Vlr Base Cálculo Cofins", "numero", 20, VOLTA),
    Coluna("base_da_cofins_stf", "Vlr Base Cálculo Cofins - STF", "numero", 24, VOLTA),
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


def gerar_exclusao_piscofins(parquet: str, destino: str, modelos=None,
                             classificacoes=None, formato: str = "xlsx") -> int:
    """Escreve a planilha do 680. Devolve quantas linhas gravou."""
    return gerar(parquet, destino, COLUNAS_DA_EXCLUSAO_PISCOFINS,
                 "Contribuições fora da base", formato=formato)

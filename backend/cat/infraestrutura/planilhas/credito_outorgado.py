"""As planilhas do crédito outorgado: o que entra, e o que ficou de fora.

Duas listas com **as mesmas colunas**, de propósito. Quem revisa o filtro abre
as duas lado a lado e procura a mesma coisa nos dois lugares — um produto que
deveria ter entrado e não entrou, ou o contrário. Colunas diferentes entre elas
obrigariam a reaprender a planilha no meio da revisão.

Os valores vão **tipados** — número é número, data é data —, e não como texto
com vírgula, que é como a origem entregava. É o que permite somar a coluna e
montar dinâmica sem antes converter a planilha inteira.

Acima de 900 mil linhas a planilha quebra em aba, como as demais desta casa; e
é por isso que o CSV existe ao lado do xlsx — a varredura de um ano de cliente
grande passa do limite do Excel com folga.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

DOCUMENTO = "Documento"
ITEM = "Item"
ICMS = "ICMS"
PIS = "PIS"
COFINS = "COFINS"
TRIAGEM = "Triagem"

COLUNAS = (
    Coluna("chave", "Chave de Acesso", "texto", 46, DOCUMENTO),
    Coluna("modelo", "Modelo", "texto", 8, DOCUMENTO),
    Coluna("numero_documento", "Número", "texto", 12, DOCUMENTO),
    Coluna("serie", "Série", "texto", 8, DOCUMENTO),
    Coluna("emissao", "Emissão", "data", 12, DOCUMENTO),
    Coluna("emitente", "CNPJ do Emitente", "texto", 20, DOCUMENTO),
    Coluna("emitente_nome", "Emitente", "texto", 34, DOCUMENTO),
    Coluna("destinatario", "CNPJ/CPF do Destinatário", "texto", 20, DOCUMENTO),
    Coluna("destinatario_nome", "Destinatário", "texto", 34, DOCUMENTO),
    Coluna("arquivo", "Arquivo de Origem", "texto", 40, DOCUMENTO),

    Coluna("numero_item", "Número", "numero_inteiro", 8, ITEM),
    Coluna("codigo", "Código", "texto", 16, ITEM),
    Coluna("descricao", "Descrição", "texto", 44, ITEM),
    Coluna("ncm", "NCM", "texto", 11, ITEM),
    Coluna("cest", "CEST", "texto", 10, ITEM),
    Coluna("cfop", "CFOP", "texto", 8, ITEM),
    Coluna("unidade", "Unidade", "texto", 9, ITEM),
    Coluna("quantidade", "Quantidade", "quantidade", 13, ITEM),
    Coluna("valor_unitario", "Valor Unitário", "numero", 14, ITEM),
    Coluna("valor", "Valor do Item", "numero", 14, ITEM),

    Coluna("cst_icms", "CST", "texto", 7, ICMS),
    Coluna("bc_icms", "Base de Cálculo", "numero", 14, ICMS),
    Coluna("aliq_icms", "Alíquota", "numero", 10, ICMS),
    Coluna("valor_icms", "Valor", "numero", 13, ICMS),

    Coluna("cst_pis", "CST", "texto", 7, PIS),
    Coluna("bc_pis", "Base de Cálculo", "numero", 14, PIS),
    Coluna("aliq_pis", "Alíquota", "numero", 10, PIS),
    Coluna("valor_pis", "Valor", "numero", 13, PIS),

    Coluna("cst_cofins", "CST", "texto", 7, COFINS),
    Coluna("bc_cofins", "Base de Cálculo", "numero", 14, COFINS),
    Coluna("aliq_cofins", "Alíquota", "numero", 10, COFINS),
    Coluna("valor_cofins", "Valor", "numero", 13, COFINS),

    # por que a linha está nesta lista. No descartado vai vazio: o motivo de
    # não entrar é sempre o mesmo — nenhum termo cadastrado apareceu na descrição
    Coluna("motivo", "Motivo", "texto", 16, TRIAGEM),
)


def gerar_elegiveis(parquet: str, destino: str, modelos=None, classificacoes=None,
                    formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS, "Crédito Outorgado", formato=formato)


def gerar_descartados(parquet: str, destino: str, modelos=None, classificacoes=None,
                      formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS, "Descartados", formato=formato)

"""As planilhas do histórico de movimentação.

Quatro saídas, todas pelo mesmo gerador da conferência (memória constante,
quebra em abas, identificador como texto, valor e data tipados):

* **movimentos** — cada item de documento, com o cadastro e a marca da
  conferência. É a que se abre para seguir um item no tempo; por isso vem
  ordenada por estabelecimento, item e data, e aceita filtro por modelo e
  por classificação;
* **itens** — o cadastro que vale, um por estabelecimento e código;
* **inventário** — o saldo de abertura, item a item;
* **analítico** — o total por CST/CFOP de cada documento, com `tem_item`.
  É por aqui que se vê o que a EFD não detalha.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

COLUNAS_MOVIMENTOS = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("codigo", "Código do item", "texto", 16),
    Coluna("descricao", "Descrição (0200)", "texto", 40),
    Coluna("codigo_barras", "Código de barras", "texto", 16),
    Coluna("ncm", "NCM", "texto", 11),
    Coluna("cest", "CEST", "texto", 10),
    Coluna("competencia", "Competência", "data", 13),
    Coluna("data", "Data do documento", "data", 13),
    Coluna("operacao", "Operação", "texto", 10),
    Coluna("modelo", "Modelo", "texto", 8),
    Coluna("numero_documento", "Número", "texto", 12),
    Coluna("chave", "Chave de acesso", "texto", 46),
    Coluna("participante", "Cód. participante", "texto", 16),
    Coluna("numero_item", "Item", "numero_inteiro", 6),
    Coluna("cfop", "CFOP", "texto", 7),
    Coluna("cst_icms", "CST ICMS", "texto", 9),
    Coluna("quantidade", "Quantidade", "quantidade", 14),
    Coluna("unidade", "Unid.", "texto", 7),
    Coluna("valor", "Valor do item", "numero", 16),
    Coluna("desconto", "Desconto", "numero", 12),
    Coluna("bc_icms", "BC ICMS", "numero", 14),
    Coluna("aliq_icms", "Alíq. ICMS", "numero", 10),
    Coluna("valor_icms", "Valor ICMS", "numero", 14),
    Coluna("bc_st", "BC ICMS-ST", "numero", 14),
    Coluna("aliq_st", "Alíq. ST", "numero", 10),
    Coluna("valor_st", "Valor ICMS-ST", "numero", 14),
    Coluna("classificacao", "Conferência", "texto", 30),
    Coluna("registro", "Registro", "texto", 9),
    Coluna("arquivo", "Arquivo da EFD", "texto", 34),
    Coluna("fonte_item", "Item de", "texto", 8),
    Coluna("codigo_xml", "Código no XML", "texto", 16),
    Coluna("gtin_xml", "GTIN no XML", "texto", 16),
    Coluna("valor_st_xml", "ICMS-ST no XML", "numero", 14),
    Coluna("retido_xml", "Retido informado no XML", "numero", 14),
    Coluna("arquivo_xml", "Arquivo do XML", "texto", 34),
)

COLUNAS_ITENS = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("codigo", "Código do item", "texto", 16),
    Coluna("descricao", "Descrição", "texto", 44),
    Coluna("codigo_barras", "Código de barras", "texto", 16),
    Coluna("codigo_anterior", "Código anterior", "texto", 14),
    Coluna("unidade", "Unid. inventário", "texto", 10),
    Coluna("tipo_item", "Tipo", "texto", 6),
    Coluna("ncm", "NCM", "texto", 11),
    Coluna("ex_ipi", "EX IPI", "texto", 7),
    Coluna("cod_gen", "Gênero", "texto", 8),
    Coluna("cod_lst", "Cód. LST", "texto", 9),
    Coluna("aliq_icms", "Alíq. ICMS", "numero", 10),
    Coluna("cest", "CEST", "texto", 10),
    Coluna("competencia", "Cadastro de (competência)", "data", 14),
    Coluna("arquivo", "Arquivo da EFD", "texto", 34),
)

COLUNAS_INVENTARIO = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("data_inventario", "Data do inventário", "data", 14),
    Coluna("motivo", "Motivo (H005)", "texto", 10),
    Coluna("codigo", "Código do item", "texto", 16),
    Coluna("unidade", "Unid.", "texto", 7),
    Coluna("quantidade", "Quantidade", "quantidade", 14),
    Coluna("valor_unitario", "Valor unitário", "quantidade", 14),
    Coluna("valor", "Valor do item", "numero", 16),
    Coluna("ind_prop", "Propriedade", "texto", 10),
    Coluna("participante", "Cód. participante", "texto", 16),
    Coluna("cod_cta", "Conta contábil", "texto", 16),
    Coluna("arquivo", "Arquivo da EFD", "texto", 34),
)

COLUNAS_ANALITICO = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("competencia", "Competência", "data", 13),
    Coluna("data", "Data do documento", "data", 13),
    Coluna("operacao", "Operação", "texto", 10),
    Coluna("modelo", "Modelo", "texto", 8),
    Coluna("numero_documento", "Número", "texto", 12),
    Coluna("chave", "Chave de acesso", "texto", 46),
    Coluna("registro", "Registro", "texto", 9),
    Coluna("cst_icms", "CST ICMS", "texto", 9),
    Coluna("cfop", "CFOP", "texto", 7),
    Coluna("aliq_icms", "Alíq. ICMS", "numero", 10),
    Coluna("valor_operacao", "Valor da operação", "numero", 16),
    Coluna("bc_icms", "BC ICMS", "numero", 14),
    Coluna("valor_icms", "Valor ICMS", "numero", 14),
    Coluna("bc_st", "BC ICMS-ST", "numero", 14),
    Coluna("valor_st", "Valor ICMS-ST", "numero", 14),
    Coluna("tem_item", "Documento tem item na EFD", "texto", 14),
    Coluna("arquivo", "Arquivo da EFD", "texto", 34),
)


def gerar_movimentos(parquet: str, destino: str,
                     modelos: frozenset[str] | None = None,
                     classificacoes: frozenset[str] | None = None,
                     formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_MOVIMENTOS, "Movimentos",
                 modelos=modelos, classificacoes=classificacoes,
                 formato=formato)


def gerar_itens(parquet: str, destino: str,
                modelos: frozenset[str] | None = None,
                classificacoes: frozenset[str] | None = None,
                formato: str = "xlsx") -> int:
    # o cadastro não tem modelo nem classificação: os filtros não se aplicam
    return gerar(parquet, destino, COLUNAS_ITENS, "Itens", formato=formato)


def gerar_inventario(parquet: str, destino: str,
                     modelos: frozenset[str] | None = None,
                     classificacoes: frozenset[str] | None = None,
                     formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_INVENTARIO, "Inventário",
                 formato=formato)


def gerar_analitico(parquet: str, destino: str,
                    modelos: frozenset[str] | None = None,
                    classificacoes: frozenset[str] | None = None,
                    formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_ANALITICO, "Analítico",
                 modelos=modelos, formato=formato)

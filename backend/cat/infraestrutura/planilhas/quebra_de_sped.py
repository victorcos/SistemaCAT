"""As planilhas da quebra de SPED.

Quatro, e duas delas são o par que importa: a **Consulta de Entradas** diz o que
a escrituração fiscal registrou como entrada, e o **razão contábil** diz o que a
contabilidade lançou. As outras duas descrevem o que foi lido — servem para
conferir a base antes de olhar o número.

Todas saem no cabeçalho padrão da casa e, acima de 900 mil linhas, quebram em
aba, como as demais. A 037 de um ano de cliente grande passa disso com folga, e
é por isso que o CSV existe ao lado do xlsx.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

# ---------------------------------------------------------------------------
# a Consulta de Entradas (037)
# ---------------------------------------------------------------------------
DOCUMENTO = "Documento"
PARTICIPANTE = "Participante"
ITEM = "Item"
PIS = "PIS"
COFINS = "COFINS"
CONTABIL = "Contábil"

COLUNAS_ENTRADAS = (
    Coluna("cnpj", "CNPJ do Estabelecimento", "texto", 20, DOCUMENTO),
    Coluna("periodo", "Período", "texto", 11, DOCUMENTO),
    Coluna("registros", "Registros", "texto", 40, DOCUMENTO),
    Coluna("modelo", "Modelo", "texto", 8, DOCUMENTO),
    Coluna("situacao", "Situação", "texto", 9, DOCUMENTO),
    Coluna("numero_do_documento", "Número do Documento", "texto", 14, DOCUMENTO),
    Coluna("serie", "Série", "texto", 8, DOCUMENTO),
    Coluna("chave", "Chave", "texto", 46, DOCUMENTO),
    Coluna("data_do_documento", "Data do Documento", "texto", 12, DOCUMENTO),
    Coluna("data_de_entrada", "Data de Entrada", "texto", 12, DOCUMENTO),
    Coluna("valor_do_documento", "Valor do Documento", "texto", 15, DOCUMENTO),
    Coluna("desconto_do_documento", "Desconto do Documento", "texto", 15, DOCUMENTO),
    Coluna("valor_da_mercadoria", "Valor da Mercadoria", "texto", 15, DOCUMENTO),
    Coluna("frete", "Frete", "texto", 12, DOCUMENTO),

    Coluna("codigo_do_participante", "Código", "texto", 12, PARTICIPANTE),
    Coluna("cnpj_do_participante", "CNPJ", "texto", 20, PARTICIPANTE),
    Coluna("cpf_do_participante", "CPF", "texto", 16, PARTICIPANTE),
    Coluna("nome_do_participante", "Nome", "texto", 34, PARTICIPANTE),
    Coluna("uf_origem_destino", "UF Origem/Destino", "texto", 12, PARTICIPANTE),
    Coluna("municipio_do_participante", "Município", "texto", 22, PARTICIPANTE),

    Coluna("numero_do_item", "Número", "texto", 8, ITEM),
    Coluna("codigo_do_item", "Código", "texto", 16, ITEM),
    Coluna("descricao_do_item", "Descrição", "texto", 38, ITEM),
    Coluna("descricao_complementar", "Descrição Complementar", "texto", 30, ITEM),
    Coluna("ncm", "NCM", "texto", 11, ITEM),
    Coluna("codigo_de_barra", "Código de Barra", "texto", 16, ITEM),
    Coluna("tipo_do_item", "Tipo do Item", "texto", 26, ITEM),
    Coluna("valor_do_item", "Valor", "texto", 14, ITEM),
    Coluna("quantidade", "Quantidade", "texto", 13, ITEM),
    Coluna("unidade", "Unidade", "texto", 9, ITEM),
    Coluna("desconto_do_item", "Desconto", "texto", 13, ITEM),
    Coluna("cfop", "CFOP", "texto", 8, ITEM),
    Coluna("descricao_do_cfop", "Descrição do CFOP", "texto", 30, ITEM),
    Coluna("natureza_do_credito", "Natureza do Crédito", "texto", 36, ITEM),
    Coluna("icms", "ICMS", "texto", 13, ITEM),
    Coluna("icms_st", "ICMS-ST", "texto", 13, ITEM),
    Coluna("ipi", "IPI", "texto", 13, ITEM),

    Coluna("cst_pis", "CST", "texto", 7, PIS),
    Coluna("base_do_pis", "Base de Cálculo", "texto", 15, PIS),
    Coluna("quantidade_base_do_pis", "Quantidade da Base", "texto", 15, PIS),
    Coluna("aliquota_do_pis", "Alíquota", "texto", 11, PIS),
    Coluna("quantidade_aliquota_do_pis", "Alíquota por Quantidade", "texto", 15, PIS),
    Coluna("pis", "Valor", "texto", 13, PIS),

    Coluna("cst_cofins", "CST", "texto", 7, COFINS),
    Coluna("base_da_cofins", "Base de Cálculo", "texto", 15, COFINS),
    Coluna("quantidade_base_da_cofins", "Quantidade da Base", "texto", 15, COFINS),
    Coluna("aliquota_da_cofins", "Alíquota", "texto", 11, COFINS),
    Coluna("quantidade_aliquota_da_cofins", "Alíquota por Quantidade", "texto", 15, COFINS),
    Coluna("cofins", "Valor", "texto", 13, COFINS),

    Coluna("conta_contabil", "Conta", "texto", 14, CONTABIL),
    Coluna("nome_da_conta", "Nome da Conta", "texto", 32, CONTABIL),
    # deduzida, não lida: ver `sped/entradas.py`
    Coluna("debito_ou_credito", "D/C (suposto)", "texto", 12, CONTABIL),
)

# ---------------------------------------------------------------------------
# o razão contábil da ECD
# ---------------------------------------------------------------------------
CONTA = "Conta"
LANCAMENTO = "Lançamento"
PARTIDA = "Partida"

COLUNAS_RAZAO = (
    Coluna("cnpj", "CNPJ do Estabelecimento", "texto", 20, CONTA),
    Coluna("conta", "Conta", "texto", 16, CONTA),
    Coluna("descricao", "Descrição", "texto", 36, CONTA),
    Coluna("conta_referencial", "Conta Referencial", "texto", 16, CONTA),

    Coluna("competencia", "Competência", "texto", 12, LANCAMENTO),
    Coluna("data", "Data", "texto", 12, LANCAMENTO),
    Coluna("numero", "Número", "texto", 12, LANCAMENTO),
    Coluna("valor_do_lancamento", "Valor do Lançamento", "texto", 16, LANCAMENTO),
    Coluna("tipo", "Tipo", "texto", 14, LANCAMENTO),

    Coluna("valor", "Valor", "texto", 14, PARTIDA),
    Coluna("debito_ou_credito", "D/C", "texto", 6, PARTIDA),
    Coluna("saldo", "Saldo Acumulado", "texto", 16, PARTIDA),
    Coluna("centro_de_custo", "Centro de Custo", "texto", 14, PARTIDA),
    Coluna("codigo_do_historico", "Código do Histórico", "texto", 12, PARTIDA),
    Coluna("historico", "Histórico", "texto", 44, PARTIDA),
    Coluna("participante", "Participante", "texto", 14, PARTIDA),
    Coluna("arquivo", "Arquivo de Origem", "texto", 30, PARTIDA),
)

# ---------------------------------------------------------------------------
# o que foi lido
# ---------------------------------------------------------------------------
COLUNAS_ARQUIVOS = (
    Coluna("nome", "Arquivo", "texto", 44),
    Coluna("tipo", "Tipo", "texto", 15),
    Coluna("cnpj", "CNPJ", "texto", 20),
    Coluna("empresa", "Empresa", "texto", 34),
    Coluna("inicio", "Início", "texto", 12),
    Coluna("fim", "Fim", "texto", 12),
    Coluna("bytes", "Bytes", "numero_inteiro", 14),
    Coluna("linhas", "Linhas", "numero_inteiro", 12),
    Coluna("registros", "Tipos de Registro", "numero_inteiro", 12),
    Coluna("itens", "Itens (C170)", "numero_inteiro", 12),
    Coluna("consolidacoes", "Consolidações (C180/C190)", "numero_inteiro", 14),
    Coluna("entradas_geradas", "Entradas Geradas", "numero_inteiro", 14),
    Coluna("contas", "Contas (I050)", "numero_inteiro", 12),
    Coluna("lancamentos", "Lançamentos (I200)", "numero_inteiro", 14),
    Coluna("partidas", "Partidas (I250)", "numero_inteiro", 14),
    Coluna("linhas_do_razao", "Linhas do Razão", "numero_inteiro", 14),
    Coluna("erro", "Erro", "texto", 44),
    Coluna("caminho", "Caminho", "texto", 60),
)

COLUNAS_CONTAGENS = (
    Coluna("arquivo", "Arquivo", "texto", 44),
    Coluna("registro", "Registro", "texto", 10),
    Coluna("quantidade", "Quantidade", "numero_inteiro", 14),
)


def gerar_entradas(parquet: str, destino: str, modelos=None, classificacoes=None,
                   formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_ENTRADAS, "Consulta de Entradas", formato=formato)


def gerar_razao_contabil(parquet: str, destino: str, modelos=None, classificacoes=None,
                         formato: str = "xlsx") -> int:
    """O razão. `classificacoes`, nesta planilha, são as **contas escolhidas**.

    Sem nenhuma, sai o razão inteiro, como sempre saiu. Com contas, sai só o
    que se vai conferir: quem confronta a contabilidade com a 037 leva meia
    dúzia de contas por vez, e baixar milhões de partidas para filtrar no Excel
    não é conferência — é espera.

    O recorte é pelo código da conta, não pelo par CNPJ+conta: a mesma conta em
    dois estabelecimentos é a mesma conta do plano, e quem escolhe "3.1.1"
    quer a 3.1.1 de todos eles. A tela avisa quando há mais de um.
    """
    return gerar(parquet, destino, COLUNAS_RAZAO, "Razão Contábil",
                 classificacoes=classificacoes, formato=formato,
                 campo_da_classificacao="conta")


def gerar_arquivos_quebrados(parquet: str, destino: str, modelos=None, classificacoes=None,
                             formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_ARQUIVOS, "SPED quebrados", formato=formato)


def gerar_contagens(parquet: str, destino: str, modelos=None, classificacoes=None,
                    formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_CONTAGENS, "Registros por arquivo", formato=formato)

"""A planilha dos itens do XML, com as colunas que a pessoa escolher.

Uma linha por item da nota — 61 colunas possíveis, e quase ninguém quer as 61.
Quem confere ICMS não olha ISSQN; quem confere PIS/COFINS não olha ST; e uma
planilha de trinta colunas inúteis é uma planilha que se rola para os lados até
desistir.

**A escolha é por campo, agrupada por bloco.** Os blocos existem porque ninguém
marca "vBCSTRet" sozinho: marca-se "ICMS-ST" e pronto. Os atalhos (`ICMS`,
`PIS/COFINS`, `Descontos`, `Tudo`) são conjuntos de blocos, e servem ao caso
comum sem impedir o raro.

**A ordem da planilha é a daqui, não a da escolha.** Marcar ICMS depois de
PIS/COFINS não põe o ICMS no fim: a ordem das colunas é sempre a mesma, e duas
planilhas do mesmo trabalho se comparam lado a lado.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

IDENTIFICACAO = "Identificação"
PARTES = "Emitente e destinatário"
PRODUTO = "Produto"
DESCONTOS = "Descontos e acessórios"
ICMS = "ICMS"
ST = "ICMS-ST e efetivo"
PISCOFINS = "PIS e COFINS"
IPI_ISSQN = "IPI e ISSQN"

# a ordem aqui é a ordem da planilha, sempre
CAMPOS = (
    Coluna("chave", "Chave de Acesso", "texto", 46, IDENTIFICACAO),
    Coluna("modelo", "Modelo", "texto", 8, IDENTIFICACAO),
    Coluna("tipo", "Entrada/Saída", "texto", 13, IDENTIFICACAO),
    Coluna("numero_documento", "Número", "texto", 12, IDENTIFICACAO),
    Coluna("serie", "Série", "texto", 8, IDENTIFICACAO),
    Coluna("emissao", "Emissão", "data", 12, IDENTIFICACAO),
    Coluna("cfop", "CFOP", "texto", 8, IDENTIFICACAO),
    Coluna("consumidor_final", "Consumidor Final", "texto", 15, IDENTIFICACAO),
    Coluna("protocolo", "Situação (cStat)", "texto", 14, IDENTIFICACAO),
    Coluna("arquivo", "Arquivo de Origem", "texto", 40, IDENTIFICACAO),

    Coluna("emitente", "CNPJ do Emitente", "texto", 20, PARTES),
    Coluna("emitente_nome", "Emitente", "texto", 34, PARTES),
    Coluna("destinatario", "CNPJ/CPF do Destinatário", "texto", 20, PARTES),
    Coluna("destinatario_nome", "Destinatário", "texto", 34, PARTES),

    Coluna("numero_item", "Número do Item", "numero_inteiro", 10, PRODUTO),
    Coluna("codigo", "Código", "texto", 16, PRODUTO),
    Coluna("gtin", "GTIN", "texto", 16, PRODUTO),
    Coluna("descricao", "Descrição", "texto", 44, PRODUTO),
    Coluna("ncm", "NCM", "texto", 11, PRODUTO),
    Coluna("cest", "CEST", "texto", 10, PRODUTO),
    Coluna("unidade", "Unidade", "texto", 9, PRODUTO),
    Coluna("quantidade", "Quantidade", "quantidade", 13, PRODUTO),
    Coluna("valor", "Valor do Item", "numero", 14, PRODUTO),

    Coluna("desconto", "Desconto", "numero", 13, DESCONTOS),
    Coluna("frete", "Frete", "numero", 13, DESCONTOS),
    Coluna("seguro", "Seguro", "numero", 13, DESCONTOS),
    Coluna("outras", "Outras Despesas", "numero", 14, DESCONTOS),
    Coluna("base_do_item", "Valor de Confronto", "numero", 15, DESCONTOS),

    Coluna("cst_icms", "CST/CSOSN", "texto", 11, ICMS),
    Coluna("bc_icms", "Base de Cálculo", "numero", 14, ICMS),
    Coluna("aliq_icms", "Alíquota", "numero", 10, ICMS),
    Coluna("valor_icms", "Valor", "numero", 13, ICMS),
    Coluna("reducao_declarada", "Redução da Base (%)", "numero", 14, ICMS),

    Coluna("bc_st", "Base da ST", "numero", 14, ST),
    Coluna("aliq_st", "Alíquota da ST", "numero", 12, ST),
    Coluna("valor_st", "Valor da ST", "numero", 13, ST),
    Coluna("fcp_st", "FCP da ST", "numero", 12, ST),
    Coluna("bc_st_retido", "Base da ST Retida", "numero", 15, ST),
    Coluna("retido_informado", "ST Retida Informada", "numero", 16, ST),
    Coluna("bc_efetiva", "Base Efetiva", "numero", 14, ST),
    Coluna("aliquota_efetiva", "Alíquota Efetiva", "numero", 13, ST),
    Coluna("icms_efetivo", "ICMS Efetivo", "numero", 13, ST),

    Coluna("cst_pis", "CST do PIS", "texto", 10, PISCOFINS),
    Coluna("bc_pis", "Base do PIS", "numero", 14, PISCOFINS),
    Coluna("aliq_pis", "Alíquota do PIS", "numero", 12, PISCOFINS),
    Coluna("valor_pis", "Valor do PIS", "numero", 13, PISCOFINS),
    Coluna("cst_cofins", "CST da COFINS", "texto", 12, PISCOFINS),
    Coluna("bc_cofins", "Base da COFINS", "numero", 14, PISCOFINS),
    Coluna("aliq_cofins", "Alíquota da COFINS", "numero", 13, PISCOFINS),
    Coluna("valor_cofins", "Valor da COFINS", "numero", 14, PISCOFINS),

    Coluna("cst_ipi", "CST do IPI", "texto", 10, IPI_ISSQN),
    Coluna("bc_ipi", "Base do IPI", "numero", 13, IPI_ISSQN),
    Coluna("aliq_ipi", "Alíquota do IPI", "numero", 12, IPI_ISSQN),
    Coluna("valor_ipi", "Valor do IPI", "numero", 13, IPI_ISSQN),
    Coluna("issqn_deducao", "Dedução do ISSQN", "numero", 15, IPI_ISSQN),
    Coluna("issqn_desconto_incondicional", "Desc. Incondicional (ISSQN)", "numero", 18, IPI_ISSQN),
    Coluna("issqn_desconto_condicional", "Desc. Condicional (ISSQN)", "numero", 18, IPI_ISSQN),
)

BLOCOS = (IDENTIFICACAO, PARTES, PRODUTO, DESCONTOS, ICMS, ST, PISCOFINS, IPI_ISSQN)

# o que cada atalho marca. Identificação e produto entram em todos: planilha de
# item sem saber de que nota ele é não serve para conferir nada
_BASE = (IDENTIFICACAO, PARTES, PRODUTO)
ATALHOS: dict[str, tuple[str, ...]] = {
    "icms": (*_BASE, DESCONTOS, ICMS, ST),
    "piscofins": (*_BASE, DESCONTOS, PISCOFINS),
    "descontos": (*_BASE, DESCONTOS),
    "tudo": BLOCOS,
}

POR_CAMPO = {c.campo: c for c in CAMPOS}


def campos_do_bloco(bloco: str) -> tuple[str, ...]:
    return tuple(c.campo for c in CAMPOS if c.bloco == bloco)


def campos_do_atalho(atalho: str) -> tuple[str, ...]:
    blocos = ATALHOS.get(atalho, BLOCOS)
    return tuple(c.campo for c in CAMPOS if c.bloco in blocos)


def colunas_escolhidas(escolha: frozenset[str] | None) -> tuple[Coluna, ...]:
    """As colunas da planilha, na ordem do catálogo.

    Sem escolha, saem todas — é o que uma extração sem opinião deve entregar.
    Campo que não existe é ignorado em silêncio de propósito: a tela manda o
    que o catálogo dela conhece, e uma coluna a menos na planilha é melhor do
    que uma rodada que falha por causa de um nome velho guardado no navegador.
    """
    if not escolha:
        return CAMPOS
    return tuple(c for c in CAMPOS if c.campo in escolha) or CAMPOS


def gerar_itens_do_xml(parquet: str, destino: str, modelos=None, classificacoes=None,
                       formato: str = "xlsx") -> int:
    """A planilha dos itens.

    `classificacoes` são os **campos** escolhidos — o canal genérico de recorte
    das planilhas, aqui usado para escolher coluna em vez de linha. `modelos`
    continua sendo o modelo do documento (55, 65, 59), e recorta linha.
    """
    return gerar(parquet, destino, colunas_escolhidas(classificacoes), "Itens do XML",
                 modelos=modelos, formato=formato)

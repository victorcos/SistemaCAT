"""As planilhas do razão: a Ficha 3 inteira e o resumo por ficha.

A ficha é a lista grande — uma linha por lançamento, e numa base real são
dezenas de milhões. É a que se baixa em CSV. O resumo por ficha é o que se
abre no Excel para achar onde está o ressarcimento e o que pede atenção.

## A Ficha 3 sai no leiaute do papel de trabalho

Decisão do Victor, 18/09/2026: a planilha da Ficha 3 segue o desenho do papel
de trabalho da CAT 42 — faixas por bloco (Dados Gerais, Entradas, Saídas, Valor
de Confronto, Saldo, Apuração, Inconsistências) e o **número do campo no
leiaute** debaixo de cada título, de (1) a (27). Quem confere a nossa entrega
contra a de outro escritório compara coluna com coluna, sem tradução no meio.

O que muda em relação ao papel de trabalho, e por quê:

* as colunas (15) a (19) levam o **ICMS suportado baixado** na saída, por
  enquadramento — não o valor da venda. É desse valor que o confronto de (20)
  ou (21) é subtraído para dar o ressarcimento ou o complemento;
* a coluna "Alíquota do ICMS" dos Dados Gerais é a **da operação**, como o
  documento a traz — e no CST 60, que não destaca nada, a que o emitente informa
  como efetiva. A **do confronto** é outra coisa, é a interna da mercadoria, e
  por isso fica no bloco do confronto, ao lado da redução de base;
* acrescentamos **CST e origem do dado**: é o que permite refazer a conta da
  linha sem abrir outro arquivo;
* as **inconsistências** são as nossas, marcadas por linha em vez de por ficha;
* não temos **alíquota do ICMS ST** nem **MVA do NCM** por linha, e coluna vazia
  em planilha de conferência custa mais do que ajuda: ficam de fora;
* as duas últimas colunas — "Tirar da Ficha" e "Motivo da Correção" — saem
  **vazias de propósito**: são o espaço da correção à mão. Quem corrige edita a
  célula do valor errado, escreve o motivo ao lado e sobe o arquivo de volta;
  `planilhas/correcoes_da_planilha.py` compara com este mesmo parquet e devolve
  o que mudou, antes de gravar.

A derivação é feita em SQL sobre o parquet, num arquivo de rascunho, e só
depois a planilha é escrita — assim o xlsx e o CSV saem das mesmas colunas, e
a Ficha 3 de milhões de linhas continua saindo com memória constante.
"""

from __future__ import annotations

import os

import duckdb
import pyarrow.parquet as pq

from cat.infraestrutura.planilhas.conferencia import (
    Coluna,
    _literal,
    _pasta_de_rascunho,
    gerar,
)

# ---------------------------------------------------------------------------
# a Ficha 3 no leiaute do papel de trabalho
# ---------------------------------------------------------------------------
GERAIS = "Dados Gerais"
ENTRADAS = "Entradas"
SAIDAS = "Saídas"
CONFRONTO = "Valor de Confronto"
SALDO = "Saldo"
APURACAO = "Apuração"
INCONSISTENCIAS = "Inconsistências"
CORRECAO = "Correção à Mão"

COLUNAS_FICHA3 = (
    Coluna("periodo", "Período", "data", 11, GERAIS),
    Coluna("cnpj", "CNPJ do Estabelecimento", "texto", 20, GERAIS),
    Coluna("codigo", "Código da Mercadoria", "texto", 16, GERAIS),
    Coluna("codigo_original", "Código Original", "texto", 16, GERAIS),
    Coluna("descricao", "Descrição", "texto", 40, GERAIS),
    Coluna("ncm", "NCM", "texto", 11, GERAIS),
    Coluna("unidade_estoque", "Unidade de Medida", "texto", 10, GERAIS),
    Coluna("unidade_origem", "Unidade de Medida (NF-e)", "texto", 11, GERAIS),
    Coluna("aliquota_documento", "Alíquota do ICMS", "quantidade", 10, GERAIS),
    Coluna("numero", "Número da Ordem", "numero_inteiro", 9, GERAIS, "1"),
    Coluna("data", "Data", "data", 11, GERAIS, "2"),
    Coluna("chave", "Chave", "texto", 46, GERAIS, "3"),
    Coluna("serie_ecf", "Número de Série de Fabricação do ECF", "texto", 12, GERAIS, "4"),
    Coluna("tipo", "Tipo 0 - Entrada 1 - Saída", "texto", 10, GERAIS, "5"),
    Coluna("serie", "Série do Documento", "texto", 9, GERAIS, "6"),
    Coluna("numero_documento", "Número do Documento", "texto", 13, GERAIS, "7"),
    Coluna("participante", "Código do Remetente ou Destinatário", "texto", 18, GERAIS, "8"),
    Coluna("cfop", "CFOP", "texto", 8, GERAIS, "9"),
    Coluna("numero_item", "Número do Item no Documento XML", "numero_inteiro", 10, GERAIS, "10"),
    # o leiaute chama de VL_ITEM, mas o que entra na conta é a base do ICMS da
    # operação — o título diz as duas coisas para ninguém somar errado
    Coluna("valor_item", "VL_ITEM (base de cálculo do ICMS)", "numero", 16, GERAIS),
    Coluna("cst_icms", "CST", "texto", 7, GERAIS),
    Coluna("origem", "Origem do Dado", "texto", 11, GERAIS),

    Coluna("qtd_entrada", "Quantidade (Entrada)", "quantidade", 12, ENTRADAS, "11"),
    Coluna("suportado_entrada",
           "Valor Total do ICMS Suportado na Retenção ou Antecipação por Substituição Tributária",
           "numero", 17, ENTRADAS, "12"),

    Coluna("cod_legal", "COD_LEGAL", "numero_inteiro", 10, SAIDAS),
    Coluna("qtd_saida", "Quantidade (Saída)", "quantidade", 12, SAIDAS, "13"),
    Coluna("suportado_unitario", "Valor Unitário do ICMS Suportado", "numero", 15, SAIDAS, "14"),
    Coluna("saida_enq1", "Saída a Consumidor ou Usuário Final - Código Enquadramento 1",
           "numero", 15, SAIDAS, "15"),
    Coluna("saida_enq2", "Fato Gerador Não Realizado - Código Enquadramento 2",
           "numero", 15, SAIDAS, "16"),
    Coluna("saida_enq3", "Saída ou Saída Subsequente com Isenção ou Não Incidência - Código Enquadramento 3",
           "numero", 15, SAIDAS, "17"),
    Coluna("saida_enq4", "Saída para Outro Estado - Código Enquadramento 4",
           "numero", 15, SAIDAS, "18"),
    Coluna("saida_enq0", "Saída para Comercialização Subsequente (Demais Saídas)",
           "numero", 15, SAIDAS, "19"),

    Coluna("confronto_saida", "ICMS Efetivo na Saída a Consumidor ou Usuário Final",
           "numero", 15, CONFRONTO, "20"),
    Coluna("confronto_entrada", "ICMS Efetivo da Entrada nas Demais Hipóteses",
           "numero", 15, CONFRONTO, "21"),
    Coluna("aliquota", "Alíquota do Confronto (%)", "quantidade", 12, CONFRONTO),
    Coluna("reducao_base", "Redução de Base (%)", "quantidade", 12, CONFRONTO),

    Coluna("saldo_quantidade", "Quantidade", "quantidade", 13, SALDO, "22"),
    Coluna("saldo_unitario", "Valor Unitário do Saldo", "quantidade", 14, SALDO, "23"),
    Coluna("saldo_valor", "Valor Total do Saldo", "numero", 14, SALDO, "24"),

    Coluna("ressarcimento", "Valor do Ressarcimento", "numero", 14, APURACAO, "25"),
    Coluna("complemento", "Valor do Complemento", "numero", 14, APURACAO, "26"),
    Coluna("credito_operacao_propria", "ICMS - Crédito da Operação Própria (artigo 271)",
           "numero", 15, APURACAO, "27"),

    Coluna("entrada_sem_suportado", "Entrada sem ICMS Suportado", "texto", 12, INCONSISTENCIAS),
    Coluna("devolucao_sem_suportado", "Devolução sem ICMS Suportado", "texto", 12, INCONSISTENCIAS),
    Coluna("ressarcimento_sem_confronto", "Ressarcimento sem Valor de Confronto",
           "texto", 12, INCONSISTENCIAS),
    Coluna("saldo_negativo", "Saldo Parcial Negativo", "texto", 12, INCONSISTENCIAS),
    Coluna("enquadramento_indefinido", "Enquadramento Indefinido", "texto", 12, INCONSISTENCIAS),
    Coluna("unidade_sem_fator", "Unidade sem Fator de Conversão", "texto", 12, INCONSISTENCIAS),
    Coluna("ficha_retirada", "Ficha Retirada do Total", "texto", 12, INCONSISTENCIAS),
    Coluna("corrigida", "Corrigida à Mão", "texto", 12, INCONSISTENCIAS),

    # as duas colunas que saem vazias de propósito: são as que a pessoa
    # preenche para devolver a planilha corrigida
    Coluna("tirar_da_ficha", "Tirar da Ficha (sim/não)", "texto", 14, CORRECAO),
    Coluna("motivo_da_correcao", "Motivo da Correção", "texto", 44, CORRECAO),
)

# como cada coluna do leiaute sai do parquet da ficha. O que não existir no
# arquivo — rodada antiga, coluna que ainda não havia — vira nulo, e a planilha
# sai assim mesmo: melhor a coluna vazia do que a etapa recusando o download.
DERIVACAO = {
    "periodo": "date_trunc('month', data)::DATE",
    "codigo_original": "coalesce(codigo_original, codigo)",
    "serie_ecf": "NULL::VARCHAR",
    "tipo": "CASE WHEN especie = 'entrada' THEN '0' ELSE '1' END",
    "qtd_entrada": "CASE WHEN especie = 'entrada' THEN abs(quantidade) END",
    "suportado_entrada": "CASE WHEN especie = 'entrada' THEN icms_suportado END",
    "cod_legal": "enquadramento",
    "qtd_saida": "CASE WHEN especie = 'saida' THEN abs(quantidade) END",
    "suportado_unitario": "CASE WHEN especie = 'saida' THEN valor_unitario_usado END",
    # (15) a (19) não levam o valor da saída: levam o **ICMS suportado que sai
    # da ficha** — quantidade vezes o unitário do saldo anterior —, na coluna do
    # enquadramento. É contra esse valor que o confronto de (20)/(21) é feito, e
    # a diferença vira o ressarcimento (25) ou o complemento (26)
    "saida_enq1": "CASE WHEN especie = 'saida' AND enquadramento = 1 THEN abs(icms_suportado) END",
    "saida_enq2": "CASE WHEN especie = 'saida' AND enquadramento = 2 THEN abs(icms_suportado) END",
    "saida_enq3": "CASE WHEN especie = 'saida' AND enquadramento = 3 THEN abs(icms_suportado) END",
    "saida_enq4": "CASE WHEN especie = 'saida' AND enquadramento = 4 THEN abs(icms_suportado) END",
    "saida_enq0": "CASE WHEN especie = 'saida' AND enquadramento = 0 THEN abs(icms_suportado) END",
    # o leiaute separa o confronto pela coluna: 1 e 3 olham a saída, 2 e 4 a entrada
    "confronto_saida": "CASE WHEN enquadramento IN (1, 3) THEN icms_efetivo END",
    "confronto_entrada": "CASE WHEN enquadramento IN (2, 4) THEN icms_efetivo END",
    "entrada_sem_suportado":
        "especie = 'entrada' AND NOT devolucao AND coalesce(icms_suportado, 0) = 0",
    "devolucao_sem_suportado": "devolucao AND coalesce(icms_suportado, 0) = 0",
    "ressarcimento_sem_confronto": "ressarcimento > 0 AND icms_efetivo IS NULL",
    "saldo_negativo": "saldo_quantidade < 0",
    # vazias na geração: é o que a pessoa escreve para devolver a planilha
    # corrigida, e o que volta é conferido em `planilhas/correcoes_da_planilha.py`
    "tirar_da_ficha": "NULL::VARCHAR",
    "motivo_da_correcao": "NULL::VARCHAR",
}


def _derivado(parquet: str, destino: str) -> str:
    """Escreve o parquet de rascunho com as colunas do leiaute e devolve o caminho."""
    tem = {c.name for c in pq.read_schema(parquet)}
    partes = []
    for coluna in COLUNAS_FICHA3:
        expressao = DERIVACAO.get(coluna.campo, f'"{coluna.campo}"')
        if coluna.campo not in DERIVACAO and coluna.campo not in tem:
            expressao = "NULL"
        partes.append(f'{expressao} AS "{coluna.campo}"')
    rascunho = os.path.join(_pasta_de_rascunho(destino), "ficha3_leiaute.parquet")
    con = duckdb.connect()
    try:
        con.execute("SET threads TO 4")
        con.execute(f"SET temp_directory = {_literal(os.path.dirname(rascunho))}")
        con.execute(f"COPY (SELECT {', '.join(partes)} FROM read_parquet({_literal(parquet)})) "
                    f"TO {_literal(rascunho)} (FORMAT parquet)")
    finally:
        con.close()
    return rascunho


COLUNAS_FICHAS = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("uf", "UF", "texto", 5),
    Coluna("codigo", "Código da mercadoria", "texto", 16),
    Coluna("descricao", "Descrição (0200)", "texto", 40),
    Coluna("linhas", "Linhas", "numero_inteiro", 8),
    Coluna("abertura_quantidade", "Abertura (quantidade)", "quantidade", 14),
    Coluna("abertura_sem_valor", "Abertura sem ICMS suportado", "texto", 12),
    Coluna("entradas", "Entradas", "quantidade", 14),
    Coluna("saidas", "Saídas", "quantidade", 14),
    Coluna("saldo_quantidade", "Saldo final (quantidade)", "quantidade", 14),
    Coluna("saldo_valor", "Saldo final (ICMS suportado)", "numero", 16),
    Coluna("ressarcimento", "Ressarcimento", "numero", 14),
    Coluna("complemento", "Complemento", "numero", 14),
    Coluna("ficou_negativo", "Estoque ficou negativo", "texto", 12),
    Coluna("retirada", "Retirada do total", "texto", 10),
    Coluna("abertura_por_saldo_negativo", "Abertura para cobrir estoque negativo", "quantidade", 14),
    Coluna("saidas_com_reducao", "Saídas com base reduzida", "numero_inteiro", 12),
    Coluna("saidas_sem_aliquota", "Saídas sem alíquota", "numero_inteiro", 10),
    Coluna("saidas_indefinidas", "Saídas indefinidas", "numero_inteiro", 10),
    Coluna("linhas_sem_fator", "Linhas com unidade sem fator", "numero_inteiro", 10),
    Coluna("inventarios_conferidos", "Inventários conferidos", "numero_inteiro", 10),
    Coluna("inventarios_divergentes", "Inventários divergentes", "numero_inteiro", 10),
    Coluna("maior_diferenca_inventario", "Maior diferença com o inventário", "quantidade", 14),
    Coluna("suspeita_de_unidade", "Suspeita de unidade", "texto", 10),
)

COLUNAS_CONFERENCIA = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    Coluna("codigo", "Código da mercadoria", "texto", 16),
    Coluna("data_inventario", "Data do inventário", "data", 12),
    Coluna("saldo_ficha", "Saldo da ficha", "quantidade", 14),
    Coluna("inventario", "Inventário (bloco H)", "quantidade", 14),
    Coluna("diferenca", "Diferença", "quantidade", 14),
    Coluna("situacao", "Situação", "texto", 16),
)


def gerar_ficha3(parquet: str, destino: str, modelos=None, classificacoes=None,
                 formato: str = "xlsx") -> int:
    rascunho = _derivado(parquet, destino)
    try:
        return gerar(rascunho, destino, COLUNAS_FICHA3, "Ficha 3", formato=formato)
    finally:
        if os.path.isfile(rascunho):
            os.remove(rascunho)


def gerar_fichas(parquet: str, destino: str, modelos=None, classificacoes=None,
                 formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_FICHAS, "Fichas", formato=formato)


def gerar_conferencia(parquet: str, destino: str, modelos=None, classificacoes=None,
                      formato: str = "xlsx") -> int:
    return gerar(parquet, destino, COLUNAS_CONFERENCIA, "Conferência com inventário", formato=formato)

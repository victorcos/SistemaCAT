"""A planilha do de-para: a entrada num bloco, a saída no outro.

O relatório anterior era uma linha por par, com origem e destino misturados às
marcas de suspeita e sem dizer qual dos dois lados tinha entrado em estoque.
Pior: código solto não aparecia — só havia linha onde havia par —, então para
saber o que faltava decidir era preciso cruzar duas listas à mão.

Aqui o cabeçalho tem duas faixas. **Entrada** é o código por onde o estoque
entrou; **Saída** é o código por onde ele saiu. Quando um dos lados não tem
par, o bloco daquele lado vem vazio, e a coluna Situação diz qual ponta é.
Ordenar por Situação separa as três listas; filtrar por ela dá cada uma.

As colunas de Como casou ficam juntas no fim, depois dos dois lados: elas
descrevem a ligação, não o produto, e no meio da linha era o que mais
confundia.
"""

from __future__ import annotations

from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

# os nomes das faixas são curtos de propósito: no CSV não há faixa, e o sistema
# prefixa o bloco ao título repetido ("Entrada - Código"). Faixa comprida virava
# um cabeçalho ilegível de 60 caracteres por coluna
ENTRADA = "Entrada"
SAIDA = "Saída"
LIGACAO = "Como se ligaram"

COLUNAS_DEPARA = (
    Coluna("cnpj", "CNPJ do estabelecimento", "texto", 20),
    # a primeira coisa que se olha: esta linha é um par, ou é uma ponta solta?
    Coluna("casamento", "Situação", "texto", 20),
    Coluna("codigo_entrada", "Código", "texto", 18, bloco=ENTRADA),
    Coluna("descricao_entrada", "Descrição", "texto", 40, bloco=ENTRADA),
    Coluna("ncm_entrada", "NCM", "texto", 11, bloco=ENTRADA),
    Coluna("quantidade_entrada", "Qtde que entrou", "quantidade", 15, bloco=ENTRADA),
    Coluna("estoque_entrada", "Estoque inicial", "quantidade", 14, bloco=ENTRADA),
    Coluna("codigo_saida", "Código", "texto", 18, bloco=SAIDA),
    Coluna("descricao_saida", "Descrição", "texto", 40, bloco=SAIDA),
    Coluna("ncm_saida", "NCM", "texto", 11, bloco=SAIDA),
    Coluna("quantidade_saida", "Qtde que saiu", "quantidade", 14, bloco=SAIDA),
    # quantidade da saída × fator = quantidade na ficha da entrada
    Coluna("fator", "Fator", "quantidade", 10, bloco=LIGACAO),
    # o que o razão faz: a saída de um código vai para a ficha deste. Os dois
    # blocos dizem quem é quem na movimentação; esta coluna diz quem recebe
    Coluna("ficha_do_codigo", "Lançado na ficha de", "texto", 19, bloco=LIGACAO),
    Coluna("como_casou", "Prova", "texto", 26, bloco=LIGACAO),
    Coluna("confianca", "Confiança", "texto", 11, bloco=LIGACAO),
    Coluna("situacao_do_par", "Decisão", "texto", 12, bloco=LIGACAO),
    # vale pela prova, sem ninguém decidir: é o que entra no razão calado
    Coluna("vale_sozinho", "Vale sozinho", "texto", 13, bloco=LIGACAO),
    Coluna("decidido_por", "Decidido por", "texto", 22, bloco=LIGACAO),
    Coluna("decidido_em", "Decidido em", "texto", 13, bloco=LIGACAO),
    Coluna("explicacao", "Explicação", "texto", 48, bloco=LIGACAO),
    Coluna("travas", "Travas", "texto", 38, bloco=LIGACAO),
    Coluna("avisos", "Avisos", "texto", 38, bloco=LIGACAO),
)


def gerar_depara(parquet: str, destino: str,
                 modelos: frozenset[str] | None = None,
                 classificacoes: frozenset[str] | None = None,
                 formato: str = "xlsx") -> int:
    """`classificacoes`, aqui, são as situações: casado, e as duas pontas soltas."""
    return gerar(parquet, destino, COLUNAS_DEPARA, "De-para",
                 modelos=modelos, classificacoes=classificacoes,
                 formato=formato, campo_da_classificacao="casamento")

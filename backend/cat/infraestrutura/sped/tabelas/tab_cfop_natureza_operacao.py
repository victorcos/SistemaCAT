"""A natureza da operação de saída, e o faturamento que vem junto.

Duas colunas do **047** que não existem no arquivo: o SPED tem o CFOP, e o MA
escreve ao lado dele "Venda", "Devolução de compra", "Transferência",
"Remessa", "Lançamento de valor" ou "Outras saídas/prestações" — e, quando a
natureza é Venda, escreve também "Faturamento" numa coluna própria.

Não confundir com `tab_cfop_natureza_credito`, que é outra coisa: aquela é a
natureza da **base de cálculo do crédito** (Tabela 4.3.7), só vale para entrada
e sai como "01 - Aquisição de bens para revenda". Esta classifica a
**operação**, vale para saída, e sai como uma palavra só.

## De onde veio

Do gabarito do 047 da DMINAS — 7.784.121 linhas, 57 competências, conferido em
29/09/2026. Aquela base usa 21 CFOP, e todos os 21 estão em `CONFIRMADAS`.

## Por que a tabela existe, se a descrição quase basta

Porque **quase** não basta. Vinte dos 21 CFOP dariam a natureza certa se a
gente apenas olhasse a primeira palavra da descrição — "Venda de…" vira Venda,
"Remessa de…" vira Remessa. O que sobra é o **5209**:

    5209  Devol de mercadoria recebida em transferência para comercialização
          → o MA classifica como **Transferência**, não como Devolução.

Ou seja: o MA classifica pela natureza da operação **original**, não pela do
retorno. Uma regra que lê a descrição erraria essa — e erraria calada. Por isso
a tabela vem primeiro e a descrição só entra quando o CFOP não está nela.

O palpite pela descrição fica marcado como palpite no nome da função, e devolve
branco quando não reconhece o começo: natureza errada com cara de certa é pior
que coluna vazia.
"""

from __future__ import annotations

VENDA = "Venda"
TRANSFERENCIA = "Transferência"
DEVOLUCAO_DE_COMPRA = "Devolução de compra"
REMESSA = "Remessa"
LANCAMENTO_DE_VALOR = "Lançamento de valor"
OUTRAS_SAIDAS = "Outras saídas/prestações"

# o que o MA escreve quando a natureza é Venda. Coluna própria, valor único
FATURAMENTO = "Faturamento"

# CFOP → natureza, como o gabarito do 047 escreveu. O número ao lado é em
# quantas linhas daquela base o par apareceu — serve para saber o que é regra
# vista milhões de vezes e o que é regra vista uma vez
CONFIRMADAS: dict[str, str] = {
    "5102": VENDA,                  # 2.867.213
    "5152": TRANSFERENCIA,          #       207
    "5202": DEVOLUCAO_DE_COMPRA,    #     1.037
    "5209": TRANSFERENCIA,          #       184 — a exceção; ver o topo
    "5403": VENDA,                  #         1
    "5405": VENDA,                  # 4.820.164
    "5409": TRANSFERENCIA,          #       667
    "5411": DEVOLUCAO_DE_COMPRA,    #     3.547
    "5901": REMESSA,                #         2
    "5910": REMESSA,                #       195
    "5915": REMESSA,                #         3
    "5924": REMESSA,                #        30
    "5927": LANCAMENTO_DE_VALOR,    #    32.354
    "5949": OUTRAS_SAIDAS,          #    53.683
    "6102": VENDA,                  #         1
    "6202": DEVOLUCAO_DE_COMPRA,    #       230
    "6403": VENDA,                  #        17
    "6404": VENDA,                  #       126
    "6411": DEVOLUCAO_DE_COMPRA,    #       472
    "6901": REMESSA,                #         8
    "6949": OUTRAS_SAIDAS,          #        29
}

# o começo da descrição do CFOP e a natureza que ele sugere. Cobre as duas
# grafias que o MA usa — a abreviada da Gestão ("Transf mercad…", "Remes de…")
# e a por extenso do 047 ("Transferência de…", "Remessa de…")
_PELO_COMECO: tuple[tuple[str, str], ...] = (
    ("venda", VENDA),
    ("transf", TRANSFERENCIA),
    ("devol", DEVOLUCAO_DE_COMPRA),
    ("remes", REMESSA),
    ("lanç", LANCAMENTO_DE_VALOR),
    ("lanc", LANCAMENTO_DE_VALOR),
    ("outra", OUTRAS_SAIDAS),
)


def natureza(cfop: str, descricao_do_cfop: str = "") -> str:
    """A natureza da operação. Branco quando não se sabe.

    A tabela manda; a descrição é o palpite de quem não está nela. Ver o topo
    do módulo para por que essa ordem importa.
    """
    codigo = (cfop or "").strip()
    if not codigo:
        return ""
    if (conhecida := CONFIRMADAS.get(codigo)) is not None:
        return conhecida
    return _palpite_pela_descricao(descricao_do_cfop)


def _palpite_pela_descricao(descricao_do_cfop: str) -> str:
    comeco = (descricao_do_cfop or "").strip().lower()
    for prefixo, qual in _PELO_COMECO:
        if comeco.startswith(prefixo):
            return qual
    return ""


def faturamento(natureza_da_operacao: str) -> str:
    """"Faturamento" quando a operação é venda; branco no resto.

    No gabarito, a coluna veio preenchida em 100% das linhas de natureza Venda
    e em nenhuma das demais — 7.687.522 contra 0, sem uma exceção.
    """
    return FATURAMENTO if natureza_da_operacao == VENDA else ""

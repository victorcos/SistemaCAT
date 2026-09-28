"""A planilha da extração de registro: colunas que mudam com o alvo.

É a única planilha desta casa cujas colunas não são fixas — todas as outras
descrevem uma coisa só (a conferência, a Ficha 3, os quadros da Gestão), e aqui
o que sai depende do registro que a pessoa pediu: o C170 tem 38 campos, o C860
tem 6, e a hierarquia soma os do pai aos da folha.

Por isso as colunas nascem do leiaute (`sped/registros.py`) em vez de estarem
escritas aqui. O cabeçalho é o nome oficial do campo, tal como o SPED o chama —
quem confere está de olho no manual da EFD, não num apelido que inventamos.

**Tudo sai como texto**, de propósito. O SPED grava valor com vírgula decimal,
data como `ddmmaaaa` e código com zero à esquerda; converter aqui exigiria
saber o tipo de cada um dos 52 registros, e errar num só estragaria em silêncio
a coluna que o analista foi conferir. Quem precisa somar converte na planilha,
à vista.
"""

from __future__ import annotations

from cat.infraestrutura.analitico.registros_do_sped import (
    COLUNAS_DA_ORIGEM,
    colunas_do_alvo,
)
from cat.infraestrutura.planilhas.conferencia import Coluna, gerar

# a origem do arquivo, que vai em toda linha
ORIGEM = "Arquivo de origem"

TITULOS_DA_ORIGEM: dict[str, str] = {
    "arquivo": "Arquivo",
    "cnpj": "CNPJ",
    "empresa": "Empresa",
    "competencia": "Competência",
}

LARGURAS_DA_ORIGEM: dict[str, int] = {
    "arquivo": 34, "cnpj": 20, "empresa": 34, "competencia": 12,
}


def colunas_da_planilha(alvo: str) -> tuple[Coluna, ...]:
    """As colunas do alvo, já no formato da planilha.

    A faixa do cabeçalho separa a origem do arquivo dos campos de cada
    registro: numa hierarquia de três níveis são quatro blocos de colunas, e
    sem a faixa ninguém sabe onde um registro acaba e o outro começa.
    """
    saida: list[Coluna] = []
    for campo in colunas_do_alvo(alvo):
        if campo in TITULOS_DA_ORIGEM:
            saida.append(Coluna(campo, TITULOS_DA_ORIGEM[campo], "texto",
                                LARGURAS_DA_ORIGEM[campo], ORIGEM))
            continue
        registro, _, nome = campo.partition("_")
        # registro simples não tem prefixo: o bloco é o próprio registro pedido
        bloco = registro if nome else alvo
        saida.append(Coluna(campo, nome or campo, "texto", _largura(nome or campo), bloco))
    return tuple(saida)


def _largura(campo: str) -> int:
    """Largura pelo que o campo costuma carregar: chave tem 44, CST tem 2."""
    if campo.startswith("CHV"):
        return 46
    if campo.startswith(("DESCR", "NOME", "COMPL")):
        return 36
    if campo.startswith(("VL_", "QUANT", "ALIQ")):
        return 15
    if campo.startswith("DT_"):
        return 12
    if campo.startswith("CST") or campo == "REG":
        return 8
    return 16


def gerar_extracao(parquet: str, destino: str, modelos=None, classificacoes=None,
                   formato: str = "xlsx", alvo: str = "") -> int:
    """A planilha de um alvo. `alvo` decide as colunas, e por isso é exigido."""
    if not alvo:
        raise ValueError("a planilha da extração precisa saber de que alvo é.")
    return gerar(parquet, destino, colunas_da_planilha(alvo), _aba(alvo), formato=formato)


def _aba(alvo: str) -> str:
    """O nome da aba. O Excel recusa `+` e corta em 31 caracteres."""
    return alvo.replace("+", " ")[:31]


__all__ = ["COLUNAS_DA_ORIGEM", "colunas_da_planilha", "gerar_extracao"]

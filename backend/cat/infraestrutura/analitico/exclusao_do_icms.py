"""A tese do ICMS fora da base do PIS/COFINS — o Tema 69, item a item.

O que sai daqui é o relatório 903: uma linha por **item de nota fiscal**, com a
base como foi escriturada, a base sem o ICMS, a diferença de cada contribuição,
a Selic acumulada e o total a recuperar corrigido. Quarenta colunas, medidas
contra o relatório do MA e batendo 100% nas 138.358 linhas da DMINAS.

A mecânica da rodada — ler, gravar, somar, separar o que prescreveu — mora em
`exclusoes_por_item.py`, compartilhada com o 839 e o 933. Aqui fica só o que é
desta tese.

## Por que esta tese não usa o agregado

A outra tese desta etapa — as contribuições fora da própria base — parte do
agregado que a Gestão deixou: somas por competência, CST e CFOP, que voltam em
segundos. Esta **não pode**: o Tema 69 se apura no item, porque a base
recalculada se reconstrói do valor do item, do desconto, do rateio do frete e
do ICMS destacado. Agregado não tem item; tem soma de item. Quem soma primeiro
e exclui depois não consegue dizer quais notas **já** excluíram o ICMS — e é
justamente essa a linha que não pode entrar no pedido.

Ler os SPED custa cerca de um minuto por ano de arquivo nesta casa. É barato
perto de pedir restituição em duplicidade.

## O mês da restituição

A correção pela Selic cresce a cada mês que passa, então o número só existe com
uma data ao lado. `ate` é o mês em que se pretende restituir; sem ele, o mês de
`referencia` — que é hoje, para quem está montando o cálculo agora. O resumo
diz qual foi usado, e a planilha e a tela repetem: número corrigido sem a data
da correção é número que ninguém consegue conferir no mês seguinte.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from cat.infraestrutura.analitico.exclusoes_por_item import (
    Andamento,
    Grupo,
    Motor,
    Resumo,
    Total,
    competencia_de,
    mes_de,
    serializar,
)
from cat.infraestrutura.analitico.exclusoes_por_item import apurar as _apurar
from cat.infraestrutura.sped.exclusao_do_icms import (
    colunas_da_exclusao,
    exclusoes_do_icms,
)
from cat.infraestrutura.sped.tabelas.tab_selic import alcanca, ultimo_mes

__all__ = [
    "ARQUIVO_DA_EXCLUSAO_DO_ICMS", "REGISTRO", "TESE_ICMS_NA_BASE",
    "Andamento", "Grupo", "Resumo", "Total", "apurar",
    "avisar_se_a_selic_nao_alcanca", "competencia_de", "mes_de", "serializar",
]

ARQUIVO_DA_EXCLUSAO_DO_ICMS = "exclusao_do_icms.parquet"

# o nome da tese no parquet agregado das exclusões, ao lado das outras
TESE_ICMS_NA_BASE = "icms_na_base"

# de onde saem todas as linhas do 903: o item da nota fiscal
REGISTRO = "C170"


def apurar(contribuicoes: list[str], destino: str, ate: str = "",
           avisar: Callable[[Andamento], None] | None = None,
           deve_parar: Callable[[], bool] | None = None,
           referencia: date | None = None,
           mensal: dict[str, Decimal] | None = None) -> Resumo:
    """Escreve o 903 em parquet e devolve o resumo.

    `mensal` é a série da Selic — do banco, em produção. Ver
    `infraestrutura/selic`.
    """
    motor = Motor(
        nome="icms", tese=TESE_ICMS_NA_BASE, arquivo=ARQUIVO_DA_EXCLUSAO_DO_ICMS,
        registro=REGISTRO, colunas=colunas_da_exclusao,
        ler=lambda caminho, codificacao, mes: exclusoes_do_icms(
            caminho, codificacao, mes, mensal=mensal),
    )
    return _apurar(motor, contribuicoes, destino, ate, avisar, deve_parar, referencia)


def avisar_se_a_selic_nao_alcanca(ate: str,
                                  mensal: dict[str, Decimal] | None = None) -> str:
    """O aviso que a tela dá **antes** de rodar uma hora à toa.

    Devolve vazio quando a série cobre o mês pedido. `mensal` é a série que
    será usada de verdade — a do banco, em produção; conferir outra aqui seria
    aprovar a rodada olhando para a série errada.
    """
    if alcanca(ate, mensal):
        return ""
    ultimo = ultimo_mes(mensal)
    onde = f"vai até {ultimo[5:]}/{ultimo[:4]}" if ultimo else "está vazia"
    return (f"A série da Selic {onde} e a correção foi pedida até "
            f"{ate[5:]}/{ate[:4]}. O Banco Central ainda não publicou esses "
            "meses, ou não deu para falar com ele: corrigir por série "
            "incompleta devolveria menos do que o devido.")

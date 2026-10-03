"""A tese do ISS fora da base do PIS/COFINS — o 933, por documento de serviço.

O relatório 933 do MA: uma linha por item de nota de serviço, com o ISS
rateado, a base sem ele, a diferença de cada contribuição, a Selic e o total a
recuperar. Trinta e duas colunas, conferidas 100% nas 33 linhas da empresa F.

A mecânica da rodada mora em `exclusoes_por_item.py`, compartilhada com o 903 e
o 839. O que é desta tese cabe em duas observações.

## Não tem CFOP

Nota de serviço não tem CFOP, então o grupo agregado vai sem a coluna — e não
com ela vazia. Vazio numa chave de agrupamento é um valor, e somaria coisas
diferentes no mesmo balde.

## O número que diz quanto da tese está faltando

O `VL_ISS` do registro A100 é facultativo. Quem não o preenche não perde o
valor — ele está na NFS-e, que este motor ainda não lê —, mas a linha sai sem
exclusão. `sem_iss` no resumo conta essas notas: é o tamanho do que a tese
ainda não alcança, e tem de estar visível na tela, não enterrado no log. Na
empresa F são 32 de 33.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from cat.infraestrutura.analitico.exclusoes_por_item import (
    Andamento,
    Motor,
    Resumo,
    serializar,
)
from cat.infraestrutura.analitico.exclusoes_por_item import apurar as _apurar
from cat.infraestrutura.sped.exclusao_do_iss import (
    colunas_da_exclusao_iss,
    exclusoes_do_iss,
)

ARQUIVO_DA_EXCLUSAO_DO_ISS = "exclusao_do_iss.parquet"

# o nome da tese no parquet agregado das exclusões, ao lado das outras
TESE_ISS_NA_BASE = "iss_na_base"

# de onde saem todas as linhas do 933: o item da nota de serviço
REGISTRO = "A170"


def apurar(contribuicoes: list[str], destino: str, ate: str = "",
           avisar: Callable[[Andamento], None] | None = None,
           deve_parar: Callable[[], bool] | None = None,
           referencia: date | None = None,
           mensal: dict[str, Decimal] | None = None) -> Resumo:
    """Escreve o 933 em parquet e devolve o resumo.

    `mensal` é a série da Selic — do banco, em produção.
    """
    motor = Motor(
        nome="iss", tese=TESE_ISS_NA_BASE, arquivo=ARQUIVO_DA_EXCLUSAO_DO_ISS,
        registro=REGISTRO, colunas=colunas_da_exclusao_iss, por_cfop=False,
        ler=lambda caminho, codificacao, mes: exclusoes_do_iss(
            caminho, codificacao, mes, mensal=mensal),
    )
    return _apurar(motor, contribuicoes, destino, ate, avisar, deve_parar, referencia)

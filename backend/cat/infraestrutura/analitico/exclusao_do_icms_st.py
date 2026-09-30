"""A tese do ICMS-ST fora da base do PIS/COFINS — o 839, item a item.

O relatório 839 do MA: uma linha por item de nota fiscal, com o ICMS-ST
**presumido**, a base sem ele, a diferença de cada contribuição, a Selic e o
total a recuperar. Quarenta e seis colunas, conferidas 100% nas 463.212 linhas
da DMINAS.

A mecânica da rodada mora em `exclusoes_por_item.py`, compartilhada com o 903 e
o 933. Aqui fica o que é desta tese — e o que é dela é a **alíquota**.

## De onde vem a alíquota, e por que ela entra por fora

O ICMS-ST não está escrito em lugar nenhum: a revenda com ST já retido tem CST
60, que por definição não destaca imposto. O MA reconstrói `base × alíquota`, e
a alíquota tem duas metades:

* **a regra**, que é lei e mora em `sped/tabelas/tab_aliquota_icms.py` —
  alíquota interna do estado, ou a Resolução 22/1989 do Senado na
  interestadual. Sozinha acerta 98,66% das linhas medidas;
* **a exceção por produto**, que é cadastro do cliente e mora no **banco**
  (`aliquota_de_item`) — cesta básica a 12%, supérfluo a 25%, isento a 0%,
  importado a 4%. São 556 pares na DMINAS.

A exceção entra aqui por parâmetro e nunca é lida daqui de dentro: quem sabe de
qual empresa é a rodada é a camada de cima, e código de item de um cliente não
tem sentido no de outro.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from cat.infraestrutura.analitico.exclusoes_por_item import (
    Andamento,
    Motor,
    Resumo,
)
from cat.infraestrutura.analitico.exclusoes_por_item import apurar as _apurar
from cat.infraestrutura.sped.exclusao_do_icms_st import (
    colunas_da_exclusao_st,
    exclusoes_do_icms_st,
)

ARQUIVO_DA_EXCLUSAO_DO_ICMS_ST = "exclusao_do_icms_st.parquet"

# o nome da tese no parquet agregado das exclusões, ao lado das outras
TESE_ICMS_ST_NA_BASE = "icms_st_na_base"

# de onde saem todas as linhas do 839: o item da nota fiscal
REGISTRO = "C170"


def apurar(contribuicoes: list[str], destino: str, ate: str = "",
           avisar: Callable[[Andamento], None] | None = None,
           deve_parar: Callable[[], bool] | None = None,
           referencia: date | None = None,
           mensal: dict[str, Decimal] | None = None,
           excecoes: dict[tuple[str, str, str, str], Decimal] | None = None) -> Resumo:
    """Escreve o 839 em parquet e devolve o resumo.

    `mensal` é a série da Selic (do banco) e `excecoes` a alíquota por produto
    que foge da regra do estado (também do banco).
    """
    motor = Motor(
        nome="icms_st", tese=TESE_ICMS_ST_NA_BASE,
        arquivo=ARQUIVO_DA_EXCLUSAO_DO_ICMS_ST, registro=REGISTRO,
        colunas=colunas_da_exclusao_st,
        ler=lambda caminho, codificacao, mes: exclusoes_do_icms_st(
            caminho, codificacao, mes, mensal=mensal, excecoes=excecoes),
    )
    return _apurar(motor, contribuicoes, destino, ate, avisar, deve_parar, referencia)

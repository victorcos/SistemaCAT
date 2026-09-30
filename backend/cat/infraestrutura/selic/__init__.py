"""A Selic que corrige o indébito, com o banco por memória.

Três peças, de fora para dentro:

- `bcb.py` fala com a série 4390 do SGS do Banco Central;
- `repositorio.py` lê e grava a tabela `selic_mensal`;
- `servico.py` decide **o que precisa ser buscado** — que é a parte que
  importa.

## Por que guardar

Taxa de mês fechado não muda. A de março de 2021 hoje é a mesma de daqui a dez
anos, e buscá-la de novo a cada rodada seria pagar rede para receber o que já
se sabe — e ficar refém de a API estar no ar num cálculo que vira pedido de
restituição. Guardando, a rodada só sai à rede pelos meses que faltam; quando
não falta nenhum, não sai.

## O que acontece quando a rede falha

Nada, se o banco já cobrir o mês da restituição — que é o caso normal depois da
primeira rodada. Se não cobrir, a etapa **recusa e diz o que falta**, em vez de
corrigir por série incompleta: número menor que o devido é o pior erro possível
aqui, porque ninguém confere um número que veio pequeno.
"""

from cat.infraestrutura.selic.servico import (
    SelicIndisponivel,
    acumulada,
    alcanca,
    serie,
)

__all__ = ["SelicIndisponivel", "acumulada", "alcanca", "serie"]

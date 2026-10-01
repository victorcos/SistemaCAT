"""O CFOP compõe receita? É o filtro comum das quatro exclusões da base.

As quatro teses — as próprias contribuições, o ICMS (903), o ICMS-ST (839) e o
ISS (933) — perguntam a mesma coisa antes de calcular qualquer coisa: **esta
operação é receita?** Imposto só sai da base de quem teve receita, e o que não é
venda nem devolução de venda não compõe receita.

Morava dentro de `sped/exclusao_do_icms.py`, de onde nasceu. Saiu em 01/10/2026,
quando a tese das contribuições passou a usá-lo: tese nenhuma deve importar
regra fiscal do módulo de outra, e uma regra que serve a quatro não é de uma.

## As duas respostas, e o que elas valem

**Faturamento** é venda. **Devolução de faturamento** é o estorno de uma venda —
e entra junto, com sinal próprio, porque desfaz receita que já foi tributada.
Vazio é tudo o mais: remessa para industrialização, bonificação, baixa de
estoque, transferência, aquisição. Nada disso é receita, e nada disso entra.

**O vazio custou R$ 215.706,22 de base para ser notado.** Até 01/10/2026 a tese
das contribuições não perguntava o CFOP — pegava toda saída com contribuição
apurada. Entravam remessa (5924, 5901, 6901), bonificação (5910) e baixa de
estoque (5927), e ficavam de fora as devoluções de venda (1411, 1202, 2411),
que são entrada e por isso caíam na regra do débito. O relatório 680 do MA, que
filtra por aqui, mostrou as duas pontas.

## De onde sai a resposta

De tabelas que já existiam: `tab_cfop_natureza_operacao` diz o que é venda, e a
natureza 12 de `tab_cfop_natureza_credito` diz o que é devolução de venda. Não
fez falta tabela nova — e é por isso que esta função é só a pergunta certa
feita a elas.
"""

from __future__ import annotations

from cat.infraestrutura.sped.tabelas import (
    tab_cfop_natureza_credito,
    tab_cfop_natureza_operacao,
)

# como o MA escreve a classificação na coluna "CFOP Faturamento". Copiado dele
# letra por letra: quem compara os dois relatórios compara texto
FATURAMENTO = "Faturamento"
DEVOLUCAO_DE_FATURAMENTO = "Devolução Faturamento"

# a natureza 12 da tabela 4.3.7: devolução de vendas
_DEVOLUCAO_DE_VENDA = "12"


def classificacao_do_cfop(cfop: str) -> str:
    """"Faturamento", "Devolução Faturamento", ou vazio para o que não é nem um.

    Vazio significa fora das teses de exclusão: elas são sobre a **receita**, e
    o que não é venda nem devolução de venda não compõe receita.
    """
    if tab_cfop_natureza_operacao.natureza(cfop, "") == tab_cfop_natureza_operacao.VENDA:
        return FATURAMENTO
    if tab_cfop_natureza_credito.codigo(cfop) == _DEVOLUCAO_DE_VENDA:
        return DEVOLUCAO_DE_FATURAMENTO
    return ""


def e_receita(cfop: str) -> bool:
    """Atalho para quem só quer saber se entra, e não qual das duas é."""
    return bool(classificacao_do_cfop(cfop))

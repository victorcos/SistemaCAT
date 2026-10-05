"""CFOP (C170/C100) -> código de Natureza da Base de Cálculo do Crédito
(Tabela 4.3.7, ver `tab_437.py`).

O layout C170 do EFD Contribuições NÃO tem campo NAT_BC_CRED nativo — essa
informação precisa ser derivada do CFOP da operação. Regra validada
campo a campo contra o arquivo de referência real "C100, C170, 0200 -
Documento e Itens - Nota Fiscal" (empresa 03, 43.497 linhas, out/2024): cruzando `Natureza Crédito` x `CFOP` x
`Tipo Operação`, a natureza do crédito segue o CFOP (não o TIPO_ITEM do
0200, como uma heurística anterior do projeto supunha — ver
`src/efd_entradas/entradas.py::_natureza_credito_por_tipo_item`, que não
bate com este relatório porque TIPO_ITEM é constante "99" em 100% das
linhas da amostra).

Toda SAÍDA (CFOP 5xxx/6xxx/7xxx) fica de fora deste mapa de propósito —
crédito de PIS/COFINS só se aplica a entradas (confirmado: 1.028/1.028
linhas de saída na amostra com Natureza Crédito vazia).

Entradas marcadas com # CONFIRMADO batem 1:1 com o arquivo de referência.
As demais seguem a mesma lógica (CFOP de compra p/comercialização->01,
p/industrialização ou uso/consumo->02, ativo imobilizado->10, devolução de
venda->12) mas não foram observadas na amostra.

Reconfirmado uma terceira vez em 30/09/2026, contra o gabarito do 037 da
empresa 05 (458.792 linhas, 57 competências): os CFOP já mapeados bateram todos, e
três novos entraram — 1113->01, 2122->02 e 1124->03, este último a primeira
natureza de **serviço** do mapa, com 157 linhas e nenhuma exceção.

E a mesma medida derrubou a segunda tentativa que havia aqui: **não existe
recurso ao TIPO_ITEM**. As 107 linhas em que o gabarito deixa a natureza vazia
são todas de CFOP que este mapa não conhece, e em 84 delas o tipo do item é
"00" — exatamente onde a regra antiga escrevia "01". Ver
`sped/entradas.py::_natureza_deduzida`.

Reconfirmado (81.150 linhas, mesma empresa, período 2020-2024) contra o
relatório "C190, C191, C195 - Consolidação e Detalhamento das NF-e -
Entradas - PIS-Cofins": todos os CFOPs já mapeados bateram 100% (nenhuma
exceção em nenhum dos 20 CFOPs distintos da amostra), e mais 2 CFOPs novos
foram confirmados nessa passada: 1652->01, 1653->02. O código "1122" tinha
sido mapeado como "01" numa leitura equivocada de crosstab na validação
anterior — corrigido para "02" (compra p/industrialização, condizente com
o texto oficial do CFOP), reconfirmado nesta passada.
"""

# Copiada do projeto Quebra de SPED em 22/09/2026, sem alteração de conteúdo.
# As marcas "# CONFIRMADO" indicam o que foi conferido contra arquivo de
# referência real — não as remova ao acrescentar entradas novas: elas são a
# diferença entre o que se sabe e o que se supõe.

from __future__ import annotations

# código de natureza (ver tab_437.TABELA) por CFOP de entrada
TABELA: dict[str, str] = {
    # Compra para comercialização (revenda) -> 01
    "1102": "01",  # CONFIRMADO
    "1121": "01",  # CONFIRMADO (MA, Gestão PIS/COFINS) — venda à ordem, já recebida do remetente
    "2121": "01",  # CONFIRMADO (MA, Gestão PIS/COFINS)
    "1113": "01",  # CONFIRMADO (MA, 037 da empresa 05) — consignação já recebida
    "1403": "01",  # CONFIRMADO
    "1652": "01",  # CONFIRMADO
    "2102": "01",  # CONFIRMADO
    "2403": "01",  # CONFIRMADO
    "3102": "01",

    # Compra para industrialização / uso ou consumo (insumo) -> 02
    "1101": "02",  # CONFIRMADO — compra p/indust ou prod rural (o bem vira insumo da produção própria)
    "1122": "02",  # CONFIRMADO
    "2122": "02",  # CONFIRMADO (MA, 037 da empresa 05) — o par interestadual do 1122
    "1401": "02",  # CONFIRMADO
    "1407": "02",  # CONFIRMADO
    "1556": "02",  # CONFIRMADO
    "1653": "02",  # CONFIRMADO
    "2101": "02",
    "2401": "02",
    "2407": "02",  # CONFIRMADO
    "2556": "02",  # CONFIRMADO
    "3556": "02",

    # Compra de bem para o ativo imobilizado (1551/2551) NÃO entra aqui.
    # O crédito de ativo imobilizado é escriturado no F120 (depreciação) e no
    # F130 (aquisição), não no C170 — confirmado contra a Gestão do MA: no
    # arquivo de referência a natureza 10 do M105 (R$ 57.149.071,52) vem
    # inteira do F130, e o MA deixa as linhas de C170 com CFOP 2551 de fora
    # dos quadros de crédito.

    # Industrialização feita por terceiro -> 03 (aquisição de serviço)
    "1124": "03",  # CONFIRMADO (MA, 037 da empresa 05) — 157 linhas, sem exceção

    # Devolução de venda (entrada) -> 12
    "1202": "12",  # CONFIRMADO
    "1411": "12",  # CONFIRMADO
    "2202": "12",
    "2411": "12",
}


def codigo(cfop: str) -> str:
    """Retorna o código de natureza de crédito (ex. "01") para o CFOP, ou "" se não mapeado."""
    return TABELA.get((cfop or "").strip(), "")


def cfop_faturamento(cfop: str) -> str:
    """"Devolução Faturamento" quando o CFOP é de devolução de venda (natureza 12), senão "".

    Confirmado contra a amostra real: as 201 linhas com "CFOP Faturamento"
    preenchido no relatório MA são exatamente as 201 linhas cujo CFOP
    resolve para natureza "12" nesta tabela — mesma regra, sem tabela extra.
    """
    return "Devolução Faturamento" if codigo(cfop) == "12" else ""

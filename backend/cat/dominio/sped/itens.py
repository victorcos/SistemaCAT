"""O que a EFD diz de cada mercadoria: cadastro, itens, analíticos e estoque.

É a matéria-prima do razão (Ficha 3). Quatro famílias de registro, e cada uma
foi conferida contra arquivo real desta casa antes de ser escrita aqui —
contagem de campos e posição, não o manual. Um campo deslocado aqui troca
quantidade por valor em milhões de linhas.

* **0200** — cadastro do item: código, descrição, código de barras, NCM, CEST,
  alíquota. É o que dá nome ao que se movimenta.
* **C170** — item de nota fiscal (filho do C100): quantidade, unidade, valor,
  CST, CFOP, base e valor do ICMS e do ICMS-ST. **Só existe nas entradas.**
  Em duas empresas reais, 27.448 C170 e nenhum com CFOP de saída: para NF-e
  de emissão própria a EFD dispensa o item, e o detalhe fica no XML.
* **C810** — item de cupom SAT (filho do C800). Leiaute do manual, porque
  em 171.652 cupons reais de São Paulo não apareceu nenhum: o SAT vai para a
  EFD só com o analítico.
* **C190 / C850** — analítico por CST, CFOP e alíquota, de nota e de cupom.
  Não tem item, mas tem o total da operação por CST — e é o que permite
  saber quanto de CST 60 saiu em cada cupom sem abrir o XML.
* **H005 / H010** — inventário: a data, o total e cada item em estoque. É o
  saldo de abertura da ficha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cat.dominio.sped.fiscais import _data, _decimal, _texto

ZERO = Decimal("0")


@dataclass(frozen=True)
class ItemCadastrado:
    """|0200|COD_ITEM|DESCR_ITEM|COD_BARRA|COD_ANT_ITEM|UNID_INV|TIPO_ITEM|
    COD_NCM|EX_IPI|COD_GEN|COD_LST|ALIQ_ICMS|CEST| — 12 campos, real."""

    codigo: str
    descricao: str
    codigo_barras: str = ""
    codigo_anterior: str = ""
    unidade: str = ""
    tipo_item: str = ""
    ncm: str = ""
    ex_ipi: str = ""
    cod_gen: str = ""
    cod_lst: str = ""
    aliq_icms: Decimal = ZERO
    cest: str = ""


@dataclass(frozen=True)
class ItemDoDocumento:
    """Uma linha de C170 ou C810, sem saber ainda de que documento é.

    Quem lê o arquivo é que amarra ao C100/C800 anterior — o registro filho
    não repete a chave do pai.
    """

    registro: str                # "C170" ou "C810"
    numero: int
    codigo: str
    quantidade: Decimal
    unidade: str
    valor: Decimal
    descricao_complementar: str = ""
    desconto: Decimal = ZERO
    ind_mov: str = ""            # 0 = com movimentação física, 1 = sem
    cst_icms: str = ""
    cfop: str = ""
    bc_icms: Decimal = ZERO
    aliq_icms: Decimal = ZERO
    valor_icms: Decimal = ZERO
    bc_st: Decimal = ZERO
    aliq_st: Decimal = ZERO
    valor_st: Decimal = ZERO


@dataclass(frozen=True)
class TotalAnalitico:
    """Uma linha de C190 (nota) ou C850 (cupom): total por CST/CFOP/alíquota."""

    registro: str
    cst_icms: str
    cfop: str
    aliq_icms: Decimal = ZERO
    valor_operacao: Decimal = ZERO
    bc_icms: Decimal = ZERO
    valor_icms: Decimal = ZERO
    bc_st: Decimal = ZERO
    valor_st: Decimal = ZERO
    valor_red_bc: Decimal = ZERO
    valor_ipi: Decimal = ZERO


@dataclass(frozen=True)
class Inventario:
    """|H005|DT_INV|VL_INV|MOT_INV| — 3 campos, real."""

    data: date | None
    valor_total: Decimal = ZERO
    motivo: str = ""             # 01 = final do período, 02..06 = outros


@dataclass(frozen=True)
class ItemEmEstoque:
    """|H010|COD_ITEM|UNID|QTD|VL_UNIT|VL_ITEM|IND_PROP|COD_PART|TXT_COMPL|
    COD_CTA|VL_ITEM_IR| — 10 campos, real."""

    codigo: str
    unidade: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor: Decimal
    ind_prop: str = ""           # 0 = próprio em poder da empresa
    participante: str = ""
    cod_cta: str = ""


def ler_0200(campos: list[str]) -> ItemCadastrado:
    return ItemCadastrado(
        codigo=_texto(campos, 2),
        descricao=_texto(campos, 3),
        codigo_barras=_texto(campos, 4),
        codigo_anterior=_texto(campos, 5),
        unidade=_texto(campos, 6),
        tipo_item=_texto(campos, 7),
        ncm=_texto(campos, 8),
        ex_ipi=_texto(campos, 9),
        cod_gen=_texto(campos, 10),
        cod_lst=_texto(campos, 11),
        aliq_icms=_decimal(_texto(campos, 12)),
        cest=_texto(campos, 13),
    )


def ler_c170(campos: list[str]) -> ItemDoDocumento:
    """|C170|NUM_ITEM|COD_ITEM|DESCR_COMPL|QTD|UNID|VL_ITEM|VL_DESC|IND_MOV|
    CST_ICMS|CFOP|COD_NAT|VL_BC_ICMS|ALIQ_ICMS|VL_ICMS|VL_BC_ICMS_ST|ALIQ_ST|
    VL_ICMS_ST|… — 37 campos, real; o que vem depois é IPI, PIS e COFINS."""
    return ItemDoDocumento(
        registro="C170",
        numero=_inteiro(_texto(campos, 2)),
        codigo=_texto(campos, 3),
        descricao_complementar=_texto(campos, 4),
        quantidade=_decimal(_texto(campos, 5)),
        unidade=_texto(campos, 6),
        valor=_decimal(_texto(campos, 7)),
        desconto=_decimal(_texto(campos, 8)),
        ind_mov=_texto(campos, 9),
        cst_icms=_texto(campos, 10),
        cfop=_texto(campos, 11),
        bc_icms=_decimal(_texto(campos, 13)),
        aliq_icms=_decimal(_texto(campos, 14)),
        valor_icms=_decimal(_texto(campos, 15)),
        bc_st=_decimal(_texto(campos, 16)),
        aliq_st=_decimal(_texto(campos, 17)),
        valor_st=_decimal(_texto(campos, 18)),
    )


def ler_c810(campos: list[str]) -> ItemDoDocumento:
    """|C810|NUM_ITEM|COD_ITEM|QTD|UNID|VL_ITEM|CST_ICMS|CFOP| — do manual.

    Não apareceu em arquivo real (o SAT vai para a EFD só com o C850), mas o
    leiaute é curto e estável; se um dia vier, entra como item de saída.
    """
    return ItemDoDocumento(
        registro="C810",
        numero=_inteiro(_texto(campos, 2)),
        codigo=_texto(campos, 3),
        quantidade=_decimal(_texto(campos, 4)),
        unidade=_texto(campos, 5),
        valor=_decimal(_texto(campos, 6)),
        cst_icms=_texto(campos, 7),
        cfop=_texto(campos, 8),
    )


def ler_c190(campos: list[str]) -> TotalAnalitico:
    """|C190|CST_ICMS|CFOP|ALIQ_ICMS|VL_OPR|VL_BC_ICMS|VL_ICMS|VL_BC_ICMS_ST|
    VL_ICMS_ST|VL_RED_BC|VL_IPI|COD_OBS| — 11 campos, real."""
    return TotalAnalitico(
        registro="C190",
        cst_icms=_texto(campos, 2),
        cfop=_texto(campos, 3),
        aliq_icms=_decimal(_texto(campos, 4)),
        valor_operacao=_decimal(_texto(campos, 5)),
        bc_icms=_decimal(_texto(campos, 6)),
        valor_icms=_decimal(_texto(campos, 7)),
        bc_st=_decimal(_texto(campos, 8)),
        valor_st=_decimal(_texto(campos, 9)),
        valor_red_bc=_decimal(_texto(campos, 10)),
        valor_ipi=_decimal(_texto(campos, 11)),
    )


def ler_c850(campos: list[str]) -> TotalAnalitico:
    """|C850|CST_ICMS|CFOP|ALIQ_ICMS|VL_OPR|VL_BC_ICMS|VL_ICMS|COD_OBS| —
    7 campos, real. Cupom não tem ST destacado: o campo não existe."""
    return TotalAnalitico(
        registro="C850",
        cst_icms=_texto(campos, 2),
        cfop=_texto(campos, 3),
        aliq_icms=_decimal(_texto(campos, 4)),
        valor_operacao=_decimal(_texto(campos, 5)),
        bc_icms=_decimal(_texto(campos, 6)),
        valor_icms=_decimal(_texto(campos, 7)),
    )


def ler_h005(campos: list[str]) -> Inventario:
    return Inventario(
        data=_data(_texto(campos, 2)),
        valor_total=_decimal(_texto(campos, 3)),
        motivo=_texto(campos, 4),
    )


def ler_h010(campos: list[str]) -> ItemEmEstoque:
    return ItemEmEstoque(
        codigo=_texto(campos, 2),
        unidade=_texto(campos, 3),
        quantidade=_decimal(_texto(campos, 4)),
        valor_unitario=_decimal(_texto(campos, 5)),
        valor=_decimal(_texto(campos, 6)),
        ind_prop=_texto(campos, 7),
        participante=_texto(campos, 8),
        cod_cta=_texto(campos, 10),
    )


def _inteiro(bruto: str) -> int:
    try:
        return int(bruto)
    except ValueError:
        return 0


# só quem passa no prefixo é quebrado em campos (mesma regra do C100/C800)
PREFIXOS_DE_ITENS = (
    b"|0200|", b"|C170|", b"|C810|", b"|C190|", b"|C850|", b"|H005|", b"|H010|",
)

LEITORES = {
    "0200": ler_0200, "C170": ler_c170, "C810": ler_c810,
    "C190": ler_c190, "C850": ler_c850, "H005": ler_h005, "H010": ler_h010,
}

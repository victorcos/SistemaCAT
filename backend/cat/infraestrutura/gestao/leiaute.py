"""Leiautes da EFD-Contribuições usados pela gestão.

Dois grupos:

1. ``DOCUMENTOS`` — registros de item/consolidação dos blocos A, C, D e F
   que levam CST, base e valor de PIS/COFINS. Cada um diz onde estão os
   campos e se a operação é entrada, saída ou vem do registro pai.
2. ``CAMPOS`` — nomes dos campos dos registros de apuração (blocos 0, M
   e 1), acessados por nome no montador dos quadros.

Índices contam a partir do código do registro: ``|C170|1|ABC|`` vira
``["C170", "1", "ABC"]``, então ``NUM_ITEM`` é o índice 1.

Registros marcados ``# VALIDADO`` bateram centavo a centavo com o export
real da Gestão do MA; os demais seguem o Guia Prático da EFD-Contribuições
e ainda não foram confrontados com um arquivo real.
"""
from __future__ import annotations

from dataclasses import dataclass

ENTRADA = "E"
SAIDA = "S"
DO_PAI = "PAI"          # IND_OPER do A100/C100 (0 = entrada, 1 = saída)
DO_PROPRIO_F100 = "F100"  # IND_OPER do próprio F100 (0 = aquisição, 1/2 = receita)


@dataclass(frozen=True)
class Tributo:
    """Onde ficam os campos de um tributo (PIS ou COFINS) no registro."""
    nome: str
    i_cst: int
    i_bc: int | None
    i_aliq: int
    i_valor: int
    i_quant: int | None = None


@dataclass(frozen=True)
class LayoutDocumento:
    reg: str
    rotulo: str             # como o MA nomeia a linha do registro
    operacao: str           # ENTRADA | SAIDA | DO_PAI | DO_PROPRIO_F100
    i_vl_item: int
    tributos: tuple[Tributo, ...]
    i_cfop: int | None = None
    i_nat: int | None = None
    cfop_do_pai: bool = False  # D201/D205: o CFOP está no D200


def _pis(i_cst, i_bc, i_aliq, i_valor, i_quant=None) -> Tributo:
    return Tributo("PIS", i_cst, i_bc, i_aliq, i_valor, i_quant)


def _cofins(i_cst, i_bc, i_aliq, i_valor, i_quant=None) -> Tributo:
    return Tributo("COFINS", i_cst, i_bc, i_aliq, i_valor, i_quant)


_LISTA_DOCUMENTOS: tuple[LayoutDocumento, ...] = (
    LayoutDocumento(
        "A170", "A100/A170 - Nota Fiscal de Serviço", DO_PAI, 4,
        (_pis(8, 9, 10, 11), _cofins(12, 13, 14, 15)), i_nat=6,
    ),
    LayoutDocumento(  # VALIDADO
        "C170", "C100/C170 - Documento - Nota Fiscal", DO_PAI, 6,
        (_pis(24, 25, 26, 29, 27), _cofins(30, 31, 32, 35, 33)), i_cfop=10,
    ),
    LayoutDocumento(  # VALIDADO
        "C175", "C100/C175 - Documento - Nota Fiscal Eletrônicas", DO_PAI, 2,
        (_pis(4, 5, 6, 9, 7), _cofins(10, 11, 12, 15, 13)), i_cfop=1,
    ),
    LayoutDocumento(
        "C181", "C180/C181 - Consolidação de Documentos Emitidos - NF-e", SAIDA, 3,
        (_pis(1, 5, 6, 9, 7),), i_cfop=2,
    ),
    LayoutDocumento(
        "C185", "C180/C185 - Consolidação de Documentos Emitidos - NF-e", SAIDA, 3,
        (_cofins(1, 5, 6, 9, 7),), i_cfop=2,
    ),
    LayoutDocumento(
        "C191", "C190/C191 - Consolidação de Documentos de Aquisição - NF-e", ENTRADA, 4,
        (_pis(2, 6, 7, 10, 8),), i_cfop=3,
    ),
    LayoutDocumento(
        "C195", "C190/C195 - Consolidação de Documentos de Aquisição - NF-e", ENTRADA, 4,
        (_cofins(2, 6, 7, 10, 8),), i_cfop=3,
    ),
    LayoutDocumento(
        "C381", "C380/C381 - Nota Fiscal de Venda a Consumidor", SAIDA, 3,
        (_pis(1, 4, 5, 8, 6),),
    ),
    LayoutDocumento(
        "C385", "C380/C385 - Nota Fiscal de Venda a Consumidor", SAIDA, 3,
        (_cofins(1, 4, 5, 8, 6),),
    ),
    LayoutDocumento(
        "C396", "C395/C396 - Notas Fiscais de Venda a Consumidor - Aquisições", ENTRADA, 2,
        (_pis(5, 6, 7, 8), _cofins(9, 10, 11, 12)), i_nat=4,
    ),
    LayoutDocumento(
        "C481", "C405/C481 - Resumo Diário de Documentos Emitidos por ECF", SAIDA, 2,
        (_pis(1, 3, 4, 7, 5),),
    ),
    LayoutDocumento(
        "C485", "C405/C485 - Resumo Diário de Documentos Emitidos por ECF", SAIDA, 2,
        (_cofins(1, 3, 4, 7, 5),),
    ),
    LayoutDocumento(
        "C491", "C490/C491 - Consolidação de Documentos Emitidos por ECF", SAIDA, 4,
        (_pis(2, 5, 6, 9, 7),), i_cfop=3,
    ),
    LayoutDocumento(
        "C495", "C490/C495 - Consolidação de Documentos Emitidos por ECF", SAIDA, 4,
        (_cofins(2, 5, 6, 9, 7),), i_cfop=3,
    ),
    LayoutDocumento(  # VALIDADO
        "C501", "C500/C501 - Nota Fiscal/Conta de Energia Elétrica/Água/Gás", ENTRADA, 2,
        (_pis(1, 4, 5, 6),), i_nat=3,
    ),
    LayoutDocumento(  # VALIDADO
        "C505", "C500/C505 - Nota Fiscal/Conta de Energia Elétrica/Água/Gás", ENTRADA, 2,
        (_cofins(1, 4, 5, 6),), i_nat=3,
    ),
    LayoutDocumento(
        "C810", "C800/C810 - Cupom Fiscal Eletrônico - CF-e", SAIDA, 2,
        (_pis(4, 5, 6, 7), _cofins(8, 9, 10, 11)), i_cfop=1,
    ),
    LayoutDocumento(
        "C870", "C860/C870 - Cupom Fiscal Eletrônico - SAT (CF-e)", SAIDA, 3,
        (_pis(5, 6, 7, 8), _cofins(9, 10, 11, 12)), i_cfop=2,
    ),
    LayoutDocumento(
        "C880", "C860/C880 - Cupom Fiscal Eletrônico - SAT (CF-e)", SAIDA, 3,
        (_pis(5, None, 7, 8, 6), _cofins(9, None, 11, 12, 10)), i_cfop=2,
    ),
    LayoutDocumento(  # VALIDADO
        "D101", "D100/D101 - Aquisição de Serviços de Transporte", ENTRADA, 2,
        (_pis(3, 5, 6, 7),), i_nat=4,
    ),
    LayoutDocumento(  # VALIDADO
        "D105", "D100/D105 - Aquisição de Serviços de Transporte", ENTRADA, 2,
        (_cofins(3, 5, 6, 7),), i_nat=4,
    ),
    LayoutDocumento(
        "D201", "D200/D201 - Resumo da Escrituração Diária - Serviços de Transporte", SAIDA, 2,
        (_pis(1, 3, 4, 5),), cfop_do_pai=True,
    ),
    LayoutDocumento(
        "D205", "D200/D205 - Resumo da Escrituração Diária - Serviços de Transporte", SAIDA, 2,
        (_cofins(1, 3, 4, 5),), cfop_do_pai=True,
    ),
    LayoutDocumento(
        "D501", "D500/D501 - Aquisição de Serviços de Comunicação", ENTRADA, 2,
        (_pis(1, 4, 5, 6),), i_nat=3,
    ),
    LayoutDocumento(
        "D505", "D500/D505 - Aquisição de Serviços de Comunicação", ENTRADA, 2,
        (_cofins(1, 4, 5, 6),), i_nat=3,
    ),
    LayoutDocumento(
        "D601", "D600/D601 - Consolidação da Prestação de Serviços de Comunicação", SAIDA, 2,
        (_pis(4, 5, 6, 7),),
    ),
    LayoutDocumento(
        "D605", "D600/D605 - Consolidação da Prestação de Serviços de Comunicação", SAIDA, 2,
        (_cofins(4, 5, 6, 7),),
    ),
    LayoutDocumento(  # VALIDADO
        "F100", "F100 - Demais Documentos e Operações", DO_PROPRIO_F100, 5,
        (_pis(6, 7, 8, 9), _cofins(10, 11, 12, 13)), i_nat=14,
    ),
    LayoutDocumento(  # VALIDADO
        "F120", "F120 - Bens Incorporados ao Ativo Imobilizado - Depreciação", ENTRADA, 5,
        (_pis(7, 8, 9, 10), _cofins(11, 12, 13, 14)), i_nat=1,
    ),
    LayoutDocumento(  # VALIDADO
        "F130", "F130 - Bens Incorporados ao Ativo Imobilizado - Aquisição", ENTRADA, 6,
        (_pis(10, 11, 12, 13), _cofins(14, 15, 16, 17)), i_nat=1,
    ),
    LayoutDocumento(
        "F150", "F150 - Crédito Presumido sobre Estoque de Abertura", ENTRADA, 2,
        (_pis(6, 5, 7, 8), _cofins(9, 5, 10, 11)), i_nat=1,
    ),
    LayoutDocumento(
        "F500", "F500 - Consolidação das Operações - Regime de Caixa", SAIDA, 1,
        (_pis(2, 4, 5, 6), _cofins(7, 9, 10, 11)), i_cfop=13,
    ),
    LayoutDocumento(
        "F550", "F550 - Consolidação das Operações - Regime de Competência", SAIDA, 1,
        (_pis(2, 4, 5, 6), _cofins(7, 9, 10, 11)), i_cfop=13,
    ),
)

DOCUMENTOS: dict[str, LayoutDocumento] = {d.reg: d for d in _LISTA_DOCUMENTOS}

# Registros pai cujo contexto o agregador acompanha.
PAIS_COM_IND_OPER = ("A100", "C100")   # IND_OPER no campo 1
PAI_CFOP_D200 = "D200"                 # CFOP no campo 7


# ---------------------------------------------------------------------------
# Registros de apuração — nomes dos campos (índice = posição na lista)
# ---------------------------------------------------------------------------

_M210_ANTIGO = [  # até 2018
    "REG", "COD_CONT", "VL_REC_BRT", "VL_BC_CONT", "ALIQ", "QUANT_BC", "ALIQ_QUANT",
    "VL_CONT_APUR", "VL_AJUS_ACRES", "VL_AJUS_REDUC", "VL_CONT_DIFER", "VL_CONT_DIFER_ANT",
    "VL_CONT_PER",
]
_M210_NOVO = [  # a partir de 2019 (ajustes de base de cálculo)  # VALIDADO
    "REG", "COD_CONT", "VL_REC_BRT", "VL_BC_CONT", "VL_AJUS_ACRES_BC", "VL_AJUS_REDUC_BC",
    "VL_BC_CONT_AJUS", "ALIQ", "QUANT_BC", "ALIQ_QUANT", "VL_CONT_APUR", "VL_AJUS_ACRES",
    "VL_AJUS_REDUC", "VL_CONT_DIFER", "VL_CONT_DIFER_ANT", "VL_CONT_PER",
]

CAMPOS: dict[str, list[str]] = {
    "0000": ["REG", "COD_VER", "TIPO_ESCRIT", "IND_SIT_ESP", "NUM_REC_ANTERIOR",
             "DT_INI", "DT_FIN", "NOME", "CNPJ", "UF", "COD_MUN", "SUFRAMA",
             "IND_NAT_PJ", "IND_ATIV"],
    "0110": ["REG", "COD_INC_TRIB", "IND_APRO_CRED", "COD_TIPO_CONT", "IND_REG_CUM"],
    "0111": ["REG", "REC_BRU_NCUM_TRIB_MI", "REC_BRU_NCUM_NT_MI", "REC_BRU_NCUM_EXP",
             "REC_BRU_CUM", "REC_BRU_TOTAL"],
    # Crédito do período (M100 PIS / M500 COFINS)  # VALIDADO
    "M100": ["REG", "COD_CRED", "IND_CRED_ORI", "VL_BC", "ALIQ", "QUANT_BC", "ALIQ_QUANT",
             "VL_CRED", "VL_AJUS_ACRES", "VL_AJUS_REDUC", "VL_CRED_DIF", "VL_CRED_DISP",
             "IND_DESC_CRED", "VL_CRED_DESC", "SLD_CRED"],
    "M105": ["REG", "NAT_BC_CRED", "CST", "VL_BC_TOT", "VL_BC_CUM", "VL_BC_NC", "VL_BC",
             "QUANT_BC_TOT", "QUANT_BC", "DESC_CRED"],
    # Consolidação da contribuição (M200 PIS / M600 COFINS)  # VALIDADO
    "M200": ["REG", "VL_TOT_CONT_NC_PER", "VL_TOT_CRED_DESC", "VL_TOT_CRED_DESC_ANT",
             "VL_TOT_CONT_NC_DEV", "VL_RET_NC", "VL_OUT_DED_NC", "VL_CONT_NC_REC",
             "VL_TOT_CONT_CUM_PER", "VL_RET_CUM", "VL_OUT_DED_CUM", "VL_CONT_CUM_REC",
             "VL_TOT_CONT_REC"],
    "M205": ["REG", "NUM_CAMPO", "COD_REC", "VL_DEBITO"],
    "M230": ["REG", "CNPJ", "VL_VEND", "VL_NAO_RECEB", "VL_CONT_DIF", "VL_CRED_DIF", "COD_CRED"],
    "M350": ["REG", "VL_TOT_FOL", "VL_EXC_BC", "VL_TOT_BC", "ALIQ_PIS_FOL", "VL_TOT_CONT_FOL"],
    "M400": ["REG", "CST", "VL_TOT_REC", "COD_CTA", "DESC_COMPL"],
    # Controle de créditos (1100 PIS / 1500 COFINS)  # VALIDADO
    "1100": ["REG", "PER_APU_CRED", "ORIG_CRED", "CNPJ_SUC", "COD_CRED", "VL_CRED_APU",
             "VL_CRED_EXT_APU", "VL_TOT_CRED_APU", "VL_CRED_DESC_PA_ANT", "VL_CRED_PER_PA_ANT",
             "VL_CRED_DCOMP_PA_ANT", "SD_CRED_DISP_EFD", "VL_CRED_DESC_EFD", "VL_CRED_PER_EFD",
             "VL_CRED_DCOMP_EFD", "VL_CRED_TRANS", "VL_CRED_OUT", "SLD_CRED_FIM"],
    # Controle de retenções (1300 PIS / 1700 COFINS)
    "1300": ["REG", "IND_NAT_RET", "PR_REC_RET", "VL_RET_APU", "VL_RET_DED", "VL_RET_PER",
             "VL_RET_DCOMP", "SLD_RET"],
}
# COFINS espelha o PIS campo a campo, só muda o código do registro.
for _pis_reg, _cof_reg in (("M100", "M500"), ("M105", "M505"), ("M200", "M600"),
                          ("M205", "M605"), ("M230", "M630"), ("M400", "M800"),
                          ("1100", "1500"), ("1300", "1700")):
    CAMPOS[_cof_reg] = CAMPOS[_pis_reg]

# Ajustes (M110/M220 PIS, M510/M620 COFINS) — somados por IND_AJ + COD_AJ
CAMPOS_AJUSTE = ["REG", "IND_AJ", "VL_AJ", "COD_AJ", "NUM_DOC", "DESCR_AJ", "DT_REF"]
REGISTROS_AJUSTE = ("M110", "M220", "M510", "M620")


def campos_m210(qtd_campos: int) -> list[str]:
    """M210/M610 mudou de leiaute em 2019 (13 -> 16 campos)."""
    return _M210_NOVO if qtd_campos >= len(_M210_NOVO) else _M210_ANTIGO


# Registros de apuração guardados inteiros (são poucos por arquivo).
REGISTROS_APURACAO: frozenset[str] = frozenset(
    set(CAMPOS) - {"0000"} | {"M210", "M610"}
)

# Registros por tributo: o montador pede "o M100 do tributo" sem saber se é PIS ou COFINS.
POR_TRIBUTO: dict[str, dict[str, str]] = {
    "PIS": {"credito": "M100", "credito_nat": "M105", "ajuste_credito": "M110",
            "consolidacao": "M200", "cod_receita": "M205", "detalhe": "M210",
            "ajuste_contrib": "M220", "diferimento": "M230", "sem_incidencia": "M400",
            "controle_credito": "1100", "controle_retencao": "1300"},
    "COFINS": {"credito": "M500", "credito_nat": "M505", "ajuste_credito": "M510",
               "consolidacao": "M600", "cod_receita": "M605", "detalhe": "M610",
               "ajuste_contrib": "M620", "diferimento": "M630", "sem_incidencia": "M800",
               "controle_credito": "1500", "controle_retencao": "1700"},
}

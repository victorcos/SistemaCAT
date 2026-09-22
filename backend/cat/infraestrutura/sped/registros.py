"""Os campos de cada registro do SPED, na ordem do leiaute.

Portado do projeto Quebra de SPED (22/09/2026). É tabela, não regra: o que está
aqui são os **nomes oficiais** dos campos, na ordem em que o leiaute os põe, e é
por eles que a extração nomeia as colunas. Acrescentar registro é acrescentar
uma linha nesta lista.

**Por que uma tabela e não posições soltas no código.** O código que extrai o
C170 precisa do CST do PIS, que é o campo 24. Escrever `campos[24]` espalhado
por cinco lugares é como se descobre, meses depois, que um deles tinha 23 — e o
erro não aparece, porque o campo ao lado também é texto e também parece um CST.
Com nome, o erro vira `KeyError` na hora.

Os leiautes são os da **EFD-Contribuições**. O C170 é o mesmo registro da EFD
ICMS/IPI, e por isso carrega `VL_BC_ICMS`, `ALIQ_ICMS` e `VL_ICMS` — o que
importa para a exclusão do ICMS da base: quando o contribuinte os preenche, o
valor está ali; quando não preenche, é preciso cruzar com a EFD ICMS/IPI.
"""

from __future__ import annotations

CAMPOS: dict[str, tuple[str, ...]] = {
    "0000": (
        "REG", "COD_VER", "TIPO_ESCRIT", "IND_SIT_ESP", "NUM_REC_ANTERIOR",
        "DT_INI", "DT_FIN", "NOME", "CNPJ", "UF", "COD_MUN", "SUFRAMA",
        "IND_NAT_PJ", "IND_ATIV",
    ),
    # cadastro do estabelecimento; liga ao bloco C pelo CNPJ do C010
    "0140": (
        "REG", "COD_EST", "NOME", "CNPJ", "UF", "IE", "COD_MUN",
        "SUFRAMA", "IND_SIT_INI_PER", "IND_ATIV",
    ),
    "0150": (
        "REG", "COD_PART", "NOME", "COD_PAIS", "CNPJ", "CPF", "IE",
        "COD_MUN", "SUFRAMA", "END", "NUM", "COMPL", "BAIRRO",
    ),
    "0200": (
        "REG", "COD_ITEM", "DESCR_ITEM", "COD_BARRA", "COD_ANT_ITEM",
        "UNID_INV", "TIPO_ITEM", "COD_NCM", "EX_IPI", "COD_GEN",
        "COD_LST", "ALIQ_ICMS", "CEST",
    ),
    "0400": ("REG", "COD_NAT", "DESCR_NAT"),
    "C010": ("REG", "CNPJ", "IND_ESCRIT"),
    "C100": (
        "REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT",
        "SER", "NUM_DOC", "CHV_NFE", "DT_DOC", "DT_E_S", "VL_DOC",
        "IND_PGTO", "VL_DESC", "VL_ABAT_NT", "VL_MERC", "IND_FRT",
        "VL_FRT", "VL_SEG", "VL_OUT_DA", "VL_BC_ICMS", "VL_ICMS",
        "VL_BC_ICMS_ST", "VL_ICMS_ST", "VL_IPI", "VL_PIS", "VL_COFINS",
        "VL_PIS_ST", "VL_COFINS_ST",
    ),
    # plano de contas; o COD_CTA dos filhos consolidados aponta para cá
    "0500": (
        "REG", "DT_ALT", "COD_NAT_CC", "IND_CTA", "NIVEL", "COD_CTA", "NOME_CTA",
        "COD_CTA_SUP",
    ),
    # --- o caminho consolidado: quando o contribuinte não escritura item a item ---
    # C180 é a consolidação das notas EMITIDAS; C190, das ADQUIRIDAS. Os dois têm
    # o mesmo leiaute e o mesmo par de filhos (PIS e COFINS), e é por isso que uma
    # função só lê os dois
    "C180": (
        "REG", "COD_MOD", "DT_INI", "DT_FIN", "COD_ITEM", "COD_NCM", "EX_IPI",
        "VL_TOT_ITEM",
    ),
    "C181": (
        "REG", "CST_PIS", "CFOP", "VL_ITEM", "VL_DESC", "VL_BC_PIS", "ALIQ_PIS_PERC",
        "QUANT_BC_PIS", "ALIQ_PIS_QUANT", "VL_PIS", "COD_CTA",
    ),
    "C185": (
        "REG", "CST_COFINS", "CFOP", "VL_ITEM", "VL_DESC", "VL_BC_COFINS",
        "ALIQ_COFINS_PERC", "QUANT_BC_COFINS", "ALIQ_COFINS_QUANT", "VL_COFINS", "COD_CTA",
    ),
    "C190": (
        "REG", "COD_MOD", "DT_INI", "DT_FIN", "COD_ITEM", "COD_NCM", "EX_IPI",
        "VL_TOT_ITEM",
    ),
    # os filhos do C190 trazem COD_PART, que os do C180 não têm: a aquisição sabe
    # de quem comprou, a venda consolidada não diz para quem vendeu
    "C191": (
        "REG", "COD_PART", "CST_PIS", "CFOP", "VL_ITEM", "VL_DESC", "VL_BC_PIS",
        "ALIQ_PIS_PERC", "QUANT_BC_PIS", "ALIQ_PIS_QUANT", "VL_PIS", "COD_CTA",
    ),
    "C195": (
        "REG", "COD_PART", "CST_COFINS", "CFOP", "VL_ITEM", "VL_DESC", "VL_BC_COFINS",
        "ALIQ_COFINS_PERC", "QUANT_BC_COFINS", "ALIQ_COFINS_QUANT", "VL_COFINS", "COD_CTA",
    ),
    "C170": (
        "REG", "NUM_ITEM", "COD_ITEM", "DESCR_COMPL", "QTD", "UNID",
        "VL_ITEM", "VL_DESC", "IND_MOV", "CST_ICMS", "CFOP", "COD_NAT",
        "VL_BC_ICMS", "ALIQ_ICMS", "VL_ICMS", "VL_BC_ICMS_ST", "ALIQ_ST",
        "VL_ICMS_ST", "IND_APUR", "CST_IPI", "COD_ENQ", "VL_BC_IPI",
        "ALIQ_IPI", "VL_IPI", "CST_PIS", "VL_BC_PIS", "ALIQ_PIS_PERC",
        "QUANT_BC_PIS", "ALIQ_PIS_REAIS", "VL_PIS", "CST_COFINS",
        "VL_BC_COFINS", "ALIQ_COFINS_PERC", "QUANT_BC_COFINS",
        "ALIQ_COFINS_REAIS", "VL_COFINS", "COD_CTA",
    ),

    # --- bloco M: a apuração. PIS e COFINS são espelhos, registro a registro ---
    # crédito
    "M100": (
        "REG", "COD_CRED", "IND_CRED_ORI", "VL_BC_PIS", "ALIQ_PIS", "QUANT_BC_PIS",
        "ALIQ_PIS_REAIS", "VL_CRED", "VL_AJUS_ACRES", "VL_AJUS_REDUC", "VL_CRED_DIF",
        "VL_CRED_DISP", "IND_DESC_CRED", "VL_CRED_DESC", "SLD_CRED",
    ),
    "M105": (
        "REG", "NAT_BC_CRED", "CST_PIS", "VL_BC_PIS_TOT", "VL_BC_PIS_CUM", "VL_BC_PIS_NC",
        "VL_BC_PIS", "QUANT_BC_PIS_TOT", "QUANT_BC_PIS", "DESC_CRED",
    ),
    "M110": ("REG", "IND_AJ", "VL_AJ", "COD_AJ", "NUM_DOC", "DESCR_AJ", "DT_REF"),
    # contribuição
    "M200": (
        "REG", "VL_TOT_CONT_NC_PER", "VL_TOT_CRED_DESC", "VL_TOT_CRED_DESC_ANT",
        "VL_TOT_CONT_NC_DEV", "VL_RET_NC", "VL_OUT_DED_NC", "VL_CONT_NC_REC",
        "VL_TOT_CONT_CUM_PER", "VL_RET_CUM", "VL_OUT_DED_CUM", "VL_CONT_CUM_REC",
        "VL_TOT_CONT_REC",
    ),
    "M210": (
        "REG", "COD_CONT", "VL_REC_BRT", "VL_BC_CONT", "ALIQ_PIS", "QUANT_BC_PIS",
        "ALIQ_PIS_REAIS", "VL_CONT_APU", "VL_AJUS_ACRES", "VL_AJUS_REDUC", "VL_CONT_DIF",
        "VL_CONT_DISP", "IND_DESC_CONT", "VL_CONT_DESC", "SLD_CRED",
    ),
    "M220": ("REG", "IND_AJ", "VL_AJ", "COD_AJ", "NUM_DOC", "DESCR_AJ", "DT_REF"),
    # e o espelho, na COFINS
    "M500": (
        "REG", "COD_CRED", "IND_CRED_ORI", "VL_BC_COFINS", "ALIQ_COFINS",
        "QUANT_BC_COFINS", "ALIQ_COFINS_REAIS", "VL_CRED", "VL_AJUS_ACRES",
        "VL_AJUS_REDUC", "VL_CRED_DIF", "VL_CRED_DISP", "IND_DESC_CRED", "VL_CRED_DESC",
        "SLD_CRED",
    ),
    "M505": (
        "REG", "NAT_BC_CRED", "CST_COFINS", "VL_BC_COFINS_TOT", "VL_BC_COFINS_CUM",
        "VL_BC_COFINS_NC", "VL_BC_COFINS", "QUANT_BC_COFINS_TOT", "QUANT_BC_COFINS",
        "DESC_CRED",
    ),
    "M510": ("REG", "IND_AJ", "VL_AJ", "COD_AJ", "NUM_DOC", "DESCR_AJ", "DT_REF"),
    "M600": (
        "REG", "VL_TOT_CONT_NC_PER", "VL_TOT_CRED_DESC", "VL_TOT_CRED_DESC_ANT",
        "VL_TOT_CONT_NC_DEV", "VL_RET_NC", "VL_OUT_DED_NC", "VL_CONT_NC_REC",
        "VL_TOT_CONT_CUM_PER", "VL_RET_CUM", "VL_OUT_DED_CUM", "VL_CONT_CUM_REC",
        "VL_TOT_CONT_REC",
    ),
    "M610": (
        "REG", "COD_CONT", "VL_REC_BRT", "VL_BC_CONT", "ALIQ_COFINS", "QUANT_BC_COFINS",
        "ALIQ_COFINS_REAIS", "VL_CONT_APU", "VL_AJUS_ACRES", "VL_AJUS_REDUC",
        "VL_CONT_DIF", "VL_CONT_DISP", "IND_DESC_CONT", "VL_CONT_DESC", "SLD_CRED",
    ),
    "M620": ("REG", "IND_AJ", "VL_AJ", "COD_AJ", "NUM_DOC", "DESCR_AJ", "DT_REF"),
}


def nomes_dos_campos(registro: str) -> tuple[str, ...]:
    """Os nomes do registro, ou vazio quando ele não está na tabela.

    Vazio em vez de erro: um registro fora da tabela ainda pode ser **contado**
    pelo índice, e contar tudo é justamente o que a quebra de SPED serve para
    fazer. Só quem precisa nomear campo é que depende desta tabela.
    """
    return CAMPOS.get(registro, ())


def posicao_do_campo(registro: str, nome: str) -> int:
    """Onde o campo está na linha. Erro claro quando o nome não existe.

    É o que substitui `campos[24]` espalhado pelo código: aqui o engano vira
    exceção na primeira execução, e não um CST errado três meses depois.
    """
    nomes = nomes_dos_campos(registro)
    try:
        return nomes.index(nome)
    except ValueError:
        raise KeyError(
            f"O registro {registro} não tem campo '{nome}'. "
            f"Tem: {', '.join(nomes) if nomes else '(registro fora da tabela)'}."
        ) from None

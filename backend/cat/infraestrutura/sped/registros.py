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
    # 9 campos. Tinha um `IND_SIT_INI_PER` a mais, que é da EFD ICMS/IPI e não
    # desta — ele empurrava o `IND_ATIV` para uma coluna que o arquivo não tem.
    # Conferido contra três competências reais em 29/09/2026
    "0140": (
        "REG", "COD_EST", "NOME", "CNPJ", "UF", "IE", "COD_MUN",
        "SUFRAMA", "IND_ATIV",
    ),
    "0150": (
        "REG", "COD_PART", "NOME", "COD_PAIS", "CNPJ", "CPF", "IE",
        "COD_MUN", "SUFRAMA", "END", "NUM", "COMPL", "BAIRRO",
    ),
    # 12 campos. O CEST saiu em 29/09/2026: ele existe no 0200 da EFD ICMS/IPI,
    # e não no desta — a coluna vinha sempre vazia, prometendo um dado que o
    # arquivo não traz
    "0200": (
        "REG", "COD_ITEM", "DESCR_ITEM", "COD_BARRA", "COD_ANT_ITEM",
        "UNID_INV", "TIPO_ITEM", "COD_NCM", "EX_IPI", "COD_GEN",
        "COD_LST", "ALIQ_ICMS",
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
    # 9 campos. Faltava o último, e o oitavo estava com o nome do leiaute do
    # ICMS/IPI (`COD_CTA_SUP`); aqui ele é a conta do plano referencial
    "0500": (
        "REG", "DT_ALT", "COD_NAT_CC", "IND_CTA", "NIVEL", "COD_CTA", "NOME_CTA",
        "COD_CTA_REF", "CNPJ_EST",
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

    # --- os ramos de documento de ENTRADA que a consulta 037 percorre ---
    # energia, água e gás (C500) · demais documentos (F100) · transporte (D100) ·
    # comunicação (D500) · ativo imobilizado (F120 depreciação, F130 aquisição)
    #
    # O bloco D tem abridor PRÓPRIO por estabelecimento (D010), independente do
    # C010: sem isso, o documento de uma filial sai com o CNPJ da matriz — bug
    # real, achado na validação do projeto de origem contra arquivo de cliente.
    "C500": (
        "REG", "COD_PART", "COD_MOD", "COD_SIT", "SER", "SUB", "NUM_DOC", "DT_DOC",
        "DT_ENT", "VL_DOC", "VL_ICMS", "COD_INF", "VL_PIS", "VL_COFINS", "CHV_DOCe",
    ),
    "C501": (
        "REG", "CST_PIS", "VL_ITEM", "NAT_BC_CRED", "VL_BC_PIS", "ALIQ_PIS", "VL_PIS",
        "COD_CTA",
    ),
    "C505": (
        "REG", "CST_COFINS", "VL_ITEM", "NAT_BC_CRED", "VL_BC_COFINS", "ALIQ_COFINS",
        "VL_COFINS", "COD_CTA",
    ),
    "F010": (
        "REG", "CNPJ",
    ),
    "F100": (
        "REG", "IND_OPER", "COD_PART", "COD_ITEM", "DT_OPER", "VL_OPER", "CST_PIS",
        "VL_BC_PIS", "ALIQ_PIS", "VL_PIS", "CST_COFINS", "VL_BC_COFINS", "ALIQ_COFINS",
        "VL_COFINS", "NAT_BC_CRED", "IND_ORIG_CRED", "COD_CTA", "COD_CCUS",
        "DESC_DOC_OPER",
    ),
    "F120": (
        "REG", "NAT_BC_CRED", "IDENT_BEM_IMOB", "IND_ORIG_CRED", "IND_UTIL_BEM_IMOB",
        "VL_OPER_DEP", "PARC_OPER_NAO_BC_CRED", "CST_PIS", "VL_BC_PIS", "ALIQ_PIS",
        "VL_PIS", "CST_COFINS", "VL_BC_COFINS", "ALIQ_COFINS", "VL_COFINS", "COD_CTA",
        "COD_CCUS", "DESC_BEM_IMOB",
    ),
    "F130": (
        "REG", "NAT_BC_CRED", "IDENT_BEM_IMOB", "IND_ORIG_CRED", "IND_UTIL_BEM_IMOB",
        "MES_OPER_AQUIS", "VL_OPER_AQUIS", "PARC_OPER_NAO_BC_CRED", "VL_BC_CRED",
        "IND_NR_PARC", "CST_PIS", "VL_BC_PIS", "ALIQ_PIS", "VL_PIS", "CST_COFINS",
        "VL_BC_COFINS", "ALIQ_COFINS", "VL_COFINS", "COD_CTA", "COD_CCUS", "DESC_BEM_IMOB",
    ),
    "D010": (
        "REG", "CNPJ",
    ),
    "D100": (
        "REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT", "SER", "SUB",
        "NUM_DOC", "CHV_CTE", "DT_DOC", "DT_A_P", "TP_CTE", "CHV_CTE_REF", "VL_DOC",
        "VL_DESC", "IND_FRT", "VL_SERV", "VL_BC_ICMS", "VL_ICMS", "VL_NT", "COD_INF",
        "COD_CTA",
    ),
    "D101": (
        "REG", "IND_NAT_FRT", "VL_ITEM", "CST_PIS", "NAT_BC_CRED", "VL_BC_PIS", "ALIQ_PIS",
        "VL_PIS", "COD_CTA",
    ),
    "D105": (
        "REG", "IND_NAT_FRT", "VL_ITEM", "CST_COFINS", "NAT_BC_CRED", "VL_BC_COFINS",
        "ALIQ_COFINS", "VL_COFINS", "COD_CTA",
    ),
    "D500": (
        "REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT", "SER", "SUB",
        "NUM_DOC", "DT_DOC", "DT_A_P", "VL_DOC", "VL_DESC", "VL_SERV", "VL_SERV_NT",
        "VL_TERC", "VL_DA", "VL_BC_ICMS", "VL_ICMS", "COD_INF", "VL_PIS", "VL_COFINS",
    ),
    "D501": (
        "REG", "CST_PIS", "VL_ITEM", "NAT_BC_CRED", "VL_BC_PIS", "ALIQ_PIS", "VL_PIS",
        "COD_CTA",
    ),
    "D505": (
        "REG", "CST_COFINS", "VL_ITEM", "NAT_BC_CRED", "VL_BC_COFINS", "ALIQ_COFINS",
        "VL_COFINS", "COD_CTA",
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
    # 16 campos desde 2019, quando entraram os três ajustes de **base de
    # cálculo**. O leiaute antigo, de 13, continua vivo em arquivo de 2018 para
    # trás e está em `CAMPOS_ANTIGOS` — é `campos_de()` que escolhe, pela
    # quantidade de campos da própria linha. Os nomes são os que a Gestão
    # conferiu contra o MA em 59 competências
    "M210": (
        "REG", "COD_CONT", "VL_REC_BRT", "VL_BC_CONT", "VL_AJUS_ACRES_BC",
        "VL_AJUS_REDUC_BC", "VL_BC_CONT_AJUS", "ALIQ_PIS", "QUANT_BC_PIS",
        "ALIQ_PIS_QUANT", "VL_CONT_APUR", "VL_AJUS_ACRES", "VL_AJUS_REDUC",
        "VL_CONT_DIFER", "VL_CONT_DIFER_ANT", "VL_CONT_PER",
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
    # o espelho do M210, com os mesmos 16 — ver a nota lá
    "M610": (
        "REG", "COD_CONT", "VL_REC_BRT", "VL_BC_CONT", "VL_AJUS_ACRES_BC",
        "VL_AJUS_REDUC_BC", "VL_BC_CONT_AJUS", "ALIQ_COFINS", "QUANT_BC_COFINS",
        "ALIQ_COFINS_QUANT", "VL_CONT_APUR", "VL_AJUS_ACRES", "VL_AJUS_REDUC",
        "VL_CONT_DIFER", "VL_CONT_DIFER_ANT", "VL_CONT_PER",
    ),
    "M620": ("REG", "IND_AJ", "VL_AJ", "COD_AJ", "NUM_DOC", "DESCR_AJ", "DT_REF"),
    # ---- cupom fiscal (ECF) e CF-e SAT ----
    # Entraram em 28/09/2026, com a extração de registro: são o que o varejo
    # precisa e o que a EFD não detalha em lugar nenhum além daqui.
    "C400": ("REG", "COD_MOD", "ECF_MOD", "ECF_FAB", "ECF_CX"),
    "C405": ("REG", "DT_DOC", "CRO", "CRZ", "NUM_COO_FIN", "GT_FIN", "VL_BRT"),
    "C460": (
        "REG", "COD_MOD", "COD_SIT", "NUM_DOC_INI", "NUM_DOC_FIN", "DT_DOC_INI",
        "DT_DOC_FIN", "VL_DOC", "VL_PIS", "VL_COFINS", "CNPJ_CPF", "NOM_ADQ",
    ),
    "C481": (
        "REG", "CST_PIS", "VL_ITEM", "NAT_BC_CRED", "VL_BC_PIS", "ALIQ_PIS_PERC",
        "QUANT_BC_PIS", "ALIQ_PIS_REAIS", "VL_PIS", "COD_CTA",
    ),
    "C485": (
        "REG", "CST_COFINS", "VL_ITEM", "NAT_BC_CRED", "VL_BC_COFINS",
        "ALIQ_COFINS_PERC", "QUANT_BC_COFINS", "ALIQ_COFINS_REAIS", "VL_COFINS",
        "COD_CTA",
    ),
    "C800": (
        "REG", "COD_MOD", "CHV_CFE", "NUM_CFE", "DT_DOC", "VL_CFE", "VL_PIS",
        "VL_COFINS", "CNPJ_CPF", "NR_SAT", "NR_CFE",
    ),
    "C490": ("REG", "DT_DOC_INI", "DT_DOC_FIN", "COD_MOD"),
    "C491": (
        "REG", "COD_ITEM", "CST_PIS", "CFOP", "VL_ITEM", "VL_BC_PIS",
        "ALIQ_PIS_PERC", "QUANT_BC_PIS", "ALIQ_PIS_QUANT", "VL_PIS", "COD_CTA",
    ),
    "C495": (
        "REG", "COD_ITEM", "CST_COFINS", "CFOP", "VL_ITEM", "VL_BC_COFINS",
        "ALIQ_COFINS_PERC", "QUANT_BC_COFINS", "ALIQ_COFINS_QUANT", "VL_COFINS",
        "COD_CTA",
    ),
    "C860": ("REG", "COD_MOD", "NR_SAT", "DT_DOC", "DOC_INIC", "DOC_FIM"),
    "C870": (
        "REG", "COD_ITEM", "CFOP", "VL_ITEM", "VL_DESC", "CST_PIS", "VL_BC_PIS",
        "ALIQ_PIS_PERC", "VL_PIS", "CST_COFINS", "VL_BC_COFINS",
        "ALIQ_COFINS_PERC", "VL_COFINS", "COD_CTA",
    ),
}


# Leiautes que mudaram de tamanho e cujo arquivo antigo ainda circula. A chave
# é (registro, quantidade de campos da linha).
#
# **Por que pela quantidade, e não pela data do arquivo.** A data diz quando a
# competência é; o leiaute, qual PVA gerou o arquivo. Uma retificadora de 2018
# transmitida em 2024 sai no leiaute novo, e ninguém avisa.
CAMPOS_ANTIGOS: dict[tuple[str, int], tuple[str, ...]] = {
    ("M210", 13): (
        "REG", "COD_CONT", "VL_REC_BRT", "VL_BC_CONT", "ALIQ_PIS", "QUANT_BC_PIS",
        "ALIQ_PIS_QUANT", "VL_CONT_APUR", "VL_AJUS_ACRES", "VL_AJUS_REDUC",
        "VL_CONT_DIFER", "VL_CONT_DIFER_ANT", "VL_CONT_PER",
    ),
    ("M610", 13): (
        "REG", "COD_CONT", "VL_REC_BRT", "VL_BC_CONT", "ALIQ_COFINS", "QUANT_BC_COFINS",
        "ALIQ_COFINS_QUANT", "VL_CONT_APUR", "VL_AJUS_ACRES", "VL_AJUS_REDUC",
        "VL_CONT_DIFER", "VL_CONT_DIFER_ANT", "VL_CONT_PER",
    ),
}


def campos_de(registro: str, quantos: int) -> tuple[str, ...]:
    """Os nomes **desta linha**, que nem sempre são os da tabela.

    O M210 ganhou três campos em 2019, no meio do registro: ler um arquivo
    antigo com o leiaute novo põe a alíquota na coluna do ajuste de base, e o
    erro não aparece — os dois são número com duas casas.
    """
    antigo = CAMPOS_ANTIGOS.get((registro, quantos))
    return antigo if antigo is not None else CAMPOS.get(registro, ())


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

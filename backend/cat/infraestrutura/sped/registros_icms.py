"""Os campos de cada registro da **EFD ICMS/IPI**, na ordem do leiaute.

Irmão de `registros.py`, que é da **EFD-Contribuições**. São dois módulos e não
um porque dois registros **colidem**: o `0000` e o `0200` existem nos dois
arquivos com leiautes diferentes, e uma tabela só teria de escolher um — lendo o
outro com os nomes errados, calado. O `0000` da Contribuições tem 14 campos e o
desta tem 15; o `0200` de lá tem 12 e o daqui tem 13, por causa do `CEST`.

## De onde saiu cada linha

**Medido contra arquivo real, não copiado do Guia Prático.** 40 EFD ICMS/IPI da
empresa G (02/2023 a 03/2026, matriz), contando os campos de cada linha e
conferindo valor por valor contra o significado esperado. A contagem vai escrita
em cada registro, porque é ela que torna a tabela conferível: quem desconfiar
roda `tools/medir_leiaute_icms.py` e compara.

Essa conferência pegou o que a leitura do Guia não pegaria: o `0200` daqui tem
mesmo o `CEST` no fim — a nota que já estava em `registros.py` dizia isso e
agora está medida dos dois lados.

## O que a tese do combustível usa, e para quê

| Registro | Para quê |
|---|---|
| `0000` | CNPJ, UF e competência do arquivo — a UF escolhe o FCV e a alíquota |
| `0150` | quem vendeu o combustível |
| `0190` | a unidade declarada (`L`, `LT`, `UN`, `KG`) |
| `0200` | NCM e descrição do item: a entrada do classificador |
| `0205` | a descrição **anterior** do item, com vigência |
| `C100` | data e documento da compra, e o prazo de 5 anos conta da emissão |
| `C170` | o item: CST, CFOP, `QTD`, `UNID` — é daqui que sai o litro |
| `C190` | o total por CST/CFOP/alíquota, que confere a soma do `C170` |
| `E110` | a apuração do mês, para dimensionar o crédito contra o saldo |
| `E111` | **o ajuste**: é assim que se descobre o crédito que o cliente já tomou |

## Dois registros que esta tabela **não** tem, e não é esquecimento

`0206` (código ANP) e `C171` (complemento de combustíveis) **não aparecem em
nenhum dos 40 arquivos da empresa G**, que consome combustível em vez de
distribuí-lo. Entrar aqui com leiaute tirado do Guia e nunca exercitado seria
pior que faltar: quem visse o nome assumiria que foi conferido.

**Eram três, e a espera rendeu o terceiro.** Rodado contra a empresa Z, o
`tools/medir_leiaute_icms.py` achou o `0220` — o registro que converte fardo,
caixa e tambor em litro — e achou com **dois tamanhos no mesmo acervo**. Medidos
depois sobre 20 milhões de linhas: 3 campos em 2,4 milhões (todas de 2021) e 4
em 17,8 milhões, sendo o quarto um código de barra numérico em 16 milhões e
vazio em 1,7 milhão. Entrou na tabela com a variante em `CAMPOS_ANTIGOS` — foi a
ferramenta que encontrou o caso, não a leitura do Guia.

`campos_de` devolve vazio para registro fora da tabela, e `posicao_do_campo`
levanta `RegistroNaoMedido` com o motivo — o engano vira exceção, não coluna
errada.

## O `C110` e a armadilha do texto livre

O `C110` traz observação em **texto livre**, e às vezes a base do ST vem escrita
ali — `"BC-ICMS-ST GASOLINA: R$ 2.350,34 VALOR-ICMS-ST: R$ 423,06"`. É tentador
usá-lo para reconstruir o ST da era anterior a 2023, que o CST 60 não destaca.

**Medido antes de virar método: 33 de 6.905 linhas de `C110`**, em pelo menos
três formatos diferentes (`BC-ICMS-ST <produto>:`, `BASE DE CALCULO DO ICMS-ST`,
`BC-ST: ... ALIQ.: ... ICMS-ST:`), cada um de um fornecedor. Meio por cento das
linhas, sem formato garantido e sem obrigação legal de existir.

Serve de **conferência** quando está lá; não serve de fonte. A fonte do ST
retido continua sendo o XML (`vICMSSTRet ÷ vBCSTRet`, que
`dominio/notafiscal/xml.py` já lê).
"""

from __future__ import annotations

from cat.dominio.sped.cabecalho import TipoSped
from cat.infraestrutura.sped import registros as contribuicoes

# Cada entrada traz, no comentário, quantas linhas reais a confirmaram.
CAMPOS: dict[str, tuple[str, ...]] = {
    # 15 campos (40 linhas). É o que separa este leiaute do da Contribuições:
    # lá são 14, com `COD_VER, TIPO_ESCRIT, IND_SIT_ESP, NUM_REC_ANTERIOR` no
    # lugar de `COD_VER, COD_FIN` — e `IND_PERFIL`, que só existe aqui.
    "0000": (
        "REG", "COD_VER", "COD_FIN", "DT_INI", "DT_FIN", "NOME", "CNPJ", "CPF",
        "UF", "IE", "COD_MUN", "IM", "SUFRAMA", "IND_PERFIL", "IND_ATIV",
    ),
    # 10 campos (40 linhas). Dados complementares do contribuinte
    "0005": (
        "REG", "FANTASIA", "CEP", "END", "NUM", "COMPL", "BAIRRO", "FONE",
        "FAX", "EMAIL",
    ),
    # 13 campos (4.288 linhas). Igual ao da Contribuições, campo a campo
    "0150": (
        "REG", "COD_PART", "NOME", "COD_PAIS", "CNPJ", "CPF", "IE",
        "COD_MUN", "SUFRAMA", "END", "NUM", "COMPL", "BAIRRO",
    ),
    # 3 campos (587 linhas). A unidade que o C170 cita em `UNID` — e é por aqui
    # que se descobre que `L`, `LT` e `LTS` são a mesma coisa num cliente e
    # coisas diferentes noutro
    "0190": ("REG", "UNID", "DESCR"),
    # 13 campos (9.295 linhas). O `CEST` no fim é o que o 0200 da
    # EFD-Contribuições não tem
    "0200": (
        "REG", "COD_ITEM", "DESCR_ITEM", "COD_BARRA", "COD_ANT_ITEM",
        "UNID_INV", "TIPO_ITEM", "COD_NCM", "EX_IPI", "COD_GEN",
        "COD_LST", "ALIQ_ICMS", "CEST",
    ),
    # 4 campos (17.784.662 linhas da empresa Z, 2022-01 em diante). **O
    # registro que leva o fardo ao litro**: `FAT_CONV` é quantas unidades de
    # inventário cabem na unidade do documento.
    #
    # O quarto campo é numérico em 16.071.847 linhas e **vazio em 1.712.813** —
    # é código de barra, que é opcional. A variante de 3 campos, sem ele, está
    # em `CAMPOS_ANTIGOS`: são 2.448.595 linhas, todas de 2021.
    "0220": ("REG", "UNID_CONV", "FAT_CONV", "COD_BARRA"),
    # 5 campos (60 linhas). A descrição **anterior** do item, com vigência.
    # Importa ao classificador: o mesmo código muda de nome no meio do período,
    # e medido na empresa G a descrição do diesel aparece truncada em 26
    # caracteres ("OLEO DIESEL B S-10 ORIGINA")
    "0205": ("REG", "DESCR_ANT_ITEM", "DT_INI", "DT_FIM", "COD_ANT_ITEM"),
    # 3 campos (296 linhas). Natureza da operação, que o C170 cita em COD_NAT
    "0400": ("REG", "COD_NAT", "DESCR_NAT"),
    # 3 campos (179 linhas). O texto que o C110 cita por código
    "0460": ("REG", "COD_OBS", "TXT"),
    # 29 campos (7.210 linhas)
    "C100": (
        "REG", "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT",
        "SER", "NUM_DOC", "CHV_NFE", "DT_DOC", "DT_E_S", "VL_DOC", "IND_PGTO",
        "VL_DESC", "VL_ABAT_NT", "VL_MERC", "IND_FRT", "VL_FRT", "VL_SEG",
        "VL_OUT_DA", "VL_BC_ICMS", "VL_ICMS", "VL_BC_ICMS_ST", "VL_ICMS_ST",
        "VL_IPI", "VL_PIS", "VL_COFINS", "VL_PIS_ST", "VL_COFINS_ST",
    ),
    # 3 campos (6.905 linhas). **Atenção ao terceiro campo.** O leiaute antigo
    # do C110 tem dois (`REG`, `COD_INF`), com o texto morando no `0450`. Nos
    # arquivos medidos há um terceiro, e ele é o texto — ver o topo do módulo
    # sobre por que não se deve extrair número dele
    "C110": ("REG", "COD_INF", "TXT_COMPL"),
    # 38 campos (15.107 linhas). `QTD` e `UNID` são o litro da tese; `CST_ICMS`
    # diz o regime (60 = ST, 61 = monofásico, 90 = ICMS destacado)
    "C170": (
        "REG", "NUM_ITEM", "COD_ITEM", "DESCR_COMPL", "QTD", "UNID",
        "VL_ITEM", "VL_DESC", "IND_MOV", "CST_ICMS", "CFOP", "COD_NAT",
        "VL_BC_ICMS", "ALIQ_ICMS", "VL_ICMS", "VL_BC_ICMS_ST", "ALIQ_ST",
        "VL_ICMS_ST", "IND_APUR", "CST_IPI", "COD_ENQ", "VL_BC_IPI",
        "ALIQ_IPI", "VL_IPI", "CST_PIS", "VL_BC_PIS", "ALIQ_PIS",
        "QUANT_BC_PIS", "ALIQ_PIS_QUANT", "VL_PIS", "CST_COFINS",
        "VL_BC_COFINS", "ALIQ_COFINS", "QUANT_BC_COFINS",
        "ALIQ_COFINS_QUANT", "VL_COFINS", "COD_CTA", "VL_ABAT_NT",
    ),
    # 12 campos (8.195 linhas). O analítico do documento: soma por
    # CST/CFOP/alíquota. Serve de conferência da soma do C170
    "C190": (
        "REG", "CST_ICMS", "CFOP", "ALIQ_ICMS", "VL_OPR", "VL_BC_ICMS",
        "VL_ICMS", "VL_BC_ICMS_ST", "VL_ICMS_ST", "VL_RED_BC", "VL_IPI",
        "COD_OBS",
    ),
    # 8 campos (2.481 linhas). Ajuste do documento, por item
    "C197": (
        "REG", "COD_AJ", "DESCR_COMPL_AJ", "COD_ITEM", "VL_BC_ICMS",
        "ALIQ_ICMS", "VL_ICMS", "VL_OUTROS",
    ),
    # 15 campos (40 linhas). A apuração do mês
    "E110": (
        "REG", "VL_TOT_DEBITOS", "VL_AJ_DEBITOS", "VL_TOT_AJ_DEBITOS",
        "VL_ESTORNOS_CRED", "VL_TOT_CREDITOS", "VL_AJ_CREDITOS",
        "VL_TOT_AJ_CREDITOS", "VL_ESTORNOS_DEB", "VL_SLD_CREDOR_ANT",
        "VL_SLD_APURADO", "VL_TOT_DED", "VL_ICMS_RECOLHER",
        "VL_SLD_CREDOR_TRANSPORTAR", "DEB_ESP",
    ),
    # 4 campos (37 linhas). **O registro central da auditoria**: é por ele que
    # se descobre o crédito que o cliente já tomou. Na empresa G o código é
    # `SP020799`, com `DESCR_COMPL_AJ` = "CRÉDITO DE DIESEL MONOFASICO"
    "E111": ("REG", "COD_AJ_APUR", "DESCR_COMPL_AJ", "VL_AJ_APUR"),
    # 10 campos (39 linhas). A obrigação a recolher do mês
    "E116": (
        "REG", "COD_OR", "VL_OR", "DT_VCTO", "COD_REC", "NUM_PROC",
        "IND_PROC", "PROC", "TXT_COMPL", "MES_REF",
    ),
}

# Leiautes que mudaram de tamanho e cujo arquivo antigo ainda circula, chaveados
# por `(registro, quantidade de campos da linha)` — o mesmo mecanismo de
# `registros.py`.
#
# **Por que pelo tamanho e não pela data.** A data diz de que competência é o
# arquivo; o tamanho, qual PVA o gerou. Na empresa Z os dois conviviam no mesmo
# acervo: 2,4 milhões de linhas com 3 campos e 17,8 milhões com 4.
CAMPOS_ANTIGOS: dict[tuple[str, int], tuple[str, ...]] = {
    ("0220", 3): ("REG", "UNID_CONV", "FAT_CONV"),
}

# Os registros do combustível que **ainda não se mediu** — ver o topo do módulo.
# Estão nomeados aqui, e só aqui, para que quem procurar por eles encontre a
# explicação em vez de achar que foram esquecidos.
NAO_MEDIDOS: dict[str, str] = {
    "0206": "código do produto conforme a tabela da ANP; obrigatório a quem "
            "distribui combustível, e ausente nos 40 arquivos de quem consome",
    "C171": "complemento de item para operações com combustíveis; ausente nos "
            "40 arquivos medidos",
}


class RegistroNaoMedido(LookupError):
    """Pediram um registro que se sabe existir e cujo leiaute não se mediu."""


def campos_de(registro: str, quantos: int) -> tuple[str, ...]:
    """Os nomes desta linha da EFD ICMS/IPI.

    Mesma assinatura de `registros.campos_de`, inclusive o `quantos`, para que
    um leitor possa trocar de tabela sem trocar de código — e é o `quantos` que
    resolve o `0220`, cujo leiaute tem duas larguras em circulação.
    """
    antigo = CAMPOS_ANTIGOS.get((registro, quantos))
    return antigo if antigo is not None else CAMPOS.get(registro, ())


def nomes_dos_campos(registro: str) -> tuple[str, ...]:
    """Os nomes do registro, ou vazio quando ele não está na tabela.

    Vazio em vez de erro, como em `registros.nomes_dos_campos`: registro fora
    da tabela ainda pode ser contado pelo índice.
    """
    return CAMPOS.get(registro, ())


def posicao_do_campo(registro: str, nome: str) -> int:
    """Onde o campo está na linha. Erro claro quando o nome não existe.

    Para os três registros de combustível que ainda não se mediu, a mensagem
    diz **isso**, em vez de "campo desconhecido" — a diferença importa para
    quem está depurando: um é engano de digitação, o outro é trabalho a fazer.
    """
    if registro in NAO_MEDIDOS:
        raise RegistroNaoMedido(
            f"O leiaute do {registro} não foi medido: {NAO_MEDIDOS[registro]}. "
            f"Medir contra arquivo de cliente que o traga e acrescentar em "
            f"`registros_icms.CAMPOS`.")
    nomes = nomes_dos_campos(registro)
    try:
        return nomes.index(nome)
    except ValueError:
        raise KeyError(
            f"O registro {registro} da EFD ICMS/IPI não tem campo {nome!r}. "
            f"Tem: {', '.join(nomes) if nomes else '(registro fora da tabela)'}."
        ) from None


# A tabela de cada tipo de SPED. É o único lugar que escolhe entre os dois
# módulos, e existe para que ninguém leia uma EFD ICMS/IPI com os nomes da
# Contribuições — que é possível, porque os dois têm `0000` e `0200`.
_TABELA_POR_TIPO = {
    TipoSped.EFD_ICMS_IPI: CAMPOS,
    TipoSped.EFD_CONTRIBUICOES: contribuicoes.CAMPOS,
}


def tabela_de(tipo: TipoSped) -> dict[str, tuple[str, ...]]:
    """A tabela de campos daquele tipo de arquivo.

    Levanta `KeyError` para ECD e ECF, que têm leiaute próprio e leitor próprio
    — devolver a tabela de outro arquivo seria o erro que este módulo existe
    para impedir.
    """
    try:
        return _TABELA_POR_TIPO[tipo]
    except KeyError:
        raise KeyError(
            f"{tipo.rotulo} não tem tabela de campos aqui: esta e "
            f"`registros.py` cobrem a EFD ICMS/IPI e a EFD-Contribuições."
        ) from None

"""Leitura do registro 0000 do SPED — puro, sem I/O.

Recebe a primeira linha do arquivo e devolve quem é a empresa e qual é o
período. É o que permite pré-cadastrar a empresa a partir do próprio arquivo,
sem ninguém digitar CNPJ.

Os três leiautes divergem no registro 0000, e é por isso que existe detecção
em vez de um parser só:

EFD ICMS/IPI
    |0000|COD_VER|COD_FIN|DT_INI|DT_FIN|NOME|CNPJ|CPF|UF|IE|COD_MUN|IM|
          SUFRAMA|IND_PERFIL|IND_ATIV|

EFD Contribuições
    |0000|COD_VER|TIPO_ESCRIT|IND_SIT_ESP|NUM_REC_ANTERIOR|DT_INI|DT_FIN|
          NOME|CNPJ|UF|COD_MUN|SUFRAMA|IND_NAT_PJ|IND_ATIV|

ECD
    |0000|LECD|DT_INI|DT_FIN|NOME|CNPJ|UF|IE|COD_MUN|IM|IND_SIT_ESP|...

ECF
    |0000|LECF|COD_VER|CNPJ|NOME|IND_SIT_INI_PER|SIT_ESPECIAL|PAT_REMAN_CIS|
          DT_SIT_ESP|DT_INI|DT_FIN|RETIFICADORA|NUM_REC|TIP_ECF|COD_SCP|

O discriminador do TIPO é o campo 2: `LECD` na ECD, `LECF` na ECF. Entre as
duas EFD, o campo 4 é data no ICMS/IPI e indicador de situação especial nas
Contribuições.

Mas os CAMPOS não são lidos por posição fixa, e isso é deliberado. Um arquivo
de ECD real desta casa não seguia o leiaute publicado — trazia dois campos a
mais antes das datas. Leiaute de SPED muda entre versões, e cada cliente gera
com a ferramenta que tem.

Nos três primeiros, o que nunca muda é a **sequência**: data de início, data de
fim, razão social e CNPJ vêm coladas, nessa ordem. O par de datas serve de
âncora e o resto se lê a partir dele.

**A ECF não segue essa sequência** — nela o CNPJ e o nome vêm *antes* das
datas, e ainda pode haver uma terceira data (DT_SIT_ESP) logo antes do par.
Então ela tem âncora própria, também por forma: o CNPJ é o campo de catorze
dígitos, o nome é o que vem depois dele, e o período é o **último** par de
datas consecutivas do registro. Posição fixa quebraria em silêncio; âncora
falha alto, dizendo o que não achou.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from cat.dominio.comum.cnpj import Cnpj, tentar

_RE_DATA = re.compile(r"^(\d{2})(\d{2})(\d{4})$")


class TipoSped(str, Enum):
    EFD_ICMS_IPI = "efd_icms_ipi"
    EFD_CONTRIBUICOES = "efd_contribuicoes"
    ECD = "ecd"
    ECF = "ecf"

    @property
    def rotulo(self) -> str:
        return {
            TipoSped.EFD_ICMS_IPI: "EFD ICMS/IPI",
            TipoSped.EFD_CONTRIBUICOES: "EFD Contribuições",
            TipoSped.ECD: "ECD — Escrituração Contábil Digital",
            TipoSped.ECF: "ECF — Escrituração Contábil Fiscal",
        }[self]

    @property
    def serve_para_cat(self) -> bool:
        """A CAT 42 é de ICMS-ST. Contribuições e ECD entram em outras frentes."""
        return self is TipoSped.EFD_ICMS_IPI

    @property
    def modulos(self) -> tuple[str, ...]:
        """Os módulos de trabalho que leem este arquivo.

        As chaves são as do catálogo de módulos, que vive em
        `Cat.Dominio/Acesso/Segmento.cs`; aqui só se diz qual arquivo alimenta
        qual trabalho. Sem isso a tela de cadastro media a remessa apenas pela
        CAT 42, e uma EFD-Contribuições — que é justamente o arquivo do
        trabalho de PIS/COFINS — aparecia como "0 servem".
        """
        return _MODULOS_POR_TIPO[self]


# Qual arquivo alimenta qual módulo de trabalho.
#
# A EFD ICMS/IPI aparece em dois: além de ser o arquivo da CAT 42, é ela que o
# PIS/COFINS lê para excluir o ICMS da base (Tema 69) — o mesmo que
# `cat.dominio.lote` já registra. A ECD também: dela sai o razão contábil que a
# quebra de SPED confronta com a EFD-Contribuições, e é a base contábil do
# lucro real.
_MODULOS_POR_TIPO: dict[TipoSped, tuple[str, ...]] = {
    TipoSped.EFD_ICMS_IPI: ("icms", "piscofins"),
    TipoSped.EFD_CONTRIBUICOES: ("piscofins",),
    TipoSped.ECD: ("piscofins", "irpj_csll"),
    TipoSped.ECF: ("irpj_csll",),
}


class ArquivoNaoReconhecido(ValueError):
    def __init__(self, motivo: str) -> None:
        self.motivo = motivo
        super().__init__(f"Não reconheci o arquivo como SPED: {motivo}")


@dataclass(frozen=True)
class CabecalhoSped:
    """O que o registro 0000 diz sobre a empresa e o período."""

    tipo: TipoSped
    cnpj: Cnpj | None
    nome: str
    uf: str
    inscricao_estadual: str
    codigo_municipio: str
    inicio: date
    fim: date
    versao_leiaute: str
    # Original ou retificadora. Importa porque as duas costumam estar na mesma
    # pasta, e a retificadora SUBSTITUI a original por inteiro: ler as duas
    # dobra os documentos do período e, pior, mistura valores de antes e
    # depois da retificação. A ECD não tem esse campo; fica False.
    retificadora: bool = False

    @property
    def e_matriz(self) -> bool:
        return self.cnpj is not None and self.cnpj.e_matriz

    @property
    def competencia(self) -> str:
        """Competência no formato mm/aaaa, como o pessoal fiscal fala."""
        return f"{self.inicio.month:02d}/{self.inicio.year}"

    @property
    def periodo_fechado_no_mes(self) -> bool:
        """Verdadeiro quando início e fim caem no mesmo mês.

        Arquivo que cruza meses é sinal de escrituração fora do padrão e merece
        atenção antes de virar competência no sistema.
        """
        return (self.inicio.year, self.inicio.month) == (self.fim.year, self.fim.month)


def _data(bruto: str) -> date:
    m = _RE_DATA.match((bruto or "").strip())
    if not m:
        raise ArquivoNaoReconhecido(f"data inesperada: {bruto!r}")
    dia, mes, ano = (int(g) for g in m.groups())
    try:
        return date(ano, mes, dia)
    except ValueError as erro:
        raise ArquivoNaoReconhecido(f"data inexistente: {bruto!r}") from erro


def _parece_data(bruto: str) -> bool:
    if not _RE_DATA.match((bruto or "").strip()):
        return False
    try:
        _data(bruto)
        return True
    except ArquivoNaoReconhecido:
        return False


def detectar_tipo(campos: list[str]) -> TipoSped:
    """Descobre o leiaute pelos campos do registro 0000."""
    if len(campos) < 8:
        raise ArquivoNaoReconhecido(
            f"registro 0000 com apenas {len(campos)} campos"
        )
    if campos[1].strip().upper().startswith("LECD"):
        return TipoSped.ECD
    if campos[1].strip().upper().startswith("LECF"):
        return TipoSped.ECF
    if _parece_data(campos[3]):
        return TipoSped.EFD_ICMS_IPI
    if len(campos) >= 7 and _parece_data(campos[5]):
        return TipoSped.EFD_CONTRIBUICOES
    raise ArquivoNaoReconhecido(
        "não achei a data de início onde nenhum dos leiautes conhecidos a coloca"
    )


def _achar_par_de_datas(campos: list[str]) -> int:
    """Índice da primeira data seguida de outra data.

    É a âncora: nos três leiautes vem DT_INI, DT_FIN, NOME, CNPJ, nessa ordem.
    """
    for i in range(1, len(campos) - 1):
        if _parece_data(campos[i]) and _parece_data(campos[i + 1]):
            return i
    raise ArquivoNaoReconhecido(
        "não achei o par de datas do período no registro 0000"
    )


def _ultimo_par_de_datas(campos: list[str]) -> int:
    """Índice do **último** par de datas consecutivas. É a âncora da ECF.

    A ECF pode trazer DT_SIT_ESP logo antes de DT_INI: numa empresa em situação
    especial, três datas ficam coladas e o primeiro par seria (DT_SIT_ESP,
    DT_INI) — um período começando na data da cisão. O último par é sempre
    (DT_INI, DT_FIN), porque nada depois deles no 0000 tem forma de data.
    """
    achado = -1
    for i in range(1, len(campos) - 1):
        if _parece_data(campos[i]) and _parece_data(campos[i + 1]):
            achado = i
    if achado < 0:
        raise ArquivoNaoReconhecido(
            "não achei o par de datas do período no registro 0000"
        )
    return achado


def _achar_cnpj(campos: list[str]) -> int:
    """Índice do primeiro campo com catorze dígitos. É o CNPJ da ECF.

    Não se confere o dígito aqui: CNPJ torto não pode derrubar a leitura do
    resto do cabeçalho — quem confere na tela vê o campo vazio e corrige.
    """
    for i, c in enumerate(campos):
        v = c.strip()
        if len(v) == 14 and v.isdigit():
            return i
    raise ArquivoNaoReconhecido("não achei o CNPJ no registro 0000 da ECF")


def _ler_ecf(campos: list[str], em) -> CabecalhoSped:
    """A ECF tem o CNPJ e o nome antes das datas, ao contrário dos outros três.

    UF e município **não estão** no 0000 da ECF — vêm no 0030, que é outro
    registro e não é problema deste leitor. Saem vazios, e quem precisar deles
    lê o 0030.
    """
    i_cnpj = _achar_cnpj(campos)
    nome = em(i_cnpj + 1)
    if not nome:
        raise ArquivoNaoReconhecido("o registro 0000 da ECF não traz a razão social")
    d = _ultimo_par_de_datas(campos)
    return CabecalhoSped(
        tipo=TipoSped.ECF,
        cnpj=tentar(em(i_cnpj)),
        nome=" ".join(nome.split()),
        uf="",
        inscricao_estadual="",
        codigo_municipio="",
        inicio=_data(em(d)),
        fim=_data(em(d + 1)),
        versao_leiaute=em(2),
        retificadora=em(d + 2) == "1",
    )


def _achar_uf(campos: list[str], a_partir_de: int) -> str:
    """UF é o primeiro campo de exatamente duas letras depois do CNPJ."""
    for c in campos[a_partir_de:]:
        v = c.strip().upper()
        if len(v) == 2 and v.isalpha():
            return v
    return ""


def _achar_municipio(campos: list[str], a_partir_de: int) -> str:
    """Código do IBGE: sete dígitos, e o primeiro par é o código da UF."""
    for c in campos[a_partir_de:]:
        v = c.strip()
        if len(v) == 7 and v.isdigit():
            return v
    return ""


def separar(linha: str) -> list[str]:
    """Quebra a linha do SPED nos pipes, descartando os das pontas."""
    bruto = linha.strip()
    if not bruto.startswith("|") or "|" not in bruto[1:]:
        raise ArquivoNaoReconhecido("a primeira linha não está no formato SPED")
    partes = bruto.split("|")
    return partes[1:-1] if bruto.endswith("|") else partes[1:]


def ler_cabecalho(linha: str) -> CabecalhoSped:
    """Lê o registro 0000 e devolve empresa e período."""
    campos = separar(linha)
    if not campos or campos[0].strip() != "0000":
        achado = campos[0].strip() if campos else "(vazio)"
        raise ArquivoNaoReconhecido(
            f"a primeira linha deveria ser o registro 0000, veio {achado!r}"
        )

    tipo = detectar_tipo(campos)

    def em(i: int) -> str:
        return campos[i].strip() if 0 <= i < len(campos) else ""

    if tipo is TipoSped.ECF:
        return _ler_ecf(campos, em)

    d = _achar_par_de_datas(campos)
    nome = em(d + 2)
    if not nome:
        raise ArquivoNaoReconhecido("o registro 0000 não traz a razão social")

    bruto_cnpj = em(d + 3)
    depois_do_cnpj = d + 4
    uf = _achar_uf(campos, depois_do_cnpj)
    i_uf = next(
        (i for i in range(depois_do_cnpj, len(campos))
         if uf and campos[i].strip().upper() == uf),
        -1,
    )
    # Depois da UF vem a IE no ICMS/IPI e na ECD, mas o código do município nas
    # Contribuições, que não têm IE. Distinguem-se pelo formato: o código do
    # IBGE tem exatamente sete dígitos. Sem esta checagem, a competência das
    # Contribuições entrava no sistema com o município no lugar da IE.
    proximo = em(i_uf + 1) if i_uf >= 0 else ""
    ie = "" if (len(proximo) == 7 and proximo.isdigit()) else proximo

    # A finalidade também se lê a partir da âncora, não por posição fixa. No
    # ICMS/IPI o COD_FIN é o campo imediatamente ANTES da data de início; nas
    # Contribuições o TIPO_ESCRIT vem três campos antes (TIPO_ESCRIT,
    # IND_SIT_ESP, NUM_REC_ANTERIOR, DT_INI). Nos dois, 0 é original e 1 é
    # retificadora. A ECD não tem finalidade.
    if tipo is TipoSped.EFD_ICMS_IPI:
        retificadora = em(d - 1) == "1"
    elif tipo is TipoSped.EFD_CONTRIBUICOES:
        retificadora = em(d - 3) == "1"
    else:
        retificadora = False

    return CabecalhoSped(
        tipo=tipo,
        # CNPJ torto não derruba a leitura: o resto do cabeçalho ainda serve, e
        # quem confere na tela vê o campo vazio e corrige
        cnpj=tentar(bruto_cnpj),
        nome=" ".join(nome.split()),
        uf=uf,
        inscricao_estadual=ie,
        codigo_municipio=_achar_municipio(campos, depois_do_cnpj),
        inicio=_data(em(d)),
        fim=_data(em(d + 1)),
        versao_leiaute=em(1),
        retificadora=retificadora,
    )

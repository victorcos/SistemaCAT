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

O discriminador do TIPO é o campo 2: na ECD vem `LECD`. Entre as duas EFD, o
campo 4 é data no ICMS/IPI e indicador de situação especial nas Contribuições.

Mas os CAMPOS não são lidos por posição fixa, e isso é deliberado. Um arquivo
de ECD real desta casa não seguia o leiaute publicado — trazia dois campos a
mais antes das datas. Leiaute de SPED muda entre versões, e cada cliente gera
com a ferramenta que tem.

O que nunca muda nos três leiautes é a **sequência**: data de início, data de
fim, razão social e CNPJ vêm coladas, nessa ordem. Então o par de datas serve
de âncora e o resto se lê a partir dele. Posição fixa quebraria em silêncio;
âncora falha alto, dizendo que não achou o par de datas.
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

    @property
    def rotulo(self) -> str:
        return {
            TipoSped.EFD_ICMS_IPI: "EFD ICMS/IPI",
            TipoSped.EFD_CONTRIBUICOES: "EFD Contribuições",
            TipoSped.ECD: "ECD — Escrituração Contábil Digital",
        }[self]

    @property
    def serve_para_cat(self) -> bool:
        """A CAT 42 é de ICMS-ST. Contribuições e ECD entram em outras frentes."""
        return self is TipoSped.EFD_ICMS_IPI


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

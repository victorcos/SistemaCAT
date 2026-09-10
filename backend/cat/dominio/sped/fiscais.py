"""Os documentos fiscais do SPED: C100 (nota fiscal) e C800 (cupom SAT).

São os dois registros que dizem **o que a empresa escriturou**. É contra eles
que se confrontam os XML e o relatório do cliente, e desse confronto saem as
duas listas do trabalho:

* documento na pasta e **não** na EFD — nota não escriturada, que sai da
  análise: se não foi escriturada, não compõe apuração;
* documento na EFD e **não** na pasta — falta o documento, e é o que se cobra
  do cliente.

Ambos os leiautes foram conferidos contra arquivo real desta casa antes de
serem escritos aqui, e não contra o manual. Já aconteceu de o arquivo real não
bater com o leiaute publicado (foi o caso da ECD), e um campo deslocado aqui
trocaria chave de nota por número de nota em milhões de linhas.

O C800 é de São Paulo: CF-e-SAT não existe nas outras UFs. Numa amostra da
Sulamericana, os estabelecimentos do Paraná não têm nenhum.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum

ZERO = Decimal("0")

# Tabela 4.1.2 da EFD ICMS/IPI.
_SITUACOES = {
    "00": ("Regular", True),
    "01": ("Regular, extemporâneo", True),
    "02": ("Cancelado", False),
    "03": ("Cancelado, extemporâneo", False),
    "04": ("Denegado", False),
    "05": ("Numeração inutilizada", False),
    "06": ("Complementar", True),
    "07": ("Complementar, extemporâneo", True),
    "08": ("Regime especial ou norma específica", True),
}

_MODELOS = {
    "01": "NF modelo 1/1-A",
    "04": "Nota Fiscal de Produtor",
    "06": "Conta de energia",
    "55": "NF-e",
    "57": "CT-e",
    "59": "CF-e-SAT",
    "65": "NFC-e",
}


class Operacao(str, Enum):
    ENTRADA = "entrada"
    SAIDA = "saida"

    @property
    def rotulo(self) -> str:
        return "Entrada" if self is Operacao.ENTRADA else "Saída"


class Emitente(str, Enum):
    PROPRIA = "propria"
    TERCEIROS = "terceiros"

    @property
    def rotulo(self) -> str:
        return "Emissão própria" if self is Emitente.PROPRIA else "Terceiros"


@dataclass(frozen=True)
class DocumentoEscriturado:
    """Uma linha de C100 ou C800, com o que o confronto precisa.

    Guarda pouco de propósito: a base tem centenas de milhões destes, e o que o
    confronto usa é a chave. Os demais campos existem para a planilha de
    cobrança fazer sentido para quem vai atrás do documento.
    """

    chave: str
    modelo: str
    situacao: str
    numero: str
    data: date | None
    valor: Decimal = ZERO
    serie: str = ""
    participante: str = ""
    operacao: Operacao = Operacao.SAIDA
    emitente: Emitente = Emitente.PROPRIA

    @property
    def situacao_rotulo(self) -> str:
        return _SITUACOES.get(self.situacao, ("Situação " + self.situacao, True))[0]

    @property
    def modelo_rotulo(self) -> str:
        return _MODELOS.get(self.modelo, f"Modelo {self.modelo}")

    @property
    def vale_na_apuracao(self) -> bool:
        """Cancelado, denegado e inutilizado não entram em apuração nenhuma."""
        return _SITUACOES.get(self.situacao, ("", True))[1]

    @property
    def pode_ser_cobrado(self) -> bool:
        """Se faz sentido pedir este documento ao cliente.

        Não faz para cancelado nem denegado — a operação não existe —, e menos
        ainda para numeração inutilizada, em que documento nenhum chegou a
        existir. Mandar isso numa planilha de cobrança queima a conversa com o
        cliente e atrasa o que interessa.
        """
        return self.vale_na_apuracao

    @property
    def sem_chave(self) -> bool:
        return len(self.chave) != 44


def _texto(campos: list[str], i: int) -> str:
    return campos[i].strip() if i < len(campos) else ""


def _data(bruto: str) -> date | None:
    """ddmmaaaa, como o SPED escreve. Vazio é vazio, não é erro."""
    b = bruto.strip()
    if len(b) != 8 or not b.isdigit():
        return None
    try:
        return date(int(b[4:]), int(b[2:4]), int(b[:2]))
    except ValueError:
        return None


def _decimal(bruto: str) -> Decimal:
    b = bruto.strip().replace(".", "").replace(",", ".")
    if not b:
        return ZERO
    try:
        return Decimal(b)
    except InvalidOperation:
        return ZERO


def ler_c100(campos: list[str]) -> DocumentoEscriturado:
    """|C100|IND_OPER|IND_EMIT|COD_PART|COD_MOD|COD_SIT|SER|NUM_DOC|CHV_NFE|…

    Conferido em arquivo real: 29 campos, chave na posição 9.
    """
    return DocumentoEscriturado(
        chave=_texto(campos, 9),
        modelo=_texto(campos, 5),
        situacao=_texto(campos, 6),
        serie=_texto(campos, 7),
        numero=_texto(campos, 8),
        data=_data(_texto(campos, 10)),
        valor=_decimal(_texto(campos, 12)),
        participante=_texto(campos, 4),
        operacao=Operacao.ENTRADA if _texto(campos, 2) == "0" else Operacao.SAIDA,
        emitente=Emitente.PROPRIA if _texto(campos, 3) == "0" else Emitente.TERCEIROS,
    )


def ler_c800(campos: list[str]) -> DocumentoEscriturado:
    """|C800|COD_MOD|COD_SIT|NUM_CFE|DT_DOC|VL_CFE|…|NR_SAT|CHV_CFE|…

    Conferido em arquivo real: 17 campos, chave na posição 11.

    Cupom SAT é sempre saída e sempre de emissão própria — o equipamento é da
    própria empresa. O participante costuma vir vazio: venda a consumidor não
    identificado.
    """
    return DocumentoEscriturado(
        chave=_texto(campos, 11),
        modelo=_texto(campos, 2) or "59",
        situacao=_texto(campos, 3),
        numero=_texto(campos, 4),
        data=_data(_texto(campos, 5)),
        valor=_decimal(_texto(campos, 6)),
        participante=_texto(campos, 9),
        operacao=Operacao.SAIDA,
        emitente=Emitente.PROPRIA,
    )


# byte a byte, sem quebrar a linha: numa varredura de 119,82 GB isso valeu 2,4
# vezes de diferença. Só quem passa no prefixo é quebrado em campos.
PREFIXOS = (b"|C100|", b"|C800|")

_LEITORES = {"C100": ler_c100, "C800": ler_c800}


def ler_documento(linha: str) -> DocumentoEscriturado | None:
    """Devolve o documento se a linha for C100 ou C800; senão, nada."""
    if not linha.startswith(("|C100|", "|C800|")):
        return None
    campos = linha.rstrip("\r\n").split("|")
    return _LEITORES[campos[1]](campos)

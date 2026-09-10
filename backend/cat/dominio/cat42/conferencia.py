"""Confronto entre o que foi escriturado e o documento que existe na pasta.

É a primeira análise do trabalho, e existe porque as duas fontes quase nunca
fecham. Da diferença saem duas listas, com destinos opostos:

**Não escriturada** — o XML está na pasta e a nota não está na EFD. Sai da
análise. Nota não escriturada não compõe apuração: o ressarcimento se pede
sobre o que foi declarado ao fisco, e incluir o que não foi declarado é
construir crédito em cima de documento que a SEFAZ não vê. Vira aviso na tela,
para alguém decidir se é erro de escrituração do cliente.

**Sem documento** — a nota está na EFD e o documento não está na pasta. É o que
se cobra do cliente. Sem o XML não há como saber o ICMS-ST retido, e sem o ST
retido não há ressarcimento daquela nota.

A chave de acesso é o que amarra os dois lados: 44 dígitos, única por
documento, presente no C100 (`CHV_NFE`), no C800 (`CHV_CFE`), no XML e na
coluna `Chave DFe` do relatório gerencial. Casar por número e série seria
frágil — série se repete entre estabelecimentos e número reinicia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

ZERO = Decimal("0")


def _numero(n: int) -> str:
    """Milhar com ponto, como se escreve em português.

    Formatar o número à parte e não a frase inteira: aplicar a troca de vírgula
    por ponto no texto todo comia a pontuação da própria frase.
    """
    return f"{n:,}".replace(",", ".")


class Origem(str, Enum):
    """De onde veio o documento que a empresa entregou."""

    XML = "xml"
    GERENCIAL = "gerencial"

    @property
    def rotulo(self) -> str:
        return "XML" if self is Origem.XML else "Relatório do cliente"


class Divergencia(str, Enum):
    NAO_ESCRITURADA = "nao_escriturada"
    SEM_DOCUMENTO = "sem_documento"

    @property
    def rotulo(self) -> str:
        return {
            Divergencia.NAO_ESCRITURADA: "Notas não escrituradas",
            Divergencia.SEM_DOCUMENTO: "Notas pendentes de documento",
        }[self]

    @property
    def explicacao(self) -> str:
        return {
            Divergencia.NAO_ESCRITURADA:
                "O documento está na pasta e a nota não está na EFD. Fica fora "
                "da análise: ressarcimento se pede sobre o que foi declarado.",
            Divergencia.SEM_DOCUMENTO:
                "A nota está na EFD e o documento não veio. Sem ele não há "
                "como saber o ICMS-ST retido — é o que se cobra do cliente.",
        }[self]

    @property
    def acao(self) -> str:
        return {
            Divergencia.NAO_ESCRITURADA: "Conferir com o cliente",
            Divergencia.SEM_DOCUMENTO: "Cobrar do cliente",
        }[self]


@dataclass(frozen=True)
class Fatia:
    """Um recorte da contagem: por modelo, por operação, por competência."""

    rotulo: str
    documentos: int
    valor: Decimal = ZERO
    # o código cru (modelo "55", "65"…). O front precisa dele para filtrar a
    # planilha de cobrança por modelo, que é o que torna a lista utilizável
    codigo: str = ""


@dataclass
class ResumoDaConferencia:
    """O que a tela mostra e o que os dois botões exportam.

    Só números e recortes: as listas em si podem ter milhões de linhas e vivem
    em parquet, não em memória nem no banco.
    """

    escriturados: int = 0
    conferidos: int = 0                 # escriturados que têm documento
    nao_escrituradas: int = 0
    sem_documento: int = 0
    sem_documento_cobravel: int = 0     # tira cancelada, denegada e inutilizada
    documentos_na_pasta: int = 0

    valor_conferido: Decimal = ZERO
    valor_nao_escriturado: Decimal = ZERO
    valor_sem_documento: Decimal = ZERO

    sem_chave_na_efd: int = 0
    origens: list[Origem] = field(default_factory=list)
    por_modelo: list[Fatia] = field(default_factory=list)
    por_operacao: list[Fatia] = field(default_factory=list)

    @property
    def cobertura(self) -> float:
        """Fração das notas escrituradas que têm documento. Zero a um."""
        if not self.escriturados:
            return 0.0
        return self.conferidos / self.escriturados

    @property
    def fecha(self) -> bool:
        return self.sem_documento == 0 and self.nao_escrituradas == 0

    @property
    def avisos(self) -> list[str]:
        avisos: list[str] = []
        if not self.origens:
            avisos.append(
                "Nenhum XML nem relatório do cliente no lote. Sem documento "
                "para confrontar, a conferência não diz nada."
            )
        if self.sem_chave_na_efd:
            avisos.append(
                f"{_numero(self.sem_chave_na_efd)} documento(s) da EFD estão sem "
                "chave de acesso e ficaram fora do confronto — costuma ser nota "
                "modelo 1 ou cupom antigo, que não tem chave."
            )
        fora_da_cobranca = self.sem_documento - self.sem_documento_cobravel
        if fora_da_cobranca > 0:
            avisos.append(
                f"{_numero(fora_da_cobranca)} das notas sem documento estão "
                "canceladas, denegadas ou com numeração inutilizada, e ficaram "
                "fora da cobrança: não existe documento a pedir."
            )
        if self.nao_escrituradas:
            avisos.append(
                f"{_numero(self.nao_escrituradas)} nota(s) da pasta não estão na "
                "EFD e saíram da análise."
            )
        return avisos

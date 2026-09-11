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


def _lista(cnpjs: list[str], ate: int = 3) -> str:
    mostrados = ", ".join(cnpjs[:ate])
    return f"{mostrados} e mais {len(cnpjs) - ate}" if len(cnpjs) > ate else mostrados


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
    por_classificacao: list[Fatia] = field(default_factory=list)

    # de quais estabelecimentos é cada lado. Quando não se cruzam, nada
    # pode casar — e a causa é sempre a mesma: importaram a EFD de uma
    # filial e os XML de outra.
    estabelecimentos_da_efd: list[str] = field(default_factory=list)
    emitentes_na_pasta: list[str] = field(default_factory=list)

    # EFD originais que ficaram fora da leitura porque havia retificadora
    # do mesmo estabelecimento e período no lote
    efd_originais_substituidas: int = 0

    # ---- o que andou desde a rodada anterior ----
    # O trabalho não termina na primeira conferência: o cliente manda o que
    # faltava e ela roda de novo. Sem estes números, a segunda rodada só diz
    # "ainda faltam 62.973" e ninguém sabe se andou.
    comparou: bool = False
    pendencias_resolvidas: int = 0
    pendencias_que_permanecem: int = 0
    pendencias_novas: int = 0

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
        if (self.conferidos == 0 and self.escriturados
                and self.documentos_na_pasta
                and self.estabelecimentos_da_efd and self.emitentes_na_pasta
                and not set(self.estabelecimentos_da_efd)
                        & set(self.emitentes_na_pasta)):
            avisos.append(
                "Nenhum documento casou, e o motivo não é falta de documento: "
                f"a EFD importada é do(s) estabelecimento(s) "
                f"{_lista(self.estabelecimentos_da_efd)} e os documentos da "
                f"pasta são de {_lista(self.emitentes_na_pasta)}. São filiais "
                "diferentes — importe a EFD e os XML do mesmo estabelecimento."
            )
        if self.efd_originais_substituidas:
            avisos.append(
                f"{_numero(self.efd_originais_substituidas)} EFD original(is) "
                "ficaram fora da leitura: havia retificadora do mesmo "
                "estabelecimento e período no lote, e a retificadora substitui "
                "a original por inteiro."
            )
        if self.sem_chave_na_efd:
            avisos.append(
                f"{_numero(self.sem_chave_na_efd)} documento(s) da EFD estão sem "
                "chave de acesso — costuma ser nota modelo 1 ou cupom antigo. "
                "Entram na lista marcados como 'conferir à mão': não dá para "
                "casar por chave, mas eles não somem do controle."
            )
        marcadas = self.sem_documento - self.sem_documento_cobravel
        if marcadas > 0:
            avisos.append(
                f"{_numero(marcadas)} das pendências são canceladas, denegadas, "
                "inutilizadas ou sem chave. Continuam na lista, marcadas — de "
                "cancelada e denegada não se espera documento, mas quem decide "
                "pedir ou não é quem trabalha, não o sistema."
            )
        if self.nao_escrituradas:
            avisos.append(
                f"{_numero(self.nao_escrituradas)} nota(s) da pasta não estão na "
                "EFD e saíram da análise."
            )
        return avisos

    @property
    def andou(self) -> str:
        """Uma frase sobre o que mudou desde a rodada anterior."""
        if not self.comparou:
            return ""
        partes = [f"{_numero(self.pendencias_resolvidas)} resolvida(s)"]
        if self.pendencias_novas:
            partes.append(f"{_numero(self.pendencias_novas)} nova(s)")
        partes.append(f"{_numero(self.pendencias_que_permanecem)} ainda pendente(s)")
        return ", ".join(partes)

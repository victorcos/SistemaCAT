"""O lote de arquivos de um trabalho — o que entra para ser analisado.

Isto é outra coisa do que a remessa do cadastro, e a diferença é o motivo de
existirem os dois caminhos:

* **cadastro** recebe uma amostra do SPED, lê só o cabeçalho e descobre de quem
  é a empresa. Termina com empresa e projeto criados. É pequeno e é uma vez.
* **lote** é a base de trabalho: o SPED de todas as competências e filiais, os
  XML das notas, os relatórios gerenciais. É o que as etapas seguintes leem.
  São gigabytes, e volta mais de uma vez — a empresa manda o que faltou, manda
  o ano seguinte, manda o relatório que o ERP só soltou depois.

Por isso o lote **aponta para uma pasta**, em vez de subir arquivo pelo
navegador. A maior base que medimos tem 7.036 arquivos, e um único relatório
gerencial tem 194 MB. Subir isso pela tela não é lento: é inviável. O sistema
roda na máquina de quem trabalha, que já enxerga a pasta de rede.

O que o lote guarda de cada arquivo é o suficiente para a etapa seguinte saber
o que abrir e o que ignorar: onde está, o que é, de quem é e de quando é.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Grupo(str, Enum):
    """De qual fonte o arquivo vem. Decide quem o lê."""

    SPED = "sped"
    XML = "xml"
    GERENCIAL = "gerencial"
    COMPACTADO = "compactado"
    OUTRO = "outro"

    @property
    def rotulo(self) -> str:
        return {
            Grupo.SPED: "SPED",
            Grupo.XML: "XML",
            Grupo.GERENCIAL: "Relatório gerencial",
            Grupo.COMPACTADO: "Compactado",
            Grupo.OUTRO: "Outro",
        }[self]


class TipoDeArquivo(str, Enum):
    SPED_ICMS_IPI = "sped_icms_ipi"
    SPED_CONTRIBUICOES = "sped_contribuicoes"
    SPED_ECD = "sped_ecd"
    SPED_OUTRO = "sped_outro"
    XML_NFE = "xml_nfe"
    XML_OUTRO = "xml_outro"
    GERENCIAL_MOVIMENTO = "gerencial_movimento"
    GERENCIAL_INVENTARIO = "gerencial_inventario"
    GERENCIAL_RESUMO = "gerencial_resumo"
    COMPACTADO = "compactado"
    NAO_BAIXADO = "nao_baixado"
    DESCONHECIDO = "desconhecido"

    @property
    def rotulo(self) -> str:
        return {
            TipoDeArquivo.SPED_ICMS_IPI: "EFD ICMS/IPI",
            TipoDeArquivo.SPED_CONTRIBUICOES: "EFD Contribuições",
            TipoDeArquivo.SPED_ECD: "ECD",
            TipoDeArquivo.SPED_OUTRO: "SPED de outro tipo",
            TipoDeArquivo.XML_NFE: "XML de NF-e",
            TipoDeArquivo.XML_OUTRO: "XML de outro documento",
            TipoDeArquivo.GERENCIAL_MOVIMENTO: "Relatório de movimento",
            TipoDeArquivo.GERENCIAL_INVENTARIO: "Relatório de inventário",
            TipoDeArquivo.GERENCIAL_RESUMO: "Resumo por produto",
            TipoDeArquivo.COMPACTADO: "Compactado",
            TipoDeArquivo.NAO_BAIXADO: "Não baixado do OneDrive",
            TipoDeArquivo.DESCONHECIDO: "Não reconhecido",
        }[self]

    @property
    def grupo(self) -> Grupo:
        if self.value.startswith("sped"):
            return Grupo.SPED
        if self.value.startswith("xml"):
            return Grupo.XML
        if self.value.startswith("gerencial"):
            return Grupo.GERENCIAL
        if self is TipoDeArquivo.COMPACTADO:
            return Grupo.COMPACTADO
        return Grupo.OUTRO

    @property
    def alimenta_a_cat(self) -> bool:
        """Se a apuração da CAT 42 lê este arquivo.

        A EFD Contribuições e a ECD entram na mesma pasta o tempo todo e não
        servem: PIS/COFINS e contabilidade não têm ICMS-ST. Aceitar sem
        distinguir faria o sistema dizer que a base está completa quando não
        está.
        """
        return self in _ALIMENTAM


_ALIMENTAM = frozenset({
    TipoDeArquivo.SPED_ICMS_IPI,
    TipoDeArquivo.XML_NFE,
    TipoDeArquivo.GERENCIAL_MOVIMENTO,
    TipoDeArquivo.GERENCIAL_INVENTARIO,
})


@dataclass(frozen=True)
class ArquivoDoLote:
    """Um arquivo da pasta, já identificado."""

    caminho: str
    nome: str
    tamanho: int
    tipo: TipoDeArquivo
    cnpj: str | None = None
    competencia: date | None = None
    uf: str = ""
    detalhe: str = ""      # o que o classificador conseguiu dizer a mais
    motivo: str = ""       # por que não foi reconhecido

    @property
    def alimenta_a_cat(self) -> bool:
        return self.tipo.alimenta_a_cat


@dataclass
class ResumoDoLote:
    """O que a pasta tem, do jeito que a tela precisa mostrar.

    Os arquivos de outra empresa ficam à parte de propósito. Pasta de rede é
    compartilhada e mistura cliente: entrar dado de uma empresa no trabalho de
    outra é o pior acidente possível aqui, e o sistema tem de barrar sozinho,
    não confiar em quem escolheu a pasta.
    """

    pasta: str = ""
    arquivos: list[ArquivoDoLote] = field(default_factory=list)
    de_outra_empresa: list[ArquivoDoLote] = field(default_factory=list)
    ignorados: int = 0
    limite_atingido: bool = False

    @property
    def total(self) -> int:
        return len(self.arquivos)

    @property
    def bytes_totais(self) -> int:
        return sum(a.tamanho for a in self.arquivos)

    @property
    def uteis(self) -> list[ArquivoDoLote]:
        return [a for a in self.arquivos if a.alimenta_a_cat]

    @property
    def por_tipo(self) -> dict[TipoDeArquivo, int]:
        contagem: dict[TipoDeArquivo, int] = {}
        for a in self.arquivos:
            contagem[a.tipo] = contagem.get(a.tipo, 0) + 1
        return contagem

    @property
    def competencias(self) -> list[date]:
        """Só do que a CAT lê.

        A EFD Contribuições de 2021 na mesma pasta faria o lote anunciar que
        cobre desde 2021, quando a apuração não vai olhar aquele arquivo. O
        período que interessa é o do dado que entra no trabalho.
        """
        return sorted({a.competencia for a in self.uteis if a.competencia})

    @property
    def cnpjs(self) -> list[str]:
        return sorted({a.cnpj for a in self.arquivos if a.cnpj})

    @property
    def serve(self) -> bool:
        """O lote só vale a pena se traz algo que a CAT 42 lê."""
        return any(a.alimenta_a_cat for a in self.arquivos)

    @property
    def avisos(self) -> list[str]:
        """O que quem confirma precisa saber antes de confirmar."""
        avisos: list[str] = []
        if self.de_outra_empresa:
            cnpjs = sorted({a.cnpj for a in self.de_outra_empresa if a.cnpj})
            avisos.append(
                f"{len(self.de_outra_empresa)} arquivo(s) são de outra empresa "
                f"({', '.join(cnpjs[:3])}{'…' if len(cnpjs) > 3 else ''}) e "
                "ficaram de fora."
            )
        nao_baixados = self.por_tipo.get(TipoDeArquivo.NAO_BAIXADO, 0)
        if nao_baixados:
            avisos.append(
                f"{nao_baixados} arquivo(s) existem só como marca de erro de "
                "sincronização: o conteúdo nunca desceu para a pasta. Abra-os "
                "na origem antes de contar com eles."
            )
        compactados = self.por_tipo.get(TipoDeArquivo.COMPACTADO, 0)
        if compactados:
            avisos.append(
                f"{compactados} arquivo(s) compactados não foram abertos. "
                "Descompacte na pasta para que entrem no lote."
            )
        desconhecidos = self.por_tipo.get(TipoDeArquivo.DESCONHECIDO, 0)
        if desconhecidos:
            avisos.append(f"{desconhecidos} arquivo(s) não foram reconhecidos.")
        if self.limite_atingido:
            avisos.append(
                "A pasta tem mais arquivos do que o limite de uma varredura. "
                "Importe por subpasta."
            )
        if not self.serve and self.arquivos:
            avisos.append(
                "Nenhum arquivo desta pasta alimenta a CAT 42. Falta a EFD "
                "ICMS/IPI, o XML das notas ou o relatório gerencial."
            )
        return avisos

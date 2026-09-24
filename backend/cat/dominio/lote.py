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

import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from cat.dominio.comum.modulos import MODULO_PADRAO, rotulo as rotulo_do_modulo

# ---------------------------------------------------------------------------
# Certificado digital: não se abre, não se lista
# ---------------------------------------------------------------------------
# A pasta do cliente costuma trazer o certificado A1 (.pfx/.p12), e o nome do
# arquivo muitas vezes carrega a senha. O lote não lê o arquivo nem grava o
# nome: a pasta com "certificado" no nome não é aberta, e o .pfx/.p12 solto é
# pulado. O que fica é a contagem (decisão do Victor, 17/09/2026).
EXTENSOES_DE_CERTIFICADO = (".pfx", ".p12")
# a palavra inteira: "CERTIFICADOS", "05 - Certificado"; não "Certificadora Ltda"
_RE_PASTA_DE_CERTIFICADO = re.compile(r"(?<![a-z])certificados?(?![a-z])")


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def e_arquivo_de_certificado(nome: str) -> bool:
    """O .pfx/.p12, e o compactado com "certificado" no nome — que é como ele costuma ir junto."""
    minusculo = nome.lower()
    if minusculo.endswith(EXTENSOES_DE_CERTIFICADO):
        return True
    raiz, extensao = os.path.splitext(minusculo)
    return extensao in (".zip", ".rar", ".7z") and e_pasta_de_certificado(raiz)


def e_pasta_de_certificado(nome: str) -> bool:
    return _RE_PASTA_DE_CERTIFICADO.search(_sem_acento(nome)) is not None


def caminho_de_certificado(caminho: str) -> bool:
    """Algum pedaço do caminho é pasta de certificado, ou o arquivo é um certificado.

    Serve para membro de zip, que vem com as pastas no nome (`CERTIFICADOS/x.pfx`).
    """
    partes = [p for p in caminho.replace("\\", "/").split("/") if p]
    if not partes:
        return False
    return e_arquivo_de_certificado(partes[-1]) or any(e_pasta_de_certificado(p) for p in partes[:-1])


def abas_de_canceladas(titulos: list[str]) -> list[str]:
    """As abas de uma planilha de canceladas que listam, de fato, notas canceladas.

    O relatório "NF-e Canceladas-Devoluções" da Advertising tem duas abas: as
    canceladas e as devoluções. Ler as duas tirava da movimentação 245
    devoluções que nunca foram canceladas. Vale a aba com "cancel" no nome;
    sem nenhuma assim, todas, menos a que diz "devol".
    """
    com_cancel = [t for t in titulos if "cancel" in _sem_acento(t)]
    if com_cancel:
        return com_cancel
    return [t for t in titulos if "devol" not in _sem_acento(t)]


@dataclass
class CertificadosIgnorados:
    """Quantos ficaram de fora sem ser abertos. Nome nenhum."""

    pastas: int = 0
    arquivos: int = 0


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
    # ECF: a escrituração contábil fiscal, de onde saem IRPJ e CSLL
    SPED_ECF = "sped_ecf"
    SPED_OUTRO = "sped_outro"
    XML_NFE = "xml_nfe"
    XML_OUTRO = "xml_outro"
    # evento de cancelamento de NF-e (procEventoNFe 110111): tira a nota da movimentação
    XML_CANCELAMENTO = "xml_cancelamento"
    # zip com XML de NF-e ou CF-e: as etapas leem os membros sem extrair
    XML_COMPACTADO = "xml_compactado"
    GERENCIAL_MOVIMENTO = "gerencial_movimento"
    GERENCIAL_INVENTARIO = "gerencial_inventario"
    GERENCIAL_RESUMO = "gerencial_resumo"
    # o TXT que o cliente transmitiu à SEFAZ, gerado por outra ferramenta: não
    # alimenta a apuração, é o que a pré-validação do cliente lê
    CAT42_ARQUIVO_DIGITAL = "cat42_arquivo_digital"
    # lista de chaves canceladas na SEFAZ (TXT, CSV ou planilha com "cancel" no nome)
    LISTA_DE_CANCELADAS = "lista_de_canceladas"
    COMPACTADO = "compactado"
    NAO_BAIXADO = "nao_baixado"
    DESCONHECIDO = "desconhecido"

    @property
    def rotulo(self) -> str:
        return {
            TipoDeArquivo.SPED_ICMS_IPI: "EFD ICMS/IPI",
            TipoDeArquivo.SPED_CONTRIBUICOES: "EFD Contribuições",
            TipoDeArquivo.SPED_ECD: "ECD",
            TipoDeArquivo.SPED_ECF: "ECF",
            TipoDeArquivo.SPED_OUTRO: "SPED de outro tipo",
            TipoDeArquivo.XML_NFE: "XML de NF-e ou CF-e",
            TipoDeArquivo.XML_OUTRO: "XML de outro documento",
            TipoDeArquivo.XML_CANCELAMENTO: "Evento de cancelamento de NF-e",
            TipoDeArquivo.XML_COMPACTADO: "Zip de XML",
            TipoDeArquivo.GERENCIAL_MOVIMENTO: "Relatório de movimento",
            TipoDeArquivo.GERENCIAL_INVENTARIO: "Relatório de inventário",
            TipoDeArquivo.GERENCIAL_RESUMO: "Resumo por produto",
            TipoDeArquivo.CAT42_ARQUIVO_DIGITAL: "Arquivo digital da CAT 42",
            TipoDeArquivo.LISTA_DE_CANCELADAS: "Lista de notas canceladas",
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
    def modulos(self) -> tuple[str, ...]:
        """Os módulos de trabalho que leem este arquivo.

        Não existe arquivo "útil" no absoluto: útil é sempre em relação ao
        trabalho. A EFD Contribuições não tem ICMS-ST e não serve à CAT 42 —
        mas é o arquivo do trabalho de PIS/COFINS. Enquanto isto era um
        sim/não da CAT, a importação de uma pasta de PIS/COFINS era recusada
        inteira, com "nada aqui alimenta a CAT 42".
        """
        return _MODULOS_POR_TIPO.get(self, ())

    def alimenta(self, modulo: str) -> bool:
        """Se o trabalho deste módulo lê este arquivo."""
        return modulo in self.modulos

    @property
    def alimenta_a_cat(self) -> bool:
        """Atalho do módulo de ICMS, que é o da CAT 42."""
        return self.alimenta("icms")


# As chaves são as do catálogo de módulos (Cat.Dominio/Acesso/Segmento.cs). A
# EFD ICMS/IPI serve a dois: é a base da CAT 42 e é dela que sai a exclusão do
# ICMS da base do PIS/COFINS. A ECD também: razão contábil na quebra de SPED e
# base contábil do lucro real. O XML entrou no PIS/COFINS em 24/09/2026, com a
# trilha de quebra de XML: é lá que estão o CST e a alíquota que o C170
# consolidado esconde. O evento de cancelamento e a lista de canceladas, não —
# quem os usa é a conferência da CAT 42.
_MODULOS_POR_TIPO: dict[TipoDeArquivo, tuple[str, ...]] = {
    TipoDeArquivo.SPED_ICMS_IPI: ("icms", "piscofins"),
    TipoDeArquivo.SPED_CONTRIBUICOES: ("piscofins",),
    TipoDeArquivo.SPED_ECD: ("piscofins", "irpj_csll"),
    TipoDeArquivo.SPED_ECF: ("irpj_csll",),
    TipoDeArquivo.XML_NFE: ("icms", "piscofins"),
    TipoDeArquivo.XML_CANCELAMENTO: ("icms",),
    TipoDeArquivo.XML_COMPACTADO: ("icms", "piscofins"),
    TipoDeArquivo.GERENCIAL_MOVIMENTO: ("icms",),
    TipoDeArquivo.GERENCIAL_INVENTARIO: ("icms",),
    TipoDeArquivo.LISTA_DE_CANCELADAS: ("icms",),
}

# O que cada trabalho espera receber, para a mensagem de pasta que não serve.
FALTA_POR_MODULO: dict[str, str] = {
    "icms": "Falta a EFD ICMS/IPI, o XML das notas ou o relatório gerencial.",
    "piscofins": "Falta a EFD-Contribuições, a ECD, a EFD ICMS/IPI ou o XML das notas.",
    "irpj_csll": "Falta a ECF ou a ECD.",
}


@dataclass(frozen=True)
class ArquivoDoLote:
    """Um arquivo da pasta, já identificado."""

    caminho: str
    nome: str
    tamanho: int
    tipo: TipoDeArquivo
    # de quem é. No SPED é o estabelecimento que gerou o arquivo; no XML é o
    # EMITENTE — e numa nota que a empresa recebe do fornecedor, o emitente
    # é o fornecedor. Por isso o XML carrega também o destinatário: a nota é
    # da empresa se ela estiver em qualquer uma das duas pontas.
    cnpj: str | None = None
    cnpj_destinatario: str | None = None
    competencia: date | None = None
    uf: str = ""
    detalhe: str = ""      # o que o classificador conseguiu dizer a mais
    motivo: str = ""       # por que não foi reconhecido
    # SPED retificador. Substitui a original do mesmo estabelecimento e
    # período por inteiro — as duas na mesma pasta é o caso comum.
    retificadora: bool = False
    # SHA-256 do conteúdo. Só é calculado quando há candidato a cópia —
    # outro arquivo com o mesmo tamanho, tipo, CNPJ, competência e
    # finalidade. Ler 100 GB inteiros a cada importação não se justifica
    # para um problema que tamanho e cabeçalho já filtram quase todo.
    hash_conteudo: str | None = None
    # Este mesmo arquivo já foi lido num OUTRO trabalho da mesma empresa —
    # guarda o nome dele. Não é cópia a recusar: é leitura a reaproveitar.
    # A exclusão do ICMS da base do PIS/COFINS precisa da EFD ICMS/IPI que o
    # trabalho de ICMS já importou, e reindexar 119 GB por causa disso seria
    # pagar duas vezes pelo mesmo byte (decisão do Victor, 22/09/2026).
    ja_lido_em: str = ""

    @property
    def reaproveitado(self) -> bool:
        return bool(self.ja_lido_em)

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
    # o módulo do trabalho que vai receber esta pasta: é ele que decide quais
    # arquivos são úteis. "icms" por padrão, que é o de todo trabalho anterior
    # à divisão por tributo
    modulo: str = MODULO_PADRAO
    arquivos: list[ArquivoDoLote] = field(default_factory=list)
    de_outra_empresa: list[ArquivoDoLote] = field(default_factory=list)
    # cópias exatas: (a cópia, de quem ela é cópia). Ficam fora de
    # `arquivos` — o mesmo SPED lido duas vezes dobra os documentos.
    copias: list[tuple[ArquivoDoLote, str]] = field(default_factory=list)
    ignorados: int = 0
    limite_atingido: bool = False
    certificados: CertificadosIgnorados = field(default_factory=CertificadosIgnorados)

    @property
    def total(self) -> int:
        return len(self.arquivos)

    @property
    def reaproveitados(self) -> list[ArquivoDoLote]:
        """Os que outro trabalho desta empresa já leu.

        Entram no lote — o trabalho novo precisa deles —, mas já se sabe que a
        leitura não custa: o material derivado está em disco. É o que permite o
        PIS/COFINS usar a EFD ICMS/IPI sem reindexá-la.
        """
        return [a for a in self.arquivos if a.reaproveitado]

    @property
    def bytes_totais(self) -> int:
        return sum(a.tamanho for a in self.arquivos)

    @property
    def uteis(self) -> list[ArquivoDoLote]:
        """Os que o trabalho DESTE módulo lê."""
        return [a for a in self.arquivos if a.tipo.alimenta(self.modulo)]

    @property
    def por_tipo(self) -> dict[TipoDeArquivo, int]:
        contagem: dict[TipoDeArquivo, int] = {}
        for a in self.arquivos:
            contagem[a.tipo] = contagem.get(a.tipo, 0) + 1
        return contagem

    @property
    def competencias(self) -> list[date]:
        """Só do que este trabalho lê.

        Num trabalho de ICMS, a EFD Contribuições de 2021 na mesma pasta faria
        o lote anunciar que cobre desde 2021, quando a apuração não vai olhar
        aquele arquivo. O período que interessa é o do dado que entra no
        trabalho — e qual dado é esse depende do módulo.
        """
        return sorted({a.competencia for a in self.uteis if a.competencia})

    @property
    def cnpjs(self) -> list[str]:
        return sorted({a.cnpj for a in self.arquivos if a.cnpj})

    @property
    def substituidas_por_retificadora(self) -> list[ArquivoDoLote]:
        """EFD originais que têm retificadora do mesmo estabelecimento e
        período nesta mesma pasta. A conferência vai ler só a retificadora."""
        retificadas = {
            (a.cnpj, a.competencia) for a in self.arquivos
            if a.tipo is TipoDeArquivo.SPED_ICMS_IPI and a.retificadora
        }
        return [
            a for a in self.arquivos
            if a.tipo is TipoDeArquivo.SPED_ICMS_IPI and not a.retificadora
            and (a.cnpj, a.competencia) in retificadas
        ]

    @property
    def serve(self) -> bool:
        """O lote só vale a pena se traz algo que este trabalho lê."""
        return any(a.tipo.alimenta(self.modulo) for a in self.arquivos)

    @property
    def avisos(self) -> list[str]:
        """O que quem confirma precisa saber antes de confirmar."""
        avisos: list[str] = []
        if self.certificados.pastas or self.certificados.arquivos:
            partes = []
            if self.certificados.pastas:
                partes.append(f"{self.certificados.pastas} pasta(s) de certificado")
            if self.certificados.arquivos:
                partes.append(f"{self.certificados.arquivos} arquivo(s) de certificado")
            avisos.append(
                f"{' e '.join(partes)} ficaram de fora sem ser abertos. O nome não é "
                "gravado: costuma carregar a senha do certificado."
            )
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
        if self.copias:
            de_fora = sum(1 for _, de in self.copias if de.startswith("já"))
            na_pasta = len(self.copias) - de_fora
            partes = []
            if na_pasta:
                partes.append(f"{na_pasta} são cópia exata de outro arquivo "
                              "desta mesma pasta")
            if de_fora:
                partes.append(f"{de_fora} são cópia exata de arquivo que já "
                              "está no trabalho")
            avisos.append(
                f"{len(self.copias)} arquivo(s) ficaram de fora: "
                + "; ".join(partes)
                + ". Conteúdo idêntico, byte a byte — só o nome ou a pasta "
                "mudou. O mesmo SPED lido duas vezes dobraria os documentos."
            )
        substituidas = self.substituidas_por_retificadora
        if substituidas:
            avisos.append(
                f"{len(substituidas)} EFD original(is) têm retificadora do mesmo "
                "estabelecimento e período nesta pasta. Entram no lote, mas a "
                "conferência lê só a retificadora: ela substitui a original "
                "por inteiro, e ler as duas dobraria os documentos do período."
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
                f"Nenhum arquivo desta pasta alimenta o trabalho de "
                f"{rotulo_do_modulo(self.modulo)}. "
                + FALTA_POR_MODULO.get(self.modulo, "")
            )
        return avisos

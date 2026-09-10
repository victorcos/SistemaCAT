"""Leitura do relatório gerencial em disco.

Junta as três peças do domínio: :mod:`cat.dominio.gerencial.leiaute` descobre a
forma do arquivo, :mod:`cat.dominio.gerencial.campos` diz que espécie é e de
qual coluna sai cada campo, e :mod:`cat.dominio.gerencial.registros` transforma
o texto em valor com as regras do trabalho.

Duas defesas que este módulo tem e que valem explicar:

**Linha de tamanho errado é descartada, não adivinhada.** O exportador de um
dos ERPs despeja a própria consulta SQL no topo do arquivo, e as quebras dela
viram separador. Alinhar isso "na força" desloca todas as colunas e produz
número plausível e errado — que é o pior defeito possível numa apuração.
Descarte com contagem e amostra no log é mais seguro.

**Muito registro inválido aborta a leitura.** Se um em cada vinte não converte,
o problema não é o dado: é o mapeamento, que casou coluna errada. Seguir em
frente aí produziria uma apuração inteira em cima de coluna trocada. Campo
obrigatório *em branco* não entra nessa conta — relatório de ERP vem cheio de
linha sem CFOP, e isso é dado incompleto, não sintoma de coluna trocada. As
duas coisas são contadas em separado.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field

from cat.dominio.gerencial.campos import Especie, Mapeamento, classificar, mapear
from cat.dominio.gerencial.leiaute import Descarte, Leiaute, farejar
from cat.dominio.gerencial.registros import ItemInventariado, MovimentoGerencial
from cat.dominio.gerencial.valores import CampoVazio, ValorInvalido
from cat.log import obter_log

log = obter_log(__name__)

# latin-1 é a última da fila porque nunca falha: se viesse antes, engoliria um
# arquivo utf-8 e trocaria os acentos por lixo silenciosamente
CODIFICACOES = ("utf-8-sig", "utf-8", "latin-1")

# quanto se lê para farejar. Cabeçalho e primeiras linhas cabem de sobra, e o
# relatório de movimento passa de 1 GB — ler tudo para inspecionar não serve
BYTES_PARA_FAREJAR = 400_000

# A partir daqui não é dado ruim, é mapeamento errado. A fração só passa a
# valer depois de uma amostra decente: num arquivo pequeno, ou nas primeiras
# linhas de um grande, um punhado de registros ruins seguidos estoura
# qualquer proporção sem que haja nada de errado com o mapeamento.
FRACAO_MAXIMA_DE_INVALIDOS = 0.05
MINIMO_PARA_AVALIAR = 500
TETO_DE_INVALIDOS = 1_000


class RelatorioIlegivel(ValueError):
    """O arquivo não dá para ler como relatório gerencial."""


@dataclass(frozen=True)
class Inspecao:
    """O que se sabe do arquivo sem ler o arquivo inteiro."""

    caminho: str
    codificacao: str
    leiaute: Leiaute
    mapeamento: Mapeamento

    @property
    def especie(self) -> Especie:
        return self.mapeamento.especie

    @property
    def utilizavel(self) -> bool:
        return self.mapeamento.utilizavel

    def resumo(self) -> dict[str, object]:
        """O que vai para o log e para a tela de importação."""
        return {
            "arquivo": os.path.basename(self.caminho),
            "especie": self.especie.value,
            "codificacao": self.codificacao,
            "separador": self.leiaute.separador,
            "colunas": self.leiaute.campos,
            "niveis_do_cabecalho": self.leiaute.niveis,
            "campos_achados": len(self.mapeamento.posicoes),
            "utilizavel": self.utilizavel,
            "tem_valores_do_xml": self.mapeamento.tem_valores_do_xml,
            "faltam_obrigatorios": [c.chave for c in self.mapeamento.faltam_obrigatorios],
            "faltam_importantes": [c.chave for c in self.mapeamento.faltam_importantes],
        }


def _decodificar(bruto: bytes) -> tuple[str, str]:
    for cod in CODIFICACOES:
        try:
            return bruto.decode(cod), cod
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1"), "latin-1"


def inspecionar(caminho: str, especie: Especie | None = None) -> Inspecao:
    """Descobre codificação, leiaute e espécie lendo só o começo do arquivo.

    ``especie`` força a interpretação quando o usuário sabe o que mandou e a
    classificação automática erra — o caso de um relatório de movimento cujo
    ERP não exporta CFOP, por exemplo.
    """
    with open(caminho, "rb") as f:
        bruto = f.read(BYTES_PARA_FAREJAR)
    if not bruto.strip():
        raise RelatorioIlegivel(f"arquivo vazio: {os.path.basename(caminho)}")

    texto, cod = _decodificar(bruto)
    linhas = texto.splitlines()
    # a última linha do bloco pode ter sido cortada no meio de um registro
    if len(bruto) == BYTES_PARA_FAREJAR and len(linhas) > 1:
        linhas = linhas[:-1]

    leiaute = farejar(linhas)
    m = (mapear(leiaute.cabecalho, especie) if especie
         else classificar(leiaute.cabecalho))

    inspecao = Inspecao(caminho=caminho, codificacao=cod, leiaute=leiaute, mapeamento=m)
    log.info("relatório gerencial inspecionado", extra=inspecao.resumo())
    return inspecao


class Leitura:
    """Percorre o arquivo entregando registros, e guarda o que descartou.

    Os contadores ficam no objeto, não no retorno, porque quem lê um arquivo de
    milhões de linhas quer consumir por gerador; conferir o descarte é coisa do
    fim, e aí basta olhar :attr:`descarte` e :attr:`invalidos`.
    """

    def __init__(self, caminho: str, especie: Especie | None = None) -> None:
        self.inspecao = inspecionar(caminho, especie)
        self.descarte = Descarte()
        self.invalidos: list[str] = []
        self.total_invalidos = 0
        self.incompletos: list[str] = []
        self.total_incompletos = 0
        self.lidas = 0

    @property
    def especie(self) -> Especie:
        return self.inspecao.especie

    def brutos(self) -> Iterator[tuple[int, dict[str, str]]]:
        """(número da linha, {chave do campo: texto da coluna})."""
        insp = self.inspecao
        leiaute, m = insp.leiaute, insp.mapeamento
        if not m.utilizavel:
            faltam = ", ".join(c.nome for c in m.faltam_obrigatorios)
            raise RelatorioIlegivel(
                f"{os.path.basename(insp.caminho)}: faltam campos obrigatórios "
                f"para {insp.especie.rotulo.lower()} — {faltam}"
            )

        posicoes = m.posicoes
        with open(insp.caminho, encoding=insp.codificacao,
                  errors="replace", newline="") as f:
            for numero, linha in enumerate(f, start=1):
                if numero <= leiaute.primeira_linha_de_dado:
                    continue
                linha = linha.rstrip("\r\n")
                if not linha.strip():
                    continue
                campos = linha.split(leiaute.separador)
                if len(campos) != leiaute.campos:
                    self.descarte.registrar(numero, linha, len(campos))
                    continue
                self.lidas += 1
                yield numero, {ch: campos[i] for ch, i in posicoes.items()}

        self._encerrar()

    def movimentos(self) -> Iterator[MovimentoGerencial]:
        yield from self._tipados(MovimentoGerencial.de, Especie.MOVIMENTO)

    def inventario(self) -> Iterator[ItemInventariado]:
        yield from self._tipados(ItemInventariado.de, Especie.INVENTARIO)

    # ------------------------------------------------------------------
    def _tipados(self, construtor, esperada: Especie) -> Iterator:
        if self.especie is not esperada:
            raise RelatorioIlegivel(
                f"{os.path.basename(self.inspecao.caminho)} é "
                f"{self.especie.rotulo.lower()}, não {esperada.rotulo.lower()}"
            )
        for numero, dados in self.brutos():
            try:
                yield construtor(dados, numero)
            except CampoVazio as e:
                self._incompleto(numero, str(e))
            except ValorInvalido as e:
                self._invalido(numero, str(e))

    def _incompleto(self, numero: int, motivo: str) -> None:
        """Falta campo obrigatório. Conta e segue — não é sintoma de nada."""
        self.total_incompletos += 1
        if len(self.incompletos) < 20:
            self.incompletos.append(f"linha {numero}: {motivo}")

    def _invalido(self, numero: int, motivo: str) -> None:
        self.total_invalidos += 1
        if len(self.invalidos) < 20:
            self.invalidos.append(f"linha {numero}: {motivo}")

        amostra_grande = self.lidas >= MINIMO_PARA_AVALIAR
        proporcao_ruim = (self.total_invalidos
                          > self.lidas * FRACAO_MAXIMA_DE_INVALIDOS)
        if self.total_invalidos >= TETO_DE_INVALIDOS or (
                amostra_grande and proporcao_ruim):
            log.error(
                "leitura abortada: registro inválido demais para ser dado ruim",
                extra={"arquivo": os.path.basename(self.inspecao.caminho),
                       "lidas": self.lidas, "invalidos": self.total_invalidos,
                       "amostra": self.invalidos[:3]},
            )
            raise RelatorioIlegivel(
                f"{os.path.basename(self.inspecao.caminho)}: "
                f"{self.total_invalidos} de {self.lidas} linhas não converteram. "
                "Isso costuma ser coluna mapeada errada, não dado ruim. "
                f"Primeiro caso — {self.invalidos[0]}"
            )

    def _encerrar(self) -> None:
        if self.descarte.linhas or self.total_invalidos or self.total_incompletos:
            log.warning(
                "relatório gerencial lido com descarte",
                extra={"arquivo": os.path.basename(self.inspecao.caminho),
                       "lidas": self.lidas,
                       "descartadas": self.descarte.linhas,
                       "invalidas": self.total_invalidos,
                       "incompletas": self.total_incompletos,
                       "amostra_descarte": self.descarte.amostra,
                       "amostra_invalidas": self.invalidos[:3],
                       "amostra_incompletas": self.incompletos[:3]},
            )
        else:
            log.info("relatório gerencial lido",
                     extra={"arquivo": os.path.basename(self.inspecao.caminho),
                            "lidas": self.lidas})


@dataclass
class Varredura:
    """O que uma pasta de relatórios tem, por espécie."""

    por_especie: dict[Especie, list[str]] = field(default_factory=dict)
    ilegiveis: list[tuple[str, str]] = field(default_factory=list)
    inutilizaveis: list[tuple[str, list[str]]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.por_especie.values())


def varrer(caminhos: list[str]) -> Varredura:
    """Inspeciona vários arquivos e diz o que dá para usar de cada um."""
    v = Varredura()
    for caminho in caminhos:
        try:
            insp = inspecionar(caminho)
        except (OSError, ValueError) as e:
            v.ilegiveis.append((caminho, str(e)))
            continue
        if not insp.utilizavel:
            v.inutilizaveis.append(
                (caminho, [c.nome for c in insp.mapeamento.faltam_obrigatorios])
            )
            continue
        v.por_especie.setdefault(insp.especie, []).append(caminho)

    log.info("pasta de relatórios varrida",
             extra={"arquivos": len(caminhos), "utilizaveis": v.total,
                    "por_especie": {e.value: len(c) for e, c in v.por_especie.items()},
                    "ilegiveis": len(v.ilegiveis),
                    "inutilizaveis": len(v.inutilizaveis)})
    return v

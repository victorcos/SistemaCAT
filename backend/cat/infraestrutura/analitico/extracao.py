"""Extrair os documentos das duas fontes para parquet.

Parquet porque é o formato de trabalho entre etapas (ARQUITETURA §7): tipado,
pequeno e o DuckDB o lê rápido. A base de uma empresa desta casa tem 100 GB de
EFD e um arquivo sozinho traz 39.265 registros C100 — carregar isso em memória
ou enfiar linha a linha no Postgres não é opção.

Duas regras de leitura que valem tempo de verdade, medidas antes neste projeto:

**Filtrar antes de quebrar a linha.** Comparar os primeiros bytes e só então
dividir em campos valeu 2,4 vezes numa varredura de 119,82 GB. A maior parte
das linhas de um EFD não é C100 nem C800 — num arquivo real, 92.335 linhas eram
C190 contra 39.265 de C100.

**Ler em binário.** Decodificar cada linha para depois descartá-la é trabalho
jogado fora. O prefixo é ASCII, então a comparação funciona em bytes, e só o
que passa é decodificado.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.cat42.conferencia import Origem
from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, ler_cabecalho
from cat.dominio.sped.fiscais import PREFIXOS, DocumentoEscriturado, ler_documento
from cat.log import obter_log

log = obter_log(__name__)

CODIFICACAO = "latin-1"          # o SPED é ISO 8859-1; latin-1 aceita tudo
LINHAS_POR_LOTE = 250_000        # quanto se acumula antes de gravar
CENTAVOS = Decimal("0.01")

ESQUEMA_EFD = pa.schema([
    ("chave", pa.string()),
    ("modelo", pa.string()),
    ("situacao", pa.string()),
    ("serie", pa.string()),
    ("numero", pa.string()),
    ("data", pa.date32()),
    ("valor", pa.decimal128(18, 2)),
    ("participante", pa.string()),
    ("operacao", pa.string()),
    ("emitente", pa.string()),
    ("cnpj", pa.string()),          # o estabelecimento, do cabeçalho do arquivo
    ("competencia", pa.date32()),
    ("arquivo", pa.string()),
])

ESQUEMA_PASTA = pa.schema([
    ("chave", pa.string()),
    ("origem", pa.string()),
    ("arquivo", pa.string()),
])

# a chave aparece no atributo Id (`NFe4121…`, `CFe3521…`) ou numa tag própria
_RE_CHAVE_XML = re.compile(
    rb'Id\s*=\s*["\'](?:NFe|CFe)(\d{44})["\']|<ch(?:NFe|CFe)>(\d{44})<')
# muitos exportadores nomeiam o arquivo pela própria chave
_RE_CHAVE_NOME = re.compile(r"(?<!\d)(\d{44})(?!\d)")

BYTES_DE_XML = 4096


@dataclass
class Progresso:
    """O que a tela mostra enquanto a extração roda."""

    arquivos_totais: int = 0
    arquivos_lidos: int = 0
    bytes_lidos: int = 0
    documentos: int = 0
    recusados: list[str] = field(default_factory=list)

    @property
    def fracao(self) -> float:
        if not self.arquivos_totais:
            return 0.0
        return min(1.0, self.arquivos_lidos / self.arquivos_totais)


Aviso = Callable[[Progresso], None]


class _Escritor:
    """Acumula linhas e grava em blocos, para não segurar tudo em memória."""

    def __init__(self, caminho: str, esquema: pa.Schema) -> None:
        self.caminho = caminho
        self.esquema = esquema
        self.colunas: dict[str, list] = {c: [] for c in esquema.names}
        self.linhas = 0
        self.total = 0
        self._escritor: pq.ParquetWriter | None = None

    def acrescentar(self, linha: dict) -> None:
        for nome, lista in self.colunas.items():
            lista.append(linha.get(nome))
        self.linhas += 1
        self.total += 1
        if self.linhas >= LINHAS_POR_LOTE:
            self.descarregar()

    def descarregar(self) -> None:
        if not self.linhas:
            return
        tabela = pa.Table.from_pydict(self.colunas, schema=self.esquema)
        if self._escritor is None:
            self._escritor = pq.ParquetWriter(self.caminho, self.esquema,
                                              compression="zstd")
        self._escritor.write_table(tabela)
        for lista in self.colunas.values():
            lista.clear()
        self.linhas = 0

    def fechar(self) -> None:
        self.descarregar()
        if self._escritor is None:
            # parquet vazio, mas com esquema: quem lê depois não precisa de if
            self._escritor = pq.ParquetWriter(self.caminho, self.esquema,
                                              compression="zstd")
            self._escritor.write_table(pa.Table.from_pydict(
                {c: [] for c in self.esquema.names}, schema=self.esquema))
        self._escritor.close()


def _dinheiro(v: Decimal) -> Decimal:
    return v.quantize(CENTAVOS)


def _documentos_do_sped(caminho: str) -> Iterator[DocumentoEscriturado]:
    """Só C100 e C800, comparando bytes antes de decodificar."""
    with open(caminho, "rb") as f:
        for bruto in f:
            if not bruto.startswith(PREFIXOS):
                continue
            doc = ler_documento(bruto.decode(CODIFICACAO))
            if doc is not None:
                yield doc


def _identificacao(caminho: str) -> tuple[str, date | None]:
    """CNPJ do estabelecimento e competência, do registro 0000."""
    try:
        with open(caminho, "rb") as f:
            primeira = f.readline().decode(CODIFICACAO)
        cabecalho = ler_cabecalho(primeira)
    except (OSError, ArquivoNaoReconhecido):
        return "", None
    return (cabecalho.cnpj.valor if cabecalho.cnpj else ""), cabecalho.inicio


def extrair_efd(caminhos: list[str], destino: str,
                avisar: Aviso | None = None) -> Progresso:
    """Escreve um parquet com todo C100 e C800 dos arquivos indicados."""
    progresso = Progresso(arquivos_totais=len(caminhos))
    escritor = _Escritor(destino, ESQUEMA_EFD)

    for caminho in caminhos:
        nome = os.path.basename(caminho)
        cnpj, competencia = _identificacao(caminho)
        try:
            for doc in _documentos_do_sped(caminho):
                escritor.acrescentar({
                    "chave": doc.chave,
                    "modelo": doc.modelo,
                    "situacao": doc.situacao,
                    "serie": doc.serie,
                    "numero": doc.numero,
                    "data": doc.data,
                    "valor": _dinheiro(doc.valor),
                    "participante": doc.participante,
                    "operacao": doc.operacao.value,
                    "emitente": doc.emitente.value,
                    "cnpj": cnpj,
                    "competencia": competencia,
                    "arquivo": nome,
                })
                progresso.documentos += 1
        except OSError as erro:
            # um arquivo ilegível não derruba a extração de outros 7 mil
            progresso.recusados.append(f"{nome}: {erro}")
            log.warning("arquivo de EFD ilegível",
                        extra={"arquivo": nome, "motivo": str(erro)})
        else:
            progresso.bytes_lidos += _tamanho(caminho)

        progresso.arquivos_lidos += 1
        if avisar is not None:
            avisar(progresso)

    escritor.fechar()
    log.info("EFD extraída", extra={"arquivos": progresso.arquivos_lidos,
                                    "documentos": escritor.total,
                                    "destino": os.path.basename(destino)})
    return progresso


def _chave_do_xml(caminho: str) -> str:
    """Do conteúdo; se não achar, do nome do arquivo."""
    try:
        with open(caminho, "rb") as f:
            inicio = f.read(BYTES_DE_XML)
    except OSError:
        inicio = b""
    achado = _RE_CHAVE_XML.search(inicio)
    if achado:
        return (achado.group(1) or achado.group(2)).decode("ascii")
    do_nome = _RE_CHAVE_NOME.search(os.path.basename(caminho))
    return do_nome.group(1) if do_nome else ""


_RE_NAO_DIGITO = re.compile(r"\D+")


def _chave_do_relatorio(bruto: str | None) -> str | None:
    """Os 44 dígitos, venham como vierem: "NFe" na frente, espaço, em blocos.

    O que o Excel estragou não tem volta — "4,12105E+43" perdeu os dígitos
    ao virar número — e devolve None, para ser contado e avisado.
    """
    digitos = _RE_NAO_DIGITO.sub("", bruto or "")
    return digitos if len(digitos) == 44 else None


def extrair_pasta(xmls: list[str], relatorios: list[str], destino: str,
                  avisar: Aviso | None = None) -> Progresso:
    """Escreve um parquet com a chave de cada documento que o cliente entregou.

    XML e relatório gerencial entram no mesmo arquivo porque, para o confronto,
    fazem o mesmo papel: dizem que o documento existe. Qual das duas fontes o
    trouxe fica na coluna `origem`, que é o que permite explicar depois de onde
    a informação veio.
    """
    from cat.dominio.gerencial.campos import Especie
    from cat.infraestrutura.arquivos.gerencial import Leitura

    progresso = Progresso(arquivos_totais=len(xmls) + len(relatorios))
    escritor = _Escritor(destino, ESQUEMA_PASTA)
    vistas: set[str] = set()

    for caminho in xmls:
        chave = _chave_do_xml(caminho)
        if chave and chave not in vistas:
            vistas.add(chave)
            escritor.acrescentar({"chave": chave, "origem": Origem.XML.value,
                                  "arquivo": os.path.basename(caminho)})
            progresso.documentos += 1
        elif not chave:
            progresso.recusados.append(
                f"{os.path.basename(caminho)}: sem chave de acesso")
        progresso.arquivos_lidos += 1
        if avisar is not None:
            avisar(progresso)

    for caminho in relatorios:
        nome = os.path.basename(caminho)
        sem_chave = 0
        try:
            leitura = Leitura(caminho)
            # inventário e resumo não têm documento nem chave; passar por
            # eles em silêncio daria "0 documentos" sem explicação
            if leitura.especie is not Especie.MOVIMENTO:
                progresso.recusados.append(
                    f"{nome}: é {leitura.especie.rotulo.lower()}, não relatório "
                    "de movimento — não tem chave de documento para conferir")
                progresso.arquivos_lidos += 1
                continue
            for _numero, dados in leitura.brutos():
                chave = _chave_do_relatorio(dados.get("chave"))
                if chave is None:
                    sem_chave += 1
                elif chave not in vistas:
                    vistas.add(chave)
                    escritor.acrescentar({
                        "chave": chave, "origem": Origem.GERENCIAL.value,
                        "arquivo": nome,
                    })
                    progresso.documentos += 1
        except (OSError, ValueError) as erro:
            progresso.recusados.append(f"{nome}: {erro}")
            log.warning("relatório ilegível no confronto",
                        extra={"arquivo": nome, "motivo": str(erro)})
        if sem_chave:
            # a nota dessas linhas vai cair como pendente, e quem for cobrar
            # precisa saber que o relatório a trazia — só que sem chave
            progresso.recusados.append(
                f"{nome}: {sem_chave} linha(s) sem chave de acesso válida, "
                "ignoradas — costuma ser chave que o Excel converteu em número")
            log.warning("relatório com linhas sem chave válida",
                        extra={"arquivo": nome, "linhas": sem_chave})
        progresso.arquivos_lidos += 1
        if avisar is not None:
            avisar(progresso)

    escritor.fechar()
    log.info("documentos da pasta extraídos",
             extra={"xmls": len(xmls), "relatorios": len(relatorios),
                    "chaves": escritor.total})
    return progresso


def _tamanho(caminho: str) -> int:
    try:
        return os.path.getsize(caminho)
    except OSError:
        return 0


def contar(caminhos: Iterable[str]) -> int:
    return sum(1 for _ in caminhos)

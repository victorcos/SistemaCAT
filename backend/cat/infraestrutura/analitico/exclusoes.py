"""A rodada das exclusões da base do PIS/COFINS.

Hoje há uma tese: as próprias contribuições fora da base
(`exclusoes/piscofins_na_propria_base.py`). A do ICMS destacado — o Tema 69 —
vem depois, e precisa de outra fonte: a EFD ICMS/IPI do mesmo CNPJ e da mesma
competência.

**De onde vêm os números, e por que isso importa no relógio.** Do agregado que
a Gestão deixou em disco: ler os 65 SPED desta casa custa uma hora, e o
agregado volta em segundos. Sem Gestão rodada, esta etapa lê os SPED ela mesma
— e grava o agregado na própria pasta, para que a próxima tese não pague de
novo. O resumo diz de onde veio, porque "demorou uma hora" e "demorou dez
segundos" são a mesma etapa com fontes diferentes, e quem acompanha merece
saber qual foi.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido
from cat.infraestrutura.exclusoes.piscofins_na_propria_base import calcular
from cat.infraestrutura.gestao.agregador import agregar_efd
from cat.infraestrutura.gestao.agregados import gravar as gravar_agregados
from cat.infraestrutura.gestao.agregados import ler as ler_agregados
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_DAS_EXCLUSOES = "exclusoes.parquet"

# a tese que esta rodada calcula. Vira coluna para que a segunda — o ICMS
# destacado — entre no mesmo parquet sem quebrar quem já lê este
TESE_PISCOFINS_NA_BASE = "piscofins_na_propria_base"

ESQUEMA = pa.schema([
    ("tese", pa.string()),
    ("cnpj", pa.string()),
    ("competencia", pa.string()),
    ("registro", pa.string()),
    ("cst", pa.string()),
    ("cfop", pa.string()),
    # tudo em centavos inteiros, como o resto da casa
    ("base", pa.int64()),
    ("excluido", pa.int64()),
    ("pis", pa.int64()),
    ("cofins", pa.int64()),
    ("base_nova_pis", pa.int64()),
    ("base_nova_cofins", pa.int64()),
    ("pis_novo", pa.int64()),
    ("cofins_novo", pa.int64()),
    ("diferenca_pis", pa.int64()),
    ("diferenca_cofins", pa.int64()),
])


class ExclusaoCancelada(RuntimeError):
    """A rodada parou porque pediram para parar."""


@dataclass
class Andamento:
    arquivos: int = 0
    grupos: int = 0


@dataclass
class Resumo:
    """O que a rodada produziu — e de onde veio."""

    fonte: str = ""                # "agregados" ou "sped"
    arquivos: int = 0
    ilegiveis: int = 0
    grupos: int = 0
    base: int = 0
    excluido: int = 0
    diferenca_pis: int = 0
    diferenca_cofins: int = 0
    competencias: list[str] = field(default_factory=list)
    # motivo -> quantas chaves do agregado não entraram na tese
    fora: dict[str, int] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    segundos: float = 0.0

    @property
    def diferenca(self) -> int:
        return self.diferenca_pis + self.diferenca_cofins


def serializar(r: Resumo) -> dict:
    return {
        "versao": 1, "fonte": r.fonte, "arquivos": r.arquivos,
        "ilegiveis": r.ilegiveis, "grupos": r.grupos,
        "base": r.base, "excluido": r.excluido,
        "diferenca_pis": r.diferenca_pis, "diferenca_cofins": r.diferenca_cofins,
        "diferenca": r.diferenca, "competencias": r.competencias,
        "fora": r.fora, "avisos": r.avisos, "segundos": r.segundos,
    }


def apurar(contribuicoes: list[str], destino: str, agregados_de: str | None = None,
           avisar: Callable[[Andamento], None] | None = None,
           deve_parar: Callable[[], bool] | None = None) -> Resumo:
    """Calcula as exclusões e grava o parquet. Devolve o resumo."""
    inicio = time.time()
    os.makedirs(destino, exist_ok=True)
    resumo = Resumo()

    agregados = ler_agregados(agregados_de) if agregados_de else []
    if agregados:
        resumo.fonte = "agregados"
        resumo.arquivos = len(agregados)
        log.info("exclusões partindo do agregado da gestão", extra={
            "arquivos": resumo.arquivos, "de": os.path.basename(agregados_de or "")})
        if avisar is not None:
            avisar(Andamento(arquivos=resumo.arquivos))
    else:
        resumo.fonte = "sped"
        agregados = _ler_os_sped(contribuicoes, destino, resumo, avisar, deve_parar)

    exclusao = calcular(agregados)
    resumo.grupos = exclusao.resumo.grupos
    resumo.base = exclusao.resumo.base
    resumo.excluido = exclusao.resumo.excluido
    resumo.diferenca_pis = exclusao.resumo.diferenca_pis
    resumo.diferenca_cofins = exclusao.resumo.diferenca_cofins
    resumo.competencias = exclusao.resumo.periodos
    resumo.fora = exclusao.resumo.fora
    resumo.avisos.extend(exclusao.resumo.avisos)

    _gravar(exclusao, os.path.join(destino, ARQUIVO_DAS_EXCLUSOES))
    if avisar is not None:
        avisar(Andamento(arquivos=resumo.arquivos, grupos=resumo.grupos))

    resumo.segundos = round(time.time() - inicio, 1)
    log.info("exclusões apuradas", extra=serializar(resumo))
    return resumo


def _ler_os_sped(contribuicoes: list[str], destino: str, resumo: Resumo,
                 avisar: Callable[[Andamento], None] | None,
                 deve_parar: Callable[[], bool] | None) -> list:
    """Sem agregado pronto, lê os arquivos — e deixa o agregado para a próxima."""
    lidos = []
    for i, caminho in enumerate(contribuicoes, start=1):
        if deve_parar is not None and deve_parar():
            raise ExclusaoCancelada("apuração das exclusões cancelada a pedido")
        try:
            lidos.append(agregar_efd(caminho))
        except (ArquivoNaoReconhecido, OSError, ValueError) as erro:
            resumo.ilegiveis += 1
            aviso = f"{os.path.basename(caminho)}: {erro}"
            resumo.avisos.append(aviso)
            log.warning("arquivo não lido na apuração das exclusões",
                        extra={"arquivo": os.path.basename(caminho), "erro": str(erro)})
        if avisar is not None:
            avisar(Andamento(arquivos=i))

    resumo.arquivos = len(lidos)
    if lidos:
        # o próximo cálculo — outra tese, ou esta de novo — não paga a leitura
        gravar_agregados(lidos, destino)
    return lidos


def _gravar(exclusao, caminho: str) -> None:
    """Uma linha por grupo. O parquet nasce mesmo sem nenhuma.

    Etapa que termina sem arquivo é etapa que a seguinte não distingue de etapa
    que não rodou.
    """
    colunas: dict[str, list] = {nome: [] for nome in ESQUEMA.names}
    for grupo, a in exclusao.grupos.items():
        if not a.consistente:
            continue
        colunas["tese"].append(TESE_PISCOFINS_NA_BASE)
        colunas["cnpj"].append(grupo.cnpj)
        colunas["competencia"].append(grupo.periodo)
        colunas["registro"].append(grupo.registro)
        colunas["cst"].append(grupo.cst)
        colunas["cfop"].append(grupo.cfop)
        colunas["base"].append(a.base)
        colunas["excluido"].append(a.excluido)
        colunas["pis"].append(a.pis)
        colunas["cofins"].append(a.cofins)
        colunas["base_nova_pis"].append(a.base_nova_pis)
        colunas["base_nova_cofins"].append(a.base_nova_cofins)
        colunas["pis_novo"].append(a.pis_novo)
        colunas["cofins_novo"].append(a.cofins_novo)
        colunas["diferenca_pis"].append(a.diferenca_pis)
        colunas["diferenca_cofins"].append(a.diferenca_cofins)

    pq.write_table(pa.Table.from_pydict(colunas, schema=ESQUEMA), caminho)

"""A etapa de quebra: lê os SPED do lote e escreve o que se confronta.

Junta o que `infraestrutura/sped/` sabe fazer numa rodada só, sobre todos os
arquivos do trabalho, e deixa em disco quatro parquets:

| arquivo | o que é |
|---|---|
| `arquivos.parquet` | um por SPED lido: de quem é, de que período, quantas linhas |
| `contagens.parquet` | quantos registros de cada tipo em cada arquivo |
| `entradas.parquet` | a Consulta de Entradas (037), de todas as EFD-Contribuições |
| `razao.parquet` | o razão contábil, de todas as ECD |

**Os dois últimos existem para serem confrontados** (prioridade do Victor,
22/09/2026): a 037 diz o que a escrituração fiscal registrou como entrada; o
razão diz o que a contabilidade lançou. Onde os dois discordam é onde está o
trabalho.

## Por que os quatro saem na etapa, e não sob demanda

Porque a leitura é sequencial e custa o arquivo inteiro. Gerar a 037 na hora do
download obrigaria a reler 5 GB a cada clique. O índice, esse sim, fica em cache
por arquivo — é o que torna barato mostrar "o que tem aqui dentro" sem reler
nada.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.parquet as pq

from cat.infraestrutura.sped.ecd import EcdInvalida, indexar_ecd, razao
from cat.infraestrutura.sped.entradas import colunas_da_entrada, entradas
from cat.infraestrutura.sped.indice import indice_de
from cat.infraestrutura.sped.leitor import codificacao_de
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_DOS_ARQUIVOS = "arquivos.parquet"
ARQUIVO_DAS_CONTAGENS = "contagens.parquet"
ARQUIVO_DAS_ENTRADAS = "entradas.parquet"
ARQUIVO_DO_RAZAO = "razao.parquet"
PASTA_DOS_INDICES = "indices"

LINHAS_POR_LOTE = 50_000

ESQUEMA_ARQUIVOS = pa.schema([
    ("nome", pa.string()), ("caminho", pa.string()), ("tipo", pa.string()),
    ("cnpj", pa.string()), ("empresa", pa.string()),
    ("inicio", pa.string()), ("fim", pa.string()),
    ("bytes", pa.int64()), ("linhas", pa.int64()), ("registros", pa.int32()),
    # o que cada tipo de arquivo rende
    ("itens", pa.int64()), ("consolidacoes", pa.int64()),
    ("contas", pa.int32()), ("lancamentos", pa.int64()), ("partidas", pa.int64()),
    ("entradas_geradas", pa.int64()), ("linhas_do_razao", pa.int64()),
    ("erro", pa.string()),
])

ESQUEMA_CONTAGENS = pa.schema([
    ("arquivo", pa.string()), ("registro", pa.string()), ("quantidade", pa.int64()),
])


class QuebraCancelada(Exception):
    """A rodada foi cancelada; nada do que ficou pela metade vale."""


@dataclass
class Andamento:
    arquivos: int = 0
    bytes: int = 0
    entradas: int = 0
    razao: int = 0


@dataclass
class Resumo:
    """O que a quebra achou, para a tela e para o histórico."""

    arquivos: int = 0
    contribuicoes: int = 0
    ecd: int = 0
    ilegiveis: int = 0
    bytes: int = 0
    linhas: int = 0
    entradas: int = 0
    linhas_do_razao: int = 0
    por_ramo: dict[str, int] = field(default_factory=dict)
    estabelecimentos: list[str] = field(default_factory=list)
    competencias: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def serializar(r: Resumo) -> dict:
    return {
        "versao": 1, "arquivos": r.arquivos, "contribuicoes": r.contribuicoes, "ecd": r.ecd,
        "ilegiveis": r.ilegiveis, "bytes": r.bytes, "linhas": r.linhas,
        "entradas": r.entradas, "linhas_do_razao": r.linhas_do_razao,
        "por_ramo": dict(sorted(r.por_ramo.items())),
        "estabelecimentos": sorted(r.estabelecimentos), "competencias": sorted(r.competencias),
        "avisos": r.avisos,
    }


class _Escritor:
    """Grava parquet em lotes, e só cria o arquivo quando há esquema.

    O esquema das entradas e do razão vem de fora (`colunas`), para que um
    trabalho sem nenhuma entrada ainda produza um parquet legível em vez de
    arquivo nenhum — a etapa seguinte não deveria precisar saber a diferença.
    """

    def __init__(self, caminho: str, colunas: list[str]) -> None:
        self.esquema = pa.schema([(c, pa.string()) for c in colunas])
        self.escritor = pq.ParquetWriter(caminho, self.esquema)
        self.lote: dict[str, list] = {c: [] for c in colunas}
        self.gravadas = 0

    def escrever(self, linha: dict) -> None:
        for coluna in self.lote:
            self.lote[coluna].append(str(linha.get(coluna, "")))
        self.gravadas += 1
        if len(self.lote[next(iter(self.lote))]) >= LINHAS_POR_LOTE:
            self._despejar()

    def _despejar(self) -> None:
        if not self.lote[next(iter(self.lote))]:
            return
        self.escritor.write_table(pa.Table.from_pydict(self.lote, schema=self.esquema))
        self.lote = {c: [] for c in self.lote}

    def fechar(self) -> None:
        self._despejar()
        self.escritor.close()


def quebrar(contribuicoes: list[str], ecds: list[str], destino: str,
            avisar: Callable[[Andamento], None] | None = None,
            deve_parar: Callable[[], bool] | None = None) -> Resumo:
    """Lê todos os SPED do trabalho e escreve os quatro parquets."""
    os.makedirs(destino, exist_ok=True)
    indices = os.path.join(destino, PASTA_DOS_INDICES)
    resumo = Resumo()
    andamento = Andamento()
    linhas_de_arquivo: list[dict] = []
    contagens: list[tuple[str, str, int]] = []

    das_entradas = _Escritor(os.path.join(destino, ARQUIVO_DAS_ENTRADAS), colunas_da_entrada())
    do_razao = _Escritor(os.path.join(destino, ARQUIVO_DO_RAZAO), _COLUNAS_DO_RAZAO)
    try:
        for caminho in contribuicoes:
            _parar_se_pedirem(deve_parar)
            linhas_de_arquivo.append(
                _uma_contribuicao(caminho, indices, das_entradas, contagens, resumo, andamento))
            if avisar:
                avisar(andamento)
        for caminho in ecds:
            _parar_se_pedirem(deve_parar)
            linhas_de_arquivo.append(_uma_ecd(caminho, do_razao, resumo, andamento))
            if avisar:
                avisar(andamento)
    finally:
        das_entradas.fechar()
        do_razao.fechar()

    resumo.entradas = das_entradas.gravadas
    resumo.linhas_do_razao = do_razao.gravadas
    _gravar_arquivos(linhas_de_arquivo, os.path.join(destino, ARQUIVO_DOS_ARQUIVOS))
    _gravar_contagens(contagens, os.path.join(destino, ARQUIVO_DAS_CONTAGENS))
    log.info("quebra de sped concluída", extra=serializar(resumo))
    return resumo


def _parar_se_pedirem(deve_parar: Callable[[], bool] | None) -> None:
    if deve_parar is not None and deve_parar():
        raise QuebraCancelada()


def _vazio(caminho: str, tipo: str, erro: str) -> dict:
    return {"nome": os.path.basename(caminho), "caminho": caminho, "tipo": tipo, "erro": erro}


def _uma_contribuicao(caminho: str, indices: str, das_entradas: _Escritor,
                      contagens: list, resumo: Resumo, andamento: Andamento) -> dict:
    """Indexa a EFD-Contribuições e tira dela a 037."""
    nome = os.path.basename(caminho)
    try:
        indice = indice_de(caminho, os.path.join(indices, _pasta_de(caminho)))
    except Exception as erro:                                      # noqa: BLE001
        log.warning("não deu para indexar a EFD-Contribuições",
                    extra={"arquivo": nome, "erro": str(erro)})
        resumo.ilegiveis += 1
        resumo.avisos.append(f"{nome}: {type(erro).__name__} ao indexar.")
        return _vazio(caminho, "contribuicoes", str(erro)[:300])

    for registro, quantos in indice.contagens.items():
        contagens.append((nome, registro, quantos))
    antes = das_entradas.gravadas
    for linha in entradas(caminho, indice.codificacao):
        das_entradas.escrever(linha.como_dicionario())
        resumo.por_ramo[linha.registros] = resumo.por_ramo.get(linha.registros, 0) + 1
    geradas = das_entradas.gravadas - antes

    resumo.arquivos += 1
    resumo.contribuicoes += 1
    resumo.bytes += indice.bytes_totais
    resumo.linhas += indice.linhas
    andamento.arquivos += 1
    andamento.bytes += indice.bytes_totais
    andamento.entradas = das_entradas.gravadas
    _anotar_identificacao(resumo, indice.cabecalho.cnpj, indice.cabecalho.inicio)
    return {
        "nome": nome, "caminho": caminho, "tipo": "contribuicoes",
        "cnpj": indice.cabecalho.cnpj, "empresa": indice.cabecalho.nome,
        "inicio": indice.cabecalho.inicio, "fim": indice.cabecalho.fim,
        "bytes": indice.bytes_totais, "linhas": indice.linhas,
        "registros": len(indice.contagens),
        "itens": indice.quantos("C170"),
        "consolidacoes": indice.quantos("C180") + indice.quantos("C190"),
        "entradas_geradas": geradas,
    }


def _uma_ecd(caminho: str, do_razao: _Escritor, resumo: Resumo, andamento: Andamento) -> dict:
    """Indexa a ECD e tira dela o razão de todas as contas analíticas."""
    nome = os.path.basename(caminho)
    try:
        indice = indexar_ecd(caminho)
    except (EcdInvalida, OSError) as erro:
        log.warning("não deu para quebrar a ECD", extra={"arquivo": nome, "erro": str(erro)})
        resumo.ilegiveis += 1
        resumo.avisos.append(f"{nome}: {erro}")
        return _vazio(caminho, "ecd", str(erro)[:300])

    antes = do_razao.gravadas
    for linha in razao(caminho, indice):
        do_razao.escrever({
            "cnpj": linha.cnpj, "conta": linha.conta, "descricao": linha.descricao,
            "conta_referencial": linha.conta_referencial, "competencia": linha.competencia,
            "data": linha.data, "numero": linha.numero,
            "valor_do_lancamento": f"{linha.valor_do_lancamento:.2f}",
            "centro_de_custo": linha.centro_de_custo, "valor": f"{linha.valor:.2f}",
            "debito_ou_credito": linha.debito_ou_credito, "historico": linha.historico,
            "codigo_do_historico": linha.codigo_do_historico,
            "participante": linha.participante, "tipo": linha.tipo,
            "saldo": f"{linha.saldo:.2f}", "arquivo": linha.arquivo,
        })
    geradas = do_razao.gravadas - antes

    resumo.arquivos += 1
    resumo.ecd += 1
    resumo.linhas += indice.partidas + indice.lancamentos
    andamento.arquivos += 1
    andamento.razao = do_razao.gravadas
    _anotar_identificacao(resumo, indice.cnpj, indice.inicio)
    return {
        "nome": nome, "caminho": caminho, "tipo": "ecd", "cnpj": indice.cnpj,
        "empresa": indice.nome, "inicio": indice.inicio, "fim": indice.fim,
        "bytes": os.path.getsize(caminho) if os.path.isfile(caminho) else 0,
        "linhas": indice.partidas + indice.lancamentos,
        "contas": len(indice.contas), "lancamentos": indice.lancamentos,
        "partidas": indice.partidas, "linhas_do_razao": geradas,
    }


def _anotar_identificacao(resumo: Resumo, cnpj: str, inicio: str) -> None:
    if cnpj and cnpj not in resumo.estabelecimentos:
        resumo.estabelecimentos.append(cnpj)
    # a competência é o mês: 2021-06-01 vira 2021-06
    if inicio and (mes := inicio[:7]) not in resumo.competencias:
        resumo.competencias.append(mes)


def _pasta_de(caminho: str) -> str:
    """Uma pasta por arquivo, com nome que não colide nem some em disco."""
    from cat.infraestrutura.sped.indice import impressao_de
    bruto = impressao_de(caminho)
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in bruto)[:120]


def _gravar_arquivos(linhas: list[dict], destino: str) -> None:
    pq.write_table(pa.Table.from_pylist(
        [{c: l.get(c, _padrao_de(c)) for c in ESQUEMA_ARQUIVOS.names} for l in linhas],
        schema=ESQUEMA_ARQUIVOS), destino)


def _padrao_de(coluna: str):
    tipo = ESQUEMA_ARQUIVOS.field(coluna).type
    return 0 if pa.types.is_integer(tipo) else ""


def _gravar_contagens(contagens: list[tuple[str, str, int]], destino: str) -> None:
    pq.write_table(pa.Table.from_pydict(
        {"arquivo": [c[0] for c in contagens], "registro": [c[1] for c in contagens],
         "quantidade": [c[2] for c in contagens]}, schema=ESQUEMA_CONTAGENS), destino)


_COLUNAS_DO_RAZAO = [
    "cnpj", "conta", "descricao", "conta_referencial", "competencia", "data", "numero",
    "valor_do_lancamento", "centro_de_custo", "valor", "debito_ou_credito", "historico",
    "codigo_do_historico", "participante", "tipo", "saldo", "arquivo",
]

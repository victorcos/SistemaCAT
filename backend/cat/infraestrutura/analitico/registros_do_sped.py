"""Extrair registros do SPED, consolidados de todos os arquivos do trabalho.

É o que a quebra sempre prometeu e não entregava. Ela abre os arquivos, conta
os registros e guarda a **posição em bytes** de cada um — e parava aí. O que o
analista precisa é o passo seguinte: "me dá todos os C170 desses 59 arquivos,
numa planilha só". Portado do projeto `Quebra de SPED` (página *Consolidar
SPEDs*), que é onde isto nasceu e continua rodando.

## Duas formas de extrair

* **o registro sozinho** — as linhas do C170, do M210, do C870, com as colunas
  do leiaute. Rápido: o índice já sabe onde cada linha está, e a leitura é
  `seek` + `readline`, uma por linha pedida;
* **a hierarquia** — a folha **com o pai**: o C170 com o C100 que o contém, o
  C191 com o C190, o M210 com o M200. É o que o SPED não dá de graça: o arquivo
  é uma lista plana em que o vínculo é a *posição*, e um C170 solto não diz de
  que nota é. Aqui a leitura é sequencial, uma passada por arquivo, carregando
  o último pai visto.

As tabelas de cadastro (0200 o item, 0150 o participante, 0140 o
estabelecimento) entram por **código**, não por posição: são lidas no bloco 0,
que vem antes, e ficam disponíveis para qualquer folha que as cite.

**As colunas têm o nome do leiaute** (`sped/registros.py`), prefixadas pelo
registro (`C100_VL_DOC`, `C170_VL_ITEM`) — sem prefixo, `VL_ITEM` do pai e da
folha se atropelariam. A identificação do arquivo de origem vai em cada linha:
sem ela, consolidar 59 competências produz uma planilha que não se confere
contra nada.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.parquet as pq

from cat.infraestrutura.analitico.escrita import (
    LeituraCancelada,
    parar_se_pedirem,
    pasta_do_indice,
)
from cat.infraestrutura.analitico.quebra_de_sped import (
    ARQUIVO_DOS_ARQUIVOS,
    PASTA_DOS_INDICES,
)
from cat.infraestrutura.sped.extracao import RegistroNaoIndexado, registros
from cat.infraestrutura.sped.indice import IndiceDoArquivo, buscar
from cat.infraestrutura.sped.leitor import campos_da_linha
from cat.infraestrutura.sped.registros import CAMPOS
from cat.log import obter_log

log = obter_log(__name__)

ARQUIVO_DA_EXTRACAO = "extracao_{alvo}.parquet"

# de onde vem cada linha, antes das colunas do leiaute
COLUNAS_DA_ORIGEM = ("arquivo", "cnpj", "empresa", "competencia")

LINHAS_POR_LOTE = 50_000


@dataclass(frozen=True)
class Hierarquia:
    """Uma folha com o contexto que o SPED só dá pela posição.

    `ancestrais` são os registros cujo **último visto antes da folha** vale —
    é assim que o leiaute amarra C170 ao C100 e M210 ao M200. `cadastros` são
    tabelas: o registro e o campo que liga a folha (ou um ancestral) a ele.
    """

    chave: str
    rotulo: str
    folha: str
    ancestrais: tuple[str, ...] = ()
    cadastros: tuple[tuple[str, str], ...] = ()

    @property
    def registros(self) -> tuple[str, ...]:
        return (*self.ancestrais, self.folha, *(r for r, _ in self.cadastros))


# As dezesseis da origem, com os mesmos agrupamentos. Acrescentar uma é
# acrescentar uma linha aqui — o resto do módulo não sabe quais existem.
HIERARQUIAS: tuple[Hierarquia, ...] = (
    Hierarquia("C100+C170", "Notas e itens (C100 + C170)", "C170", ("C010", "C100"),
               (("0200", "COD_ITEM"), ("0150", "COD_PART"))),
    Hierarquia("C190+C191", "Entradas consolidadas — PIS (C190 + C191)", "C191",
               ("C010", "C190"), (("0200", "COD_ITEM"),)),
    Hierarquia("C190+C195", "Entradas consolidadas — COFINS (C190 + C195)", "C195",
               ("C010", "C190"), (("0200", "COD_ITEM"),)),
    Hierarquia("C180+C181", "Vendas consolidadas — PIS (C180 + C181)", "C181",
               ("C010", "C180"), (("0200", "COD_ITEM"),)),
    Hierarquia("C180+C185", "Vendas consolidadas — COFINS (C180 + C185)", "C185",
               ("C010", "C180"), (("0200", "COD_ITEM"),)),
    Hierarquia("C400+C405+C481", "Cupom fiscal — PIS (C405 + C481)", "C481",
               ("C010", "C400", "C405")),
    Hierarquia("C400+C405+C485", "Cupom fiscal — COFINS (C405 + C485)", "C485",
               ("C010", "C400", "C405")),
    Hierarquia("C490+C491", "Cupom consolidado — PIS (C490 + C491)", "C491",
               ("C010", "C490"), (("0200", "COD_ITEM"),)),
    Hierarquia("C490+C495", "Cupom consolidado — COFINS (C490 + C495)", "C495",
               ("C010", "C490"), (("0200", "COD_ITEM"),)),
    Hierarquia("C860+C870", "CF-e SAT e itens (C860 + C870)", "C870",
               ("C010", "C860"), (("0200", "COD_ITEM"),)),
    Hierarquia("M100+M105", "Base do crédito de PIS (M100 + M105)", "M105", ("M100",)),
    Hierarquia("M100+M110", "Ajustes do crédito de PIS (M100 + M110)", "M110", ("M100",)),
    Hierarquia("M200+M210", "Detalhamento do PIS (M200 + M210)", "M210", ("M200",)),
    Hierarquia("M200+M210+M220", "Ajustes do PIS (M210 + M220)", "M220", ("M200", "M210")),
    Hierarquia("M500+M505", "Base do crédito de COFINS (M500 + M505)", "M505", ("M500",)),
    Hierarquia("M500+M510", "Ajustes do crédito de COFINS (M500 + M510)", "M510", ("M500",)),
    Hierarquia("M600+M610", "Detalhamento da COFINS (M600 + M610)", "M610", ("M600",)),
    Hierarquia("M600+M610+M620", "Ajustes da COFINS (M610 + M620)", "M620", ("M600", "M610")),
    Hierarquia("0140+0200", "Itens por estabelecimento (0140 + 0200)", "0200", ("0140",)),
)

POR_CHAVE: dict[str, Hierarquia] = {h.chave: h for h in HIERARQUIAS}

# o bloco é a primeira letra (ou o dígito) do registro: é como o leiaute do
# SPED se organiza, e é por ele que a tela filtra
BLOCOS: dict[str, str] = {
    "0": "Bloco 0 — abertura e tabelas",
    "A": "Bloco A — serviços",
    "C": "Bloco C — mercadorias",
    "D": "Bloco D — serviços de transporte e comunicação",
    "F": "Bloco F — demais operações",
    "I": "Bloco I — contábil (ECD)",
    "M": "Bloco M — apuração",
    "P": "Bloco P — folha de salários",
    "1": "Bloco 1 — complementos",
}


def bloco_de(registro: str) -> str:
    return (registro or "0")[0].upper()


class QuebraNaoEncontrada(FileNotFoundError):
    """A execução da quebra não tem o que esta leitura precisa em disco."""


class AlvoDesconhecido(ValueError):
    """Pediram um registro sem leiaute, ou uma hierarquia que não existe."""


# ---------------------------------------------------------------------------
# o que dá para extrair
# ---------------------------------------------------------------------------
def _arquivos(destino: str) -> list[dict]:
    caminho = os.path.join(destino, ARQUIVO_DOS_ARQUIVOS)
    if not os.path.isfile(caminho):
        raise QuebraNaoEncontrada(
            "Os arquivos desta quebra não estão mais em disco. Rode a quebra de novo.")
    return pq.read_table(caminho).to_pylist()


def _indice(destino: str, caminho_do_sped: str) -> IndiceDoArquivo | None:
    pasta = os.path.join(destino, PASTA_DOS_INDICES, pasta_do_indice(caminho_do_sped))
    return buscar(pasta, caminho_do_sped)


def disponiveis(destino: str) -> dict:
    """O que há para extrair: registros com contagem, e as hierarquias possíveis.

    Só entra o registro que **tem leiaute** nesta casa: oferecer um cuja
    extração sairia com colunas sem nome é oferecer trabalho, não resultado.
    A hierarquia aparece quando a **folha** existe em algum arquivo — é o
    mesmo critério da origem, e é o certo: o pai sem folha não gera linha.
    """
    total: dict[str, int] = {}
    sem_indice = 0
    for linha in _arquivos(destino):
        indice = _indice(destino, linha.get("caminho") or "")
        if indice is None:
            sem_indice += 1
            continue
        for registro, quantos in indice.contagens.items():
            if quantos and registro in CAMPOS:
                total[registro] = total.get(registro, 0) + quantos

    simples = [{"alvo": r, "rotulo": r, "bloco": bloco_de(r), "quantidade": q,
                "colunas": len(COLUNAS_DA_ORIGEM) + len(CAMPOS[r]), "hierarquia": False}
               for r, q in sorted(total.items())]
    hierarquias = [{"alvo": h.chave, "rotulo": h.rotulo, "bloco": bloco_de(h.folha),
                    "quantidade": total.get(h.folha, 0),
                    "colunas": len(_colunas(h)), "hierarquia": True}
                   for h in HIERARQUIAS if total.get(h.folha, 0)]

    log.info("alvos disponíveis para extração", extra={
        "execucao_pasta": os.path.basename(destino), "registros": len(simples),
        "hierarquias": len(hierarquias), "sem_indice": sem_indice})
    return {
        "linhas": [*hierarquias, *simples],
        "blocos": sorted({l["bloco"] for l in (*hierarquias, *simples)}),
        "rotulos_dos_blocos": BLOCOS,
        # arquivo cujo índice não serve mais: a extração sai sem ele, e quem
        # confere o total com o cliente precisa saber disso
        "sem_indice": sem_indice,
    }


# ---------------------------------------------------------------------------
# extrair
# ---------------------------------------------------------------------------
def _prefixadas(registro: str) -> list[str]:
    """As colunas de um registro, com o nome do registro na frente.

    Sem prefixo, o `VL_ITEM` do pai e o da folha viram uma coluna só — e o
    Excel não avisa: mostra a última que chegou.
    """
    return [f"{registro}_{campo}" for campo in CAMPOS[registro]]


def _colunas(alvo: Hierarquia | str) -> list[str]:
    if isinstance(alvo, str):
        return [*COLUNAS_DA_ORIGEM, *CAMPOS[alvo]]
    colunas = list(COLUNAS_DA_ORIGEM)
    for registro in (*alvo.ancestrais, alvo.folha):
        colunas += _prefixadas(registro)
    for registro, _ in alvo.cadastros:
        colunas += _prefixadas(registro)
    return colunas


def colunas_do_alvo(alvo: str) -> list[str]:
    """As colunas da planilha deste alvo, na ordem em que saem."""
    return _colunas(_resolver(alvo))


def _resolver(alvo: str) -> Hierarquia | str:
    limpo = (alvo or "").strip().upper()
    if limpo in POR_CHAVE:
        return POR_CHAVE[limpo]
    if limpo in CAMPOS:
        return limpo
    raise AlvoDesconhecido(
        f"{alvo or '(vazio)'} não é registro com leiaute nem hierarquia conhecida.")


def extrair(destino: str, alvo: str,
            deve_parar: Callable[[], bool] | None = None) -> str:
    """Grava o parquet com todas as linhas do alvo e devolve o caminho."""
    resolvido = _resolver(alvo)
    colunas = _colunas(resolvido)
    esquema = pa.schema([(c, pa.string()) for c in colunas])
    nome = (resolvido if isinstance(resolvido, str) else resolvido.chave).replace("+", "_")
    caminho = os.path.join(destino, ARQUIVO_DA_EXTRACAO.format(alvo=nome))
    # nome provisório: duas telas pedindo o mesmo alvo ao mesmo tempo leriam um
    # parquet pela metade, e isso não aparece como erro — aparece como linha
    # faltando na conferência
    parcial = f"{caminho}.{os.getpid()}.parcial"

    escritor = pq.ParquetWriter(parcial, esquema, compression="zstd")
    lote: dict[str, list[str]] = {c: [] for c in colunas}
    gravadas = 0
    lidos = 0

    def despejar() -> None:
        if not lote[colunas[0]]:
            return
        escritor.write_table(pa.Table.from_pydict(lote, schema=esquema))
        for valores in lote.values():
            valores.clear()

    def acrescentar(linha: dict[str, str]) -> None:
        nonlocal gravadas
        for coluna in colunas:
            lote[coluna].append(linha.get(coluna, ""))
        gravadas += 1
        if gravadas % LINHAS_POR_LOTE == 0:
            despejar()

    try:
        for arquivo in _arquivos(destino):
            parar_se_pedirem(deve_parar)
            caminho_do_sped = arquivo.get("caminho") or ""
            indice = _indice(destino, caminho_do_sped)
            if indice is None:
                continue
            lidos += 1
            origem = {
                "arquivo": arquivo.get("nome") or os.path.basename(caminho_do_sped),
                "cnpj": arquivo.get("cnpj") or "",
                "empresa": arquivo.get("empresa") or "",
                "competencia": (arquivo.get("inicio") or "")[:7],
            }
            if isinstance(resolvido, str):
                _do_registro(caminho_do_sped, indice, resolvido, origem, acrescentar)
            else:
                _da_hierarquia(caminho_do_sped, indice, resolvido, origem, acrescentar)
        despejar()
        escritor.close()
    except BaseException:
        escritor.close()
        if os.path.isfile(parcial):
            os.remove(parcial)
        raise
    os.replace(parcial, caminho)

    log.info("extração concluída", extra={
        "execucao_pasta": os.path.basename(destino), "alvo": alvo,
        "linhas": gravadas, "arquivos": lidos})
    return caminho


def _do_registro(caminho: str, indice: IndiceDoArquivo, registro: str,
                 origem: dict[str, str], acrescentar) -> None:
    """Pelo índice: só as linhas daquele registro, por `seek`."""
    try:
        linhas = registros(caminho, indice, registro)
    except RegistroNaoIndexado:
        return
    nomes = CAMPOS[registro]
    for valores in linhas:
        linha = dict(origem)
        for i, campo in enumerate(nomes):
            linha[campo] = valores[i] if i < len(valores) else ""
        acrescentar(linha)


def _da_hierarquia(caminho: str, indice: IndiceDoArquivo, h: Hierarquia,
                   origem: dict[str, str], acrescentar) -> None:
    """Uma passada pelo arquivo, carregando o último pai visto.

    Sequencial, e não por `seek`, porque o vínculo do SPED **é a ordem**: o
    C170 pertence ao C100 que veio antes dele. Pular direto para as posições da
    folha perderia exatamente a informação que se foi buscar.
    """
    de_interesse = {r.encode("ascii") for r in h.registros}
    atual: dict[str, list[str]] = {}
    tabelas: dict[str, dict[str, list[str]]] = {r: {} for r, _ in h.cadastros}
    ligacao = dict(h.cadastros)

    with open(caminho, "rb") as arquivo:
        for bruto in arquivo:
            # compara em bytes antes de decodificar: numa base de 119 GB, a
            # decodificação de toda linha é o que come o tempo
            corte = bruto[:8]
            if not any(corte.startswith(b"|" + r) for r in de_interesse):
                continue
            valores = campos_da_linha(bruto, indice.codificacao)
            if not valores:
                continue
            registro = valores[0]
            if registro in tabelas:
                codigo = _campo(registro, valores, ligacao[registro])
                if codigo:
                    tabelas[registro][codigo] = valores
            if registro in h.ancestrais:
                atual[registro] = valores
                continue
            if registro != h.folha:
                continue
            linha = dict(origem)
            for pai in h.ancestrais:
                _nomear(linha, pai, atual.get(pai, []))
            _nomear(linha, h.folha, valores)
            for cadastro, campo in h.cadastros:
                codigo = _campo(h.folha, valores, campo)
                if not codigo:
                    codigo = next(
                        (c for pai in h.ancestrais
                         if (c := _campo(pai, atual.get(pai, []), campo))), "")
                _nomear(linha, cadastro, tabelas[cadastro].get(codigo, []))
            acrescentar(linha)


def _nomear(linha: dict[str, str], registro: str, valores: Iterable[str]) -> None:
    lista = list(valores)
    for i, campo in enumerate(CAMPOS[registro]):
        linha[f"{registro}_{campo}"] = lista[i] if i < len(lista) else ""


def _campo(registro: str, valores: list[str], campo: str) -> str:
    """O valor de um campo pelo nome do leiaute. Vazio quando o registro não o tem."""
    nomes = CAMPOS.get(registro, ())
    if campo not in nomes:
        return ""
    i = nomes.index(campo)
    return valores[i] if i < len(valores) else ""

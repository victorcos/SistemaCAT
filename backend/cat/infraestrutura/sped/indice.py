"""O índice do arquivo: o que ele tem, e onde cada coisa está.

Esta é a **quebra de SPED** propriamente dita, portada do projeto de mesmo nome
(22/09/2026). Uma passada pelo arquivo produz duas coisas:

* **a contagem de cada registro** — é o que responde "o que tem neste arquivo?"
  sem abrir nada. Numa EFD real, 92.335 linhas de C190 contra 39.265 de C100;
* **a posição em bytes** dos registros pedidos — é o que permite devolver
  qualquer bloco depois com um `seek`, em tempo constante, sem reler nada.

A segunda é a que muda o jogo. Uma EFD-Contribuições de cliente grande passa de
5 GB e dez milhões de linhas; sem índice, mostrar a página 40 do C170 custa uma
varredura inteira. Com índice, custa quarenta `seek`.

## O índice mora em disco, e não no Postgres

Decisão de 22/09/2026, junto com o critério do banco: o Postgres guarda o que
alguém **decide, aprova ou audita**; isto é cache de leitura. Guardar milhões de
inteiros por arquivo numa tabela seria pagar caro para responder o que o
`seek()` responde de graça — e o índice é descartável: apagado, refaz-se.

## Versão do esquema

O índice guarda a versão com que foi feito. Mudou o que se indexa, o arquivo
velho é ignorado e refeito sozinho — em vez de servir um índice que não tem o
registro novo e fazer a extração devolver vazio sem explicar por quê.

## A impressão do arquivo

O que identifica o arquivo no cache é caminho, tamanho e data de modificação —
não o conteúdo. Hashear 5 GB para decidir se vale reusar o índice custaria quase
o mesmo que refazê-lo. É o mesmo raciocínio de `ja_lidos_na_empresa`: na dúvida,
o que muda é o custo, não a correção, porque a impressão diferente só faz
reindexar.
"""

from __future__ import annotations

import array
import json
import os
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.parquet as pq

from cat.dominio.sped.cabecalho import ArquivoNaoReconhecido, ler_cabecalho
from cat.infraestrutura.sped.leitor import (
    BUFFER_DE_REDE,
    codificacao_de,
    linhas_com_posicao,
    registro_de,
    tamanho_de,
)
from cat.log import obter_log

log = obter_log(__name__)

# Sobe quando muda o que o índice guarda. Índice de versão anterior é ignorado
# e refeito, em vez de servir um recorte que já não é o que o código espera.
# 2: entraram os registros do caminho consolidado (C180/C190 e filhos)
# 3: entrou o bloco M — a apuração das contribuições e os ajustes dela
VERSAO_DO_ESQUEMA = 3

# Os registros cujas posições se guardam por padrão. Guardar de todos custaria
# memória à toa: a contagem já responde a maior parte das perguntas, e posição
# só serve para quem vai extrair.
#
# São os dos dois caminhos que a EFD-Contribuições pode tomar: o item a item
# (C170 com a nota e as tabelas do bloco 0) e o consolidado por produto e CFOP
# (C180/C190 com os filhos de PIS e COFINS). Metade dos clientes escritura de um
# jeito, metade do outro, e a apuração tem de ler os dois.
ALVOS_PADRAO: tuple[str, ...] = (
    "0140", "0150", "0200", "0400", "0500", "C010",
    "C100", "C170",
    "C180", "C181", "C185",
    "C190", "C191", "C195",
    # o bloco M: a apuração, e é dele que sai o número que o cliente pergunta
    "M100", "M105", "M110", "M200", "M210", "M220",
    "M500", "M505", "M510", "M600", "M610", "M620",
)

ARQUIVO_DO_INDICE = "indice.json"
ARQUIVO_DAS_POSICOES = "posicoes.parquet"

_ESQUEMA_POSICOES = pa.schema([("registro", pa.string()), ("posicao", pa.int64())])


@dataclass
class Cabecalho:
    """O registro 0000, já normalizado: de quem é o arquivo e de que período.

    Quem lê o 0000 é `dominio/sped/cabecalho.py`, e não este módulo. Os três
    leiautes — EFD ICMS/IPI, EFD-Contribuições e ECD — põem CNPJ, nome e datas
    em posições **diferentes**, e o domínio já detecta qual é qual. O porte
    original trazia só o leiaute das Contribuições; apontado a uma EFD ICMS/IPI
    real, devolvia a UF no lugar do CNPJ e a razão social no lugar da data
    (22/09/2026, achado no primeiro teste contra arquivo de verdade).
    """

    cnpj: str = ""
    nome: str = ""
    tipo: str = ""
    uf: str = ""
    inicio: str = ""       # aaaa-mm-dd
    fim: str = ""
    retificadora: bool = False

    def como_json(self) -> dict:
        return {"cnpj": self.cnpj, "nome": self.nome, "tipo": self.tipo, "uf": self.uf,
                "inicio": self.inicio, "fim": self.fim, "retificadora": self.retificadora}


@dataclass
class IndiceDoArquivo:
    """O que uma passada pelo arquivo descobriu."""

    caminho: str
    bytes_totais: int
    codificacao: str
    contagens: dict[str, int] = field(default_factory=dict)
    posicoes: dict[str, array.array] = field(default_factory=dict)
    cabecalho: Cabecalho = field(default_factory=Cabecalho)
    versao_do_esquema: int = VERSAO_DO_ESQUEMA

    @property
    def linhas(self) -> int:
        return sum(self.contagens.values())

    def quantos(self, registro: str) -> int:
        return self.contagens.get(registro, 0)

    def tem_posicoes(self, registro: str) -> bool:
        return bool(self.posicoes.get(registro))

    def como_json(self) -> dict:
        return {
            "caminho": self.caminho,
            "bytes_totais": self.bytes_totais,
            "codificacao": self.codificacao,
            "linhas": self.linhas,
            "contagens": dict(sorted(self.contagens.items())),
            "indexados": sorted(r for r, p in self.posicoes.items() if p),
            "cabecalho": self.cabecalho.como_json(),
            "versao_do_esquema": self.versao_do_esquema,
        }


def _cabecalho_de(linhas: Iterable[bytes], codificacao: str) -> Cabecalho:
    """O 0000 lido pelo domínio, que conhece os três leiautes.

    Arquivo cujo 0000 o domínio não reconhece devolve cabeçalho vazio em vez de
    derrubar a indexação: contar os registros continua útil mesmo quando não se
    sabe de quem é o arquivo — e é justamente isso que se quer ver ao apontar a
    quebra para um SPED estranho.
    """
    for bruta in linhas:
        texto = bruta.decode(codificacao, errors="replace")
        if not texto.lstrip().startswith("|0000|"):
            continue
        try:
            lido = ler_cabecalho(texto)
        except ArquivoNaoReconhecido as erro:
            log.warning("registro 0000 não reconhecido", extra={"motivo": str(erro)})
            return Cabecalho()
        return Cabecalho(
            cnpj=lido.cnpj.valor if lido.cnpj else "",
            nome=lido.nome, tipo=lido.tipo.value, uf=lido.uf,
            inicio=lido.inicio.isoformat(), fim=lido.fim.isoformat(),
            retificadora=lido.retificadora)
    return Cabecalho()


# blocos que começam depois do 0: ver qualquer um deles diz que o bloco 0 acabou
_FORA_DO_BLOCO_ZERO = frozenset(b"ABCDFIMP19")


def indexar(caminho: str, alvos: Iterable[str] = ALVOS_PADRAO,
            avisar: Callable[[int, int], None] | None = None,
            a_cada: int = 50 << 20) -> IndiceDoArquivo:
    """Lê o arquivo uma vez e devolve o índice.

    `avisar(lidos, totais)` é chamado a cada 50 MiB — a etapa usa isso para a
    barra andar; sem ele, um arquivo de 5 GB fica minutos sem dar sinal.
    """
    codificacao = codificacao_de(caminho)
    totais = tamanho_de(caminho)
    alvos_em_bytes = {alvo.encode("ascii"): alvo for alvo in alvos}
    contagens: Counter[bytes] = Counter()
    # array de int64 gasta 8 bytes por posição; uma lista de int gastaria ~28.
    # Num arquivo com 8 milhões de C170 isso é 64 MB contra 224 MB
    posicoes: dict[bytes, array.array] = {a: array.array("q") for a in alvos_em_bytes}
    do_bloco_zero: list[bytes] = []
    bloco_zero_acabou = False
    proximo_aviso = a_cada

    for posicao, linha in linhas_com_posicao(caminho, buffer=BUFFER_DE_REDE):
        registro = registro_de(linha)
        if registro is None:
            continue
        contagens[registro] += 1
        if registro in posicoes:
            posicoes[registro].append(posicao)
        if not bloco_zero_acabou:
            if registro.startswith(b"0"):
                do_bloco_zero.append(linha)
            elif registro[:1] in _FORA_DO_BLOCO_ZERO:
                bloco_zero_acabou = True
        if avisar and posicao >= proximo_aviso:
            avisar(posicao, totais)
            proximo_aviso += a_cada
    if avisar:
        avisar(totais, totais)

    # `registro_de` devolve o que estiver entre os dois primeiros "|" de
    # QUALQUER linha que comece com "|", e isso não garante registro SPED
    # válido: exportação com preâmbulo produz token com byte não-ASCII, que
    # derrubaria o decode estrito depois de o arquivo inteiro já ter sido lido.
    # O "replace" transforma isso num registro esquisito na contagem, que é
    # exatamente o que se quer ver
    indice = IndiceDoArquivo(
        caminho=os.path.abspath(caminho),
        bytes_totais=totais,
        codificacao=codificacao,
        contagens={r.decode("ascii", errors="replace"): q for r, q in contagens.items()},
        posicoes={alvos_em_bytes[r]: p for r, p in posicoes.items()},
        cabecalho=_cabecalho_de(do_bloco_zero, codificacao),
    )
    log.info("sped indexado", extra={
        "arquivo": os.path.basename(caminho), "bytes": totais, "linhas": indice.linhas,
        "registros": len(indice.contagens), "cnpj": indice.cabecalho.cnpj,
        "competencia": indice.cabecalho.inicio,
    })
    return indice


# ---------------------------------------------------------------------------
# cache em disco
# ---------------------------------------------------------------------------
def impressao_de(caminho: str) -> str:
    """O que identifica o arquivo no cache: tamanho e data, não conteúdo.

    Hashear 5 GB para decidir se o índice ainda vale custaria quase o mesmo que
    refazê-lo. Impressão diferente só faz reindexar — o custo muda, a resposta
    não.
    """
    try:
        info = os.stat(caminho)
        return f"{os.path.basename(caminho)}-{info.st_size}-{int(info.st_mtime)}"
    except OSError:
        return os.path.basename(caminho)


def guardar(indice: IndiceDoArquivo, pasta: str) -> str:
    """Grava o índice na pasta e devolve o caminho dela.

    Duas peças: um JSON pequeno com contagens e cabeçalho — que é o que a tela
    lê — e um parquet com as posições, que é grande e só a extração abre.
    """
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, ARQUIVO_DO_INDICE), "w", encoding="utf-8") as saida:
        json.dump(indice.como_json(), saida, ensure_ascii=False, indent=1)
    registros: list[str] = []
    valores: list[int] = []
    for registro, lista in sorted(indice.posicoes.items()):
        registros.extend([registro] * len(lista))
        valores.extend(lista)
    pq.write_table(
        pa.Table.from_pydict({"registro": registros, "posicao": valores},
                             schema=_ESQUEMA_POSICOES),
        os.path.join(pasta, ARQUIVO_DAS_POSICOES))
    log.info("índice guardado", extra={"pasta": pasta, "posicoes": len(valores)})
    return pasta


def buscar(pasta: str, caminho: str) -> IndiceDoArquivo | None:
    """O índice guardado, se ainda serve. Nulo quando não serve — e por quê.

    Não serve quando: não existe, foi feito por uma versão anterior do esquema,
    ou o arquivo mudou de tamanho desde então. Em qualquer dos casos a resposta
    é refazer, nunca servir o que está lá.
    """
    alvo = os.path.join(pasta, ARQUIVO_DO_INDICE)
    if not os.path.isfile(alvo):
        return None
    try:
        with open(alvo, encoding="utf-8") as entrada:
            bruto = json.load(entrada)
    except (OSError, ValueError) as erro:
        log.warning("índice ilegível, será refeito", extra={"pasta": pasta, "motivo": str(erro)})
        return None
    if bruto.get("versao_do_esquema") != VERSAO_DO_ESQUEMA:
        log.info("índice de versão anterior, será refeito",
                 extra={"pasta": pasta, "tinha": bruto.get("versao_do_esquema"),
                        "espera": VERSAO_DO_ESQUEMA})
        return None
    if bruto.get("bytes_totais") != tamanho_de(caminho):
        log.info("o arquivo mudou desde o índice, será refeito",
                 extra={"arquivo": os.path.basename(caminho)})
        return None

    posicoes: dict[str, array.array] = {}
    parquet = os.path.join(pasta, ARQUIVO_DAS_POSICOES)
    if os.path.isfile(parquet):
        tabela = pq.read_table(parquet)
        for registro, posicao in zip(tabela.column("registro").to_pylist(),
                                     tabela.column("posicao").to_pylist()):
            posicoes.setdefault(registro, array.array("q")).append(posicao)
    cabecalho = bruto.get("cabecalho", {})
    return IndiceDoArquivo(
        caminho=bruto.get("caminho", caminho),
        bytes_totais=bruto.get("bytes_totais", 0),
        codificacao=bruto.get("codificacao", "cp1252"),
        contagens=bruto.get("contagens", {}),
        posicoes=posicoes,
        cabecalho=Cabecalho(**{c: cabecalho.get(c, "") for c in ("cnpj", "nome", "inicio", "fim")}),
        versao_do_esquema=VERSAO_DO_ESQUEMA,
    )


def indice_de(caminho: str, pasta: str, alvos: Iterable[str] = ALVOS_PADRAO,
              avisar: Callable[[int, int], None] | None = None) -> IndiceDoArquivo:
    """O índice do arquivo: do cache quando serve, refeito quando não."""
    guardado = buscar(pasta, caminho)
    if guardado is not None:
        log.info("índice reaproveitado", extra={"arquivo": os.path.basename(caminho),
                                                "linhas": guardado.linhas})
        return guardado
    indice = indexar(caminho, alvos, avisar=avisar)
    guardar(indice, pasta)
    return indice

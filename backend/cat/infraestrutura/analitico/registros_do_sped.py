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

import hashlib
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

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
from cat.infraestrutura.sped.registros import CAMPOS, campos_de
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

    `par` é a segunda folha, **pareada por posição** dentro do grupo do pai: um
    C190 traz primeiro todos os C191 (PIS) e depois todos os C195 (COFINS), na
    mesma ordem, e o que se quer ver é o par lado a lado — é o leiaute do
    Sistema MA, e é contra ele que a conferência é feita. Com `par`, a leitura
    junta o grupo inteiro antes de emitir.

    `dedup_por` guarda uma linha por valor daquela coluna, ficando com a
    última: o 0200 é redeclarado **inteiro em todo arquivo mensal**, e 59
    competências devolveriam o catálogo 59 vezes.
    """

    chave: str
    rotulo: str
    folha: str
    ancestrais: tuple[str, ...] = ()
    cadastros: tuple[tuple[str, str], ...] = ()
    par: str = ""
    dedup_por: str = ""

    @property
    def registros(self) -> tuple[str, ...]:
        return (*self.ancestrais, self.folha, *(r for r, _ in self.cadastros),
                *((self.par,) if self.par else ()))

    @property
    def pai_imediato(self) -> str:
        return self.ancestrais[-1] if self.ancestrais else ""


# As dezesseis da origem, com os mesmos agrupamentos. Acrescentar uma é
# acrescentar uma linha aqui — o resto do módulo não sabe quais existem.
HIERARQUIAS: tuple[Hierarquia, ...] = (
    Hierarquia("C100+C170", "Notas e itens (C100 + C170)", "C170", ("C010", "C100"),
               (("0200", "COD_ITEM"), ("0150", "COD_PART"), ("0140", "CNPJ"),
                ("0400", "COD_NAT"))),
    # o analítico da NFC-e: não tem item, tem uma linha por CFOP e CST. Por
    # isso não casa com o 0200 — e por isso é o registro mais numeroso do
    # varejo, quatro de cada cinco linhas do 047 numa base real
    Hierarquia("C100+C175", "NFC-e e o analítico dela (C100 + C175)", "C175",
               ("C010", "C100"), (("0150", "COD_PART"),)),
    Hierarquia("A100+A170", "Notas de serviço e itens (A100 + A170)", "A170",
               ("A010", "A100"), (("0150", "COD_PART"), ("0200", "COD_ITEM"))),
    Hierarquia("C190+C191+C195", "Entradas consolidadas — PIS e COFINS (C190 + C191 + C195)",
               "C191", ("C010", "C190"), (("0200", "COD_ITEM"), ("0500", "COD_CTA")),
               par="C195"),
    Hierarquia("C180+C181+C185", "Vendas consolidadas — PIS e COFINS (C180 + C181 + C185)",
               "C181", ("C010", "C180"), (("0200", "COD_ITEM"), ("0500", "COD_CTA")),
               par="C185"),
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
    Hierarquia("0140+0200", "Catálogo de itens (0140 + 0200)", "0200", ("0140",),
               dedup_por="0200_COD_ITEM"),
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


@dataclass(frozen=True)
class Recorte:
    """O que entra na extração. Tudo vazio: sai inteira.

    São os mesmos filtros da página de origem, em dois níveis. **No arquivo**
    — CNPJ e período de apuração — o recorte é barato: o arquivo inteiro é
    pulado sem ser aberto. **Na linha**, o campo é procurado pelo sufixo do
    nome: `CST_PIS` acha `C170_CST_PIS`, `C870_CST_PIS` ou o `CST_PIS` nu do
    registro simples, sem uma lista de nomes possíveis para manter.

    Valor e data vêm do SPED como texto (`1.234,56`, `04062021`); a conversão
    é feita aqui, na comparação, e não na saída — a planilha continua
    entregando o que o arquivo escreveu.
    """

    # no arquivo
    cnpjs: frozenset[str] = frozenset()
    de: str = ""
    ate: str = ""
    # na linha
    cst_pis: frozenset[str] = frozenset()
    cst_cofins: frozenset[str] = frozenset()
    cfop: frozenset[str] = frozenset()
    cod_item: frozenset[str] = frozenset()
    cod_nat: frozenset[str] = frozenset()
    num_doc: frozenset[str] = frozenset()
    ind_aj: frozenset[str] = frozenset()
    cod_aj: frozenset[str] = frozenset()
    ind_oper: str = ""
    descricao: tuple[str, ...] = ()
    doc_de: str = ""
    doc_ate: str = ""
    vl_pis_min: Decimal | None = None
    vl_pis_max: Decimal | None = None
    vl_item_min: Decimal | None = None
    vl_item_max: Decimal | None = None

    @property
    def vazio(self) -> bool:
        return self == Recorte()

    def aceita_arquivo(self, cnpj: str, inicio: str, fim: str) -> bool:
        """O arquivo inteiro passa? CNPJ e período vêm do 0000, pelo índice."""
        if self.cnpjs and _so_digitos(cnpj) not in self.cnpjs:
            return False
        # o arquivo entra se o período dele **toca** o pedido: uma EFD de junho
        # interessa a quem pediu de 15/06 a 15/07
        if self.de and fim and fim < self.de:
            return False
        if self.ate and inicio and inicio > self.ate:
            return False
        return True

    def aceita_linha(self, linha: dict[str, str]) -> bool:
        for campo, valores in (("CST_PIS", self.cst_pis), ("CST_COFINS", self.cst_cofins),
                               ("CFOP", self.cfop), ("COD_ITEM", self.cod_item),
                               ("COD_NAT", self.cod_nat), ("NUM_DOC", self.num_doc),
                               ("IND_AJ", self.ind_aj), ("COD_AJ", self.cod_aj)):
            if valores and _do_campo(linha, campo) not in valores:
                return False
        if self.ind_oper and _do_campo(linha, "IND_OPER") != self.ind_oper:
            return False
        if self.descricao and not _casa_descricao(linha, self.descricao):
            return False
        if (self.doc_de or self.doc_ate) and not self._na_data(linha):
            return False
        if not self._no_valor(linha, "VL_PIS", self.vl_pis_min, self.vl_pis_max):
            return False
        if not self._no_valor(linha, "VL_ITEM", self.vl_item_min, self.vl_item_max):
            return False
        return True

    def _na_data(self, linha: dict[str, str]) -> bool:
        for campo in ("DT_DOC", "DT_DOC_INI", "DT_INI", "DT_REF"):
            bruto = _do_campo(linha, campo)
            if not bruto:
                continue
            data = _data_do_sped(bruto)
            if data is None:
                return True
            if self.doc_de and data < self.doc_de:
                return False
            if self.doc_ate and data > self.doc_ate:
                return False
            return True
        # a linha não tem data nenhuma: quem filtra por data não a quer
        return False

    def _no_valor(self, linha: dict[str, str], campo: str,
                  minimo: Decimal | None, maximo: Decimal | None) -> bool:
        if minimo is None and maximo is None:
            return True
        valor = _decimal_do_sped(_do_campo(linha, campo))
        if valor is None:
            return False
        if minimo is not None and valor < minimo:
            return False
        return not (maximo is not None and valor > maximo)


def _so_digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def _do_campo(linha: dict[str, str], campo: str) -> str:
    """O valor de um campo, ache-se ele nu ou prefixado pelo registro.

    Pelo sufixo, e não por uma lista de nomes possíveis: `CST_PIS` acha o do
    C170, o do C870 e o do C491 sem que ninguém precise mantê-los escritos.
    """
    if campo in linha:
        return linha[campo]
    sufixo = f"_{campo}"
    for nome, valor in linha.items():
        if nome.endswith(sufixo):
            return valor
    return ""


def _casa_descricao(linha: dict[str, str], termos: tuple[str, ...]) -> bool:
    """Pedaço de qualquer coluna de descrição, sem diferenciar maiúscula."""
    textos = [v.lower() for nome, v in linha.items() if "DESCR" in nome and v]
    return any(t in texto for texto in textos for t in termos)


def _data_do_sped(bruto: str) -> str | None:
    """`04062021` vira `2021-06-04`, que é o que se compara como texto."""
    digitos = _so_digitos(bruto)
    if len(digitos) != 8:
        return None
    return f"{digitos[4:]}-{digitos[2:4]}-{digitos[:2]}"


def _decimal_do_sped(bruto: str) -> Decimal | None:
    """`1.234,56` vira Decimal. Vazio e lixo viram None, e não zero."""
    texto = (bruto or "").strip().replace(".", "").replace(",", ".")
    if not texto:
        return None
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


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

    **E só entra o que esta quebra consegue extrair.** São duas listas
    diferentes: a contagem vê TODO registro do arquivo, e o índice só guarda a
    posição dos de `ALVOS_PADRAO`. Oferecendo pela contagem, a tela prometia
    registro que a extração não entregava — foi assim que 0000, F010, C501 e
    C505 viraram erro na mão do usuário. O que foi contado e não indexado sai
    em `nao_extraiveis`, com a contagem: some da lista de extração, mas não some
    da tela, senão quem confere lê como "não existe no SPED".

    A **hierarquia não entra nesse filtro**: ela lê o arquivo sequencialmente
    (o vínculo do SPED é a ordem), não pelas posições do índice.
    """
    total: dict[str, int] = {}
    com_posicao: set[str] = set()
    sem_indice = 0
    for linha in _arquivos(destino):
        indice = _indice(destino, linha.get("caminho") or "")
        if indice is None:
            sem_indice += 1
            continue
        for registro, quantos in indice.contagens.items():
            if quantos and registro in CAMPOS:
                total[registro] = total.get(registro, 0) + quantos
        com_posicao.update(r for r, posicoes in indice.posicoes.items() if posicoes)

    simples = [{"alvo": r, "rotulo": r, "bloco": bloco_de(r), "quantidade": q,
                "colunas": len(COLUNAS_DA_ORIGEM) + len(CAMPOS[r]), "hierarquia": False}
               for r, q in sorted(total.items()) if r in com_posicao]
    nao_extraiveis = [{"alvo": r, "quantidade": q, "bloco": bloco_de(r)}
                      for r, q in sorted(total.items()) if r not in com_posicao]
    hierarquias = [{"alvo": h.chave, "rotulo": h.rotulo, "bloco": bloco_de(h.folha),
                    "quantidade": total.get(h.folha, 0),
                    "colunas": len(_colunas(h)), "hierarquia": True}
                   for h in HIERARQUIAS if total.get(h.folha, 0)]

    estabelecimentos = sorted(
        {(a.get("cnpj") or "", a.get("empresa") or "") for a in _arquivos(destino)} - {("", "")})
    log.info("alvos disponíveis para extração", extra={
        "execucao_pasta": os.path.basename(destino), "registros": len(simples),
        "hierarquias": len(hierarquias), "sem_indice": sem_indice,
        "nao_extraiveis": [n["alvo"] for n in nao_extraiveis]})
    if nao_extraiveis:
        log.warning("registros contados que esta quebra não indexou", extra={
            "execucao_pasta": os.path.basename(destino),
            "registros": [n["alvo"] for n in nao_extraiveis],
            "acao": "rodar a quebra de novo para indexá-los"})
    return {
        "linhas": [*hierarquias, *simples],
        "blocos": sorted({l["bloco"] for l in (*hierarquias, *simples)}),
        "rotulos_dos_blocos": BLOCOS,
        # quem aparece nos arquivos: a tela oferece em vez de pedir digitado
        "estabelecimentos": [{"cnpj": c, "empresa": e} for c, e in estabelecimentos],
        # arquivo cujo índice não serve mais: a extração sai sem ele, e quem
        # confere o total com o cliente precisa saber disso
        "sem_indice": sem_indice,
        # registro que existe nos arquivos mas esta quebra não indexou: fica
        # fora de `linhas` porque não se extrai, e vem aqui porque existe —
        # some da lista de extração sem sumir da tela. Resolve rodando a
        # quebra de novo, que reindexa com o ALVOS_PADRAO de hoje.
        "nao_extraiveis": nao_extraiveis,
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
    for registro in (*alvo.ancestrais, alvo.folha, *((alvo.par,) if alvo.par else ())):
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


def extrair(destino: str, alvo: str, recorte: Recorte | None = None,
            deve_parar: Callable[[], bool] | None = None) -> str:
    """Grava o parquet com as linhas do alvo e devolve o caminho.

    Com `recorte`, o arquivo que não interessa nem é aberto e a linha que não
    passa nem é gravada — filtrar depois, na planilha, obrigaria a escrever
    milhões de linhas para jogar fora.
    """
    resolvido = _resolver(alvo)
    recorte = recorte or Recorte()
    colunas = _colunas(resolvido)
    esquema = pa.schema([(c, pa.string()) for c in colunas])
    nome = (resolvido if isinstance(resolvido, str) else resolvido.chave).replace("+", "_")
    caminho = os.path.join(destino, ARQUIVO_DA_EXTRACAO.format(
        alvo=nome + impressao_do_recorte(recorte)))
    # nome provisório: duas telas pedindo o mesmo alvo ao mesmo tempo leriam um
    # parquet pela metade, e isso não aparece como erro — aparece como linha
    # faltando na conferência
    parcial = f"{caminho}.{os.getpid()}.parcial"

    escritor = pq.ParquetWriter(parcial, esquema, compression="zstd")
    lote: dict[str, list[str]] = {c: [] for c in colunas}
    gravadas = 0
    lidos = 0
    fora_do_recorte = 0

    def despejar() -> None:
        if not lote[colunas[0]]:
            return
        escritor.write_table(pa.Table.from_pydict(lote, schema=esquema))
        for valores in lote.values():
            valores.clear()

    # o catálogo deduplicado: uma linha por código, ficando com a última vista
    unicas: dict[str, dict[str, str]] = {}
    dedup = resolvido.dedup_por if isinstance(resolvido, Hierarquia) else ""
    recusadas = 0

    def gravar(linha: dict[str, str]) -> None:
        nonlocal gravadas
        for coluna in colunas:
            lote[coluna].append(linha.get(coluna, ""))
        gravadas += 1
        if gravadas % LINHAS_POR_LOTE == 0:
            despejar()

    def acrescentar(linha: dict[str, str]) -> None:
        nonlocal recusadas
        if not recorte.aceita_linha(linha):
            recusadas += 1
            return
        if dedup:
            unicas[linha.get(dedup, "")] = linha
            return
        gravar(linha)

    arquivos_com_o_alvo = 0

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
            # contado ANTES do recorte: "este registro existe na quebra?" é
            # pergunta sobre o índice, não sobre o filtro. Contando depois, um
            # CNPJ que não casa com nada devolveria "registro não indexado" em
            # vez da lista vazia que o recorte pede.
            if isinstance(resolvido, str) and indice.posicoes.get(resolvido):
                arquivos_com_o_alvo += 1
            if not recorte.aceita_arquivo(indice.cabecalho.cnpj,
                                          indice.cabecalho.inicio, indice.cabecalho.fim):
                fora_do_recorte += 1
                continue
            if isinstance(resolvido, str):
                _do_registro(caminho_do_sped, indice, resolvido, origem, acrescentar)
            else:
                _da_hierarquia(caminho_do_sped, indice, resolvido, origem, acrescentar)

        # Registro que nenhum índice guardou não pode virar planilha vazia: a
        # contagem da tela vê todo registro do arquivo, mas o índice só guarda
        # os de ALVOS_PADRAO, e a tela acaba oferecendo alvo que não se extrai
        # (foi o caso do C501 e do C505). Planilha com só o cabeçalho é pior que
        # erro — quem recebe lê como "não existe no SPED".
        if isinstance(resolvido, str) and lidos and not arquivos_com_o_alvo:
            raise AlvoDesconhecido(
                f"O registro {resolvido} não foi indexado nesta quebra, então não "
                f"há o que extrair. Rode a quebra de novo para indexá-lo."
            )
        # o deduplicado só pode sair no fim: a última ocorrência é a que vale,
        # e ela pode estar no último arquivo
        for linha in unicas.values():
            gravar(linha)
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
        "linhas": gravadas, "arquivos": lidos,
        "arquivos_fora_do_recorte": fora_do_recorte,
        "linhas_fora_do_recorte": recusadas,
        "deduplicadas": len(unicas) if dedup else 0,
        "recortado": not recorte.vazio})
    return caminho


def impressao_do_recorte(recorte: Recorte) -> str:
    """Um sufixo curto e estável por recorte.

    Sem ele, pedir o C170 de um CNPJ e depois o de outro serviria o primeiro
    parquet para o segundo — é o mesmo defeito que o cache das planilhas já
    tinha corrigido com o sufixo do recorte.
    """
    if recorte.vazio:
        return ""
    return "_" + hashlib.sha1(repr(recorte).encode()).hexdigest()[:8]


def _do_registro(caminho: str, indice: IndiceDoArquivo, registro: str,
                 origem: dict[str, str], acrescentar) -> None:
    """Pelo índice: só as linhas daquele registro, por `seek`.

    Arquivo que não tem o registro é pulado, não derruba a extração: o C500 só
    aparece em alguns meses, e a planilha tem de sair com o que existe.

    O `for` fica **dentro** do `try` de propósito. `registros()` é um gerador —
    chamá-lo não executa nada, e o `RegistroNaoIndexado` só é levantado no
    primeiro `next()`, isto é, no `for`. Com o `try` só em volta da chamada, a
    proteção nunca pegava e a extração do C500 morria com 500.
    """
    try:
        for valores in registros(caminho, indice, registro):
            linha = dict(origem)
            # os nomes são os **desta linha**: o M210 ganhou três campos em 2019,
            # e um arquivo antigo lido com o leiaute novo põe a alíquota na coluna
            # do ajuste de base — dois números de duas casas, e o erro não aparece
            for i, campo in enumerate(campos_de(registro, len(valores))):
                linha[campo] = valores[i] if i < len(valores) else ""
            acrescentar(linha)
    except RegistroNaoIndexado:
        log.info("registro ausente neste arquivo, pulado",
                 extra={"arquivo": os.path.basename(caminho), "registro": registro})
        return


def _da_hierarquia(caminho: str, indice: IndiceDoArquivo, h: Hierarquia,
                   origem: dict[str, str], acrescentar) -> None:
    """Uma passada pelo arquivo, carregando o último pai visto.

    Sequencial, e não por `seek`, porque o vínculo do SPED **é a ordem**: o
    C170 pertence ao C100 que veio antes dele. Pular direto para as posições da
    folha perderia exatamente a informação que se foi buscar.

    Com `par`, o grupo do pai é acumulado e só sai quando fecha: o C190 traz
    todos os C191 e depois todos os C195, e o que se quer é o par lado a lado.
    """
    de_interesse = {r.encode("ascii") for r in h.registros}
    atual: dict[str, list[str]] = {}
    tabelas: dict[str, dict[str, list[str]]] = {r: {} for r, _ in h.cadastros}
    ligacao = dict(h.cadastros)
    folhas: list[list[str]] = []
    pares: list[list[str]] = []

    def fechar_grupo() -> None:
        """Emite o grupo acumulado, pareando folha e par por posição."""
        if not folhas and not pares:
            return
        for i in range(max(len(folhas), len(pares))):
            linha = dict(origem)
            for pai in h.ancestrais:
                _nomear(linha, pai, atual.get(pai, []))
            _nomear(linha, h.folha, folhas[i] if i < len(folhas) else [])
            _nomear(linha, h.par, pares[i] if i < len(pares) else [])
            _com_cadastros(linha, h, folhas[i] if i < len(folhas) else [], atual,
                           tabelas, ligacao)
            acrescentar(linha)
        folhas.clear()
        pares.clear()

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
                if registro != h.folha:
                    continue
            if registro in h.ancestrais:
                if h.par and registro == h.pai_imediato:
                    fechar_grupo()
                atual[registro] = valores
                continue
            if h.par and registro == h.par:
                pares.append(valores)
                continue
            if registro != h.folha:
                continue
            if h.par:
                folhas.append(valores)
                continue
            linha = dict(origem)
            for pai in h.ancestrais:
                _nomear(linha, pai, atual.get(pai, []))
            _nomear(linha, h.folha, valores)
            _com_cadastros(linha, h, valores, atual, tabelas, ligacao)
            acrescentar(linha)
    fechar_grupo()


def _com_cadastros(linha: dict[str, str], h: Hierarquia, folha: list[str],
                   atual: dict[str, list[str]], tabelas: dict[str, dict[str, list[str]]],
                   ligacao: dict[str, str]) -> None:
    """As tabelas de cadastro, ligadas pelo código que a folha (ou um pai) traz."""
    for cadastro, campo in h.cadastros:
        codigo = _campo(h.folha, folha, campo)
        if not codigo:
            codigo = next(
                (c for pai in h.ancestrais
                 if (c := _campo(pai, atual.get(pai, []), campo))), "")
        _nomear(linha, cadastro, tabelas[cadastro].get(codigo, []))


def _nomear(linha: dict[str, str], registro: str, valores: Iterable[str]) -> None:
    if not registro:
        return
    lista = list(valores)
    # a coluna é a do leiaute canônico; o **nome de cada posição** é o da linha.
    # Num arquivo antigo os três ajustes de base não existem, e as colunas deles
    # ficam vazias — que é a verdade, e não um valor deslocado
    for campo in CAMPOS[registro]:
        linha.setdefault(f"{registro}_{campo}", "")
    for i, campo in enumerate(campos_de(registro, len(lista))):
        # a linha pode vir mais curta que o leiaute — o pai que ainda não
        # apareceu chega vazio, e o SPED corta campo final em branco
        linha[f"{registro}_{campo}"] = lista[i] if i < len(lista) else ""


def _campo(registro: str, valores: list[str], campo: str) -> str:
    """O valor de um campo pelo nome do leiaute. Vazio quando o registro não o tem."""
    nomes = campos_de(registro, len(valores))
    if campo not in nomes:
        return ""
    i = nomes.index(campo)
    return valores[i] if i < len(valores) else ""

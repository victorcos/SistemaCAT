"""O arquivo digital da CAT 42 — o leiaute em código. Puro, sem I/O.

Sétima etapa. O cálculo está na Ficha 3 (`razao.py`) e o fechamento do período
em `apuracao.py`; aqui é **como o arquivo é escrito**, campo a campo, pelo
*Manual de Orientação da Formação do Arquivo Digital*, versão 1.50, transcrito
em `docs/LEIAUTE_ARQUIVO_DIGITAL.md`.

## O que foi conferido contra arquivo real, antes de escrever

Três arquivos que a empresa T transmitiu (2022 a 2024, até 77 MB) confirmam o
que o manual diz e resolvem o que ele deixa ambíguo:

* a linha **não começa com `|`**, ao contrário da EFD; e só termina com `|`
  quando o último campo é vazio — que é o que `"|".join(campos)` dá sozinho;
* CRLF em todas as linhas, Latin-1;
* quantidade sempre com 3 casas (`1,000`), valor sempre com 2 (`0,00`),
  alíquota com 2 (`18,00`), nº do item com 3 dígitos (`033`), país `1058`;
* todo item do 0200 tem 1050, e todo item do 1100 está no 0200.

## Sem sinal

Quantidade e valores de 1100 e 1200 vão positivos, inclusive nas devoluções: o
Pós-Validador põe o sinal ao compor a Ficha 3. Valor negativo aqui é defeito de
quem chamou, e o módulo recusa em vez de escrever.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from cat.dominio.icms.cat42.enquadramento import CFOP_DEVOLUCAO

VERSAO_DO_LEIAUTE = "01"          # 1.0.0, obrigatória a partir de 01/01/2018
PAIS_BRASIL = "1058"
CODIFICACAO = "latin-1"
FIM_DE_LINHA = "\r\n"

# modelos que vão no 1100; o resto é documento não eletrônico (1200)
MODELOS_ELETRONICOS = frozenset({"55", "59", "65"})
# participante só citado nestes modelos não entra no 0150 (item 0150 do manual)
MODELOS_SEM_PARTICIPANTE = frozenset({"02", "2D", "59", "60", "65"})

_DEVOLUCOES = frozenset(c.replace(".", "") for c in CFOP_DEVOLUCAO)
_RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_RE_ESPACOS = re.compile(r"\s+")


class ValorInvalido(ValueError):
    """O que o arquivo não pode levar: valor negativo, data torta, campo sem conteúdo."""


class Finalidade(str, Enum):
    REMESSA_REGULAR = "00"
    INTIMACAO = "01"
    SUBSTITUICAO = "02"


class IndicadorDeOperacao(str, Enum):
    ENTRADA = "0"
    SAIDA = "1"


class Natureza(Enum):
    """As quatro naturezas da tabela de obrigatoriedade do manual (seção 5).

    O indicador diz o sentido físico (entrou ou saiu); o CFOP de devolução
    diz se a operação anula outra. Devolução de venda chega como entrada;
    devolução de compra sai.
    """

    ENTRADA = "entrada"
    DEVOLUCAO_DE_ENTRADA = "devolucao_de_entrada"
    SAIDA = "saida"
    DEVOLUCAO_DE_SAIDA = "devolucao_de_saida"

    @classmethod
    def de(cls, ind_oper: str, cfop: str) -> "Natureza":
        devolucao = cfop.replace(".", "") in _DEVOLUCOES
        if ind_oper == IndicadorDeOperacao.ENTRADA.value:
            return cls.DEVOLUCAO_DE_SAIDA if devolucao else cls.ENTRADA
        return cls.DEVOLUCAO_DE_ENTRADA if devolucao else cls.SAIDA

    @property
    def leva_icms_tot(self) -> bool:
        return self is not Natureza.SAIDA

    @property
    def leva_cod_legal(self) -> bool:
        return self in (Natureza.SAIDA, Natureza.DEVOLUCAO_DE_SAIDA)


# ---------------------------------------------------------------------------
# o leiaute, campo a campo
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Campo:
    """Uma coluna do leiaute.

    `tamanho` None é "sem máximo" (o `-` da tabela); texto sem máximo vai até
    255. `decimais` None é inteiro, sem vírgula. `exato` é o `*` da tabela.
    """

    nome: str
    tipo: str                    # "C" alfanumérico, "N" numérico
    tamanho: int | None = None
    exato: bool = False
    decimais: int | None = None
    obrigatorio: bool = True     # O; os OC têm regra própria

    @property
    def maximo(self) -> int:
        if self.tamanho is not None:
            return self.tamanho
        return 255 if self.tipo == "C" else 10_000


def _c(nome, tamanho=None, obrigatorio=True, exato=False):
    return Campo(nome, "C", tamanho, exato, None, obrigatorio)


def _n(nome, tamanho=None, decimais=None, obrigatorio=True, exato=False):
    return Campo(nome, "N", tamanho, exato, decimais, obrigatorio)


# Errata do manual 1.50: o REG de 1050, 1100 e 1200 aparece como "N 002", mas
# o texto fixo tem 4 caracteres. Tratado como os outros.
_REG = _c("REG", 4, exato=True)

LEIAUTE: dict[str, tuple[Campo, ...]] = {
    "0000": (_REG, _n("PERIODO", 6, exato=True), _c("NOME"), _n("CNPJ", 14, exato=True),
             _c("IE", 14), _n("COD_MUN", 7, exato=True), _n("COD_VER", 2), _n("COD_FIN", 2)),
    "0150": (_REG, _c("COD_PART", 60), _c("NOME"), _n("COD_PAIS", 5, obrigatorio=False),
             _n("CNPJ", 14, obrigatorio=False, exato=True), _n("CPF", 11, obrigatorio=False, exato=True),
             _c("IE", 14, obrigatorio=False), _n("COD_MUN", 7, obrigatorio=False, exato=True)),
    "0200": (_REG, _c("COD_ITEM", 60), _c("DESCR_ITEM"), _c("COD_BARRA", obrigatorio=False),
             _c("UNID_INV", 6), _c("COD_NCM", 8), _n("ALIQ_ICMS", decimais=2, obrigatorio=False),
             _n("CEST", 7, obrigatorio=False, exato=True)),
    "0205": (_REG, _c("COD_ITEM"), _c("COD_ANT_ITEM"), _c("DESCR_ANT_ITEM", obrigatorio=False)),
    "1050": (_REG, _c("COD_ITEM", 60), _n("QTD_INI", decimais=3), _n("ICMS_TOT_INI", decimais=2),
             _n("QTD_FIM", decimais=3), _n("ICMS_TOT_FIM", decimais=2)),
    "1100": (_REG, _n("CHV_DOC", 44, exato=True), _n("DATA", 8, exato=True), _n("NUM_ITEM", 3),
             _n("IND_OPER", 1), _c("COD_ITEM", 60), _n("CFOP", 4, exato=True),
             _n("QTD", decimais=3), _n("ICMS_TOT", decimais=2, obrigatorio=False),
             _n("VL_CONFR", decimais=2, obrigatorio=False), _n("COD_LEGAL", 1, obrigatorio=False)),
    "1200": (_REG, _c("COD_PART", 60, obrigatorio=False), _c("COD_MOD", 2), _c("ECF_FAB", 21, obrigatorio=False),
             _c("SER", 3, obrigatorio=False), _n("NUM_DOC", 9), _n("NUM_ITEM", 3), _n("IND_OPER", 1),
             _n("DATA", 8, exato=True), _n("CFOP", 4, exato=True), _c("COD_ITEM", 60),
             _n("QTD", decimais=3), _n("ICMS_TOT", decimais=2, obrigatorio=False),
             _n("VL_CONFR", decimais=2, obrigatorio=False), _n("COD_LEGAL", 1, obrigatorio=False)),
}

# a ordem dos blocos no arquivo; 0205 é filho do 0200 e vem colado nele
ORDEM_DOS_REGISTROS = {"0000": 0, "0150": 1, "0200": 2, "0205": 2, "1050": 3, "1100": 4, "1200": 5}


# ---------------------------------------------------------------------------
# formatação
# ---------------------------------------------------------------------------
def numero(valor: Decimal | int | None, casas: int, nome: str = "") -> str:
    """Vírgula decimal, sem milhar, com as casas do registro. Vazio fica vazio.

    Arredonda meio para cima, só aqui: o razão guarda 15 casas e arredondar
    antes da escrita deslocaria o saldo.
    """
    if valor is None:
        return ""
    d = Decimal(valor)
    if d < 0:
        raise ValorInvalido(f"{nome or 'valor'} negativo ({d}): o arquivo digital não leva sinal")
    if casas == 0:
        return str(int(d.quantize(Decimal(1), rounding=ROUND_HALF_UP)))
    q = d.quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    return format(q, "f").replace(".", ",")


def data(d: date) -> str:
    return d.strftime("%d%m%Y")


def periodo(ano: int, mes: int) -> str:
    return f"{mes:02d}{ano:04d}"


def texto(valor: str | None, maximo: int = 255) -> str:
    """Texto que cabe no arquivo: sem `|`, sem controle, em Latin-1, cortado.

    Caractere fora do Latin-1 (aspas curvas, travessão, emoji) vira o mais
    próximo que existe nele, e só então `?`: descrição de mercadoria vem do ERP
    com de tudo, e recusar a linha por um apóstrofo seria pior.
    """
    if not valor:
        return ""
    limpo = _RE_CONTROLE.sub(" ", valor.replace("|", " "))
    limpo = _RE_ESPACOS.sub(" ", limpo).strip()
    saida = []
    for ch in limpo:
        try:
            ch.encode(CODIFICACAO)
            saida.append(ch)
        except UnicodeEncodeError:
            aproximado = unicodedata.normalize("NFKD", ch).encode(CODIFICACAO, "ignore").decode(CODIFICACAO)
            saida.append(aproximado or {"‘": "'", "’": "'", "“": '"', "”": '"',
                                        "–": "-", "—": "-"}.get(ch, "?"))
    return "".join(saida)[:maximo]


def so_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def sem_mascara(valor: str | None) -> str:
    """Série e subsérie vão sem máscara: `U-2` vira `U2` (item de formato do manual)."""
    return re.sub(r"[^0-9A-Za-z]", "", valor or "")


def linha(campos: list[str]) -> str:
    """O manual: sem `|` no início nem no fim, salvo campo vazio na ponta."""
    return "|".join(campos)


# ---------------------------------------------------------------------------
# os registros
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Abertura:
    """0000 — um por arquivo: um estabelecimento, um mês."""

    ano: int
    mes: int
    nome: str
    cnpj: str
    ie: str
    cod_mun: str
    finalidade: Finalidade = Finalidade.REMESSA_REGULAR

    def campos(self) -> list[str]:
        if not 1 <= self.mes <= 12:
            raise ValorInvalido(f"mês {self.mes} fora do calendário")
        return ["0000", periodo(self.ano, self.mes), texto(self.nome), so_digitos(self.cnpj),
                texto(so_digitos(self.ie) or self.ie, 14), so_digitos(self.cod_mun),
                VERSAO_DO_LEIAUTE, self.finalidade.value]


@dataclass(frozen=True)
class Participante:
    """0150 — quem aparece nas operações do mês, inclusive o próprio estabelecimento."""

    codigo: str
    nome: str
    cnpj: str = ""
    cpf: str = ""
    ie: str = ""
    cod_mun: str = ""
    cod_pais: str = PAIS_BRASIL

    def campos(self) -> list[str]:
        return ["0150", texto(self.codigo, 60), texto(self.nome), so_digitos(self.cod_pais),
                so_digitos(self.cnpj), "" if self.cnpj else so_digitos(self.cpf),
                texto(so_digitos(self.ie) or self.ie, 14), so_digitos(self.cod_mun)]


@dataclass(frozen=True)
class Item:
    """0200 — 8 campos, não os 13 da EFD. Código e unidade são os do bloco H."""

    codigo: str
    descricao: str
    unidade: str
    ncm: str
    codigo_barras: str = ""
    aliquota: Decimal | None = None
    cest: str = ""

    def campos(self) -> list[str]:
        return ["0200", texto(self.codigo, 60), texto(self.descricao), texto(self.codigo_barras),
                texto(self.unidade, 6), so_digitos(self.ncm)[:8], numero(self.aliquota, 2, "ALIQ_ICMS"),
                so_digitos(self.cest)]


@dataclass(frozen=True)
class Saldo:
    """1050 — o saldo da Ficha 3 no início do primeiro dia e no fim do último."""

    codigo: str
    qtd_ini: Decimal
    icms_tot_ini: Decimal
    qtd_fim: Decimal
    icms_tot_fim: Decimal

    def campos(self) -> list[str]:
        return ["1050", texto(self.codigo, 60), numero(self.qtd_ini, 3, "QTD_INI"),
                numero(self.icms_tot_ini, 2, "ICMS_TOT_INI"), numero(self.qtd_fim, 3, "QTD_FIM"),
                numero(self.icms_tot_fim, 2, "ICMS_TOT_FIM")]


@dataclass(frozen=True)
class Operacao:
    """O que 1100 e 1200 têm em comum: a linha da Ficha 3 vista pelo arquivo."""

    data: date
    num_item: int
    ind_oper: IndicadorDeOperacao
    codigo: str
    cfop: str
    quantidade: Decimal
    icms_tot: Decimal | None = None
    vl_confr: Decimal | None = None
    cod_legal: int | None = None

    @property
    def natureza(self) -> Natureza:
        return Natureza.de(self.ind_oper.value, self.cfop)

    def _valores(self) -> list[str]:
        """ICMS_TOT, VL_CONFR e COD_LEGAL como a tabela da seção 5 manda.

        Quem monta a operação pode mandar a mais (o ICMS da venda, por exemplo):
        o que a natureza não admite sai vazio aqui, e não no arquivo.
        """
        n = self.natureza
        icms = numero(self.icms_tot, 2, "ICMS_TOT") if n.leva_icms_tot else ""
        legal = "" if not n.leva_cod_legal or self.cod_legal is None else str(self.cod_legal)
        confronto = (numero(self.vl_confr, 2, "VL_CONFR")
                     if n.leva_cod_legal and self.cod_legal and self.cod_legal > 0 else "")
        return [icms, confronto, legal]

    def _item(self) -> str:
        if not 1 <= self.num_item <= 999:
            raise ValorInvalido(f"nº do item {self.num_item} fora de 1 a 999")
        return f"{self.num_item:03d}"


@dataclass(frozen=True)
class DocumentoEletronico(Operacao):
    """1100 — NF-e, NFC-e e CF-e SAT, pela chave."""

    chave: str = ""

    def campos(self) -> list[str]:
        return ["1100", so_digitos(self.chave), data(self.data), self._item(), self.ind_oper.value,
                texto(self.codigo, 60), so_digitos(self.cfop), numero(self.quantidade, 3, "QTD"),
                *self._valores()]


@dataclass(frozen=True)
class DocumentoNaoEletronico(Operacao):
    """1200 — ordem diferente do 1100: CFOP antes do código do item."""

    modelo: str = ""
    numero_documento: str = ""
    participante: str = ""
    serie: str = ""
    ecf_fab: str = ""

    def campos(self) -> list[str]:
        return ["1200", texto(self.participante, 60), texto(self.modelo, 2), texto(self.ecf_fab, 21),
                sem_mascara(self.serie)[:3], so_digitos(self.numero_documento)[-9:], self._item(),
                self.ind_oper.value, data(self.data), so_digitos(self.cfop), texto(self.codigo, 60),
                numero(self.quantidade, 3, "QTD"), *self._valores()]


@dataclass
class ArquivoDigital:
    """Um estabelecimento, um mês. Escreve na ordem que o manual exige."""

    abertura: Abertura
    participantes: list[Participante] = field(default_factory=list)
    itens: list[Item] = field(default_factory=list)
    saldos: list[Saldo] = field(default_factory=list)
    eletronicos: list[DocumentoEletronico] = field(default_factory=list)
    nao_eletronicos: list[DocumentoNaoEletronico] = field(default_factory=list)

    def linhas(self):
        yield linha(self.abertura.campos())
        for grupo in (self.participantes, self.itens, self.saldos, self.eletronicos, self.nao_eletronicos):
            for registro in grupo:
                yield linha(registro.campos())

    def nome(self, previa: bool = False) -> str:
        return nome_do_arquivo(self.abertura.cnpj, self.abertura.ano, self.abertura.mes, previa)


def nome_do_arquivo(cnpj: str, ano: int, mes: int, previa: bool = False) -> str:
    """`CAT5_SP_<CNPJ>_<M>_<AAAA>.txt`, o nome dos arquivos que a empresa T transmitiu
    (mês sem zero à esquerda). A prévia leva PREVIA no nome, para nunca ser
    confundida com o que vai à SEFAZ."""
    sufixo = "_PREVIA" if previa else ""
    return f"CAT5_SP_{so_digitos(cnpj)}_{mes}_{ano}{sufixo}.txt"


class TravaDoArquivo(Enum):
    """O que impede um arquivo apto na etapa 6 de ir para o envio.

    A etapa 6 diz se a competência fecha; esta diz se o arquivo se escreve. Um
    arquivo com trava sai como prévia: dá para abrir e conferir, e o nome diz
    que não é o que vai à SEFAZ.
    """

    NAO_APTA = ("Competência com pendência na apuração", "Resolver o que a etapa 6 aponta para esta competência.")
    SEM_DOCUMENTO = ("Linha da Ficha 3 sem documento para o arquivo",
                     "A venda de PDV do relatório não tem chave nem nº do item: falta o XML dos cupons.")
    SAIDA_INDEFINIDA = ("Saída sem enquadramento", "Dizer quem comprou, ou escolher o cupom no 0 no trabalho.")
    DEVOLUCAO_SEM_VENDA = ("Devolução de venda sem a venda original",
                           "O COD_LEGAL da devolução é o da venda: falta a nota referenciada.")
    CONFRONTO_PENDENTE = ("Saída enquadrada sem valor de confronto",
                          "Enquadramentos 2 e 4 dependem do ICMS da operação própria da entrada.")
    SALDO_NEGATIVO = ("Estoque negativo no 1050", "Ficha retirada por estoque negativo: falta movimento.")
    # quantidade positiva e ICMS negativo: a devolução de compra tirou mais
    # imposto do que o estoque guardava. Na empresa V, 813 saldos — quase sempre
    # abertura sem ICMS suportado (item 3.3.8 do manual do sistema)
    VALOR_NEGATIVO = ("ICMS negativo no 1050 com estoque positivo",
                      "Devolução de compra maior que o ICMS em estoque: em geral a abertura veio sem imposto.")
    ITEM_SEM_CADASTRO = ("Item sem cadastro (0200) na EFD", "Importar a EFD do mês ou conferir o código.")
    PARTICIPANTE_SEM_CADASTRO = ("Participante sem cadastro (0150) na EFD", "Importar a EFD do mês do estabelecimento.")
    SEM_ABERTURA = ("Estabelecimento sem EFD no mês para o 0000", "O nome, a IE e o município vêm do 0000 da EFD.")
    PRE_VALIDACAO = ("A pré-validação achou erro", "Ver as ocorrências do arquivo.")

    @property
    def codigo(self) -> str:
        return self.name.lower()

    @property
    def rotulo(self) -> str:
        return self.value[0]

    @property
    def o_que_fazer(self) -> str:
        return self.value[1]


def cod_legal_da_devolucao_de_venda(cfop: str, cupom_no_zero: bool) -> int | None:
    """O enquadramento da venda que a devolução anula, quando dá para saber sem a nota.

    Devolução de venda carrega o COD_LEGAL da venda original. Sem a nota
    referenciada, só dois casos se resolvem: a que vem de fora do estado (a
    venda foi interestadual, enquadramento 4) e, no trabalho que põe o cupom
    no 0, a de dentro do estado — ali consumidor e revendedor são 0 os dois.
    O resto devolve None, e a linha fica pendente em vez de enquadrada no escuro.
    """
    limpo = so_digitos(cfop)
    if limpo.startswith("2"):
        return 4
    if limpo.startswith("1") and cupom_no_zero:
        return 0
    return None

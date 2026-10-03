"""As compras da EFD ICMS/IPI, item a item — a matéria-prima do crédito.

Uma passada por arquivo, uma linha por item de **entrada**, com o documento e o
cadastro do item já juntos. É o que a apuração do combustível multiplica, e é o
que o classificador classifica.

**Este módulo não sabe o que é combustível.** Ele entrega todas as compras; quem
decide o que é diesel é o classificador, e quem decide quanto vale é a apuração.
A razão é a de sempre nesta casa: classificação muda quando entra cliente novo,
tributação muda quando sai convênio, e extração não muda. Três relógios, três
módulos.

## O que é mais simples aqui que na EFD-Contribuições

**Um estabelecimento por arquivo.** A ICMS/IPI traz o CNPJ no `0000` e não tem
`0140` nem `C010` — conferido na lista de registros de 40 arquivos reais. Por
isso o cadastro é uma tabela por arquivo, e não a `CadastroPorEstabelecimento`
que a 037 precisa: lá o mesmo `COD_ITEM` é outra mercadoria em cada filial, aqui
cada filial é outro arquivo.

**Nove ramos viram um.** O crédito de combustível nasce de compra de mercadoria,
que é `C100 > C170`. O bloco D é serviço de transporte, o C500 é energia e o
F100 nem existe aqui.

## O que o dado real ensinou, e sem o que eu teria errado

Medido em 40 EFD ICMS/IPI da empresa G (02/2023 a 03/2026): 7.210 documentos,
6.819 de entrada, 15.107 itens de entrada.

**O `CST_ICMS` carrega duas coisas diferentes.** Para o fornecedor de regime
normal são três dígitos de **origem + CST** (`061` é origem 0, CST 61); para o
do Simples Nacional é o **CSOSN**, que é outro domínio no mesmo campo. Alguns
códigos são ambíguos na forma: `500` pode ser origem 5 com CST 00 (tributada
integralmente) ou CSOSN 500 (ST cobrado anteriormente) — e as duas leituras
dizem o oposto sobre haver imposto.

Resolvido por medição, não por escolha: das **3.245 linhas com `500`, uma só**
traz ICMS destacado. Tributada integralmente traria em quase todas. É CSOSN.
O mesmo método resolveu `400` (179 linhas, nenhuma com ICMS). Já `260` e `560`
são origem + CST 60, porque o CSOSN não tem esses códigos.

**O `VL_ICMS` do C170 é esparso, e isto derruba o caminho óbvio.** O CST `000`
— tributada integralmente — tem 610 linhas de entrada e **só 24 com valor de
ICMS**. O campo é facultativo conforme o perfil, e este cliente quase não o
preenche. Quem for reconstruir ICMS destacado tem de ir ao **`C190`**, que é
obrigatório e soma por CST/CFOP/alíquota. Aqui o campo sai como veio, e sai
`None` quando veio vazio — ver `_decimal`.

**Vazio não é zero.** Foi a lição do relatório 680, e vale igual: alíquota
ausente e alíquota zero são fatos diferentes, e somar as duas como zero esconde
qual dos dois aconteceu.

**Documento cancelado existe e é pouco.** 21 dos 7.210 vieram com `COD_SIT`
`02`. Pouco o bastante para passar despercebido num total, e o suficiente para
um pedido conter nota cancelada. Os itens deles não saem, e a contagem do que
ficou de fora vai no log — nunca descarte calado.

**As unidades do mesmo produto variam no mesmo cliente.** Nas 2.226 linhas de
CST 61 aparecem `L`, `LT`, `LTS` e `l`. Normalizar isso é trabalho do
classificador, com o `0190` e, quando existir, o `0220` — este módulo entrega a
unidade como o arquivo a escreveu.

**Uma pista anotada, não usada.** Das 2.226 linhas de CST 61, **920 trazem
`ALIQ_ICMS` preenchida** e só 2 trazem `VL_ICMS`. No monofásico não há alíquota
percentual, então o que está ali é outra coisa — possivelmente a ad rem no campo
errado. Vale olhar quando a apuração estiver de pé; não vale adivinhar agora.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from cat.infraestrutura.sped.leitor import BUFFER_DE_REDE, campos, registro_de
from cat.infraestrutura.sped.registros_icms import CAMPOS
from cat.log import obter_log

log = obter_log(__name__)

# IND_OPER do C100: 0 é entrada, 1 é saída
ENTRADA = "0"

# COD_SIT que não rende crédito: documento cancelado (02 e 03, o segundo
# extemporâneo), NF-e denegada (04) e numeração inutilizada (05). O resto
# escritura normalmente — inclusive 06, 07 e 08, que são complementar e
# regime especial.
#
# Medido nos 40 arquivos: 7.187 com `00`, 21 com `02`, 2 com `08`.
SITUACOES_SEM_CREDITO = {"02", "03", "04", "05"}

MOTIVO_CANCELADO = "documento cancelado, denegado ou inutilizado"
MOTIVO_SAIDA = "documento de saída"
MOTIVO_LINHA_TORTA = "linha com número de campos fora do leiaute"

# Os códigos do **CSOSN** — o domínio que o Simples Nacional põe no mesmo campo
# `CST_ICMS`. Todos de três dígitos, como origem+CST, e por isso confundíveis.
#
# `500` e `400` estão aqui por **medição**, não por leitura: `500` tem 3.245
# linhas de entrada e uma só com ICMS destacado, e `400` tem 179 e nenhuma —
# origem+CST 00 traria imposto em quase todas. Ver o topo do módulo.
CSOSN = frozenset({"101", "102", "103", "201", "202", "203", "300", "400",
                   "500", "900"})

# A origem da mercadoria: o primeiro dígito, de 0 a 8. **Não há origem 9** — é
# por isso que `900` só pode ser CSOSN, e não origem 9 com CST 00.
ORIGENS = frozenset("012345678")

# Os CST de ICMS que existem.
#
# **A lista clássica não serve mais, e foi aqui que eu errei primeiro.** Escrevi
# {00, 10, 20, 30, 40, 41, 50, 51, 60, 70, 90} — a de sempre — e com ela o
# `061` não era reconhecido como nada. O monofásico criou quatro códigos que
# não estão naquela lista, e um deles **é a tese inteira**:
#
# * `02` — monofásica própria;
# * `15` — monofásica própria e por responsabilidade, com encerramento;
# * `53` — monofásica sobre combustíveis com diferimento;
# * `61` — monofásica cobrada anteriormente. É o CST que marca a compra de
#   combustível de quem consome, e o que o módulo existe para achar.
CST_DE_ICMS = frozenset({"00", "02", "10", "15", "20", "30", "40", "41", "50",
                         "51", "53", "60", "61", "70", "90"})

_POS = {reg: {nome: i for i, nome in enumerate(nomes)}
        for reg, nomes in CAMPOS.items()}

_DE_INTERESSE = {b"0000", b"0150", b"0190", b"0200", b"C100", b"C170"}


@dataclass(frozen=True)
class CodigoDeTributacao:
    """O que o campo `CST_ICMS` diz, depois de desfeita a ambiguidade.

    `cst` e `origem` vêm preenchidos para fornecedor de regime normal; `csosn`,
    para o do Simples Nacional. Nunca os dois — e quando o código não é nenhum
    dos dois, os três ficam vazios e `bruto` guarda o que o arquivo trazia.
    """

    bruto: str
    origem: str = ""
    cst: str = ""
    csosn: str = ""
    # o código cabe nos dois domínios e a leitura é escolha, não leitura.
    # Ver `AMBIGUOS`
    ambiguo: bool = False

    @property
    def e_monofasico(self) -> bool:
        """CST 61 — e **só** o 61. O 60 é toda mercadoria de ST, não combustível."""
        return self.cst == "61"

    @property
    def e_substituicao(self) -> bool:
        """CST 60 ou CSOSN 500: imposto cobrado anteriormente por substituição."""
        return self.cst == "60" or self.csosn == "500"


def _e_origem_com_cst(codigo: str) -> bool:
    return codigo[0] in ORIGENS and codigo[1:] in CST_DE_ICMS


# Os códigos que cabem nos **dois** domínios, e para os quais a leitura é
# escolha e não leitura. Calculados, e não digitados, para que acrescentar um
# CST novo recalcule a lista em vez de deixá-la velha em silêncio.
#
# São cinco: `102` e `202` (origem+CST 02, o monofásico próprio) e `300`, `400`
# e `500` (origem+CST 00). Nos 40 arquivos medidos todos se comportaram como
# CSOSN — `500` tem 3.245 linhas com uma só de ICMS destacado, `400` tem 179 com
# nenhuma —, e é por isso que o CSOSN vence. Mas o par sai marcado `ambiguo`,
# para que a apuração possa recusá-lo em vez de confiar numa estatística de um
# cliente.
AMBIGUOS = frozenset(c for c in CSOSN if _e_origem_com_cst(c))


def codigo_de_tributacao(bruto: str) -> CodigoDeTributacao:
    """Desfaz a ambiguidade do campo `CST_ICMS`.

    Três dígitos que podem ser **origem + CST** (fornecedor de regime normal) ou
    **CSOSN** (Simples Nacional). O CSOSN vence nos cinco códigos que cabem nos
    dois, porque foi assim que o dado se comportou nos 40 arquivos medidos — e
    nesses casos o resultado sai marcado `ambiguo`.

    Código que não cabe em nenhum dos dois volta só com o `bruto` preenchido:
    inventar leitura para código desconhecido é como se escreve um crédito em
    cima de um campo que ninguém entendeu.
    """
    limpo = (bruto or "").strip()
    if len(limpo) != 3 or not limpo.isdigit():
        return CodigoDeTributacao(bruto=limpo)
    if limpo in CSOSN:
        return CodigoDeTributacao(bruto=limpo, csosn=limpo,
                                  ambiguo=limpo in AMBIGUOS)
    if _e_origem_com_cst(limpo):
        return CodigoDeTributacao(bruto=limpo, origem=limpo[0], cst=limpo[1:])
    return CodigoDeTributacao(bruto=limpo)


@dataclass
class LinhaDeCompra:
    """Um item de entrada, com o documento e o cadastro do item juntos."""

    # do arquivo
    cnpj_do_estabelecimento: str
    uf: str
    competencia: str            # "aaaa-mm"
    # do documento
    situacao: str
    modelo: str
    serie: str
    numero: str
    chave: str
    data_de_emissao: str        # "aaaa-mm-dd"
    cnpj_do_fornecedor: str
    nome_do_fornecedor: str
    # do item
    numero_do_item: str
    codigo_do_item: str
    descricao_no_documento: str
    quantidade: Decimal | None
    unidade: str
    valor_do_item: Decimal | None
    cfop: str
    tributacao: CodigoDeTributacao
    base_do_icms: Decimal | None
    aliquota_do_icms: Decimal | None
    valor_do_icms: Decimal | None
    base_do_st: Decimal | None
    aliquota_do_st: Decimal | None
    valor_do_st: Decimal | None
    # do cadastro (0200), que é por arquivo porque o arquivo é de um
    # estabelecimento só
    descricao_do_item: str = ""
    ncm: str = ""
    unidade_de_inventario: str = ""
    cest: str = ""


@dataclass
class ItemDoCadastro:
    """O `0200` de um item, com as descrições anteriores do `0205`.

    O classificador precisa das duas pontas: a descrição de hoje e as de antes.
    Medido na empresa G, a do diesel aparece truncada em 26 caracteres
    ("OLEO DIESEL B S-10 ORIGINA") — e o mesmo código troca de nome no meio do
    período, que é o que o `0205` registra.
    """

    codigo: str
    descricao: str = ""
    ncm: str = ""
    unidade: str = ""
    cest: str = ""
    anteriores: list[tuple[str, str, str]] = field(default_factory=list)


def _decimal(bruto: str) -> Decimal | None:
    """O número do SPED, ou `None` quando o campo veio vazio.

    **Vazio não é zero** — ver o topo do módulo. O separador decimal é a vírgula
    e não há separador de milhar; valor que não converte volta `None` em vez de
    derrubar a passada, e a contagem disso vai no log.
    """
    texto = (bruto or "").strip()
    if not texto:
        return None
    try:
        return Decimal(texto.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _data(bruto: str) -> str:
    """`DDMMAAAA` do SPED em `aaaa-mm-dd`. Vazio volta vazio."""
    texto = (bruto or "").strip()
    if len(texto) != 8 or not texto.isdigit():
        return ""
    return f"{texto[4:]}-{texto[2:4]}-{texto[:2]}"


def _competencia(bruto: str) -> str:
    """`DDMMAAAA` do `0000` em `aaaa-mm`."""
    texto = (bruto or "").strip()
    if len(texto) != 8 or not texto.isdigit():
        return ""
    return f"{texto[4:]}-{texto[2:4]}"


def _em(registro: str, linha: list[str], nome: str) -> str:
    """O campo pelo nome. Linha curta devolve vazio em vez de estourar."""
    i = _POS[registro][nome]
    return linha[i] if i < len(linha) else ""


def compras(caminho: str, codificacao: str) -> Iterator[LinhaDeCompra]:
    """Todos os itens de entrada do arquivo, numa passada.

    Gerador de propósito: a base de um supermercado tem 156 mil itens em doze
    competências, e quem filtra combustível descarta quase todos. Materializar
    a lista para jogar fora 98% dela seria pagar memória por nada.
    """
    contexto = _Contexto()
    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro is None or registro not in _DE_INTERESSE:
                continue
            yield from contexto.ver(
                registro, campos(linha.decode(codificacao, errors="replace")))

    log.info("compras da EFD ICMS/IPI lidas", extra={
        "arquivo": os.path.basename(caminho),
        "cnpj": contexto.cnpj, "competencia": contexto.competencia,
        "documentos": contexto.documentos, "itens": contexto.itens,
        "descartes": dict(sorted(contexto.descartes.items())),
    })


def itens_do_cadastro(caminho: str, codificacao: str) -> dict[str, ItemDoCadastro]:
    """O `0200` e o `0205` do arquivo, por código de item.

    Separado de `compras` porque tem outro consumidor e outro tamanho: o
    classificador roda sobre **códigos distintos**, que são milhares, e não
    sobre linhas de item, que são centenas de milhares. Fazer as duas coisas na
    mesma passada obrigaria a carregar o cadastro inteiro para produzir cada
    linha, ou a devolver uma tupla que mistura dois tempos de vida.

    O bloco 0 é pequeno perto do bloco C: a segunda passada custa pouco e o
    módulo fica com uma responsabilidade por função.
    """
    itens: dict[str, ItemDoCadastro] = {}
    ultimo = ""
    with open(caminho, "rb", buffering=BUFFER_DE_REDE) as arquivo:
        for linha in arquivo:
            registro = registro_de(linha)
            if registro not in (b"0200", b"0205"):
                continue
            valores = campos(linha.decode(codificacao, errors="replace"))
            if registro == b"0200":
                codigo = _em("0200", valores, "COD_ITEM").strip()
                if not codigo:
                    continue
                itens[codigo] = ItemDoCadastro(
                    codigo=codigo,
                    descricao=_em("0200", valores, "DESCR_ITEM").strip(),
                    ncm=_em("0200", valores, "COD_NCM").strip(),
                    unidade=_em("0200", valores, "UNID_INV").strip(),
                    cest=_em("0200", valores, "CEST").strip(),
                )
                ultimo = codigo
            elif ultimo in itens:
                # o 0205 pende do 0200 anterior: é filho, não irmão
                itens[ultimo].anteriores.append((
                    _em("0205", valores, "DESCR_ANT_ITEM").strip(),
                    _data(_em("0205", valores, "DT_INI")),
                    _data(_em("0205", valores, "DT_FIM")),
                ))

    log.info("cadastro de itens da EFD ICMS/IPI lido", extra={
        "arquivo": os.path.basename(caminho), "itens": len(itens),
        "com_descricao_anterior": sum(1 for i in itens.values() if i.anteriores),
    })
    return itens


class _Contexto:
    """O estado da passada: o cabeçalho, o cadastro e o documento aberto.

    Classe e não closures porque são quatro coisas vivas ao mesmo tempo — o
    `0000`, duas tabelas do bloco 0 e o C100 corrente — e porque o contador de
    descartes precisa sobreviver ao gerador para entrar no log.
    """

    def __init__(self) -> None:
        self.cnpj = ""
        self.uf = ""
        self.competencia = ""
        self.participantes: dict[str, tuple[str, str]] = {}
        self.cadastro: dict[str, tuple[str, str, str, str]] = {}
        self.c100: list[str] | None = None
        self.c100_rende_credito = False
        self.documentos = 0
        self.itens = 0
        self.descartes: dict[str, int] = {}

    def _descartar(self, motivo: str) -> None:
        self.descartes[motivo] = self.descartes.get(motivo, 0) + 1

    def ver(self, registro: bytes, valores: list[str]) -> Iterator[LinhaDeCompra]:
        if registro == b"0000":
            self._ler_cabecalho(valores)
        elif registro == b"0150":
            self._ler_participante(valores)
        elif registro == b"0200":
            self._ler_item(valores)
        elif registro == b"C100":
            self._abrir_documento(valores)
        elif registro == b"C170" and self.c100 is not None:
            linha = self._montar(valores)
            if linha is not None:
                yield linha

    def _ler_cabecalho(self, valores: list[str]) -> None:
        if len(valores) != len(CAMPOS["0000"]):
            self._descartar(MOTIVO_LINHA_TORTA)
            return
        self.cnpj = _em("0000", valores, "CNPJ").strip()
        self.uf = _em("0000", valores, "UF").strip().upper()
        self.competencia = _competencia(_em("0000", valores, "DT_INI"))

    def _ler_participante(self, valores: list[str]) -> None:
        codigo = _em("0150", valores, "COD_PART").strip()
        if codigo:
            self.participantes[codigo] = (
                _em("0150", valores, "CNPJ").strip(),
                _em("0150", valores, "NOME").strip(),
            )

    def _ler_item(self, valores: list[str]) -> None:
        codigo = _em("0200", valores, "COD_ITEM").strip()
        if codigo:
            self.cadastro[codigo] = (
                _em("0200", valores, "DESCR_ITEM").strip(),
                _em("0200", valores, "COD_NCM").strip(),
                _em("0200", valores, "UNID_INV").strip(),
                _em("0200", valores, "CEST").strip(),
            )

    def _abrir_documento(self, valores: list[str]) -> None:
        """Abre o C100 e decide, já aqui, se os itens dele rendem crédito."""
        if len(valores) != len(CAMPOS["C100"]):
            self._descartar(MOTIVO_LINHA_TORTA)
            self.c100, self.c100_rende_credito = None, False
            return
        self.documentos += 1
        self.c100 = valores
        situacao = _em("C100", valores, "COD_SIT").strip()
        if _em("C100", valores, "IND_OPER").strip() != ENTRADA:
            self.c100_rende_credito = False
            self._descartar(MOTIVO_SAIDA)
        elif situacao in SITUACOES_SEM_CREDITO:
            self.c100_rende_credito = False
            self._descartar(MOTIVO_CANCELADO)
        else:
            self.c100_rende_credito = True

    def _montar(self, valores: list[str]) -> LinhaDeCompra | None:
        if not self.c100_rende_credito:
            return None
        if len(valores) != len(CAMPOS["C170"]):
            self._descartar(MOTIVO_LINHA_TORTA)
            return None

        doc = self.c100 or []
        codigo = _em("C170", valores, "COD_ITEM").strip()
        descricao, ncm, unidade_inv, cest = self.cadastro.get(
            codigo, ("", "", "", ""))
        cnpj_forn, nome_forn = self.participantes.get(
            _em("C100", doc, "COD_PART").strip(), ("", ""))

        self.itens += 1
        return LinhaDeCompra(
            cnpj_do_estabelecimento=self.cnpj,
            uf=self.uf,
            competencia=self.competencia,
            situacao=_em("C100", doc, "COD_SIT").strip(),
            modelo=_em("C100", doc, "COD_MOD").strip(),
            serie=_em("C100", doc, "SER").strip(),
            numero=_em("C100", doc, "NUM_DOC").strip(),
            chave=_em("C100", doc, "CHV_NFE").strip(),
            data_de_emissao=_data(_em("C100", doc, "DT_DOC")),
            cnpj_do_fornecedor=cnpj_forn,
            nome_do_fornecedor=nome_forn,
            numero_do_item=_em("C170", valores, "NUM_ITEM").strip(),
            codigo_do_item=codigo,
            descricao_no_documento=_em("C170", valores, "DESCR_COMPL").strip(),
            quantidade=_decimal(_em("C170", valores, "QTD")),
            unidade=_em("C170", valores, "UNID").strip(),
            valor_do_item=_decimal(_em("C170", valores, "VL_ITEM")),
            cfop=_em("C170", valores, "CFOP").strip(),
            tributacao=codigo_de_tributacao(_em("C170", valores, "CST_ICMS")),
            base_do_icms=_decimal(_em("C170", valores, "VL_BC_ICMS")),
            aliquota_do_icms=_decimal(_em("C170", valores, "ALIQ_ICMS")),
            valor_do_icms=_decimal(_em("C170", valores, "VL_ICMS")),
            base_do_st=_decimal(_em("C170", valores, "VL_BC_ICMS_ST")),
            aliquota_do_st=_decimal(_em("C170", valores, "ALIQ_ST")),
            valor_do_st=_decimal(_em("C170", valores, "VL_ICMS_ST")),
            descricao_do_item=descricao,
            ncm=ncm,
            unidade_de_inventario=unidade_inv,
            cest=cest,
        )

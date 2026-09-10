"""As linhas do relatório gerencial, já com tipo e já com as regras do trabalho.

O leitor de arquivo entrega texto cru por campo. Aqui esse texto vira data,
decimal e CFOP — e, mais importante, viram as duas decisões que o relatório
gerencial obriga a tomar linha a linha:

**Qual ST vale.** Quando o ERP extrai o valor do XML numa coluna e o valor do
próprio ERP em outra, e os dois divergem, vale o do XML. É a regra que o
Victor fixou para todo o sistema: o documento fiscal é o que a SEFAZ vê.
:attr:`MovimentoGerencial.origem_do_st` diz qual dos dois ganhou, para a
divergência aparecer em relatório em vez de sumir.

**Quanto de imposto a mercadoria carregou.** O manual soma a parcela própria
do substituto, a retida e o FECOEP. Quem compra de substituído não tem
retenção na nota — tem o ST retido anteriormente, informado à parte. As duas
situações caem em :attr:`MovimentoGerencial.imposto_suportado`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from cat.dominio.gerencial import valores as v

ZERO = Decimal("0")

# primeiro dígito do CFOP: 1, 2 e 3 entram; 5, 6 e 7 saem
_ENTRADA = frozenset("123")


class OrigemDoSt(str, Enum):
    XML = "xml"
    ERP = "erp"
    RETIDO_ANTERIOR = "retido_anterior"
    SEM_ST = "sem_st"

    @property
    def rotulo(self) -> str:
        return {
            OrigemDoSt.XML: "XML",
            OrigemDoSt.ERP: "ERP",
            OrigemDoSt.RETIDO_ANTERIOR: "ST retido anteriormente",
            OrigemDoSt.SEM_ST: "sem ST",
        }[self]


@dataclass(frozen=True)
class MovimentoGerencial:
    """Uma linha de item de documento."""

    numero_linha: int
    codigo_item: str
    data: date
    cfop: str
    quantidade: Decimal
    valor_item: Decimal = ZERO

    descricao_item: str = ""
    codigo_barras: str = ""
    ncm: str = ""

    chave: str = ""
    numero_doc: int | None = None
    cnpj_participante: str | None = None
    cpf_participante: str | None = None
    uf_participante: str = ""
    cst_icms: str = ""

    bc_icms: Decimal = ZERO
    valor_icms: Decimal = ZERO
    bc_st: Decimal = ZERO
    valor_st: Decimal = ZERO
    valor_fcp_st: Decimal = ZERO

    bc_st_xml: Decimal = ZERO
    valor_st_xml: Decimal = ZERO
    st_retido_anterior: Decimal = ZERO

    # ---------------- regras do trabalho ----------------
    @property
    def e_entrada(self) -> bool:
        return self.cfop[:1] in _ENTRADA

    @property
    def origem_do_st(self) -> OrigemDoSt:
        if self.valor_st_xml:
            return OrigemDoSt.XML
        if self.valor_st:
            return OrigemDoSt.ERP
        if self.st_retido_anterior:
            return OrigemDoSt.RETIDO_ANTERIOR
        return OrigemDoSt.SEM_ST

    @property
    def st_que_vale(self) -> Decimal:
        """O XML ganha do ERP; sem os dois, vale o retido anteriormente."""
        return {
            OrigemDoSt.XML: self.valor_st_xml,
            OrigemDoSt.ERP: self.valor_st,
            OrigemDoSt.RETIDO_ANTERIOR: self.st_retido_anterior,
            OrigemDoSt.SEM_ST: ZERO,
        }[self.origem_do_st]

    @property
    def divergencia_de_st(self) -> Decimal:
        """Quanto o ERP se afastou do XML. Zero quando não há os dois."""
        if not (self.valor_st_xml and self.valor_st):
            return ZERO
        return self.valor_st - self.valor_st_xml

    @property
    def imposto_suportado(self) -> Decimal:
        """ICMS próprio + ST + FECOEP, que é o que o manual manda somar.

        Quando o ST vem de "retido anteriormente" não há parcela própria na
        nota: a mercadoria já veio tributada, e somar o ICMS da operação
        contaria imposto que não é da mercadoria.
        """
        if self.origem_do_st is OrigemDoSt.RETIDO_ANTERIOR:
            return self.st_retido_anterior + self.valor_fcp_st
        return self.valor_icms + self.st_que_vale + self.valor_fcp_st

    @property
    def unitario_suportado(self) -> Decimal:
        if not self.quantidade:
            return ZERO
        return self.imposto_suportado / self.quantidade

    # ---------------- construção ----------------
    @classmethod
    def de(cls, dados: dict[str, str], numero_linha: int) -> MovimentoGerencial:
        """Monta a partir do texto cru que o leitor entregou."""
        # data e CFOP em branco não dão registro: sem data não há posição no
        # razão, e sem CFOP não se sabe se entrou ou saiu. Vira linha
        # incompleta, contada e mostrada — não some, e também não vira zero.
        d = v.data(dados.get("data"), campo="data")
        if d is None:
            raise v.CampoVazio("data", dados.get("data", ""))
        c = v.cfop(dados.get("cfop"))
        if c is None:
            raise v.CampoVazio("cfop", dados.get("cfop", ""))
        codigo = v.texto(dados.get("codigo_item"))
        if not codigo:
            raise v.CampoVazio("codigo_item")

        cnpj, cpf = v.documento(dados.get("cnpj_participante"))
        return cls(
            numero_linha=numero_linha,
            codigo_item=codigo,
            data=d,
            cfop=c,
            quantidade=v.decimal(dados.get("quantidade"), campo="quantidade"),
            valor_item=v.decimal(dados.get("valor_item"), campo="valor_item"),
            descricao_item=v.texto(dados.get("descricao_item")),
            codigo_barras=v.texto(dados.get("codigo_barras")),
            ncm=v.texto(dados.get("ncm")),
            chave=v.texto(dados.get("chave")),
            numero_doc=v.inteiro(dados.get("numero_doc")),
            cnpj_participante=cnpj,
            cpf_participante=cpf,
            uf_participante=v.texto(dados.get("uf_participante")).upper(),
            cst_icms=v.texto(dados.get("cst_icms")),
            bc_icms=v.decimal(dados.get("bc_icms"), campo="bc_icms"),
            valor_icms=v.decimal(dados.get("valor_icms"), campo="valor_icms"),
            bc_st=v.decimal(dados.get("bc_st"), campo="bc_st"),
            valor_st=v.decimal(dados.get("valor_st"), campo="valor_st"),
            valor_fcp_st=v.decimal(dados.get("valor_fcp_st"), campo="valor_fcp_st"),
            bc_st_xml=v.decimal(dados.get("bc_st_xml"), campo="bc_st_xml"),
            valor_st_xml=v.decimal(dados.get("valor_st_xml"), campo="valor_st_xml"),
            st_retido_anterior=v.decimal(dados.get("st_retido_anterior"),
                                         campo="st_retido_anterior"),
        )


@dataclass(frozen=True)
class ItemInventariado:
    """Uma linha do inventário: o saldo do item e o imposto que ele carrega.

    É o estoque de abertura da Ficha 3 (item 4.1.1). Quando o ERP entrega o ST
    médio por unidade, dispensa a derivação do item 3.3.8 — que é a parte mais
    frágil da montagem, porque depende de reconstituir quais entradas formaram
    o saldo.
    """

    numero_linha: int
    codigo_item: str
    quantidade: Decimal

    estabelecimento: str = ""
    descricao_item: str = ""
    codigo_barras: str = ""
    ncm: str = ""

    custo_medio: Decimal = ZERO
    custo_empresa: Decimal = ZERO
    data_ultima_compra: date | None = None

    icms_unitario: Decimal = ZERO
    bc_st_unitaria: Decimal = ZERO
    st_unitario: Decimal = ZERO
    fcp_st_unitario: Decimal = ZERO
    aliquota_icms: Decimal = ZERO
    aliquota_fcp: Decimal = ZERO

    @property
    def custo(self) -> Decimal:
        """O custo médio manda; o da empresa só entra quando ele vem zerado."""
        return self.custo_medio or self.custo_empresa

    @property
    def valor_do_estoque(self) -> Decimal:
        return self.quantidade * self.custo

    @property
    def suportado_unitario(self) -> Decimal:
        return self.icms_unitario + self.st_unitario + self.fcp_st_unitario

    @property
    def suportado_total(self) -> Decimal:
        return self.quantidade * self.suportado_unitario

    @property
    def tem_imposto_pronto(self) -> bool:
        """Se o ERP já deu o ST por unidade, não é preciso derivar."""
        return bool(self.st_unitario or self.icms_unitario)

    @classmethod
    def de(cls, dados: dict[str, str], numero_linha: int) -> ItemInventariado:
        codigo = v.texto(dados.get("codigo_item"))
        if not codigo:
            raise v.CampoVazio("codigo_item")
        return cls(
            numero_linha=numero_linha,
            codigo_item=codigo,
            quantidade=v.decimal(dados.get("quantidade_estoque"),
                                 campo="quantidade_estoque"),
            estabelecimento=v.texto(dados.get("estabelecimento")),
            descricao_item=v.texto(dados.get("descricao_item")),
            codigo_barras=v.texto(dados.get("codigo_barras")),
            ncm=v.texto(dados.get("ncm")),
            custo_medio=v.decimal(dados.get("custo_medio"), campo="custo_medio"),
            custo_empresa=v.decimal(dados.get("custo_empresa"), campo="custo_empresa"),
            data_ultima_compra=v.data(dados.get("data_ultima_compra"),
                                      campo="data_ultima_compra"),
            icms_unitario=v.decimal(dados.get("icms_unitario"), campo="icms_unitario"),
            bc_st_unitaria=v.decimal(dados.get("bc_st_unitaria"), campo="bc_st_unitaria"),
            st_unitario=v.decimal(dados.get("st_unitario"), campo="st_unitario"),
            fcp_st_unitario=v.decimal(dados.get("fcp_st_unitario"),
                                      campo="fcp_st_unitario"),
            aliquota_icms=v.decimal(dados.get("aliquota_icms"), campo="aliquota_icms"),
            aliquota_fcp=v.decimal(dados.get("aliquota_fcp"), campo="aliquota_fcp"),
        )

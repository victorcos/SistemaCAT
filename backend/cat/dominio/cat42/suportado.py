"""O ICMS suportado na entrada — a matéria-prima da Ficha 3. Puro, sem I/O.

O manual define, no item sobre a coluna 12: o ICMS suportado é a base de
cálculo da sujeição passiva por substituição multiplicada pela alíquota interna
aplicável à saída ao consumidor final. Na prática isso é **o imposto da
operação própria do substituto somado ao retido por substituição**, incluído o
FECOEP da Lei 16.006/2015.

Exemplo do próprio manual: mercadoria a R$ 100,00, IVA-ST de 50%, alíquota
interna de 18%. Base de retenção R$ 150,00 e ICMS suportado R$ 27,00, sendo
R$ 18,00 de operação própria e R$ 9,00 de retido.

## Por que isto é uma etapa inteira, e não uma soma

Porque em quase metade das entradas o número não está no arquivo. Medido na
base real deste cliente, 8.761.002 itens de entrada:

| CST | Itens | Traz ICMS | Traz ST |
|---|---|---|---|
| 60 | 3.705.774 | 0,0% | 0,0% |
| 40 | 2.066.118 | 0,0% | 0,0% |
| 00 | 1.235.767 | 99,9% | 2,0% |
| 20 | 1.073.629 | 98,9% | 0,0% |
| 10 | 58.339 | 99,5% | 95,9% |

O **CST 60 é 42% das entradas e vem com zero nos dois campos**, e está certo
assim: 60 é mercadoria cujo imposto já foi retido antes, então o remetente não
destaca nada. Quem suportou o imposto foi alguém lá atrás, e o valor precisa
vir de outro lugar.

Daí a forma deste módulo: não uma função que devolve um número, mas uma
**cascata de fontes** que devolve o número **e de onde ele veio**. Um valor
estimado e um valor lido da nota não podem virar a mesma coluna sem aviso —
é a diferença entre um pedido de ressarcimento sustentável e um chute.

## O que este módulo não faz

Não busca a informação. Recebe o que já foi lido e decide. Achar o valor do
CST 60 é trabalho de infraestrutura: está no `infAdFisco` da NF-e, no formato
`&|codigo|valor|&`, ou na coluna "ST integral" do relatório gerencial do
cliente. Aqui só se diz qual fonte vale mais e o que fazer quando nenhuma
serve.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

ZERO = Decimal(0)

# Os conjuntos abaixo têm só os DOIS dígitos da tributação, porque é contra eles
# que se compara (`EntradaParaApurar.cst` descarta o primeiro dígito, que é a
# origem da mercadoria). Uma versão anterior trazia "500" e "201" aqui, que
# nunca casavam com nada: no EFD, "500" é origem 5 com CST 00 — tributado sem
# substituição —, e não o CSOSN do Simples Nacional.

# CST cujo imposto já foi retido em operação anterior. O remetente não destaca,
# e é por isso que o valor tem de vir de fora do documento.
CST_JA_RETIDO = frozenset({"60"})

# CST em que o remetente é o substituto e destaca a retenção no documento.
CST_COM_RETENCAO = frozenset({"10", "30", "70"})

# CST 90, "outras", não diz se há substituição. Medido em 2021-05 na base do
# Amigão: metade dos itens de CST 90 que casaram com o relatório do cliente
# tinham imposto informado. Então CST 90 sem valor é dado que falta, não item
# sem imposto — tratá-lo como "sem o que apurar" esconderia pendência real.
CST_PODE_TER_ST = frozenset({"90"})


class Pendencia(Enum):
    """Por que um item ficou sem apuração. São duas coisas opostas.

    A tela de apuração tem uma regra que não se negocia: "não apurável" não é
    sempre erro. Numa base real, 75,6% dos itens sem apuração eram CST 40 —
    isento, que por definição não tem imposto suportado. Pintar isso de alerta
    treina quem confere a ignorar o alerta, e aí o que de fato falta passa
    junto.
    """

    SEM_O_QUE_APURAR = "sem_o_que_apurar"
    """O CST não é de substituição: não há imposto suportado a apurar."""

    FALTA_DADO = "falta_dado"
    """Deveria haver valor e não há. Exige providência."""

    @property
    def exige_providencia(self) -> bool:
        return self is Pendencia.FALTA_DADO


class Fonte(Enum):
    """De onde saiu o ICMS suportado, da mais confiável para a menos.

    A ordem é a da própria cascata, e o número serve para comparar: fonte
    menor é fonte melhor. Guardar isto por linha é o que permite responder,
    na hora da defesa, quanto do pedido se apoia em documento e quanto em
    estimativa.
    """

    DOCUMENTO = 1
    """Destacado na entrada: operação própria mais retenção, do próprio C170."""

    INFORMADO_PELO_FORNECEDOR = 2
    """CST 60 com o retido informado na nota (`infAdFisco`) ou no relatório."""

    BASE_E_ALIQUOTA = 3
    """Sem valor, mas com base de ST e alíquota interna: reconstrói o imposto."""

    NAO_APURAVEL = 9
    """Nada disso existe. Entra na ficha com zero e fica marcado."""

    @property
    def e_documental(self) -> bool:
        """Se o número veio de documento, e não de reconstrução."""
        return self in (Fonte.DOCUMENTO, Fonte.INFORMADO_PELO_FORNECEDOR)

    @property
    def rotulo(self) -> str:
        return _ROTULOS[self]


_ROTULOS = {
    Fonte.DOCUMENTO: "Destacado na entrada",
    Fonte.INFORMADO_PELO_FORNECEDOR: "Informado pelo fornecedor",
    Fonte.BASE_E_ALIQUOTA: "Reconstruído por base e alíquota",
    Fonte.NAO_APURAVEL: "Não apurável",
}


@dataclass(frozen=True)
class EntradaParaApurar:
    """O que se sabe de um item de entrada, venha de onde vier.

    Os campos opcionais são os que nem sempre existem: `retido_informado` vem
    da nota ou do relatório do cliente, e `aliquota_interna` vem do cadastro
    0200 do próprio estabelecimento.
    """

    cst_icms: str = ""
    valor_icms: Decimal = ZERO
    valor_st: Decimal = ZERO
    fcp_st: Decimal = ZERO
    bc_st: Decimal = ZERO
    retido_informado: Decimal | None = None
    aliquota_interna: Decimal | None = None

    @property
    def cst(self) -> str:
        """Só os dois últimos dígitos importam: o primeiro é a origem."""
        limpo = (self.cst_icms or "").strip()
        return limpo[-2:] if len(limpo) >= 2 else limpo


@dataclass(frozen=True)
class IcmsSuportado:
    """O valor apurado e a sua procedência."""

    valor: Decimal
    fonte: Fonte
    motivo: str = ""
    # só quando não apurou: separa "não há o que apurar" de "falta dado"
    pendencia: Pendencia | None = None

    @property
    def apurado(self) -> bool:
        return self.fonte is not Fonte.NAO_APURAVEL


def apurar(entrada: EntradaParaApurar) -> IcmsSuportado:
    """O ICMS suportado deste item de entrada, pela primeira fonte que servir.

    A ordem não é preferência de estilo: é ordem de prova. O que está destacado
    no documento vale mais que o que o fornecedor informou por fora, e os dois
    valem mais que uma reconstrução por alíquota.
    """
    destacado = entrada.valor_st + entrada.fcp_st
    if destacado > ZERO:
        # operação própria do substituto mais o retido, como manda o manual
        return IcmsSuportado(
            valor=entrada.valor_icms + destacado,
            fonte=Fonte.DOCUMENTO,
        )

    if entrada.retido_informado is not None and entrada.retido_informado > ZERO:
        return IcmsSuportado(
            valor=entrada.retido_informado,
            fonte=Fonte.INFORMADO_PELO_FORNECEDOR,
        )

    if (entrada.bc_st > ZERO
            and entrada.aliquota_interna is not None
            and entrada.aliquota_interna > ZERO):
        return IcmsSuportado(
            valor=_arredondar(entrada.bc_st * entrada.aliquota_interna / 100),
            fonte=Fonte.BASE_E_ALIQUOTA,
        )

    pendencia, motivo = _porque_nao(entrada)
    return IcmsSuportado(valor=ZERO, fonte=Fonte.NAO_APURAVEL,
                         motivo=motivo, pendencia=pendencia)


def _porque_nao(entrada: EntradaParaApurar) -> tuple[Pendencia, str]:
    """A frase que a tela mostra, e de que lado da linha ela cai.

    Dizer 'não apurável' sem dizer por quê obriga quem confere a abrir o
    arquivo para descobrir sozinho. E dizer por quê sem separar o que falta do
    que não existe faz o CST 40 parecer defeito.
    """
    cst = entrada.cst
    if cst in CST_JA_RETIDO:
        return (Pendencia.FALTA_DADO,
                "CST 60: o imposto foi retido antes e o remetente não destaca. "
                "Falta o retido informado na nota ou no relatório do cliente.")
    if cst in CST_COM_RETENCAO:
        return (Pendencia.FALTA_DADO,
                "CST de retenção sem valor destacado — a nota deveria trazer "
                "o imposto retido e não trouxe.")
    if cst in CST_PODE_TER_ST:
        return (Pendencia.FALTA_DADO,
                "CST 90, outras operações: pode haver substituição, e nenhuma "
                "fonte informou o imposto. Conferir o documento.")
    if not cst:
        return (Pendencia.FALTA_DADO,
                "Item sem CST: não dá para dizer sequer se é mercadoria de ST.")
    return (Pendencia.SEM_O_QUE_APURAR,
            f"CST {cst} não é de substituição tributária: não há imposto "
            "suportado a apurar neste item.")


def _arredondar(v: Decimal) -> Decimal:
    """Duas casas, como o valor monetário do documento.

    O razão guarda quinze casas porque ali o arredondamento é do custo médio,
    que se propaga; aqui o número é dinheiro de nota fiscal e já veio assim.
    """
    return v.quantize(Decimal("0.01"))


@dataclass
class ResumoDaApuracao:
    """Quanto do ICMS suportado se sustenta em documento, e quanto não.

    É o número que decide se a apuração pode ser entregue: um total alto
    apoiado em reconstrução não é o mesmo trabalho que o mesmo total apoiado
    em nota, e a tela tem de dizer isso antes de alguém assinar embaixo.
    """

    itens: int = 0
    valor_total: Decimal = ZERO
    # itens com o XML ao lado do C170, e quantos se apoiaram no retido que o XML informa
    itens_com_valor_do_xml: int = 0
    itens_com_retido_do_xml: int = 0
    por_fonte: dict[Fonte, int] | None = None
    valor_por_fonte: dict[Fonte, Decimal] | None = None
    por_pendencia: dict[Pendencia, int] | None = None

    def __post_init__(self) -> None:
        if self.por_fonte is None:
            self.por_fonte = {f: 0 for f in Fonte}
        if self.valor_por_fonte is None:
            self.valor_por_fonte = {f: ZERO for f in Fonte}
        if self.por_pendencia is None:
            self.por_pendencia = {p: 0 for p in Pendencia}

    def somar(self, resultado: IcmsSuportado) -> None:
        self.itens += 1
        self.valor_total += resultado.valor
        self.por_fonte[resultado.fonte] += 1
        self.valor_por_fonte[resultado.fonte] += resultado.valor
        if resultado.pendencia is not None:
            self.por_pendencia[resultado.pendencia] += 1

    @property
    def itens_apurados(self) -> int:
        return self.itens - self.por_fonte[Fonte.NAO_APURAVEL]

    @property
    def cobertura(self) -> float:
        """Fração dos itens com algum valor apurado."""
        return self.itens_apurados / self.itens if self.itens else 0.0

    @property
    def valor_documental(self) -> Decimal:
        """Quanto do total veio de documento, e não de reconstrução."""
        return sum((self.valor_por_fonte[f] for f in Fonte if f.e_documental),
                   ZERO)

    @property
    def fracao_documental(self) -> float:
        if self.valor_total == ZERO:
            return 0.0
        return float(self.valor_documental / self.valor_total)

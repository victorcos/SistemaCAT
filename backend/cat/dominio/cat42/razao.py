"""Razão do item — a Ficha 3 da CAT 42, em código. Puro, sem I/O.

O manual não pede um relatório: pede **o método**. Três obrigações numa frase
só, no item 2.2:

> Deverá ser escriturada uma única ficha **para cada código de mercadoria**,
> utilizando-se o sistema de **controle permanente de estoques**, observando
> que o registro diário das entradas e de quaisquer devoluções deverá ser
> realizado **antes do registro das saídas**, adotando, para efeito de
> avaliação, o método do **custo médio ponderado móvel**.

A ordem dentro do dia não é organização: entrada lançada depois da saída daria
outro custo médio, logo outro ressarcimento. Por isso a ordenação é do domínio,
não de quem chama.

O que circula aqui é o **ICMS suportado**: o imposto da operação própria do
substituto somado ao retido por substituição, incluído o FECOEP. É esse valor
que entra no estoque e sai na baixa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum, IntEnum

ZERO = Decimal(0)
# a Ficha 3 grava 15 casas; arredondar antes do fim desloca o total
CASAS = Decimal("0.000000000000001")


class EnquadramentoLegal(IntEnum):
    """Tabela do item 3.3.6.1.1 do manual, sobre o artigo 269 do RICMS."""

    DEMAIS_SAIDAS = 0
    CONSUMIDOR_FINAL = 1
    FATO_GERADOR_NAO_REALIZADO = 2
    ISENCAO_OU_NAO_INCIDENCIA = 3
    OUTRO_ESTADO = 4

    @property
    def gera_ressarcimento(self) -> bool:
        """Enquadramentos 1 a 4 podem gerar ressarcimento; o 0 nunca."""
        return self is not EnquadramentoLegal.DEMAIS_SAIDAS

    @property
    def confronta_com_saida(self) -> bool:
        """Diz qual valor de confronto usar.

        Enquadramentos 1 e 3 confrontam com o ICMS efetivo na SAÍDA (coluna 20).
        Os demais confrontam com o ICMS efetivo da ENTRADA (coluna 21).
        """
        return self in (
            EnquadramentoLegal.CONSUMIDOR_FINAL,
            EnquadramentoLegal.ISENCAO_OU_NAO_INCIDENCIA,
        )


class Especie(Enum):
    """O que o movimento faz com o estoque.

    Devolução não é espécie própria: é a origem com sinal invertido, como manda
    o item 3.3.6. Guardar isso como sinal, e não como tipo, evita duplicar toda
    a regra de cálculo.
    """

    ABERTURA = "abertura"
    ENTRADA = "entrada"
    SAIDA = "saida"

    @property
    def e_entrada(self) -> bool:
        return self in (Especie.ABERTURA, Especie.ENTRADA)


# Dentro do mesmo dia: abertura, depois entradas e devoluções, depois saídas.
_PRIORIDADE = {Especie.ABERTURA: 0, Especie.ENTRADA: 1, Especie.SAIDA: 2}


class MovimentoInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Movimento:
    """Um lançamento na ficha, antes de virar linha do razão."""

    data: date
    especie: Especie
    quantidade: Decimal
    # só nas entradas: o ICMS suportado que entra com a mercadoria.
    # Nas saídas fica None, porque o valor vem do saldo da linha anterior.
    icms_suportado: Decimal | None = None
    enquadramento: EnquadramentoLegal = EnquadramentoLegal.DEMAIS_SAIDAS
    # valor de confronto: o ICMS efetivo, da saída ou da entrada conforme o
    # enquadramento. Sem ele não há ressarcimento a apurar.
    icms_efetivo: Decimal | None = None
    devolucao: bool = False
    cfop: str = ""
    documento: str = ""
    origem: str = ""          # de onde veio: "sped" ou "xml"
    ordem_na_fonte: int = 0    # desempate estável dentro do mesmo dia

    def __post_init__(self) -> None:
        if self.quantidade < ZERO:
            raise MovimentoInvalido(
                "quantidade vem sempre positiva; devolução se marca em "
                "`devolucao`, não com sinal negativo"
            )
        if self.especie.e_entrada and self.icms_suportado is None:
            raise MovimentoInvalido(
                "entrada precisa do ICMS suportado, nem que seja zero"
            )

    @property
    def sinal(self) -> int:
        """Devolução anula a operação de origem, então inverte o sinal."""
        return -1 if self.devolucao else 1

    @property
    def direcao(self) -> int:
        """O que o movimento faz com o estoque: +1 soma, -1 tira.

        São dois fatores independentes e confundi-los foi um bug real: a
        espécie diz o sentido natural (entrada soma, saída tira) e a devolução
        inverte esse sentido. Devolução de saída, por exemplo, é uma entrada.
        """
        return (1 if self.especie.e_entrada else -1) * self.sinal

    @property
    def chave_de_ordem(self) -> tuple:
        return (self.data, _PRIORIDADE[self.especie], self.ordem_na_fonte)


@dataclass(frozen=True)
class LinhaRazao:
    """Uma linha da Ficha 3, já com o saldo depois do movimento."""

    numero: int
    movimento: Movimento
    # quantidade e valor com o sinal aplicado
    quantidade: Decimal
    icms_suportado: Decimal
    valor_unitario_usado: Decimal      # coluna 14: unitário do saldo anterior
    saldo_quantidade: Decimal
    saldo_valor: Decimal
    saldo_unitario: Decimal
    ressarcimento: Decimal
    complemento: Decimal

    @property
    def data(self) -> date:
        return self.movimento.data


class RazaoDoItem:
    """A ficha de um item. Recebe movimentos, devolve linhas e saldo.

    Não guarda I/O nem sabe de onde os movimentos vieram. É o que permite
    testar a regra com dez linhas inventadas, em milissegundos.
    """

    def __init__(self, codigo_item: str, saldo_inicial: "SaldoInicial | None" = None):
        self.codigo_item = codigo_item
        self._movimentos: list[Movimento] = []
        self._inicial = saldo_inicial or SaldoInicial(ZERO, ZERO)

    def lancar(self, movimento: Movimento) -> None:
        self._movimentos.append(movimento)

    def lancar_varios(self, movimentos) -> None:
        self._movimentos.extend(movimentos)

    def apurar(self) -> list[LinhaRazao]:
        """Roda a ficha inteira e devolve as linhas em ordem.

        A ordenação acontece aqui, não em quem chama: o manual exige entradas e
        devoluções antes das saídas no mesmo dia, e essa é a regra que decide o
        custo médio.
        """
        saldo_qtd = self._inicial.quantidade
        saldo_val = self._inicial.valor
        linhas: list[LinhaRazao] = []

        for i, m in enumerate(sorted(self._movimentos, key=lambda x: x.chave_de_ordem), 1):
            # o unitário da saída vem do saldo ANTES deste movimento
            unitario = (saldo_val / saldo_qtd) if saldo_qtd else ZERO

            qtd = m.quantidade * m.direcao
            if m.especie.e_entrada:
                val = (m.icms_suportado or ZERO) * m.direcao
            else:
                # na saída o valor sai pelo unitário do saldo anterior
                val = qtd * unitario

            saldo_qtd += qtd
            saldo_val += val
            # estoque zerado não guarda valor residual de arredondamento
            if saldo_qtd == ZERO:
                saldo_val = ZERO

            ressarc, compl = self._apurar_confronto(m, abs(val))

            linhas.append(
                LinhaRazao(
                    numero=i,
                    movimento=m,
                    quantidade=qtd,
                    icms_suportado=val,
                    valor_unitario_usado=unitario if not m.especie.e_entrada else ZERO,
                    saldo_quantidade=saldo_qtd,
                    saldo_valor=saldo_val,
                    saldo_unitario=(saldo_val / saldo_qtd) if saldo_qtd else ZERO,
                    ressarcimento=ressarc,
                    complemento=compl,
                )
            )
        return linhas

    @staticmethod
    def _apurar_confronto(m: Movimento, suportado: Decimal) -> tuple[Decimal, Decimal]:
        """Ressarcimento e complemento de uma saída.

        Ressarcimento é a diferença positiva entre o enquadramento e o valor de
        confronto. Complemento é a diferença negativa, e **só existe no
        enquadramento 1** — foi o que o manual esclareceu e que a gente havia
        interpretado errado antes.

        Devolução de saída não apura nem um nem outro (item 2.2, colunas 25 e
        26: "exceto nas devoluções de saída").
        """
        if m.especie.e_entrada or m.devolucao:
            return ZERO, ZERO
        if not m.enquadramento.gera_ressarcimento or m.icms_efetivo is None:
            return ZERO, ZERO

        diferenca = suportado - m.icms_efetivo
        if diferenca > ZERO:
            return diferenca, ZERO
        if m.enquadramento is EnquadramentoLegal.CONSUMIDOR_FINAL:
            return ZERO, -diferenca
        return ZERO, ZERO


@dataclass(frozen=True)
class SaldoInicial:
    """Saldo transcrito do período anterior (item 3.3.1 do manual)."""

    quantidade: Decimal
    valor: Decimal

    @property
    def unitario(self) -> Decimal:
        return self.valor / self.quantidade if self.quantidade else ZERO


@dataclass(frozen=True)
class EntradaAnterior:
    """Uma entrada de antes do inventário de abertura, na unidade da ficha."""

    data: date
    quantidade: Decimal
    icms_suportado: Decimal
    ordem: int = 0          # desempate estável no mesmo dia: a maior é a mais recente


@dataclass(frozen=True)
class ValorDaAbertura:
    valor: Decimal
    coberta: Decimal        # quanto da quantidade as entradas alcançaram
    quantidade: Decimal = ZERO

    @property
    def parcial(self) -> bool:
        return ZERO < self.coberta < self.quantidade

    @property
    def sem_valor(self) -> bool:
        return self.quantidade > ZERO and self.coberta == ZERO


def valor_da_abertura(quantidade: Decimal, entradas) -> ValorDaAbertura:
    """O ICMS suportado do estoque de abertura, pelas entradas mais recentes.

    O inventário do cliente pode vir sem o imposto (o do Amigão veio vazio em
    842 mil linhas). O manual não diz como valorar a abertura, mas diz, no
    item 3.3.8, como se acha o valor quando não se identifica a entrada: as
    entradas mais recentes, suficientes para comportar a quantidade, com média
    ponderada quando uma nota não basta. É a mesma pergunta — de que entradas
    veio este estoque — e foi a regra escolhida (decisão do Victor, 16/09/2026).

    Quando as entradas não alcançam a quantidade inteira, o que falta é
    valorado pela média das que alcançaram, e `coberta` diz quanto foi de fato
    coberto. Sem entrada nenhuma, o valor é zero e a ficha fica sinalizada.
    """
    if quantidade <= ZERO:
        return ValorDaAbertura(ZERO, ZERO, quantidade)
    restante = quantidade
    valor = ZERO
    for e in sorted(entradas, key=lambda e: (e.data, e.ordem), reverse=True):
        if restante <= ZERO:
            break
        if e.quantidade <= ZERO:
            continue
        usada = min(restante, e.quantidade)
        valor += e.icms_suportado * usada / e.quantidade
        restante -= usada
    coberta = quantidade - restante
    if ZERO < coberta < quantidade:
        valor = valor * quantidade / coberta
    return ValorDaAbertura(valor, coberta, quantidade)


@dataclass
class ResumoDoRazao:
    """Totais de uma ficha, para conferir contra o que o cliente entregou."""

    codigo_item: str = ""
    linhas: int = 0
    ressarcimento: Decimal = field(default=ZERO)
    complemento: Decimal = field(default=ZERO)
    saldo_quantidade: Decimal = field(default=ZERO)
    saldo_valor: Decimal = field(default=ZERO)

    @classmethod
    def de(cls, codigo_item: str, linhas: list[LinhaRazao]) -> "ResumoDoRazao":
        ultima = linhas[-1] if linhas else None
        return cls(
            codigo_item=codigo_item,
            linhas=len(linhas),
            ressarcimento=sum((l.ressarcimento for l in linhas), ZERO),
            complemento=sum((l.complemento for l in linhas), ZERO),
            saldo_quantidade=ultima.saldo_quantidade if ultima else ZERO,
            saldo_valor=ultima.saldo_valor if ultima else ZERO,
        )

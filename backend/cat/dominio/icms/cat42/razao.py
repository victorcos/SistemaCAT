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

from bisect import bisect_right

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
    # coluna 27, art. 271 do RICMS: no enquadramento 4, a coluna 21 (o ICMS da
    # operação própria da entrada) volta ao contribuinte como crédito
    credito_operacao_propria: Decimal = ZERO

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
            credito = (m.icms_efetivo if m.enquadramento is EnquadramentoLegal.OUTRO_ESTADO
                       and not m.especie.e_entrada and not m.devolucao and m.icms_efetivo is not None
                       else ZERO)

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
                    credito_operacao_propria=credito,
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

    O inventário do cliente pode vir sem o imposto (o da empresa 19 veio vazio em
    842 mil linhas). O manual não diz como valorar a abertura, mas diz, no
    item 3.3.8, como se acha o valor quando não se identifica a entrada: as
    entradas mais recentes, suficientes para comportar a quantidade, com média
    ponderada quando uma nota não basta. É a mesma pergunta — de que entradas
    veio este estoque — e foi a regra escolhida (decisão do Victor, 16/09/2026).

    Quando as entradas não alcançam a quantidade inteira, o que falta é
    valorado pela média das que alcançaram, e `coberta` diz quanto foi de fato
    coberto. Sem entrada nenhuma, o valor é zero e a ficha fica sinalizada.
    """
    return _compor(quantidade, sorted(entradas, key=lambda e: (e.data, e.ordem), reverse=True))


def valor_pelas_entradas_seguintes(quantidade: Decimal, entradas) -> ValorDaAbertura:
    """O ICMS das primeiras entradas a partir de uma data, da mais antiga para a
    mais nova.

    É o caminho da saída de enquadramento 2 ou 4 que aconteceu antes de qualquer
    entrada com destaque do ICMS próprio: vale a primeira que veio depois, e as
    seguintes se uma não basta (decisão do Victor, 26/11/2026).
    """
    return _compor(quantidade, sorted(entradas, key=lambda e: (e.data, e.ordem)))


def _compor(quantidade: Decimal, entradas_em_ordem) -> ValorDaAbertura:
    """Usa as entradas NA ORDEM DADA até cobrir a quantidade, com média
    ponderada quando uma não basta (item 3.3.8)."""
    if quantidade <= ZERO:
        return ValorDaAbertura(ZERO, ZERO, quantidade)
    restante = quantidade
    valor = ZERO
    for e in entradas_em_ordem:
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


def valor_pelas_entradas_do_remetente(quantidade: Decimal, entradas_do_remetente) -> ValorDaAbertura:
    """O ICMS suportado da entrada que veio sem ele, pelas entradas do remetente.

    A Portaria CAT 42/2018 manda quem dá a saída informar o retido na nota
    (`vICMSSTRet`, ID N27) e diz, no § 5º, como achá-lo quando não se identifica
    a entrada: **as entradas mais recentes, suficientes para comportar a
    quantidade envolvida** (redação da CAT-111/18, efeitos desde 01/01/2019).

    É o caso da transferência entre filiais do mesmo titular: medido numa rede de
    varejo em 2026, 94% das entradas por transferência vinham sem o retido, porque
    o CD não o informava. O valor que a nota deveria trazer é o que o remetente
    teria calculado, então ele vem das entradas do remetente, até a data da
    transferência. Não é o custo médio da ficha dele: o parágrafo fala em
    entradas, e o custo médio misturaria saldo antigo com compra recente.

    A conta é a mesma da abertura (item 3.3.8): mesmas entradas mais recentes,
    mesma média quando uma nota não basta, mesmo `coberta` dizendo quanto delas
    alcançou a quantidade.
    """
    return valor_da_abertura(quantidade, entradas_do_remetente)


# ---------------------------------------------------------------------------
# transferência recebida sem o retido: de onde vem o destaque
# ---------------------------------------------------------------------------
# Decisão do Victor, 25/11/2026. Até aqui a transferência sem retido era sempre
# valorada pelas entradas mais recentes do REMETENTE (§ 5º). Na conferência da
# Ficha 3 do projeto 1 (um item de uma loja) o valor não batia com a entrada
# destacada mais próxima da própria loja, porque a do CD vencia por estar mais
# perto no tempo. A ordem passa a ser:
#   1º o destaque do mesmo produto NA MESMA FILIAL, até 6 meses para trás
#      (prioridade) ou, se não houver, até 6 meses para frente;
#   2º sem destaque na filial, o de outra filial DA MESMA UF — primeiro o
#      remetente, depois a filial com o destaque mais próximo —, na mesma
#      janela, e a linha diz de que filial ele veio;
#   3º sem destaque nenhum, nada é estimado: a linha fica marcada para estimar.
# A composição não muda: as entradas da janela, a partir da mais próxima, até
# cobrir a quantidade, com média ponderada quando uma nota não basta.
# "Destaque" é o retido que a nota trouxe: uma transferência valorada por esta
# regra não serve de destaque para outra.
JANELA_DO_DESTAQUE_EM_MESES = 6


class CriterioDoSuportado(str, Enum):
    MESMA_FILIAL_ANTERIOR = "mesma_filial_anterior"
    MESMA_FILIAL_POSTERIOR = "mesma_filial_posterior"
    REMETENTE_ANTERIOR = "remetente_anterior"
    REMETENTE_POSTERIOR = "remetente_posterior"
    OUTRA_FILIAL_ANTERIOR = "outra_filial_anterior"
    OUTRA_FILIAL_POSTERIOR = "outra_filial_posterior"
    PRECISA_ESTIMAR = "precisa_estimar"

    @property
    def rotulo(self) -> str:
        return _ROTULO_DO_CRITERIO[self.value]


_ROTULO_DO_CRITERIO = {
    "mesma_filial_anterior": "Mesma filial, até 6 meses antes",
    "mesma_filial_posterior": "Mesma filial, até 6 meses depois",
    "remetente_anterior": "Filial remetente, até 6 meses antes",
    "remetente_posterior": "Filial remetente, até 6 meses depois",
    "outra_filial_anterior": "Outra filial da mesma UF, até 6 meses antes",
    "outra_filial_posterior": "Outra filial da mesma UF, até 6 meses depois",
    "precisa_estimar": "Sem destaque: precisa estimar",
}


def somar_meses(dia: date, meses: int) -> date:
    """`dia` deslocado de `meses` (negativo volta), no último dia do mês quando
    o dia não existe nele (31/08 - 6 meses = 28/02)."""
    total = dia.year * 12 + dia.month - 1 + meses
    ano, mes = divmod(total, 12)
    mes += 1
    seguinte = date(ano + (mes == 12), mes % 12 + 1, 1)
    ultimo = (seguinte - date.resolution).day
    return date(ano, mes, min(dia.day, ultimo))


@dataclass(frozen=True)
class DestaquesDaFilial:
    """As entradas COM destaque de um produto numa filial, em ordem de data."""

    entradas: list
    datas: list = field(default_factory=list)

    def __post_init__(self):
        if not self.datas:
            object.__setattr__(self, "datas", [e.data for e in self.entradas])

    def anteriores(self, dia: date) -> list:
        """Da mais recente até `dia` (inclusive) para trás, dentro da janela."""
        inicio = somar_meses(dia, -JANELA_DO_DESTAQUE_EM_MESES)
        achadas = []
        i = bisect_right(self.datas, dia)
        while i > 0 and self.datas[i - 1] >= inicio:
            i -= 1
            achadas.append(self.entradas[i])
        return achadas

    def posteriores(self, dia: date) -> list:
        """Da mais próxima depois de `dia` para frente, dentro da janela."""
        fim = somar_meses(dia, JANELA_DO_DESTAQUE_EM_MESES)
        achadas = []
        j = bisect_right(self.datas, dia)
        while j < len(self.datas) and self.datas[j] <= fim:
            achadas.append(self.entradas[j])
            j += 1
        return achadas


@dataclass(frozen=True)
class DestaqueEscolhido:
    criterio: CriterioDoSuportado
    filial: str | None              # de que filial veio o destaque
    valor: ValorDaAbertura
    entradas_usadas: int

    @property
    def precisa_estimar(self) -> bool:
        return self.criterio is CriterioDoSuportado.PRECISA_ESTIMAR


def _ate_cobrir(entradas: list, quantidade: Decimal) -> list:
    usadas, coberto = [], ZERO
    for e in entradas:
        if coberto >= quantidade:
            break
        usadas.append(e)
        coberto += e.quantidade
    return usadas


def escolher_destaque(
    quantidade: Decimal,
    dia: date,
    filial: str,
    remetente: str | None,
    destaques: dict,
    mesma_uf: set | None = None,
) -> DestaqueEscolhido:
    """O ICMS suportado da transferência recebida sem retido, pela ordem da
    decisão de 25/11/2026 (ver o bloco acima).

    `destaques` traz, por filial, as entradas com destaque DO PRODUTO desta
    ficha (`DestaquesDaFilial`); `mesma_uf` são as filiais da UF de `filial`
    — None quando não há cadastro de UF, e então todas valem.
    """
    C = CriterioDoSuportado

    def compor(criterio, origem, entradas):
        usadas = _ate_cobrir(entradas, quantidade)
        return DestaqueEscolhido(criterio, origem, _compor(quantidade, usadas), len(usadas))

    def da(origem, anterior, posterior):
        d = destaques.get(origem)
        if d is None:
            return None
        if antes := d.anteriores(dia):
            return compor(anterior, origem, antes)
        if depois := d.posteriores(dia):
            return compor(posterior, origem, depois)
        return None

    if (r := da(filial, C.MESMA_FILIAL_ANTERIOR, C.MESMA_FILIAL_POSTERIOR)) is not None:
        return r

    def vale(f):
        return f != filial and (mesma_uf is None or f in mesma_uf)

    if remetente and vale(remetente):
        if (r := da(remetente, C.REMETENTE_ANTERIOR, C.REMETENTE_POSTERIOR)) is not None:
            return r
    outras = sorted(f for f in destaques if vale(f) and f != remetente)
    # a filial cujo destaque está mais perto da data: antes, a mais recente; só
    # sem nenhuma antes, a mais próxima depois. Empate: o menor CNPJ (a lista
    # está em ordem e max/min ficam com o primeiro que achar)
    melhor = None
    for f in outras:
        if antes := destaques[f].anteriores(dia):
            if melhor is None or antes[0].data > melhor[0]:
                melhor = (antes[0].data, f, antes)
    if melhor is not None:
        return compor(C.OUTRA_FILIAL_ANTERIOR, melhor[1], melhor[2])
    for f in outras:
        if depois := destaques[f].posteriores(dia):
            if melhor is None or depois[0].data < melhor[0]:
                melhor = (depois[0].data, f, depois)
    if melhor is not None:
        return compor(C.OUTRA_FILIAL_POSTERIOR, melhor[1], melhor[2])
    return DestaqueEscolhido(C.PRECISA_ESTIMAR, None, ValorDaAbertura(ZERO, ZERO, quantidade), 0)


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

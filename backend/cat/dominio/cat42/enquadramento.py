"""De que CFOP sai cada enquadramento legal da Ficha 3. Puro, sem I/O.

O enquadramento decide **em qual coluna** da ficha o valor cai — 15, 16, 17,
18 ou 19 — e **contra o quê** ele é confrontado: o ICMS efetivo da saída
(coluna 20) ou o da entrada (coluna 21). Errar aqui não dá número errado num
item: dá apuração inteira errada, e do jeito que passa despercebido.

Por isso este módulo separa três coisas que costumam virar uma só:

* o que o **manual fixa**, e aqui é regra;
* o que a **estrutura do CFOP** decide sozinha, como o primeiro dígito dizer
  se a operação saiu do estado;
* o que **depende de quem comprou**, que nenhum CFOP responde por completo e
  que este módulo devolve como indefinido em vez de adivinhar.

## O que o manual fixa

| Regra | Enquadramento |
|---|---|
| Baixa de estoque, CFOP 5.927 | 2, fato gerador não realizado |
| Saída para outro estado | 4 |
| Saída com isenção ou não incidência | 3 |

Devolução não é enquadramento: é a operação de origem com o sinal invertido,
e quem trata disso é `Movimento.devolucao`, no razão.

## Por que "indefinido" existe

Numa base real desta casa, 91.007.428 linhas analíticas de saída:

| CFOP | Linhas | O que é |
|---|---|---|
| 5102 | 60,4 milhões | venda de mercadoria de terceiros |
| 5405 | 29,1 milhões | venda de mercadoria com ST, contribuinte substituído |
| 5152 | 0,6 milhão | transferência |
| 5409 | 0,3 milhão | transferência com ST |

O 5.102 e o 5.405 são 98% do movimento, e o enquadramento deles depende de
**quem comprou**: consumidor final cai no 1, contribuinte que vai revender cai
no 0. O CFOP não distingue os dois casos sozinho, e chutar aqui seria decidir
o destino de quase toda a apuração sem base. Quando a informação não vem,
devolve-se `None` e a linha entra contada como indefinida — visível, não
suposta.
"""

from __future__ import annotations

from enum import Enum

from cat.dominio.cat42.razao import EnquadramentoLegal


class VendaAConsumidor(str, Enum):
    """Como o trabalho enquadra a venda a consumidor final. É escolha do
    trabalho, não do sistema (decisão do Victor, 16/09/2026).

    O manual põe a venda a consumidor final no enquadramento 1, que confronta
    o suportado com a alíquota vezes o preço de venda: dá ressarcimento quando
    se vendeu abaixo da base presumida e **complemento** quando se vendeu acima.

    Os arquivos que a IRMAOS BOA transmitiu fazem outra coisa: o cupom (CF-e
    SAT, CFOP 5.405) vai com COD_LEGAL **0**, na Ficha 3 e no arquivo, e só a
    perda (5.927) entra no enquadramento 2. Não há complemento. Medido em três
    arquivos reais, 2022 a 2024.

    As duas leituras mudam o valor do pedido — no piloto do Amigão, o
    complemento inteiro vem do enquadramento 1 —, e por isso o razão guarda
    qual delas usou.
    """

    ENQUADRAMENTO_1 = "enquadramento_1"
    DEMAIS_SAIDAS = "demais_saidas"

    @property
    def rotulo(self) -> str:
        return {
            VendaAConsumidor.ENQUADRAMENTO_1: "Enquadramento 1: pede ressarcimento e recolhe complemento",
            VendaAConsumidor.DEMAIS_SAIDAS: "Demais saídas (0): só as perdas e as interestaduais",
        }[self]

    @classmethod
    def de(cls, valor: str | None) -> "VendaAConsumidor":
        """O valor gravado no trabalho; vazio é o do manual."""
        return cls(valor) if valor else cls.ENQUADRAMENTO_1

# Baixa de estoque: perecimento, deterioração, roubo, furto, extravio. O manual
# manda uma única nota por período, um item por mercadoria.
CFOP_BAIXA_DE_ESTOQUE = frozenset({"5927", "5.927"})

# Transferência entre estabelecimentos do mesmo titular. Não é saída a
# consumidor: a mercadoria segue para revenda, então é "demais saídas".
CFOP_TRANSFERENCIA = frozenset({
    "5151", "5152", "5153", "5155", "5156",
    "5408", "5409",
    "6151", "6152", "6153", "6155", "6156",
    "6408", "6409",
})

# Devolução. Não define enquadramento — inverte o sinal da operação original.
# O 5.410 fica aqui e não em transferência: é devolução de compra para
# industrialização em operação com ST. Ter o mesmo CFOP nos dois conjuntos
# faria a ordem das regras decidir o resultado, que é como se esconde um erro.
CFOP_DEVOLUCAO = frozenset({
    "1201", "1202", "1410", "1411",
    "2201", "2202", "2410", "2411",
    "5201", "5202", "5410", "5411",
    "6201", "6202", "6410", "6411",
})

# Uso e consumo. Não entra no estoque de comercialização que a Ficha 3 controla:
# a compra para consumo (1.407, 1.556), a transferência de material de consumo
# (1.557) e as devoluções e saídas correspondentes. No Amigão eram 366 linhas
# de entrada na ficha (decisão do Victor, 16/09/2026: excluir e contar).
CFOP_USO_E_CONSUMO = frozenset({
    "1407", "1556", "1557", "2407", "2556", "2557",
    "5556", "5557", "6556", "6557",
})

# Outras entradas e saídas (X.949). Na Advertising eram remessa e retorno de
# armazém e depósito: a mercadoria sai e volta, e a venda de verdade já está na
# ficha. Deixá-las dentro dava saída e entrada pelo preço de custo — um falso
# ressarcimento (decisão do Victor, 16/09/2026: excluir e contar, como a RVZ).
CFOP_OUTRAS_X949 = frozenset({"1949", "2949", "3949", "5949", "6949", "7949"})

# Modelos que só existem para documentar venda a consumidor final. Não é
# suposição sobre o comprador: é o que o modelo é. Tabela 4.1.1 do leiaute.
#
#   02 . Nota Fiscal de Venda a Consumidor
#   2D . Cupom Fiscal emitido por ECF
#   59 . CF-e SAT
#   65 . NFC-e
#
# Numa base real esses modelos são 98,4% das linhas de saída: 66,1% em NFC-e e
# 32,3% em CF-e SAT. O modelo 55, que de fato pode ir para qualquer comprador,
# é 1,6% — e quase todo ele é transferência, que o CFOP já resolve.
MODELOS_DE_CONSUMIDOR_FINAL = frozenset({"02", "2", "2D", "59", "65"})

# CST de saída sem imposto a incidir. O 60 NÃO entra: mercadoria com ST já
# retida é justamente o caso do ressarcimento, e classificá-la como isenta
# jogaria a apuração inteira na coluna errada.
CST_ISENTO_OU_NAO_TRIBUTADO = frozenset({"40", "41", "50"})


def _limpo(cfop: str) -> str:
    return (cfop or "").replace(".", "").strip()


def consumidor_final_pelo_modelo(modelo: str) -> bool | None:
    """Se o modelo do documento já diz que a venda foi a consumidor final.

    Devolve `None` para o modelo 55 e afins: a NF-e serve aos dois casos, e
    dizer que ela é de consumidor seria exatamente o chute que este módulo
    existe para evitar.
    """
    m = (modelo or "").strip().upper().lstrip("0") or "0"
    alvo = {x.lstrip("0") or "0" for x in MODELOS_DE_CONSUMIDOR_FINAL}
    return True if m in alvo else None


def e_devolucao(cfop: str) -> bool:
    """Devolução inverte o lado, e isso é do razão, não do enquadramento."""
    return _limpo(cfop) in {_limpo(c) for c in CFOP_DEVOLUCAO}


def e_interestadual(cfop: str) -> bool:
    """O primeiro dígito do CFOP diz o destino: 5 dentro, 6 e 7 fora."""
    limpo = _limpo(cfop)
    return bool(limpo) and limpo[0] in ("6", "7")


def classificar(
    cfop: str,
    cst_icms: str = "",
    consumidor_final: bool | None = None,
    modelo: str = "",
    venda_a_consumidor: VendaAConsumidor = VendaAConsumidor.ENQUADRAMENTO_1,
) -> EnquadramentoLegal | None:
    """O enquadramento desta saída, ou `None` quando não dá para saber.

    `consumidor_final` é a informação que o CFOP não carrega. Quando vem,
    decide entre o enquadramento 1 e o 0. Quando não vem, as vendas comuns
    ficam indefinidas de propósito.

    `venda_a_consumidor` é a escolha do trabalho. Em `DEMAIS_SAIDAS` a venda
    comum é 0 dos dois lados — consumidor ou contribuinte que revende —, e
    deixa de haver o que perguntar sobre quem comprou.

    A ordem das regras é de força: o que o manual fixa vem antes do que o CFOP
    sugere, e o que o CFOP sugere vem antes do que se poderia supor.
    """
    limpo = _limpo(cfop)
    if not limpo:
        return None

    # 1. o que o manual fixa
    if limpo in {_limpo(c) for c in CFOP_BAIXA_DE_ESTOQUE}:
        return EnquadramentoLegal.FATO_GERADOR_NAO_REALIZADO

    if e_interestadual(limpo):
        return EnquadramentoLegal.OUTRO_ESTADO

    cst = (cst_icms or "").strip()[-2:]
    if cst in CST_ISENTO_OU_NAO_TRIBUTADO:
        return EnquadramentoLegal.ISENCAO_OU_NAO_INCIDENCIA

    # 2. o que a estrutura do CFOP decide
    if limpo in {_limpo(c) for c in CFOP_TRANSFERENCIA}:
        # segue para revenda: não é saída a consumidor
        return EnquadramentoLegal.DEMAIS_SAIDAS

    # 3. o que depende de quem comprou — a menos que o trabalho não peça o
    # enquadramento 1: aí consumidor e revendedor caem os dois no 0
    if venda_a_consumidor is VendaAConsumidor.DEMAIS_SAIDAS:
        return EnquadramentoLegal.DEMAIS_SAIDAS

    # o modelo do documento responde por quase todo o movimento, e responde por
    # definição, não por suposição
    if consumidor_final is None:
        consumidor_final = consumidor_final_pelo_modelo(modelo)
    if consumidor_final is True:
        return EnquadramentoLegal.CONSUMIDOR_FINAL
    if consumidor_final is False:
        return EnquadramentoLegal.DEMAIS_SAIDAS
    return None


def motivo_do_indefinido(cfop: str) -> str:
    """A frase que a tela mostra quando não se soube classificar."""
    limpo = _limpo(cfop)
    if not limpo:
        return "Saída sem CFOP: não há como enquadrar."
    return (
        f"CFOP {limpo} depende de quem comprou: consumidor final cai no "
        "enquadramento 1, contribuinte que revende cai no 0. Falta essa "
        "informação na fonte."
    )

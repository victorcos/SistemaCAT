"""Correção à mão: o que uma pessoa pode mudar no que o sistema calculou.

O sistema lê documento fiscal, e documento fiscal vem errado. Alíquota que o
0200 não traz, enquadramento que nenhum CFOP decide, nota cancelada que não veio
na lista de canceladas, quantidade digitada errada no ERP do cliente. Até aqui
esses casos viravam pendência contada — visível, e parada. A correção é o jeito
de destravá-los **sem mexer no dado de origem**: o parquet do documento continua
como o documento é, e a correção fica ao lado, com autor, data e motivo.

## O que se pode corrigir

| Campo | Alvo | Para quê |
|---|---|---|
| `aliquota` | mercadoria | a interna do confronto, quando o cadastro não traz ou traz errado |
| `reducao_base` | mercadoria | o percentual de redução, quando a entrada não permite deduzi-lo |
| `enquadramento` | linha | o 1, 2, 3, 4 ou 0 que o CFOP e o `indFinal` não decidem |
| `quantidade` | linha | o que o ERP escriturou errado |
| `valor_item` | linha | idem, e é a base do confronto |
| `icms_suportado` | linha | o imposto da entrada, quando a nota não o traz |
| `excluida` | linha | tirar da ficha o que não devia estar, ou trazer de volta |

## Três regras que não se negociam

**Correção é do trabalho, não da empresa** (decisão do Victor, 20/09/2026). O
de-para vale para a empresa porque o código do fornecedor não muda de ano para
ano; uma alíquota corrigida, sim — muda com a lei, e o trabalho seguinte tem de
olhar de novo em vez de herdar.

**Toda correção tem motivo escrito.** É o que a fiscalização vai ler, e é o que
o revisor precisa para aprovar a entrega. Sem motivo, não grava.

**Correção não apaga o original.** O valor que o documento trazia continua no
parquet, e a Ficha 3 mostra os dois: o que veio e o que se corrigiu. Desfazer é
tirar a correção, não reescrever o dado.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum


class Alvo(str, Enum):
    """O que a correção alcança."""

    MERCADORIA = "mercadoria"   # todas as linhas daquele código, no trabalho
    LINHA = "linha"             # um item de um documento


class Campo(str, Enum):
    ALIQUOTA = "aliquota"
    REDUCAO_BASE = "reducao_base"
    ENQUADRAMENTO = "enquadramento"
    QUANTIDADE = "quantidade"
    VALOR_ITEM = "valor_item"
    ICMS_SUPORTADO = "icms_suportado"
    EXCLUIDA = "excluida"

    @property
    def alvo(self) -> Alvo:
        return (Alvo.MERCADORIA if self in (Campo.ALIQUOTA, Campo.REDUCAO_BASE)
                else Alvo.LINHA)

    @property
    def rotulo(self) -> str:
        return {
            Campo.ALIQUOTA: "Alíquota interna",
            Campo.REDUCAO_BASE: "Redução de base (%)",
            Campo.ENQUADRAMENTO: "Enquadramento legal",
            Campo.QUANTIDADE: "Quantidade",
            Campo.VALOR_ITEM: "Valor do item (base do ICMS)",
            Campo.ICMS_SUPORTADO: "ICMS suportado",
            Campo.EXCLUIDA: "Fora da ficha",
        }[self]

    @property
    def o_que_faz(self) -> str:
        return {
            Campo.ALIQUOTA: "Troca a alíquota do confronto de todas as linhas da mercadoria.",
            Campo.REDUCAO_BASE: "Troca a redução de base da mercadoria; 0 tira a redução.",
            Campo.ENQUADRAMENTO: "Define o enquadramento legal da saída, inclusive quando ficou indefinido.",
            Campo.QUANTIDADE: "Troca a quantidade da linha, na unidade em que ela está na ficha.",
            Campo.VALOR_ITEM: "Troca o valor do item, que é a base do valor de confronto.",
            Campo.ICMS_SUPORTADO: "Troca o ICMS suportado que a entrada traz para a ficha.",
            Campo.EXCLUIDA: "Tira a linha da ficha (sim) ou traz de volta uma tirada antes (não).",
        }[self]


MOTIVO_MINIMO = 3
MOTIVO_MAXIMO = 500
CORRECOES_POR_PEDIDO = 5000

_Q4 = Decimal("0.0001")
_Q6 = Decimal("0.000001")


class CorrecaoInvalida(ValueError):
    """A correção não se sustenta, e gravá-la seria pior que recusá-la."""


@dataclass(frozen=True)
class Correcao:
    """Uma correção já conferida, pronta para gravar ou aplicar."""

    campo: Campo
    valor: Decimal | int | bool
    motivo: str
    cnpj: str = ""
    codigo: str = ""
    documento: str = ""
    numero_item: int | None = None

    @property
    def alvo(self) -> Alvo:
        return self.campo.alvo

    @property
    def valor_gravado(self) -> str:
        """O valor como texto, que é como ele atravessa banco e parquet."""
        if isinstance(self.valor, bool):
            return "sim" if self.valor else "nao"
        return str(self.valor)


def _decimal(valor, campo: Campo) -> Decimal:
    try:
        return Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError) as erro:
        raise CorrecaoInvalida(f"{campo.rotulo}: '{valor}' não é um número.") from erro


def validar(campo: str | Campo, valor, motivo: str | None, cnpj: str = "", codigo: str = "",
            documento: str = "", numero_item=None) -> Correcao:
    """Confere a correção e devolve-a normalizada, ou recusa dizendo por quê.

    A mesma regra vale para quem sobe planilha e para quem edita na tela: é por
    isso que ela mora aqui, e não em cada porta de entrada.
    """
    try:
        campo = Campo(campo)
    except ValueError as erro:
        raise CorrecaoInvalida(f"Campo desconhecido: {campo}.") from erro

    texto = (motivo or "").strip()
    if len(texto) < MOTIVO_MINIMO:
        raise CorrecaoInvalida("Toda correção precisa de um motivo escrito — é o que a fiscalização vai ler.")
    if len(texto) > MOTIVO_MAXIMO:
        raise CorrecaoInvalida(f"O motivo passa de {MOTIVO_MAXIMO} caracteres.")

    cnpj = (cnpj or "").strip()
    if cnpj and (len(cnpj) != 14 or not cnpj.isdigit()):
        raise CorrecaoInvalida("O CNPJ do estabelecimento tem 14 dígitos.")
    codigo = (codigo or "").strip()
    documento = (documento or "").strip()

    if campo.alvo is Alvo.MERCADORIA:
        if not codigo:
            raise CorrecaoInvalida(f"{campo.rotulo} é da mercadoria: falta o código dela.")
        documento, numero_item = "", None
    else:
        if not documento:
            raise CorrecaoInvalida(f"{campo.rotulo} é da linha: falta a chave ou o número do documento.")
        if numero_item in (None, ""):
            raise CorrecaoInvalida(
                f"{campo.rotulo} é da linha: falta o número do item no documento. "
                "Linha de relatório de PDV, que não tem item, não pode ser corrigida uma a uma.")
        try:
            numero_item = int(numero_item)
        except (TypeError, ValueError) as erro:
            raise CorrecaoInvalida(f"Número do item inválido: {numero_item}.") from erro
        if numero_item <= 0:
            raise CorrecaoInvalida("O número do item começa em 1.")

    valor_final: Decimal | int | bool
    if campo is Campo.EXCLUIDA:
        texto_valor = str(valor).strip().lower()
        if texto_valor in ("sim", "true", "1", "s", "x"):
            valor_final = True
        elif texto_valor in ("nao", "não", "false", "0", "n", ""):
            valor_final = False
        else:
            raise CorrecaoInvalida(f"{campo.rotulo}: responda sim ou não, não '{valor}'.")
    elif campo is Campo.ENQUADRAMENTO:
        numero = _decimal(valor, campo)
        if numero != numero.to_integral_value() or not 0 <= numero <= 4:
            raise CorrecaoInvalida("O enquadramento legal é um número de 0 a 4.")
        valor_final = int(numero)
    elif campo is Campo.ALIQUOTA:
        numero = _decimal(valor, campo)
        if not 0 < numero <= 100:
            raise CorrecaoInvalida("A alíquota vai de zero (exclusive) a 100.")
        valor_final = numero.quantize(_Q4)
    elif campo is Campo.REDUCAO_BASE:
        numero = _decimal(valor, campo)
        if not 0 <= numero < 100:
            raise CorrecaoInvalida("A redução de base vai de 0 a 100 (exclusive); 0 tira a redução.")
        valor_final = numero.quantize(_Q4)
    elif campo is Campo.QUANTIDADE:
        numero = _decimal(valor, campo)
        if numero <= 0:
            raise CorrecaoInvalida("A quantidade é maior que zero: o sinal quem dá é a espécie do movimento.")
        valor_final = numero.quantize(_Q6)
    else:                                   # valor do item e ICMS suportado
        numero = _decimal(valor, campo)
        if numero < 0:
            raise CorrecaoInvalida(f"{campo.rotulo} não pode ser negativo.")
        valor_final = numero.quantize(_Q6)

    return Correcao(campo=campo, valor=valor_final, motivo=texto, cnpj=cnpj, codigo=codigo,
                    documento=documento, numero_item=numero_item)

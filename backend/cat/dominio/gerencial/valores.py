"""Conversão dos valores do relatório gerencial para os tipos do domínio.

O relatório é texto exportado de ERP, e cada ERP escreve à sua maneira. O que
vimos em arquivo real, e que estas funções tratam:

* data ``02/01/20`` — dia/mês/ano com **ano de dois dígitos**;
* CFOP ``1.102`` — com ponto, que não faz parte do código;
* decimal ``10,881`` e ``1275,55`` — vírgula decimal, três ou duas casas;
* participante ``00176231110`` — onze dígitos, ou seja **CPF**, não CNPJ
  (produtor rural entrega nota como pessoa física).

Nada aqui levanta exceção por valor vazio: coluna em branco é a regra no
relatório, e quem chama decide se a ausência importa. Valor **inválido** é
outra coisa — esse levanta, porque silenciar um número que veio errado é como
se perde dinheiro numa apuração.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")

# ano de dois dígitos: abaixo do pivô é 2000, acima é 1900. Trabalho fiscal
# não olha para antes de 1970, então o pivô nunca estorva.
PIVO_DO_SECULO = 70

_SO_DIGITOS = re.compile(r"\D")
# o separador é obrigatório aqui: sem ele, `02012020` casaria como 0201/20/20
_RE_DATA = re.compile(r"^(\d{1,4})[/.-](\d{1,2})[/.-](\d{2,4})$")


class ValorInvalido(ValueError):
    """O campo veio preenchido, mas não dá para ler como o tipo esperado."""

    def __init__(self, campo: str, bruto: str, esperado: str) -> None:
        self.campo = campo
        self.bruto = bruto
        super().__init__(f"{campo}={bruto!r} não é {esperado}")


class CampoVazio(ValorInvalido):
    """O registro precisa do campo e ele veio em branco.

    Separado de :class:`ValorInvalido` de propósito. Campo em branco é dado
    incompleto — acontece o tempo todo em relatório de ERP, e o certo é
    contar e seguir. Valor corrompido é sintoma de coluna mapeada errada, e
    seguir aí é apurar em cima de coluna trocada. Uma coisa não pode acionar
    a defesa da outra.
    """

    def __init__(self, campo: str, bruto: str = "") -> None:
        self.campo = campo
        self.bruto = bruto
        ValueError.__init__(self, f"{campo} em branco")


def texto(bruto: str | None) -> str:
    return (bruto or "").strip()


def decimal(bruto: str | None, *, campo: str = "valor") -> Decimal:
    """Número em português: vírgula decimal, ponto de milhar.

    Regra de desempate quando só há ponto: ``1.234`` é milhar (três casas
    depois do último ponto), ``1.23`` é decimal. Vale para o que os ERPs
    escrevem; um relatório que use ponto decimal com três casas seria lido
    com fator mil de erro, e por isso o número que sai daqui é sempre
    conferido contra o total do documento na etapa de movimentos.
    """
    t = texto(bruto).replace(" ", "").replace("\xa0", "")
    if not t:
        return ZERO

    negativo = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("()-")
    if not t:
        return ZERO

    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif "." in t:
        cabeca, _, cauda = t.rpartition(".")
        if cabeca and len(cauda) == 3:
            t = t.replace(".", "")

    try:
        v = Decimal(t)
    except InvalidOperation:
        raise ValorInvalido(campo, texto(bruto), "um número") from None
    return -v if negativo else v


def inteiro(bruto: str | None, *, campo: str = "numero") -> int | None:
    t = _SO_DIGITOS.sub("", texto(bruto))
    return int(t) if t else None


def data(bruto: str | None, *, campo: str = "data") -> date | None:
    """dd/mm/aa, dd/mm/aaaa, ddmmaaaa ou aaaa-mm-dd."""
    t = texto(bruto)
    if not t:
        return None

    digitos = _SO_DIGITOS.sub("", t)
    if t == digitos and len(digitos) == 8:      # ddmmaaaa, colado, como no SPED
        a, b, c = digitos[:2], digitos[2:4], digitos[4:]
    else:
        m = _RE_DATA.match(t)
        if m is None:
            raise ValorInvalido(campo, t, "uma data")
        a, b, c = m.groups()
    if len(a) == 4:                      # aaaa-mm-dd
        ano, mes, dia = int(a), int(b), int(c)
    else:                                # dd/mm/aa(aa)
        dia, mes, ano = int(a), int(b), int(c)
        if len(c) <= 2:
            ano += 2000 if ano < PIVO_DO_SECULO else 1900

    try:
        return date(ano, mes, dia)
    except ValueError:
        raise ValorInvalido(campo, t, "uma data válida") from None


def cfop(bruto: str | None, *, campo: str = "cfop") -> str | None:
    """``1.102`` e ``1102`` são o mesmo CFOP. Sai sempre com quatro dígitos."""
    t = _SO_DIGITOS.sub("", texto(bruto))
    if not t:
        return None
    if len(t) != 4:
        raise ValorInvalido(campo, texto(bruto), "um CFOP de quatro dígitos")
    return t


def documento(bruto: str | None) -> tuple[str | None, str | None]:
    """Devolve ``(cnpj, cpf)``: onze dígitos é CPF, catorze é CNPJ.

    Não valida dígito verificador aqui — o relatório é fonte de terceiro e uma
    inscrição malformada não deve derrubar a importação inteira. Quem precisa
    de garantia usa o objeto :class:`~cat.dominio.comum.cnpj.Cnpj`.
    """
    t = texto(bruto)
    limpo = re.sub(r"[^0-9A-Za-z]", "", t)
    if len(limpo) == 14:
        return limpo.upper(), None
    if len(limpo) == 11:
        return None, limpo
    return None, None

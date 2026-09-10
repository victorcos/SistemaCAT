"""CNPJ — objeto de valor.

Suporta os dois formatos, e isso não é preciosismo: a Receita passou a emitir
CNPJ **alfanumérico** em 31/07/2026. Um validador que só aceite dígito recusaria
empresa nova legítima.

Estrutura, igual nos dois formatos:

    AAAAAAAA  OOOO  DD
    └─raiz─┘  └ord┘ └dv┘
    1      8  9  12  13,14

- Raiz (1 a 8) e ordem (9 a 12): letras maiúsculas ou dígitos.
- Dígitos verificadores (13 e 14): sempre numéricos.
- Matriz é a ordem `0001`; o resto é filial.

O dígito verificador usa módulo 11 sobre o valor de cada caractere na tabela
ASCII menos 48. Assim `0`..`9` valem 0..9 e `A`..`Z` valem 17..42. Como os
dígitos mantêm o valor, **CNPJ antigo dá o mesmo resultado nas duas regras**,
então uma só implementação atende os dois.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TAMANHO = 14
ORDEM_MATRIZ = "0001"

_RE_VALIDO = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
_RE_LIMPAR = re.compile(r"[^0-9A-Za-z]")

_PESOS_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


class CnpjInvalido(ValueError):
    def __init__(self, valor: str, motivo: str) -> None:
        self.valor = valor
        self.motivo = motivo
        super().__init__(f"CNPJ inválido ({motivo}): {valor}")


def _valor(caractere: str) -> int:
    """Valor do caractere na conta do dígito: ASCII menos 48."""
    return ord(caractere) - 48


def _digito(base: str, pesos: tuple[int, ...]) -> str:
    soma = sum(_valor(c) * p for c, p in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def limpar(bruto: str) -> str:
    """Tira pontuação e põe em maiúsculas, sem validar."""
    return _RE_LIMPAR.sub("", bruto or "").upper()


def digitos_verificadores(base_doze: str) -> str:
    """Calcula os dois dígitos a partir dos doze primeiros caracteres."""
    d1 = _digito(base_doze, _PESOS_1)
    d2 = _digito(base_doze + d1, _PESOS_2)
    return d1 + d2


@dataclass(frozen=True)
class Cnpj:
    """CNPJ validado. Guarda sempre limpo e em maiúsculas."""

    valor: str

    def __post_init__(self) -> None:
        limpo = limpar(self.valor)
        if len(limpo) != TAMANHO:
            raise CnpjInvalido(self.valor, f"precisa de {TAMANHO} caracteres")
        if not _RE_VALIDO.match(limpo):
            raise CnpjInvalido(
                self.valor,
                "os 12 primeiros aceitam letra ou dígito e os 2 últimos só dígito",
            )
        # repetição só de um caractere passa no módulo 11 mas não existe
        if len(set(limpo)) == 1:
            raise CnpjInvalido(self.valor, "sequência repetida")
        if digitos_verificadores(limpo[:12]) != limpo[12:]:
            raise CnpjInvalido(self.valor, "dígito verificador não confere")
        object.__setattr__(self, "valor", limpo)

    # ---------- partes ----------
    @property
    def raiz(self) -> str:
        """Os 8 primeiros. Identifica o grupo, comum a todas as filiais."""
        return self.valor[:8]

    @property
    def ordem(self) -> str:
        """Posições 9 a 12. Diz qual estabelecimento é."""
        return self.valor[8:12]

    @property
    def dv(self) -> str:
        return self.valor[12:]

    # ---------- perguntas ----------
    @property
    def e_matriz(self) -> bool:
        return self.ordem == ORDEM_MATRIZ

    @property
    def e_alfanumerico(self) -> bool:
        """Verdadeiro quando há letra, ou seja, é do formato novo."""
        return any(c.isalpha() for c in self.valor)

    def mesma_raiz(self, outro: "Cnpj") -> bool:
        return self.raiz == outro.raiz

    def matriz(self) -> "Cnpj":
        """O CNPJ da matriz do mesmo grupo.

        Recalcula o dígito porque trocar a ordem muda o verificador.
        """
        if self.e_matriz:
            return self
        base = self.raiz + ORDEM_MATRIZ
        return Cnpj(base + digitos_verificadores(base))

    # ---------- apresentação ----------
    @property
    def formatado(self) -> str:
        v = self.valor
        return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}"

    def __str__(self) -> str:
        return self.formatado


def tentar(bruto: str) -> Cnpj | None:
    """Devolve o CNPJ ou None. Útil ao ler arquivo de terceiro, onde recusar a
    linha inteira por um campo torto é pior do que seguir sem ele."""
    try:
        return Cnpj(bruto)
    except (CnpjInvalido, TypeError):
        return None

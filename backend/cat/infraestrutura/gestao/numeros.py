"""Conversão de valores SPED para inteiros exatos.

Tudo na gestão trabalha em **centavos inteiros** (e alíquotas em
décimos-milésimos de ponto percentual). Somar float de milhões de linhas
acumula erro, e o MA arredonda o crédito recalculado por grupo — um erro
de 1e-9 no lugar errado vira 1 centavo de diferença no relatório.

Formato SPED: vírgula decimal e nenhum separador de milhar
(``104977871,55``). Campo vazio vale zero.
"""
from __future__ import annotations


class ValorInvalido(ValueError):
    """Campo numérico que não segue o formato SPED."""


def centavos(campo: bytes | str) -> int:
    """``b"1234,56"`` -> ``123456``. Vazio -> 0.

    Casas além da 2ª são arredondadas (meio para cima). O leiaute oficial
    não permite mais de duas em campo monetário, mas há ERP que grava.
    """
    if not campo:
        return 0
    if isinstance(campo, str):
        campo = campo.encode("ascii", "replace")
    campo = campo.strip()
    if not campo:
        return 0
    negativo = campo[:1] == b"-"
    if negativo:
        campo = campo[1:]
    inteiro, _, frac = campo.partition(b",")
    try:
        valor = int(inteiro or b"0") * 100
        if frac:
            valor += int((frac + b"00")[:2])
            if len(frac) > 2 and frac[2:3] >= b"5":
                valor += 1
    except ValueError as exc:
        raise ValorInvalido(f"valor {campo!r} fora do formato SPED") from exc
    return -valor if negativo else valor


def aliquota_10k(campo: bytes | str) -> int:
    """Alíquota percentual em décimos-milésimos: ``"1,6500"`` -> ``16500``."""
    if not campo:
        return 0
    if isinstance(campo, str):
        campo = campo.encode("ascii", "replace")
    campo = campo.strip()
    if not campo:
        return 0
    inteiro, _, frac = campo.partition(b",")
    try:
        return int(inteiro or b"0") * 10_000 + int((frac + b"0000")[:4])
    except ValueError as exc:
        raise ValorInvalido(f"alíquota {campo!r} fora do formato SPED") from exc


def arredondar_div(numerador: int, divisor: int) -> int:
    """Divisão inteira com arredondamento meio para cima (simétrico)."""
    if numerador < 0:
        return -arredondar_div(-numerador, divisor)
    q, r = divmod(numerador, divisor)
    return q + 1 if r * 2 >= divisor else q


def credito_recalculado(base_centavos: int, aliq_10k: int) -> int:
    """Base x alíquota, arredondado ao centavo (base em centavos, alíquota em %·10⁴)."""
    return arredondar_div(base_centavos * aliq_10k, 1_000_000)


def formatar_aliquota(aliq_10k: int) -> str:
    """``16500`` -> ``"1.65"`` — ponto decimal e 2 casas, como o MA rotula."""
    return f"{aliq_10k / 10_000:.2f}"

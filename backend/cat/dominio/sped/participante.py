"""O registro 0150 da EFD ICMS/IPI — o cadastro de participantes. Puro, sem I/O.

    |0150|COD_PART|NOME|COD_PAIS|CNPJ|CPF|IE|COD_MUN|SUFRAMA|END|NUM|COMPL|BAIRRO|

Entrou para a etapa 7: o 0150 do arquivo digital da CAT 42 é este mesmo
cadastro, com menos campos, e o C100 da EFD cita o participante pelo código
que só este registro traduz. Recebe os campos como `linha.split("|")`, a
convenção dos outros leitores de registro (`campos[1]` é o nome do registro).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParticipanteDaEfd:
    codigo: str
    nome: str
    cod_pais: str
    cnpj: str
    cpf: str
    ie: str
    cod_mun: str


def ler_participante(campos: list[str]) -> ParticipanteDaEfd | None:
    """None quando a linha não tem os campos que a CAT 42 usa."""
    if len(campos) < 9 or campos[1] != "0150":
        return None

    def em(i: int) -> str:
        return campos[i].strip()

    return ParticipanteDaEfd(codigo=em(2), nome=em(3), cod_pais=em(4), cnpj=em(5), cpf=em(6),
                             ie=em(7), cod_mun=em(8))

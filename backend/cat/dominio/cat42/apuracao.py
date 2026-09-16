"""A apuração do período: o que se pede, o que se recolhe e o que ainda trava.

Sexta etapa. A Ficha 3 calcula linha a linha; aqui o período fecha — por
**estabelecimento e mês**, que é a unidade do arquivo digital (o registro 0000
leva CNPJ, IE e o período `mmaaaa`).

## Ressarcimento e complemento não se compensam

São coisas opostas: o ressarcimento é crédito a pedir e o complemento é imposto
a recolher. A Ficha 3 os separa nas colunas 25 e 26, e o manual só admite
complemento no enquadramento 1. Somar um contra o outro esconderia os dois, e
por isso o líquido existe aqui apenas como leitura — nunca como o valor do
pedido.

## Competência apta é competência sem pendência

Apurar não é o mesmo que poder entregar. O número aparece sempre; o que decide
se ele segue para o arquivo digital é não haver nada pendente: fora de São
Paulo (a CAT 42 é paulista), ficha retirada por estoque negativo, confronto que
ainda não se calcula, saída sem alíquota, enquadramento indefinido, saldo que
não fecha com o inventário. Cada motivo é dito com todas as letras, porque é a
lista de trabalho de quem vai fechar o pedido.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

ZERO = Decimal(0)


class MotivoDeBloqueio(Enum):
    """Por que uma competência ainda não pode virar arquivo digital."""

    FORA_DE_SP = "fora_de_sp"
    FICHA_RETIRADA = "ficha_retirada"
    CONFRONTO_PENDENTE = "confronto_pendente"
    SEM_ALIQUOTA = "sem_aliquota"
    ENQUADRAMENTO_INDEFINIDO = "enquadramento_indefinido"
    DIVERGE_DO_INVENTARIO = "diverge_do_inventario"
    SEM_INVENTARIO = "sem_inventario"

    @property
    def rotulo(self) -> str:
        return _ROTULOS[self]

    @property
    def o_que_fazer(self) -> str:
        return _O_QUE_FAZER[self]


_ROTULOS = {
    MotivoDeBloqueio.FORA_DE_SP: "Estabelecimento fora de São Paulo",
    MotivoDeBloqueio.FICHA_RETIRADA: "Ficha retirada por estoque negativo",
    MotivoDeBloqueio.CONFRONTO_PENDENTE: "Confronto dos enquadramentos 2 e 4 não apurado",
    MotivoDeBloqueio.SEM_ALIQUOTA: "Saída sem alíquota interna no cadastro",
    MotivoDeBloqueio.ENQUADRAMENTO_INDEFINIDO: "Saída com enquadramento indefinido",
    MotivoDeBloqueio.DIVERGE_DO_INVENTARIO: "Saldo não fecha com o inventário",
    MotivoDeBloqueio.SEM_INVENTARIO: "Sem inventário no mês para conferir o saldo",
}

_O_QUE_FAZER = {
    MotivoDeBloqueio.FORA_DE_SP: "A CAT 42 é paulista: esta competência não gera arquivo.",
    MotivoDeBloqueio.FICHA_RETIRADA: "Falta movimento — perdas, meses do relatório de saídas, produção.",
    MotivoDeBloqueio.CONFRONTO_PENDENTE: "Depende do ICMS da operação própria da entrada (coluna 21).",
    MotivoDeBloqueio.SEM_ALIQUOTA: "Completar a alíquota interna no cadastro de itens (0200).",
    MotivoDeBloqueio.ENQUADRAMENTO_INDEFINIDO: "Dizer quem comprou: nota modelo 55 não responde sozinha.",
    MotivoDeBloqueio.DIVERGE_DO_INVENTARIO: "Conferir o estoque do mês: falta movimento ou sobra lançamento.",
    MotivoDeBloqueio.SEM_INVENTARIO: "Sem bloco H no mês não há como conferir o saldo declarado.",
}


@dataclass(frozen=True)
class CompetenciaApurada:
    """Um estabelecimento num mês: o que se pede, o que se recolhe, o que falta.

    Os contadores são de linhas da Ficha 3, menos `fichas_retiradas`, que é de
    mercadorias. Cada um deles, acima de zero, vira um motivo de bloqueio.
    """

    cnpj: str
    uf: str
    competencia: str                      # "2021-05"
    ressarcimento: Decimal = ZERO
    complemento: Decimal = ZERO
    # coluna 27 da Ficha 3, art. 271 do RICMS: só no enquadramento 4, e vem da
    # coluna 21 — que ainda não é apurada. Fica preparada e zerada, de propósito
    credito_operacao_propria: Decimal = ZERO
    itens: int = 0
    linhas: int = 0
    fichas_retiradas: int = 0
    confronto_pendente: int = 0
    sem_aliquota: int = 0
    indefinidas: int = 0
    inventarios_conferidos: int = 0
    inventarios_divergentes: int = 0

    @property
    def liquido(self) -> Decimal:
        """Só leitura. O pedido é o ressarcimento; o complemento se recolhe."""
        return self.ressarcimento - self.complemento

    @property
    def motivos(self) -> list[MotivoDeBloqueio]:
        """O que trava esta competência, na ordem em que se resolve."""
        travas = [
            (self.uf not in ("", "SP"), MotivoDeBloqueio.FORA_DE_SP),
            (self.fichas_retiradas > 0, MotivoDeBloqueio.FICHA_RETIRADA),
            (self.confronto_pendente > 0, MotivoDeBloqueio.CONFRONTO_PENDENTE),
            (self.sem_aliquota > 0, MotivoDeBloqueio.SEM_ALIQUOTA),
            (self.indefinidas > 0, MotivoDeBloqueio.ENQUADRAMENTO_INDEFINIDO),
            (self.inventarios_divergentes > 0, MotivoDeBloqueio.DIVERGE_DO_INVENTARIO),
            (self.inventarios_conferidos == 0, MotivoDeBloqueio.SEM_INVENTARIO),
        ]
        return [motivo for trava, motivo in travas if trava]

    @property
    def apta(self) -> bool:
        """Pode virar arquivo digital. Apurada, todas são; apta, só as limpas."""
        return not self.motivos

"""O histórico de um trabalho: o que aconteceu, quando e por quem.

Um trabalho da CAT dura meses e passa por várias mãos. Quando um número é
questionado — e é sempre questionado, às vezes um ano depois — a pergunta não
é só "de qual base saiu", que a execução responde; é "por que este trabalho
ficou parado em março", "quem decidiu que a competência era essa", "quem
recebeu isto do fulano quando ele saiu de férias".

Nada disso cabe num campo. Cabe numa linha do tempo com duas naturezas de
entrada, misturadas de propósito:

* **o que o sistema fez** — lote importado, conferência concluída, status
  alterado. Ninguém digita: o próprio caso de uso registra;
* **o que a pessoa disse** — o comentário. É onde mora o que nenhum campo
  captura.

Ficam juntas porque separá-las mentiria sobre a ordem dos fatos: o comentário
"conferi com o cliente, ele vai mandar o que falta" só faz sentido logo abaixo
da conferência que achou 92 mil pendências.

**Evento não se apaga nem se edita.** É registro, não anotação: um histórico
que se reescreve não serve para responder pergunta de auditoria. Comentário
errado se corrige com outro comentário.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class StatusDoProjeto(str, Enum):
    """Em que pé o trabalho está. Aparece no cartão, antes de qualquer número.

    São quatro e não mais: status demais vira campo que ninguém mantém. A
    diferença que importa é entre *trabalhando*, *parado por uma razão* e
    *acabou* — e "acabou" tem dois finais possíveis, o bom e o outro.
    """

    EM_ANDAMENTO = "em_andamento"
    PAUSADO = "pausado"
    CANCELADO = "cancelado"
    CONCLUIDO = "concluido"

    @property
    def rotulo(self) -> str:
        return {
            StatusDoProjeto.EM_ANDAMENTO: "Em andamento",
            StatusDoProjeto.PAUSADO: "Pausado",
            StatusDoProjeto.CANCELADO: "Cancelado",
            StatusDoProjeto.CONCLUIDO: "Concluído",
        }[self]

    @property
    def explicacao(self) -> str:
        return {
            StatusDoProjeto.EM_ANDAMENTO: "O trabalho está correndo.",
            StatusDoProjeto.PAUSADO:
                "Parado por ora — em geral esperando o cliente. Volta a andar "
                "sem perder nada do que já foi feito.",
            StatusDoProjeto.CANCELADO:
                "Não vai seguir. Fica no sistema com o histórico inteiro; "
                "cancelar não é apagar.",
            StatusDoProjeto.CONCLUIDO: "Entregue.",
        }[self]

    @property
    def aceita_processamento(self) -> bool:
        """Se faz sentido rodar etapa neste trabalho.

        Num trabalho cancelado, não: gastaria horas de máquina numa apuração
        que ninguém vai entregar. Pausado também não — pausar existe
        justamente para o trabalho não andar sozinho enquanto se espera.
        """
        return self in (StatusDoProjeto.EM_ANDAMENTO, StatusDoProjeto.CONCLUIDO)

    @property
    def exige_motivo(self) -> bool:
        """Parar ou cancelar sem dizer por quê é o que gera a pergunta de
        três meses depois que ninguém sabe responder."""
        return self in (StatusDoProjeto.PAUSADO, StatusDoProjeto.CANCELADO)


class TipoDeEvento(str, Enum):
    """O que pode entrar na linha do tempo.

    O valor é gravado no banco: mudar um destes textos reescreve o passado,
    então só se acrescenta.
    """

    CRIADO = "criado"
    COMENTARIO = "comentario"
    STATUS = "status"
    SUCESSAO = "sucessao"
    LOTE_IMPORTADO = "lote_importado"
    LOTE_REMOVIDO = "lote_removido"
    ETAPA_INICIADA = "etapa_iniciada"
    ETAPA_CONCLUIDA = "etapa_concluida"
    ETAPA_FALHOU = "etapa_falhou"
    PLANILHA_BAIXADA = "planilha_baixada"

    @property
    def e_do_sistema(self) -> bool:
        """Tudo que não é o que a pessoa escreveu."""
        return self is not TipoDeEvento.COMENTARIO


@dataclass(frozen=True)
class Evento:
    """Uma linha da história. Imutável, como o fato que descreve."""

    tipo: TipoDeEvento
    autor: str                      # nome de exibição de quem fez
    quando: datetime
    texto: str = ""                 # o comentário, ou a frase pronta do sistema
    # o que mudou, para quem quiser reconstruir: {"de": ..., "para": ...}
    dados: dict = field(default_factory=dict)
    id: int = 0
    autor_id: int | None = None

    @property
    def e_comentario(self) -> bool:
        return self.tipo is TipoDeEvento.COMENTARIO


# ---------------------------------------------------------------------------
# As frases do sistema.
#
# Ficam no domínio, e não na tela, por duas razões: a mesma frase vale para a
# tela, para o log e para um relatório futuro; e escrevê-las aqui obriga a
# pensar no que o evento significa, em vez de despejar o nome técnico da
# etapa na cara de quem lê.
# ---------------------------------------------------------------------------

TAMANHO_MAXIMO_DO_COMENTARIO = 2000


class ComentarioVazio(ValueError):
    def __init__(self) -> None:
        super().__init__("O comentário não pode ficar vazio.")


class ComentarioLongoDemais(ValueError):
    def __init__(self) -> None:
        super().__init__(
            f"O comentário passa de {TAMANHO_MAXIMO_DO_COMENTARIO} caracteres. "
            "Se precisa de tudo isso, provavelmente é um documento — anexe o "
            "arquivo no lote e comente o essencial."
        )


def validar_comentario(texto: str) -> str:
    limpo = texto.strip()
    if not limpo:
        raise ComentarioVazio
    if len(limpo) > TAMANHO_MAXIMO_DO_COMENTARIO:
        raise ComentarioLongoDemais
    return limpo


class MesmoStatus(ValueError):
    def __init__(self, status: StatusDoProjeto) -> None:
        super().__init__(f"O trabalho já está como {status.rotulo.lower()}.")


class MotivoObrigatorio(ValueError):
    def __init__(self, status: StatusDoProjeto) -> None:
        super().__init__(
            f"Diga por que o trabalho está sendo {status.rotulo.lower()}. "
            "Sem o motivo, daqui a três meses ninguém sabe responder."
        )


def frase_de_status(de: StatusDoProjeto, para: StatusDoProjeto) -> str:
    return f"{de.rotulo} → {para.rotulo}"


def frase_de_sucessao(de: str | None, para: str) -> str:
    return f"{de} → {para}" if de else f"Responsável definido: {para}"

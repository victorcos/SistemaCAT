"""O histórico de um trabalho, na parte que o motor usa.

A linha do tempo mistura o que o sistema fez com o que a pessoa disse. As regras
de comentar, mudar status e passar adiante — e as frases da tela — moram na API
em C# desde 13/09/2026 (api/src/Cat.Dominio/Projeto/Historico.cs). Ficam aqui
os valores que o motor grava e lê: o status, para barrar etapa em trabalho
parado, e o tipo de evento, para registrar o que as etapas fazem.

**Evento não se apaga nem se edita.** É registro, não anotação.
"""

from __future__ import annotations

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
    def aceita_processamento(self) -> bool:
        """Se faz sentido rodar etapa neste trabalho.

        Num trabalho cancelado, não: gastaria horas de máquina numa apuração
        que ninguém vai entregar. Pausado também não — pausar existe
        justamente para o trabalho não andar sozinho enquanto se espera.
        """
        return self in (StatusDoProjeto.EM_ANDAMENTO, StatusDoProjeto.CONCLUIDO)


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
    PARAMETRO_ALTERADO = "parametro_alterado"
    # a etapa 8 só conclui quando um revisor ou gestor aprova o pacote gerado
    ENTREGA_APROVADA = "entrega_aprovada"

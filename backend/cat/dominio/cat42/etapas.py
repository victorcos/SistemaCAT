"""As etapas do trabalho da CAT 42, na ordem em que existem.

Isto é conhecimento de domínio, não decoração de tela: a ordem vem do próprio
manual. Não dá para montar o razão sem os movimentos, nem apurar ressarcimento
sem o razão, nem gerar o arquivo digital sem a apuração.

Deixar isso no domínio faz a tela ser um espelho do processo. Quando uma etapa
entrar em operação, a tela reflete sozinha.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SituacaoEtapa(str, Enum):
    CONCLUIDA = "concluida"
    EM_ANDAMENTO = "em_andamento"
    PENDENTE = "pendente"
    BLOQUEADA = "bloqueada"          # falta a etapa anterior
    NAO_DISPONIVEL = "nao_disponivel"  # ainda não construída no sistema

    @property
    def rotulo(self) -> str:
        return {
            SituacaoEtapa.CONCLUIDA: "Concluída",
            SituacaoEtapa.EM_ANDAMENTO: "Em andamento",
            SituacaoEtapa.PENDENTE: "Pendente",
            SituacaoEtapa.BLOQUEADA: "Aguardando etapa anterior",
            SituacaoEtapa.NAO_DISPONIVEL: "Ainda não disponível",
        }[self]


@dataclass(frozen=True)
class DefinicaoEtapa:
    chave: str
    nome: str
    descricao: str
    # False enquanto a funcionalidade não existe. Mostrar a etapa mesmo assim é
    # deliberado: o usuário vê o caminho inteiro e sabe onde o trabalho está.
    implementada: bool = False


# A ordem desta lista É a ordem do processo.
ETAPAS: tuple[DefinicaoEtapa, ...] = (
    DefinicaoEtapa(
        chave="importar",
        nome="Importar base de dados",
        descricao=(
            "Apontar a pasta com a base do trabalho: EFD ICMS/IPI, XML das "
            "notas e relatórios do ERP. O sistema identifica cada arquivo e "
            "separa o que é de outra empresa. Pode voltar quantas vezes a "
            "empresa mandar arquivo — o cadastro é que acontece uma vez só."
        ),
        implementada=True,
    ),
    DefinicaoEtapa(
        chave="movimentos",
        nome="Extrair movimentos",
        descricao=(
            "Ler os registros C100 e C170 de cada documento, o cadastro de item "
            "(0200) e o inventário (Bloco H), que dá o saldo de abertura."
        ),
    ),
    DefinicaoEtapa(
        chave="st_suportado",
        nome="Apurar o ICMS suportado",
        descricao=(
            "Determinar o imposto suportado de cada entrada. Quando o SPED e o "
            "XML divergem, vale o XML — é o documento fiscal."
        ),
    ),
    DefinicaoEtapa(
        chave="razao",
        nome="Montar o razão dos itens",
        descricao=(
            "A Ficha 3: uma ficha por mercadoria, custo médio ponderado móvel, "
            "entradas e devoluções antes das saídas no mesmo dia."
        ),
    ),
    DefinicaoEtapa(
        chave="apuracao",
        nome="Apurar ressarcimento e complemento",
        descricao=(
            "Confrontar o imposto suportado com o ICMS efetivo, por "
            "enquadramento legal, e conferir o saldo final contra o inventário."
        ),
    ),
    DefinicaoEtapa(
        chave="arquivo_digital",
        nome="Gerar o arquivo digital",
        descricao=(
            "Montar os registros 0000 a 1200 no leiaute da CAT 42 e passar pela "
            "pré-validação antes do envio à SEFAZ."
        ),
    ),
    DefinicaoEtapa(
        chave="entrega",
        nome="Relatórios e entrega",
        descricao=(
            "Planilhas de conferência por filial e competência, e o dossiê que "
            "acompanha o pedido."
        ),
    ),
)

POR_CHAVE = {e.chave: e for e in ETAPAS}


@dataclass(frozen=True)
class EtapaDoProjeto:
    """Uma etapa, já com a situação naquele projeto."""

    definicao: DefinicaoEtapa
    situacao: SituacaoEtapa
    detalhe: str = ""

    @property
    def acessivel(self) -> bool:
        """Se vale a pena o usuário clicar."""
        return self.situacao in (
            SituacaoEtapa.CONCLUIDA,
            SituacaoEtapa.EM_ANDAMENTO,
            SituacaoEtapa.PENDENTE,
        )


def montar(concluidas: set[str], em_andamento: str | None = None) -> list[EtapaDoProjeto]:
    """Monta o roteiro do projeto a partir do que já foi feito.

    Uma etapa fica bloqueada enquanto a anterior não concluiu, porque a ordem é
    de dependência real: sem movimentos não há razão, sem razão não há apuração.
    """
    saida: list[EtapaDoProjeto] = []
    anterior_ok = True

    for d in ETAPAS:
        if not d.implementada:
            situacao = SituacaoEtapa.NAO_DISPONIVEL
        elif d.chave in concluidas:
            situacao = SituacaoEtapa.CONCLUIDA
        elif d.chave == em_andamento:
            situacao = SituacaoEtapa.EM_ANDAMENTO
        elif anterior_ok:
            situacao = SituacaoEtapa.PENDENTE
        else:
            situacao = SituacaoEtapa.BLOQUEADA

        saida.append(EtapaDoProjeto(definicao=d, situacao=situacao))
        anterior_ok = anterior_ok and situacao is SituacaoEtapa.CONCLUIDA

    return saida


def progresso(etapas: list[EtapaDoProjeto]) -> tuple[int, int]:
    """Quantas concluídas de quantas já existem no sistema.

    O denominador ignora o que ainda não foi construído: dizer "1 de 7" quando
    só uma etapa existe passaria a impressão errada de atraso.
    """
    disponiveis = [e for e in etapas if e.definicao.implementada]
    feitas = sum(1 for e in disponiveis if e.situacao is SituacaoEtapa.CONCLUIDA)
    return feitas, len(disponiveis)

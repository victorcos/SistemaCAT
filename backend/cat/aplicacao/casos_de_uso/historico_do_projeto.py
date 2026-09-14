"""O histórico do trabalho, na parte que é do motor: registrar e barrar.

A tela lê a linha do tempo, comenta, muda status e passa o trabalho adiante pela
API em C# desde 13/09/2026 (docs/MIGRACAO_CSHARP.md). Fica aqui o que as etapas
do motor fazem sozinhas:

* **registrar** o que aconteceu — lote importado, etapa iniciada, concluída ou
  falhou —, na mesma tabela e no mesmo formato que o C# grava;
* **barrar** etapa em trabalho pausado ou cancelado (`exigir_que_ande`).

**Registrar evento nunca derruba a operação que o gerou.** Se gravar a linha do
histórico falhar, o lote continua importado e a conferência continua concluída
— o que se perde é a anotação, e isso vai para o log. O contrário seria
absurdo: uma extração de 44 minutos desfeita porque a frase "extração
concluída" não coube no banco.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.dominio.projeto.historico import StatusDoProjeto, TipoDeEvento
from cat.infraestrutura.repositorios.modelos import (
    EventoDoProjetoDB,
    ProjetoDB,
    UsuarioDB,
)
from cat.log import obter_log

log = obter_log(__name__)


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------
def registrar(
    sessao: Session,
    projeto_id: int,
    tipo: TipoDeEvento,
    *,
    texto: str = "",
    dados: dict | None = None,
    por: UsuarioDB | None = None,
    autor_id: int | None = None,
    autor_nome: str = "",
    commit: bool = True,
) -> None:
    """Põe uma linha na história. Falhar aqui não derruba a operação.

    `por` é a linha do usuário no banco; quem só tem o id passa `autor_id`.
    """
    if por is not None:
        autor_id = getattr(por, "id", None)
        autor_nome = getattr(por, "nome_exibicao", "") or autor_nome

    try:
        sessao.add(
            EventoDoProjetoDB(
                projeto_id=projeto_id,
                tipo=tipo.value,
                texto=texto,
                dados=dados or None,
                autor_id=autor_id,
                autor_nome=autor_nome or "Sistema",
                criado_em=datetime.now(timezone.utc),
            )
        )
        if commit:
            sessao.commit()
    except Exception as erro:                    # noqa: BLE001
        # o fato aconteceu; perder a anotação dele é ruim, não fatal
        log.warning(
            "não deu para registrar o evento do projeto",
            extra={"projeto_id": projeto_id, "tipo": tipo.value,
                   "motivo": str(erro)},
        )
        if commit:
            sessao.rollback()


def registrar_de_etapa(
    sessao: Session,
    projeto_id: int,
    tipo: TipoDeEvento,
    etapa: str,
    texto: str,
    *,
    dados: dict | None = None,
    autor_id: int | None = None,
) -> None:
    """Atalho para o que as etapas registram. O autor vem do banco: a tarefa
    roda fora da requisição e não tem o usuário em mãos."""
    nome = ""
    if autor_id is not None:
        nome = sessao.scalar(
            select(UsuarioDB.nome_exibicao).where(UsuarioDB.id == autor_id)
        ) or ""
    registrar(
        sessao, projeto_id, tipo,
        texto=texto,
        dados={"etapa": etapa, **(dados or {})},
        autor_id=autor_id,
        autor_nome=nome,
    )



class TrabalhoParado(ValueError):
    """O status do trabalho impede a operação."""


def exigir_que_ande(p: ProjetoDB, acao: str) -> None:
    """Trabalho pausado ou cancelado não roda etapa.

    Existe porque pausar tem de significar alguma coisa: sem isto, "pausado"
    seria só uma cor no cartão, e uma extração de 44 minutos continuaria
    disparando num trabalho que a equipe decidiu parar. E em trabalho
    cancelado é pior que inútil — é apuração que ninguém vai entregar.
    """
    status = _status_de(p)
    if status.aceita_processamento:
        return
    raise TrabalhoParado(
        f"Este trabalho está {status.rotulo.lower()} e não é possível {acao}. "
        + (
            "Retome-o no histórico para seguir."
            if status is StatusDoProjeto.PAUSADO
            else "Um trabalho cancelado fica só para consulta."
        )
    )


def status_de(p: ProjetoDB) -> StatusDoProjeto:
    """O status como enum, tolerando valor antigo gravado no banco."""
    return _status_de(p)


def _status_de(p: ProjetoDB) -> StatusDoProjeto:
    try:
        return StatusDoProjeto(p.status)
    except ValueError:
        return StatusDoProjeto.EM_ANDAMENTO

"""A história do trabalho: registrar, ler, comentar, mudar status, suceder.

O registro é a parte mais delicada, e a decisão que vale explicar é esta:
**registrar evento nunca derruba a operação que o gerou.** Se gravar a linha
do histórico falhar, o lote continua importado e a conferência continua
concluída — o que se perde é a anotação, e isso vai para o log. O contrário
seria absurdo: uma extração de 44 minutos desfeita porque a frase "extração
concluída" não coube no banco.

Por isso `registrar` engole exceção e por isso ele recebe a sessão de quem
chama: o evento entra na mesma transação do fato que descreve, quando há uma.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cat.dominio.acesso.usuario import Papel, Usuario
from cat.dominio.projeto.historico import (
    Evento,
    MesmoStatus,
    MotivoObrigatorio,
    StatusDoProjeto,
    TipoDeEvento,
    frase_de_status,
    frase_de_sucessao,
    validar_comentario,
)
from cat.infraestrutura.repositorios.modelos import (
    EventoDoProjetoDB,
    ProjetoDB,
    UsuarioDB,
)
from cat.log import obter_log

log = obter_log(__name__)

# quantos eventos a tela traz por vez. Um trabalho de um ano com uso diário
# passa de mil linhas, e ninguém rola mil linhas atrás do que aconteceu ontem.
POR_PAGINA = 50


class ProjetoNaoEncontrado(ValueError):
    def __init__(self) -> None:
        super().__init__("Trabalho não encontrado.")


class NaoPodeSuceder(PermissionError):
    def __init__(self) -> None:
        super().__init__(
            "Só gestor passa um trabalho para outra pessoa. Quem executa pede "
            "ao gestor — a carteira é decisão de quem coordena."
        )


class SucessorInvalido(ValueError):
    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)


def _projeto(projeto_id: int, sessao: Session) -> ProjetoDB:
    p = sessao.get(ProjetoDB, projeto_id)
    if p is None:
        raise ProjetoNaoEncontrado
    return p


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
    por: Usuario | UsuarioDB | None = None,
    autor_id: int | None = None,
    autor_nome: str = "",
    commit: bool = True,
) -> None:
    """Põe uma linha na história. Falhar aqui não derruba a operação.

    `por` aceita tanto o usuário do domínio quanto a linha do banco, porque
    metade dos pontos de registro tem um e metade tem o outro — exigir
    conversão em cada ponto só espalharia ruído.
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


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def listar(
    projeto_id: int,
    sessao: Session,
    *,
    antes_de: int | None = None,
    quantos: int = POR_PAGINA,
    so_comentarios: bool = False,
) -> tuple[list[Evento], bool]:
    """Os eventos, do mais recente para o mais antigo.

    Devolve também se há mais para trás — é o que a tela precisa para decidir
    se mostra "carregar mais", sem ter de contar a tabela inteira.
    """
    _projeto(projeto_id, sessao)

    consulta = select(EventoDoProjetoDB).where(
        EventoDoProjetoDB.projeto_id == projeto_id
    )
    if so_comentarios:
        consulta = consulta.where(
            EventoDoProjetoDB.tipo == TipoDeEvento.COMENTARIO.value
        )
    if antes_de is not None:
        consulta = consulta.where(EventoDoProjetoDB.id < antes_de)

    # pede um a mais para saber se há próxima página
    linhas = list(
        sessao.scalars(
            consulta.order_by(EventoDoProjetoDB.id.desc()).limit(quantos + 1)
        )
    )
    tem_mais = len(linhas) > quantos
    return [_como_evento(l) for l in linhas[:quantos]], tem_mais


def contar_comentarios(projeto_id: int, sessao: Session) -> int:
    return sessao.scalar(
        select(func.count())
        .select_from(EventoDoProjetoDB)
        .where(
            EventoDoProjetoDB.projeto_id == projeto_id,
            EventoDoProjetoDB.tipo == TipoDeEvento.COMENTARIO.value,
        )
    ) or 0


def _como_evento(l: EventoDoProjetoDB) -> Evento:
    try:
        tipo = TipoDeEvento(l.tipo)
    except ValueError:
        # tipo gravado por uma versão mais nova: mostra como comentário do
        # sistema em vez de sumir da linha do tempo
        tipo = TipoDeEvento.COMENTARIO
    return Evento(
        id=l.id,
        tipo=tipo,
        autor=l.autor_nome,
        autor_id=l.autor_id,
        quando=l.criado_em,
        texto=l.texto,
        dados=l.dados or {},
    )


# ---------------------------------------------------------------------------
# Escrita pela tela
# ---------------------------------------------------------------------------
def comentar(projeto_id: int, texto: str, por: Usuario, sessao: Session) -> Evento:
    p = _projeto(projeto_id, sessao)
    limpo = validar_comentario(texto)

    linha = EventoDoProjetoDB(
        projeto_id=p.id,
        tipo=TipoDeEvento.COMENTARIO.value,
        texto=limpo,
        autor_id=por.id,
        autor_nome=por.nome_exibicao,
        criado_em=datetime.now(timezone.utc),
    )
    sessao.add(linha)
    sessao.commit()
    sessao.refresh(linha)
    log.info("comentário no trabalho",
             extra={"projeto_id": p.id, "por_usuario_id": por.id,
                    "caracteres": len(limpo)})
    return _como_evento(linha)


def alterar_status(
    projeto_id: int, novo: StatusDoProjeto, motivo: str, por: Usuario, sessao: Session
) -> ProjetoDB:
    p = _projeto(projeto_id, sessao)
    atual = _status_de(p)
    if atual is novo:
        raise MesmoStatus(novo)
    if novo.exige_motivo and not motivo.strip():
        raise MotivoObrigatorio(novo)

    p.status = novo.value
    registrar(
        sessao, p.id, TipoDeEvento.STATUS,
        texto=motivo.strip(),
        dados={"de": atual.value, "para": novo.value,
               "frase": frase_de_status(atual, novo)},
        por=por,
        commit=False,
    )
    sessao.commit()
    sessao.refresh(p)
    log.warning("status do trabalho alterado",
                extra={"projeto_id": p.id, "de": atual.value, "para": novo.value,
                       "por_usuario_id": por.id, "motivo": motivo.strip()[:200]})
    return p


def suceder(
    projeto_id: int, novo_id: int, motivo: str, por: Usuario, sessao: Session
) -> ProjetoDB:
    """Passa o trabalho para outra pessoa. Só gestor e dev.

    A validação do sucessor não é burocracia: passar um trabalho para conta
    desativada é como ele fica sem dono sem ninguém perceber.
    """
    if not por.papel.administra_usuarios:
        raise NaoPodeSuceder

    p = _projeto(projeto_id, sessao)
    novo = sessao.get(UsuarioDB, novo_id)
    if novo is None:
        raise SucessorInvalido("A pessoa escolhida não existe.")
    if not novo.ativo:
        raise SucessorInvalido(
            f"{novo.nome_exibicao} está com o acesso desativado. Reative antes "
            "de passar o trabalho, ou escolha outra pessoa."
        )
    if p.responsavel_id == novo.id:
        raise SucessorInvalido(f"{novo.nome_exibicao} já responde por este trabalho.")

    anterior = p.responsavel.nome_exibicao if p.responsavel else None
    p.responsavel_id = novo.id
    registrar(
        sessao, p.id, TipoDeEvento.SUCESSAO,
        texto=motivo.strip(),
        dados={"de": anterior, "para": novo.nome_exibicao,
               "de_id": p.responsavel_id, "para_id": novo.id,
               "frase": frase_de_sucessao(anterior, novo.nome_exibicao)},
        por=por,
        commit=False,
    )
    sessao.commit()
    sessao.refresh(p)
    log.warning("trabalho passado para outra pessoa",
                extra={"projeto_id": p.id, "de": anterior,
                       "para": novo.nome_exibicao, "por_usuario_id": por.id})
    return p


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


def sucessores_possiveis(sessao: Session) -> list[UsuarioDB]:
    """Quem pode receber um trabalho: conta ativa, e que não seja só leitura.

    Passar um trabalho para quem não pode escrever nele deixaria o trabalho
    parado por falta de permissão, e a causa não apareceria em lugar nenhum.
    """
    papeis = [p.value for p in Papel if p.pode_escrever]
    return list(
        sessao.scalars(
            select(UsuarioDB)
            .where(UsuarioDB.ativo.is_(True), UsuarioDB.papel.in_(papeis))
            .order_by(UsuarioDB.nome_exibicao)
        )
    )

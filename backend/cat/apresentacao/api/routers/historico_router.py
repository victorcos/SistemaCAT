"""O histórico de um trabalho: linha do tempo, comentários, status, sucessão.

Quatro coisas que a tela faz aqui:

* **ler a linha do tempo** — `GET /projetos/{id}/historico`, do mais recente
  para o mais antigo, paginado por `antes_de` (o id do último que você já
  tem). Sem `offset`: com evento entrando enquanto se lê, offset repete e
  pula linha;
* **comentar** — `POST /projetos/{id}/historico/comentarios`;
* **mudar o status** — `PATCH /projetos/{id}/status`, com motivo obrigatório
  para pausar e cancelar;
* **passar o trabalho para outra pessoa** — `PATCH /projetos/{id}/responsavel`,
  só para gestor e dev.

Quem vê o trabalho vê o histórico inteiro. O escopo por empresa já limita o
que cada um alcança, e dentro de um trabalho não há segredo entre quem
trabalha nele.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status as http
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.historico_do_projeto import (
    NaoPodeSuceder,
    ProjetoNaoEncontrado,
    SucessorInvalido,
    alterar_status,
    comentar,
    listar,
    sucessores_possiveis,
    suceder,
)
from cat.apresentacao.api.seguranca import (
    UsuarioAtual,
    exigir_capacidade,
    exigir_empresa,
)
from cat.dominio.acesso.usuario import Usuario
from cat.dominio.projeto.historico import (
    Evento,
    MesmoStatus,
    MotivoObrigatorio,
    StatusDoProjeto,
    TipoDeEvento,
)
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.infraestrutura.repositorios.modelos import ProjetoDB
from cat.log import contexto, obter_log

log = obter_log(__name__)
router = APIRouter(prefix="/api", tags=["histórico"])

PodeEscrever = Annotated[
    Usuario, Depends(exigir_capacidade("pode_escrever", "mexer no trabalho"))
]


# ---------------------------------------------------------------------------
# Contratos
# ---------------------------------------------------------------------------
class EventoDto(BaseModel):
    id: int
    tipo: str
    rotulo_do_tipo: str
    texto: str
    dados: dict
    autor: str
    autor_id: int | None
    quando: str
    e_comentario: bool


class PaginaDeHistorico(BaseModel):
    eventos: list[EventoDto]
    tem_mais: bool
    # o id para pedir a página seguinte; None quando acabou
    proximo_cursor: int | None = None


class PedidoDeComentario(BaseModel):
    texto: str = Field(min_length=1, max_length=2000)


class PedidoDeStatus(BaseModel):
    status: StatusDoProjeto
    motivo: str = ""


class PedidoDeSucessao(BaseModel):
    responsavel_id: int
    motivo: str = ""


class PessoaDto(BaseModel):
    id: int
    nome_exibicao: str
    usuario: str
    papel: str
    cargo: str


class StatusDto(BaseModel):
    """O catálogo de status, para a tela não reescrever os rótulos."""

    valor: str
    rotulo: str
    explicacao: str
    exige_motivo: bool


ROTULOS_DE_TIPO: dict[TipoDeEvento, str] = {
    TipoDeEvento.CRIADO: "Trabalho criado",
    TipoDeEvento.COMENTARIO: "Comentário",
    TipoDeEvento.STATUS: "Status alterado",
    TipoDeEvento.SUCESSAO: "Responsável alterado",
    TipoDeEvento.LOTE_IMPORTADO: "Arquivos importados",
    TipoDeEvento.LOTE_REMOVIDO: "Lote removido",
    TipoDeEvento.ETAPA_INICIADA: "Etapa iniciada",
    TipoDeEvento.ETAPA_CONCLUIDA: "Etapa concluída",
    TipoDeEvento.ETAPA_FALHOU: "Etapa falhou",
    TipoDeEvento.PLANILHA_BAIXADA: "Planilha baixada",
}


def _dto(e: Evento) -> EventoDto:
    return EventoDto(
        id=e.id,
        tipo=e.tipo.value,
        rotulo_do_tipo=ROTULOS_DE_TIPO.get(e.tipo, e.tipo.value),
        texto=e.texto,
        dados=e.dados,
        autor=e.autor,
        autor_id=e.autor_id,
        quando=e.quando.isoformat(),
        e_comentario=e.e_comentario,
    )


def _projeto(projeto_id: int, usuario: Usuario, sessao: Session) -> ProjetoDB:
    p = sessao.get(ProjetoDB, projeto_id)
    if p is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Trabalho não encontrado.")
    exigir_empresa(usuario, p.empresa_id)
    return p


def _traduzir(erro: Exception) -> HTTPException:
    if isinstance(erro, ProjetoNaoEncontrado):
        return HTTPException(http.HTTP_404_NOT_FOUND, str(erro))
    if isinstance(erro, NaoPodeSuceder):
        return HTTPException(http.HTTP_403_FORBIDDEN, str(erro))
    if isinstance(erro, (MesmoStatus, MotivoObrigatorio, SucessorInvalido, ValueError)):
        return HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, str(erro))
    raise erro


# ---------------------------------------------------------------------------
# 1. Linha do tempo
# ---------------------------------------------------------------------------
@router.get("/projetos/{projeto_id}/historico", response_model=PaginaDeHistorico)
def ler_historico(
    projeto_id: int,
    usuario: UsuarioAtual,
    sessao: Annotated[Session, Depends(obter_sessao)],
    antes_de: int | None = None,
    quantos: int = 50,
    so_comentarios: bool = False,
) -> PaginaDeHistorico:
    _projeto(projeto_id, usuario, sessao)
    eventos, tem_mais = listar(
        projeto_id, sessao,
        antes_de=antes_de,
        quantos=min(max(quantos, 1), 200),
        so_comentarios=so_comentarios,
    )
    return PaginaDeHistorico(
        eventos=[_dto(e) for e in eventos],
        tem_mais=tem_mais,
        proximo_cursor=eventos[-1].id if eventos and tem_mais else None,
    )


# ---------------------------------------------------------------------------
# 2. Comentar
# ---------------------------------------------------------------------------
@router.post("/projetos/{projeto_id}/historico/comentarios",
             response_model=EventoDto, status_code=http.HTTP_201_CREATED)
def comentar_no_trabalho(
    projeto_id: int,
    pedido: PedidoDeComentario,
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> EventoDto:
    _projeto(projeto_id, usuario, sessao)
    with contexto(etapa="comentario", projeto_id=projeto_id, usuario_id=usuario.id):
        try:
            return _dto(comentar(projeto_id, pedido.texto, usuario, sessao))
        except Exception as erro:
            raise _traduzir(erro) from erro


# ---------------------------------------------------------------------------
# 3. Status
# ---------------------------------------------------------------------------
@router.get("/status-de-projeto", response_model=list[StatusDto])
def listar_status() -> list[StatusDto]:
    """O catálogo, com rótulo e explicação — a tela não reescreve nenhum."""
    return [
        StatusDto(
            valor=s.value,
            rotulo=s.rotulo,
            explicacao=s.explicacao,
            exige_motivo=s.exige_motivo,
        )
        for s in StatusDoProjeto
    ]


@router.patch("/projetos/{projeto_id}/status")
def mudar_status(
    projeto_id: int,
    pedido: PedidoDeStatus,
    usuario: PodeEscrever,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> dict:
    _projeto(projeto_id, usuario, sessao)
    with contexto(etapa="status", projeto_id=projeto_id, usuario_id=usuario.id):
        try:
            p = alterar_status(projeto_id, pedido.status, pedido.motivo, usuario, sessao)
        except Exception as erro:
            raise _traduzir(erro) from erro
    return {"status": p.status, "rotulo": StatusDoProjeto(p.status).rotulo}


# ---------------------------------------------------------------------------
# 4. Sucessão
# ---------------------------------------------------------------------------
@router.get("/projetos/{projeto_id}/sucessores", response_model=list[PessoaDto])
def listar_sucessores(
    projeto_id: int,
    usuario: UsuarioAtual,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> list[PessoaDto]:
    """Quem pode receber o trabalho: conta ativa e papel que escreve."""
    _projeto(projeto_id, usuario, sessao)
    return [
        PessoaDto(
            id=u.id, nome_exibicao=u.nome_exibicao, usuario=u.usuario,
            papel=u.papel, cargo=u.cargo,
        )
        for u in sucessores_possiveis(sessao)
    ]


@router.patch("/projetos/{projeto_id}/responsavel")
def mudar_responsavel(
    projeto_id: int,
    pedido: PedidoDeSucessao,
    usuario: UsuarioAtual,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> dict:
    _projeto(projeto_id, usuario, sessao)
    with contexto(etapa="sucessao", projeto_id=projeto_id, usuario_id=usuario.id):
        try:
            p = suceder(projeto_id, pedido.responsavel_id, pedido.motivo, usuario, sessao)
        except Exception as erro:
            raise _traduzir(erro) from erro
    return {
        "responsavel_id": p.responsavel_id,
        "responsavel": p.responsavel.nome_exibicao if p.responsavel else None,
    }

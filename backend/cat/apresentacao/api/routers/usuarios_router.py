"""Rotas de gestão de usuários. Só gestor entra aqui.

Não há autocadastro nem redefinição por e-mail: o sistema roda na rede interna,
a base é fechada, e conceder acesso a dado fiscal de cliente precisa ser ato
deliberado de quem responde pela equipe.

A única rota aberta a qualquer usuário autenticado é a troca da própria senha,
que é também o único caminho para sair da senha provisória.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.gerir_usuarios import (
    GerirUsuariosUseCase,
    SenhaAtualIncorreta,
    SenhaRepetida,
    UsuarioJaExiste,
    UsuarioNaoEncontrado,
)
from cat.apresentacao.api.seguranca import UsuarioAtual, exigir_capacidade
from cat.config import obter_config
from cat.dominio.acesso.usuario import (
    Cargo,
    NaoPodeAlterarSiMesmo,
    Papel,
    SenhaFraca,
    UltimoGestor,
    Usuario,
)
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql
from cat.log import contexto, obter_log

log = obter_log(__name__)
router = APIRouter(prefix="/api/usuarios", tags=["usuários"])

# quem administra usuários: gestor e dev. A lista de papéis mora no domínio,
# em Papel.administra_usuarios, e não aqui.
SoGestor = Annotated[
    Usuario,
    Depends(exigir_capacidade("administra_usuarios", "administrar usuários")),
]


# ---------------------------------------------------------------------------
# Contratos
# ---------------------------------------------------------------------------
class UsuarioResumo(BaseModel):
    id: int
    usuario: str
    email: str
    nome_exibicao: str
    papel: str
    cargo: str
    ativo: bool
    bloqueado: bool
    senha_provisoria: bool
    tentativas_falhas: int
    empresas: list[int]
    ultimo_acesso: str | None = None


class PedidoCriar(BaseModel):
    usuario: str = Field(min_length=3, max_length=40)
    email: str
    nome_exibicao: str = Field(min_length=2)
    papel: Papel
    cargo: Cargo = Cargo.OUTRO


class RespostaCriado(BaseModel):
    usuario: UsuarioResumo
    senha_provisoria: str
    aviso: str = (
        "Entregue esta senha pessoalmente. Ela não será exibida de novo e "
        "só serve para o primeiro acesso, quando a troca é obrigatória."
    )


class RespostaSenhaRedefinida(BaseModel):
    senha_provisoria: str
    aviso: str = (
        "Entregue esta senha pessoalmente. Ela não será exibida de novo e "
        "só serve para o próximo acesso, quando a troca é obrigatória."
    )


class PedidoPapel(BaseModel):
    papel: Papel


class PedidoCargo(BaseModel):
    cargo: Cargo


class PedidoSituacao(BaseModel):
    ativo: bool


class PedidoTrocarSenha(BaseModel):
    senha_atual: str
    senha_nova: str


# ---------------------------------------------------------------------------
def _caso(sessao: Session) -> GerirUsuariosUseCase:
    return GerirUsuariosUseCase(
        repositorio=UsuarioRepositorioSql(sessao),
        senhas=SenhasArgon2(obter_config().senha_pimenta),
    )


def _resumo(u: Usuario) -> UsuarioResumo:
    return UsuarioResumo(
        id=u.id,
        usuario=u.usuario,
        email=u.email,
        nome_exibicao=u.nome_exibicao,
        papel=u.papel.value,
        cargo=u.cargo.value,
        ativo=u.ativo,
        bloqueado=u.bloqueado,
        senha_provisoria=u.senha_provisoria,
        tentativas_falhas=u.tentativas_falhas,
        empresas=list(u.empresas),
        ultimo_acesso=u.ultimo_acesso.isoformat() if u.ultimo_acesso else None,
    )


def _traduzir(erro: Exception) -> HTTPException:
    """Erro de domínio vira resposta HTTP. A regra fica no domínio; aqui só a
    tradução do código."""
    if isinstance(erro, UsuarioNaoEncontrado):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(erro))
    if isinstance(erro, (UltimoGestor, NaoPodeAlterarSiMesmo)):
        return HTTPException(status.HTTP_409_CONFLICT, str(erro))
    if isinstance(erro, UsuarioJaExiste):
        return HTTPException(status.HTTP_409_CONFLICT, str(erro))
    if isinstance(erro, (SenhaFraca, SenhaRepetida, ValueError)):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro))
    if isinstance(erro, SenhaAtualIncorreta):
        return HTTPException(status.HTTP_401_UNAUTHORIZED, str(erro))
    raise erro


# ---------------------------------------------------------------------------
# Rota de qualquer usuário autenticado
# ---------------------------------------------------------------------------
# ATENÇÃO: esta rota tem de ser declarada ANTES de "/{alvo_id}/senha".
# O FastAPI casa na ordem de declaração, e "eu" seria capturado como se fosse
# um identificador, resultando em 403 ou 422 em vez da troca de senha.
@router.post("/eu/senha", status_code=status.HTTP_204_NO_CONTENT)
def trocar_propria_senha(
    pedido: PedidoTrocarSenha,
    usuario: UsuarioAtual,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> None:
    """Único caminho para sair da senha provisória."""
    with contexto(etapa="trocar_propria_senha", usuario_id=usuario.id):
        try:
            _caso(sessao).trocar_propria_senha(
                usuario=usuario,
                senha_atual=pedido.senha_atual,
                senha_nova=pedido.senha_nova,
            )
        except Exception as erro:
            raise _traduzir(erro) from erro


# ---------------------------------------------------------------------------
# Rotas de gestor
# ---------------------------------------------------------------------------
@router.get("", response_model=list[UsuarioResumo])
def listar(
    gestor: SoGestor, sessao: Annotated[Session, Depends(obter_sessao)]
) -> list[UsuarioResumo]:
    return [_resumo(u) for u in _caso(sessao).listar()]


@router.post("", response_model=RespostaCriado, status_code=status.HTTP_201_CREATED)
def criar(
    pedido: PedidoCriar,
    gestor: SoGestor,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> RespostaCriado:
    with contexto(etapa="criar_usuario", por_usuario_id=gestor.id):
        try:
            r = _caso(sessao).criar(
                usuario=pedido.usuario,
                email=pedido.email,
                nome_exibicao=pedido.nome_exibicao,
                papel=pedido.papel,
                cargo=pedido.cargo,
                criado_por=gestor,
            )
        except Exception as erro:
            raise _traduzir(erro) from erro
    return RespostaCriado(
        usuario=_resumo(r.usuario), senha_provisoria=r.senha_provisoria
    )


@router.post("/{alvo_id}/senha", response_model=RespostaSenhaRedefinida)
def redefinir_senha(
    alvo_id: int,
    gestor: SoGestor,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> RespostaSenhaRedefinida:
    with contexto(etapa="redefinir_senha", por_usuario_id=gestor.id):
        try:
            senha = _caso(sessao).redefinir_senha(alvo_id=alvo_id, por=gestor)
        except Exception as erro:
            raise _traduzir(erro) from erro
    return RespostaSenhaRedefinida(senha_provisoria=senha)


@router.patch("/{alvo_id}/papel", response_model=UsuarioResumo)
def alterar_papel(
    alvo_id: int,
    pedido: PedidoPapel,
    gestor: SoGestor,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> UsuarioResumo:
    with contexto(etapa="alterar_papel", por_usuario_id=gestor.id):
        try:
            return _resumo(
                _caso(sessao).alterar_papel(
                    alvo_id=alvo_id, papel=pedido.papel, por=gestor
                )
            )
        except Exception as erro:
            raise _traduzir(erro) from erro


@router.patch("/{alvo_id}/cargo", response_model=UsuarioResumo)
def alterar_cargo(
    alvo_id: int,
    pedido: PedidoCargo,
    gestor: SoGestor,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> UsuarioResumo:
    with contexto(etapa="alterar_cargo", por_usuario_id=gestor.id):
        try:
            return _resumo(
                _caso(sessao).alterar_cargo(
                    alvo_id=alvo_id, cargo=pedido.cargo, por=gestor
                )
            )
        except Exception as erro:
            raise _traduzir(erro) from erro


@router.patch("/{alvo_id}/situacao", response_model=UsuarioResumo)
def definir_situacao(
    alvo_id: int,
    pedido: PedidoSituacao,
    gestor: SoGestor,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> UsuarioResumo:
    with contexto(etapa="definir_situacao", por_usuario_id=gestor.id):
        try:
            return _resumo(
                _caso(sessao).definir_situacao(
                    alvo_id=alvo_id, ativo=pedido.ativo, por=gestor
                )
            )
        except Exception as erro:
            raise _traduzir(erro) from erro


@router.post("/{alvo_id}/desbloquear", response_model=UsuarioResumo)
def desbloquear(
    alvo_id: int,
    gestor: SoGestor,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> UsuarioResumo:
    with contexto(etapa="desbloquear", por_usuario_id=gestor.id):
        try:
            return _resumo(_caso(sessao).desbloquear(alvo_id=alvo_id, por=gestor))
        except Exception as erro:
            raise _traduzir(erro) from erro


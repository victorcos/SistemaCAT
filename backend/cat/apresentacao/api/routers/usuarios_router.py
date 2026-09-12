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
from cat.aplicacao.casos_de_uso.alocar_em_empresas import (
    EmpresaInexistente,
    NaoPodeAlocar,
    NaoPodeTirarDeSi,
    UsuarioNaoEncontrado as AlvoDeAlocacaoNaoEncontrado,
    definir as definir_acesso_a_empresas,
    listar as listar_empresas_do_usuario,
)
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


class PedidoDados(BaseModel):
    nome_exibicao: str = Field(min_length=2)
    email: str


class PedidoDeAcesso(BaseModel):
    """As empresas que a pessoa deve alcançar depois desta chamada."""

    empresas: list[int]


class AcessoDto(BaseModel):
    empresa_id: int
    razao_social: str
    uf: str | None = None
    tem_acesso: bool
    desde: str | None = None


class MudancaDeAcessoDto(BaseModel):
    concedidas: list[str]
    encerradas: list[str]


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
    if isinstance(erro, NaoPodeAlocar):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(erro))
    if isinstance(erro, AlvoDeAlocacaoNaoEncontrado):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(erro))
    if isinstance(erro, (NaoPodeTirarDeSi, EmpresaInexistente)):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro))
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


# ---------------------------------------------------------------------------
# Acesso às empresas
#
# É daqui que sai o escopo de visibilidade: `Usuario.empresas` são as
# alocações vigentes, e toda consulta a dado fiscal passa por elas. Até esta
# rota existir, a alocação só nascia de quem cadastrava a empresa pelo SPED —
# e os demais ficavam sem acesso a nada, sem caminho para ganhá-lo.
# ---------------------------------------------------------------------------
@router.get("/{alvo_id}/empresas", response_model=list[AcessoDto])
def listar_acesso(
    alvo_id: int,
    gestor: SoGestor,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> list[AcessoDto]:
    """Todas as empresas, marcando quais esta pessoa alcança hoje."""
    try:
        return [
            AcessoDto(
                empresa_id=a.empresa_id, razao_social=a.razao_social, uf=a.uf,
                tem_acesso=a.tem_acesso,
                desde=a.desde.isoformat() if a.desde else None,
            )
            for a in listar_empresas_do_usuario(alvo_id, sessao)
        ]
    except Exception as erro:
        raise _traduzir(erro) from erro


@router.put("/{alvo_id}/empresas", response_model=MudancaDeAcessoDto)
def definir_acesso(
    alvo_id: int,
    pedido: PedidoDeAcesso,
    gestor: SoGestor,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> MudancaDeAcessoDto:
    """Faz o acesso ser exatamente esta lista de empresas.

    Tirar acesso não apaga a alocação: encerra (`fim`), porque quem tinha
    acesso a um dado em determinado mês precisa continuar respondível.
    """
    with contexto(etapa="alocar_em_empresas", por_usuario_id=gestor.id,
                  alvo_id=alvo_id):
        try:
            mudou = definir_acesso_a_empresas(
                alvo_id, set(pedido.empresas), gestor, sessao
            )
        except Exception as erro:
            raise _traduzir(erro) from erro
    return MudancaDeAcessoDto(
        concedidas=mudou.concedidas, encerradas=mudou.encerradas
    )


@router.patch("/{alvo_id}/dados", response_model=UsuarioResumo)
def alterar_dados(
    alvo_id: int,
    pedido: PedidoDados,
    gestor: SoGestor,
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> UsuarioResumo:
    """Nome de exibição e e-mail. Papel, cargo e situação têm rota própria
    porque têm regra própria (mínimo de gestores, não alterar a si mesmo)."""
    with contexto(etapa="alterar_dados", por_usuario_id=gestor.id):
        try:
            return _resumo(
                _caso(sessao).alterar_dados(
                    alvo_id=alvo_id, nome_exibicao=pedido.nome_exibicao,
                    email=pedido.email, por=gestor,
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


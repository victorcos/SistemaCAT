"""Quem é o usuário da requisição, e o que ele pode."""

from __future__ import annotations

from typing import Annotated, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from cat.config import obter_config
from cat.dominio.acesso.usuario import Papel, Usuario
from cat.infraestrutura.auth.token import TokenInvalido, TokensJwt
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql
from cat.log import obter_log

log = obter_log(__name__)
esquema = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def obter_tokens() -> TokensJwt:
    c = obter_config()
    return TokensJwt(c.jwt_segredo, c.jwt_algoritmo, c.jwt_minutos)


def usuario_atual(
    token: Annotated[str | None, Depends(esquema)],
    sessao: Annotated[Session, Depends(obter_sessao)],
) -> Usuario:
    nao_autorizado = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessão inválida ou expirada.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise nao_autorizado
    try:
        conteudo = obter_tokens().ler(token)
    except TokenInvalido as erro:
        log.warning("token recusado", extra={"motivo": erro.motivo})
        raise nao_autorizado from erro

    # relemos do banco de propósito: se a pessoa foi desativada ou perdeu a
    # alocação depois de o token ser emitido, o acesso cai na hora
    usuario = UsuarioRepositorioSql(sessao).buscar_por_id(conteudo.usuario_id)
    if usuario is None or not usuario.ativo:
        log.warning("token válido de usuário ausente ou inativo",
                    extra={"usuario_id": conteudo.usuario_id})
        raise nao_autorizado
    return usuario


UsuarioAtual = Annotated[Usuario, Depends(usuario_atual)]


def exigir_capacidade(
    nome: str, descricao: str
) -> Callable[[Usuario], Usuario]:
    """Exige uma CAPACIDADE do domínio, não um papel específico.

    Enumerar papéis na rota faz com que todo papel novo exija caçar rotas para
    atualizar. Perguntando a capacidade, o domínio continua sendo a única fonte
    de quem pode o quê.
    """

    def verificar(usuario: UsuarioAtual) -> Usuario:
        if not getattr(usuario.papel, nome, False):
            log.warning(
                "acesso negado por falta de capacidade",
                extra={"usuario_id": usuario.id, "papel": usuario.papel.value,
                       "capacidade_exigida": nome},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Você não tem permissão para {descricao}.",
            )
        return usuario

    return verificar


def exigir_papel(*papeis: Papel) -> Callable[[Usuario], Usuario]:
    def verificar(usuario: UsuarioAtual) -> Usuario:
        if usuario.papel not in papeis:
            log.warning(
                "acesso negado por papel",
                extra={"usuario_id": usuario.id, "papel": usuario.papel.value,
                       "exigido": [p.value for p in papeis]},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para esta operação.",
            )
        return usuario

    return verificar


def exigir_empresa(usuario: Usuario, empresa_id: int) -> None:
    """Todo acesso a dado fiscal passa por aqui. Nunca filtrar no front."""
    if usuario.acessa_por_excecao(empresa_id):
        # o dev passou sem alocação: registra como exceção para não virar
        # rotina invisível no meio do tráfego normal
        log.warning(
            "acesso a empresa por exceção de dev",
            extra={"usuario_id": usuario.id, "usuario": usuario.usuario,
                   "empresa": empresa_id, "papel": usuario.papel.value,
                   "sem_alocacao": True},
        )
        return
    if not usuario.enxerga_empresa(empresa_id):
        log.warning(
            "acesso negado a empresa fora do escopo",
            extra={"usuario_id": usuario.id, "empresa_pedida": empresa_id,
                   "empresas_do_usuario": list(usuario.empresas)},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem acesso a esta empresa.",
        )

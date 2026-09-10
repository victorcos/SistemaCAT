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

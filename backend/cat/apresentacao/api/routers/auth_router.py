"""Rotas de autenticação. Finas: validam entrada, chamam caso de uso, traduzem erro."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cat.aplicacao.casos_de_uso.autenticar import AutenticarUseCase
from cat.apresentacao.api.seguranca import UsuarioAtual, obter_tokens
from cat.dominio.acesso.usuario import (
    CredencialInvalida, UsuarioBloqueado, UsuarioInativo,
)
from cat.config import obter_config
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.banco import obter_sessao
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql
from cat.log import contexto, obter_log

log = obter_log(__name__)
router = APIRouter(prefix="/api/auth", tags=["autenticação"])

# atraso mínimo da resposta de login, para que "usuário não existe" e "senha
# errada" levem o mesmo tempo e não dê para descobrir contas pelo relógio
PISO_RESPOSTA_S = 0.35


class RespostaToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: "RespostaUsuario"


class RespostaUsuario(BaseModel):
    id: int
    usuario: str
    email: str
    nome_exibicao: str
    papel: str
    empresas: list[int]
    ultimo_acesso: str | None = None


RespostaToken.model_rebuild()


@router.post("/token", response_model=RespostaToken)
def entrar(
    formulario: Annotated[OAuth2PasswordRequestForm, Depends()],
    sessao: Annotated[Session, Depends(obter_sessao)],
    request: Request,
) -> RespostaToken:
    inicio = time.perf_counter()
    origem = request.client.host if request.client else "?"

    with contexto(etapa="login", origem=origem):
        caso = AutenticarUseCase(
            repositorio=UsuarioRepositorioSql(sessao),
            senhas=SenhasArgon2(obter_config().senha_pimenta),
            tokens=obter_tokens(),
        )
        try:
            r = caso.executar(formulario.username, formulario.password)
        except CredencialInvalida as erro:
            _nivelar_tempo(inicio)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=str(erro),
                headers={"WWW-Authenticate": "Bearer"},
            ) from erro
        except (UsuarioInativo, UsuarioBloqueado) as erro:
            _nivelar_tempo(inicio)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=str(erro)
            ) from erro

        _nivelar_tempo(inicio)
        return RespostaToken(
            access_token=r.token,
            expires_in=r.expira_em,
            usuario=_para_resposta(r.usuario),
        )


@router.get("/eu", response_model=RespostaUsuario)
def eu(usuario: UsuarioAtual) -> RespostaUsuario:
    return _para_resposta(usuario)


def _para_resposta(u) -> RespostaUsuario:
    return RespostaUsuario(
        id=u.id,
        usuario=u.usuario,
        email=u.email,
        nome_exibicao=u.nome_exibicao,
        papel=u.papel.value,
        empresas=list(u.empresas),
        ultimo_acesso=u.ultimo_acesso.isoformat() if u.ultimo_acesso else None,
    )


def _nivelar_tempo(inicio: float) -> None:
    restante = PISO_RESPOSTA_S - (time.perf_counter() - inicio)
    if restante > 0:
        time.sleep(restante)

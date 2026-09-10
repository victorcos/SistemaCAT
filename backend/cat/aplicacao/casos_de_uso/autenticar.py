"""Caso de uso: autenticar. Orquestra domínio e portas, sem tocar em I/O."""

from __future__ import annotations

from dataclasses import dataclass

from cat.aplicacao.portas import EmissorDeToken, RepositorioUsuario, VerificadorDeSenha
from cat.dominio.acesso.usuario import (
    CredencialInvalida,
    Usuario,
    UsuarioBloqueado,
    UsuarioInativo,
)
from cat.log import obter_log

log = obter_log(__name__)


@dataclass(frozen=True)
class Autenticado:
    token: str
    expira_em: int
    usuario: Usuario


class AutenticarUseCase:
    def __init__(
        self,
        repositorio: RepositorioUsuario,
        senhas: VerificadorDeSenha,
        tokens: EmissorDeToken,
    ) -> None:
        self._repo = repositorio
        self._senhas = senhas
        self._tokens = tokens

    def executar(self, nome_usuario: str, senha: str) -> Autenticado:
        nome_usuario = (nome_usuario or "").strip().lower()
        usuario = self._repo.buscar_por_usuario(nome_usuario)

        if usuario is None:
            # não dizemos "usuário não existe": isso entrega quais contas existem
            log.warning(
                "tentativa de login para usuário inexistente",
                extra={"usuario_informado": nome_usuario, "motivo": "nao_encontrado"},
            )
            raise CredencialInvalida()

        try:
            usuario.garantir_que_pode_entrar()
        except UsuarioInativo:
            log.warning(
                "login recusado, usuário inativo",
                extra={"usuario_id": usuario.id, "usuario": usuario.usuario,
                       "motivo": "inativo"},
            )
            raise
        except UsuarioBloqueado as erro:
            log.warning(
                "login recusado, usuário bloqueado",
                extra={"usuario_id": usuario.id, "usuario": usuario.usuario,
                       "motivo": "bloqueado", "tentativas": erro.tentativas},
            )
            raise

        if not self._senhas.conferir(senha, self._repo.obter_hash_senha(usuario.id)):
            usuario.registrar_falha()
            self._repo.salvar_tentativa(usuario)
            log.warning(
                "login recusado, senha incorreta",
                extra={"usuario_id": usuario.id, "usuario": usuario.usuario,
                       "motivo": "senha_incorreta",
                       "tentativas_falhas": usuario.tentativas_falhas,
                       "tentativas_restantes": usuario.tentativas_restantes},
            )
            raise CredencialInvalida()

        usuario.registrar_sucesso()
        self._repo.salvar_tentativa(usuario)
        token, expira_em = self._tokens.emitir(usuario)

        log.info(
            "login concluído",
            extra={"usuario_id": usuario.id, "usuario": usuario.usuario,
                   "papel": usuario.papel.value,
                   "empresas": list(usuario.empresas), "expira_em_s": expira_em},
        )
        return Autenticado(token=token, expira_em=expira_em, usuario=usuario)

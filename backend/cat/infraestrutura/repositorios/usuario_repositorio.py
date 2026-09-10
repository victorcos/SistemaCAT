"""Repositório de usuário. Traduz tabela em entidade de domínio."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cat.dominio.acesso.usuario import Papel, Usuario
from cat.config import obter_config
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.log import obter_log
from cat.infraestrutura.repositorios.modelos import UsuarioDB

log = obter_log(__name__)


def _para_dominio(linha: UsuarioDB) -> Usuario:
    # escopo de visibilidade vem SÓ das alocações vigentes
    empresas = tuple(
        sorted({a.empresa_id for a in linha.alocacoes if a.fim is None})
    )
    try:
        papel = Papel(linha.papel)
    except ValueError:
        log.error(
            "papel desconhecido no banco, rebaixando para leitura",
            extra={"usuario_id": linha.id, "papel_encontrado": linha.papel},
        )
        papel = Papel.LEITURA
    return Usuario(
        id=linha.id,
        usuario=linha.usuario,
        email=linha.email,
        nome_exibicao=linha.nome_exibicao,
        papel=papel,
        ativo=linha.ativo,
        tentativas_falhas=linha.tentativas_falhas,
        ultimo_acesso=linha.ultimo_acesso,
        empresas=empresas,
    )


class UsuarioRepositorioSql:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao
        self._senhas = SenhasArgon2(obter_config().senha_pimenta)

    def buscar_por_usuario(self, usuario: str) -> Usuario | None:
        linha = self._s.scalar(select(UsuarioDB).where(UsuarioDB.usuario == usuario))
        return _para_dominio(linha) if linha else None

    def buscar_por_id(self, usuario_id: int) -> Usuario | None:
        linha = self._s.get(UsuarioDB, usuario_id)
        return _para_dominio(linha) if linha else None

    def obter_hash_senha(self, usuario_id: int) -> str:
        linha = self._s.get(UsuarioDB, usuario_id)
        return linha.senha_hash if linha else ""

    def salvar_tentativa(self, usuario: Usuario) -> None:
        linha = self._s.get(UsuarioDB, usuario.id)
        if linha is None:
            log.error("tentativa de salvar usuário inexistente",
                      extra={"usuario_id": usuario.id})
            return
        linha.tentativas_falhas = usuario.tentativas_falhas
        linha.ultimo_acesso = usuario.ultimo_acesso
        self._s.commit()

    def regravar_hash_senha(self, usuario_id: int, novo_hash: str) -> None:
        """Atualiza o resumo para o formato atual, sem tocar na senha do usuário."""
        linha = self._s.get(UsuarioDB, usuario_id)
        if linha is None:
            log.error("regravação de hash para usuário inexistente",
                      extra={"usuario_id": usuario_id})
            return
        anterior = linha.senha_hash[:7]
        linha.senha_hash = novo_hash
        self._s.commit()
        log.info("resumo de senha migrado para o formato atual",
                 extra={"usuario_id": usuario_id, "formato_anterior": anterior,
                        "formato_atual": novo_hash[:7]})

    def criar(
        self, usuario: str, email: str, nome_exibicao: str, senha: str, papel: Papel
    ) -> Usuario:
        linha = UsuarioDB(
            usuario=usuario,
            email=email,
            nome_exibicao=nome_exibicao,
            senha_hash=self._senhas.gerar(senha),
            papel=papel.value,
        )
        self._s.add(linha)
        self._s.commit()
        self._s.refresh(linha)
        log.info("usuário criado",
                 extra={"usuario_id": linha.id, "usuario": usuario,
                        "papel": papel.value})
        return _para_dominio(linha)

    def existe_algum(self) -> bool:
        return self._s.scalar(select(UsuarioDB.id).limit(1)) is not None

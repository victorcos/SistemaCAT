"""Repositório de usuário. Traduz tabela em entidade de domínio."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cat.config import obter_config
from cat.dominio.acesso.usuario import Cargo, Papel, Usuario
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.modelos import UsuarioDB
from cat.log import obter_log

log = obter_log(__name__)


def _enum(tipo, valor: str, padrao, usuario_id: int | None, campo: str):
    """Converte texto do banco em enum, sem derrubar a aplicação.

    Valor desconhecido rebaixa para o padrão e registra. Melhor um usuário com
    menos permissão do que uma exceção que impede todo mundo de entrar.
    """
    try:
        return tipo(valor)
    except ValueError:
        log.error(
            f"{campo} desconhecido no banco, usando o padrão",
            extra={"usuario_id": usuario_id, "encontrado": valor,
                   "padrao": padrao.value},
        )
        return padrao


def _para_dominio(linha: UsuarioDB) -> Usuario:
    # escopo de visibilidade vem SÓ das alocações vigentes
    empresas = tuple(sorted({a.empresa_id for a in linha.alocacoes if a.fim is None}))
    return Usuario(
        id=linha.id,
        usuario=linha.usuario,
        email=linha.email,
        nome_exibicao=linha.nome_exibicao,
        papel=_enum(Papel, linha.papel, Papel.LEITURA, linha.id, "papel"),
        cargo=_enum(Cargo, linha.cargo, Cargo.OUTRO, linha.id, "cargo"),
        ativo=linha.ativo,
        tentativas_falhas=linha.tentativas_falhas,
        bloqueado_ate=linha.bloqueado_ate,
        senha_provisoria=linha.senha_provisoria,
        ultimo_acesso=linha.ultimo_acesso,
        empresas=empresas,
    )


class UsuarioRepositorioSql:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao
        self._senhas = SenhasArgon2(obter_config().senha_pimenta)

    # ---------- leitura ----------
    def buscar_por_usuario(self, usuario: str) -> Usuario | None:
        linha = self._s.scalar(select(UsuarioDB).where(UsuarioDB.usuario == usuario))
        return _para_dominio(linha) if linha else None

    def buscar_por_email(self, email: str) -> Usuario | None:
        linha = self._s.scalar(select(UsuarioDB).where(UsuarioDB.email == email))
        return _para_dominio(linha) if linha else None

    def buscar_por_id(self, usuario_id: int) -> Usuario | None:
        linha = self._s.get(UsuarioDB, usuario_id)
        return _para_dominio(linha) if linha else None

    def listar(self) -> list[Usuario]:
        linhas = self._s.scalars(
            select(UsuarioDB).order_by(UsuarioDB.ativo.desc(), UsuarioDB.usuario)
        )
        return [_para_dominio(linha) for linha in linhas]

    def contar_gestores_ativos(self) -> int:
        return (
            self._s.scalar(
                select(func.count(UsuarioDB.id)).where(
                    UsuarioDB.papel == Papel.GESTOR.value,
                    UsuarioDB.ativo.is_(True),
                )
            )
            or 0
        )

    def obter_hash_senha(self, usuario_id: int) -> str:
        linha = self._s.get(UsuarioDB, usuario_id)
        return linha.senha_hash if linha else ""

    # ---------- escrita ----------
    def criar(
        self,
        *,
        usuario: str,
        email: str,
        nome_exibicao: str,
        senha_hash: str,
        papel: Papel,
        cargo: Cargo = Cargo.OUTRO,
        senha_provisoria: bool = False,
    ) -> Usuario:
        linha = UsuarioDB(
            usuario=usuario,
            email=email,
            nome_exibicao=nome_exibicao,
            senha_hash=senha_hash,
            papel=papel.value,
            cargo=cargo.value,
            senha_provisoria=senha_provisoria,
        )
        self._s.add(linha)
        self._s.commit()
        self._s.refresh(linha)
        return _para_dominio(linha)

    def salvar_tentativa(self, usuario: Usuario) -> None:
        linha = self._alterar(usuario.id, "salvar tentativa")
        if linha is None:
            return
        linha.tentativas_falhas = usuario.tentativas_falhas
        linha.bloqueado_ate = usuario.bloqueado_ate
        linha.ultimo_acesso = usuario.ultimo_acesso
        self._s.commit()

    def regravar_hash_senha(self, usuario_id: int, novo_hash: str) -> None:
        """Atualiza o resumo para o formato atual, sem tocar na senha do usuário."""
        linha = self._alterar(usuario_id, "regravar hash")
        if linha is None:
            return
        anterior = linha.senha_hash[:7]
        linha.senha_hash = novo_hash
        self._s.commit()
        log.info(
            "resumo de senha migrado para o formato atual",
            extra={"usuario_id": usuario_id, "formato_anterior": anterior,
                   "formato_atual": novo_hash[:7]},
        )

    def definir_senha(
        self, usuario_id: int, novo_hash: str, *, provisoria: bool
    ) -> None:
        linha = self._alterar(usuario_id, "definir senha")
        if linha is None:
            return
        linha.senha_hash = novo_hash
        linha.senha_provisoria = provisoria
        self._s.commit()

    def definir_papel(self, usuario_id: int, papel: Papel) -> None:
        linha = self._alterar(usuario_id, "definir papel")
        if linha is None:
            return
        linha.papel = papel.value
        self._s.commit()

    def definir_cargo(self, usuario_id: int, cargo: Cargo) -> None:
        linha = self._alterar(usuario_id, "definir cargo")
        if linha is None:
            return
        linha.cargo = cargo.value
        self._s.commit()

    def definir_situacao(self, usuario_id: int, ativo: bool) -> None:
        linha = self._alterar(usuario_id, "definir situação")
        if linha is None:
            return
        linha.ativo = ativo
        self._s.commit()

    def desbloquear(self, usuario_id: int) -> None:
        linha = self._alterar(usuario_id, "desbloquear")
        if linha is None:
            return
        linha.tentativas_falhas = 0
        linha.bloqueado_ate = None
        self._s.commit()

    def existe_algum(self) -> bool:
        return self._s.scalar(select(UsuarioDB.id).limit(1)) is not None

    # ---------- interno ----------
    def _alterar(self, usuario_id: int, acao: str) -> UsuarioDB | None:
        linha = self._s.get(UsuarioDB, usuario_id)
        if linha is None:
            log.error(
                f"tentativa de {acao} em usuário inexistente",
                extra={"usuario_id": usuario_id},
            )
        return linha

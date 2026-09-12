"""Casos de uso da gestão de usuários.

Cadastro e redefinição de senha ficam com o gestor. O sistema roda na rede
interna, a base de usuários é fechada e conceder acesso a dado fiscal de cliente
precisa ser ato deliberado. Não há autocadastro nem redefinição por e-mail.

As três salvaguardas que isso exige estão aqui:

1. O sistema recusa ficar com menos de tres gestores ativos, que sao os
   cargos de direcao, gerencia e coordenacao.
2. A redefinição gera senha provisória de uso único; o gestor nunca escolhe a
   senha de ninguém, e quem entra com ela só consegue trocar a senha.
3. A saída de emergência é por linha de comando no servidor, em
   `cat.apresentacao.cli.emergencia`.
"""

from __future__ import annotations

from dataclasses import dataclass

from cat.aplicacao.portas import RepositorioUsuario, VerificadorDeSenha
from cat.dominio.acesso.usuario import (
    Cargo,
    NaoPodeAlterarSiMesmo,
    Papel,
    Usuario,
    garantir_minimo_de_gestores,
    gerar_senha_provisoria,
    validar_email,
    validar_nome_de_usuario,
    validar_politica_de_senha,
)
from cat.log import obter_log

log = obter_log(__name__)


class UsuarioJaExiste(Exception):
    def __init__(self, campo: str) -> None:
        super().__init__(f"Já existe usuário com este {campo}.")


class UsuarioNaoEncontrado(Exception):
    def __init__(self) -> None:
        super().__init__("Usuário não encontrado.")


class SenhaAtualIncorreta(Exception):
    def __init__(self) -> None:
        super().__init__("A senha atual está incorreta.")


class SenhaRepetida(Exception):
    def __init__(self) -> None:
        super().__init__("A nova senha precisa ser diferente da atual.")


@dataclass(frozen=True)
class UsuarioCriado:
    usuario: Usuario
    senha_provisoria: str


class GerirUsuariosUseCase:
    """Uma classe por ser tudo variação do mesmo assunto e compartilhar as
    mesmas salvaguardas. Cada método é uma operação completa."""

    def __init__(
        self, repositorio: RepositorioUsuario, senhas: VerificadorDeSenha
    ) -> None:
        self._repo = repositorio
        self._senhas = senhas

    # ---------- consulta ----------
    def listar(self) -> list[Usuario]:
        return self._repo.listar()

    # ---------- cadastro ----------
    def criar(
        self,
        *,
        usuario: str,
        email: str,
        nome_exibicao: str,
        papel: Papel,
        cargo: Cargo,
        criado_por: Usuario,
    ) -> UsuarioCriado:
        usuario = validar_nome_de_usuario(usuario)
        email = validar_email(email)
        nome_exibicao = nome_exibicao.strip()
        if not nome_exibicao:
            raise ValueError("O nome de exibição não pode ficar vazio.")

        if self._repo.buscar_por_usuario(usuario) is not None:
            raise UsuarioJaExiste("nome de usuário")
        if self._repo.buscar_por_email(email) is not None:
            raise UsuarioJaExiste("e-mail")

        senha = gerar_senha_provisoria()
        novo = self._repo.criar(
            usuario=usuario,
            email=email,
            nome_exibicao=nome_exibicao,
            senha_hash=self._senhas.gerar(senha),
            papel=papel,
            cargo=cargo,
            senha_provisoria=True,
        )
        log.info(
            "usuário criado",
            extra={"usuario_id": novo.id, "usuario": novo.usuario,
                   "papel": papel.value, "cargo": cargo.value,
                   "por_usuario_id": criado_por.id},
        )
        return UsuarioCriado(usuario=novo, senha_provisoria=senha)

    # ---------- senha ----------
    def redefinir_senha(self, *, alvo_id: int, por: Usuario) -> str:
        """Gera senha provisória de uso único. Devolve para o gestor entregar.

        O gestor não escolhe a senha. Se escolhesse, passaria a saber a senha da
        pessoa, e o resumo de mão única perderia sentido na prática.
        """
        alvo = self._buscar(alvo_id)
        senha = gerar_senha_provisoria()
        self._repo.definir_senha(
            alvo.id, self._senhas.gerar(senha), provisoria=True
        )
        self._repo.desbloquear(alvo.id)
        log.warning(
            "senha redefinida por gestor",
            extra={"usuario_id": alvo.id, "usuario": alvo.usuario,
                   "por_usuario_id": por.id, "provisoria": True},
        )
        return senha

    def trocar_propria_senha(
        self, *, usuario: Usuario, senha_atual: str, senha_nova: str
    ) -> None:
        """A pessoa troca a própria senha. Único caminho para sair da provisória."""
        hash_atual = self._repo.obter_hash_senha(usuario.id)
        if not self._senhas.conferir(senha_atual, hash_atual):
            log.warning(
                "troca de senha recusada, senha atual incorreta",
                extra={"usuario_id": usuario.id, "motivo": "senha_atual_incorreta"},
            )
            raise SenhaAtualIncorreta()
        if senha_atual == senha_nova:
            raise SenhaRepetida()

        validar_politica_de_senha(senha_nova)
        self._repo.definir_senha(
            usuario.id, self._senhas.gerar(senha_nova), provisoria=False
        )
        log.info("senha trocada pelo próprio usuário",
                 extra={"usuario_id": usuario.id})

    # ---------- papel e situação ----------
    def alterar_dados(self, *, alvo_id: int, nome_exibicao: str, email: str,
                      por: Usuario) -> Usuario:
        """Nome de exibição e e-mail. O nome de usuário não muda nunca: é a
        identidade nos logs e nas alocações."""
        alvo = self._buscar(alvo_id)
        email = validar_email(email)
        nome_exibicao = nome_exibicao.strip()
        if not nome_exibicao:
            raise ValueError("O nome de exibição não pode ficar vazio.")
        dono = self._repo.buscar_por_email(email)
        if dono is not None and dono.id != alvo.id:
            raise UsuarioJaExiste("e-mail")

        self._repo.definir_dados(alvo.id, nome_exibicao, email)
        log.info("dados alterados",
                 extra={"usuario_id": alvo.id, "usuario": alvo.usuario,
                        "email_anterior": alvo.email, "email_novo": email,
                        "por_usuario_id": por.id})
        return self._buscar(alvo_id)

    def alterar_cargo(self, *, alvo_id: int, cargo: Cargo, por: Usuario) -> Usuario:
        alvo = self._buscar(alvo_id)
        self._repo.definir_cargo(alvo.id, cargo)
        log.info("cargo alterado",
                 extra={"usuario_id": alvo.id, "cargo_anterior": alvo.cargo.value,
                        "cargo_novo": cargo.value, "por_usuario_id": por.id})
        return self._buscar(alvo_id)

    def alterar_papel(self, *, alvo_id: int, papel: Papel, por: Usuario) -> Usuario:
        alvo = self._buscar(alvo_id)
        if alvo.id == por.id and papel is not Papel.GESTOR:
            raise NaoPodeAlterarSiMesmo("rebaixar")
        if alvo.papel is Papel.GESTOR and papel is not Papel.GESTOR:
            self._checar_gestores_apos_perder(alvo)

        self._repo.definir_papel(alvo.id, papel)
        log.warning(
            "papel alterado",
            extra={"usuario_id": alvo.id, "usuario": alvo.usuario,
                   "papel_anterior": alvo.papel.value, "papel_novo": papel.value,
                   "por_usuario_id": por.id},
        )
        return self._buscar(alvo_id)

    def definir_situacao(self, *, alvo_id: int, ativo: bool, por: Usuario) -> Usuario:
        alvo = self._buscar(alvo_id)
        if alvo.id == por.id and not ativo:
            raise NaoPodeAlterarSiMesmo("desativar")
        if alvo.papel is Papel.GESTOR and alvo.ativo and not ativo:
            self._checar_gestores_apos_perder(alvo)

        self._repo.definir_situacao(alvo.id, ativo)
        log.warning(
            "situação de usuário alterada",
            extra={"usuario_id": alvo.id, "usuario": alvo.usuario,
                   "ativo": ativo, "por_usuario_id": por.id},
        )
        return self._buscar(alvo_id)

    def desbloquear(self, *, alvo_id: int, por: Usuario) -> Usuario:
        alvo = self._buscar(alvo_id)
        self._repo.desbloquear(alvo.id)
        log.info(
            "usuário desbloqueado por gestor",
            extra={"usuario_id": alvo.id, "usuario": alvo.usuario,
                   "tentativas_antes": alvo.tentativas_falhas,
                   "por_usuario_id": por.id},
        )
        return self._buscar(alvo_id)

    # ---------- interno ----------
    def _buscar(self, alvo_id: int) -> Usuario:
        alvo = self._repo.buscar_por_id(alvo_id)
        if alvo is None:
            raise UsuarioNaoEncontrado()
        return alvo

    def _checar_gestores_apos_perder(self, alvo: Usuario) -> None:
        """Quantos gestores sobrariam se este deixasse de contar."""
        restantes = self._repo.contar_gestores_ativos() - 1
        try:
            garantir_minimo_de_gestores(restantes)
        except Exception:
            log.warning(
                "alteração recusada para não deixar o sistema sem gestores",
                extra={"usuario_id": alvo.id, "gestores_restantes": restantes},
            )
            raise

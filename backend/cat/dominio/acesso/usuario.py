"""Domínio de acesso — puro, sem banco, sem framework, sem I/O.

Estas regras têm de rodar em teste de unidade em milissegundos. Se alguém
precisar de um banco para testar o que está aqui, o desenho quebrou.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

# tentativas antes de bloquear; alto o bastante para não atrapalhar quem erra a
# senha, baixo o bastante para inviabilizar tentativa por força bruta
MAX_TENTATIVAS = 5
TAMANHO_MINIMO_SENHA = 10

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_RE_USUARIO = re.compile(r"^[a-z0-9._-]{3,40}$")


class Papel(str, Enum):
    """O que a pessoa pode fazer. Ortogonal a QUAIS empresas ela enxerga."""

    GESTOR = "gestor"       # administra usuários e alocações
    ANALISTA = "analista"   # executa apuração e aprova de-para
    REVISOR = "revisor"     # confere e aprova entrega
    LEITURA = "leitura"     # só consulta

    @property
    def administra_usuarios(self) -> bool:
        return self is Papel.GESTOR

    @property
    def pode_escrever(self) -> bool:
        return self in (Papel.GESTOR, Papel.ANALISTA, Papel.REVISOR)


class SenhaFraca(ValueError):
    """Senha que não atende à política."""


class CredencialInvalida(Exception):
    """Usuário ou senha errados. A mensagem é sempre a mesma, de propósito:
    dizer 'usuário não existe' entrega quais contas existem."""

    def __init__(self) -> None:
        super().__init__("Usuário ou senha inválidos.")


class UsuarioInativo(Exception):
    def __init__(self) -> None:
        super().__init__("Usuário inativo. Procure um gestor.")


class UsuarioBloqueado(Exception):
    def __init__(self, tentativas: int) -> None:
        self.tentativas = tentativas
        super().__init__(
            "Usuário bloqueado por excesso de tentativas. Procure um gestor."
        )


def validar_politica_de_senha(senha: str) -> None:
    """Levanta SenhaFraca se a senha não servir.

    Comprimento pesa mais que exigência de caractere especial, que só empurra o
    usuário para 'Senha@123'. Exigimos tamanho e alguma variedade.
    """
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise SenhaFraca(
            f"A senha precisa de pelo menos {TAMANHO_MINIMO_SENHA} caracteres."
        )
    if senha.lower() == senha or senha.upper() == senha:
        raise SenhaFraca("A senha precisa misturar maiúsculas e minúsculas.")
    if not any(c.isdigit() for c in senha):
        raise SenhaFraca("A senha precisa de pelo menos um número.")
    if senha.strip() != senha:
        raise SenhaFraca("A senha não pode começar nem terminar com espaço.")


def validar_nome_de_usuario(nome: str) -> str:
    nome = nome.strip().lower()
    if not _RE_USUARIO.match(nome):
        raise ValueError(
            "Nome de usuário deve ter de 3 a 40 caracteres, entre letras "
            "minúsculas, números, ponto, hífen e sublinhado."
        )
    return nome


def validar_email(email: str) -> str:
    email = email.strip().lower()
    if not _RE_EMAIL.match(email):
        raise ValueError("E-mail inválido.")
    return email


@dataclass
class Usuario:
    """Quem entra no sistema.

    `empresas` é o escopo de visibilidade, derivado das alocações vigentes.
    Papel diz o QUE pode fazer; empresas dizem SOBRE QUEM. São coisas
    diferentes e não podem ser fundidas: um gestor sem alocação na Casa Avenida
    não enxerga dado da Casa Avenida.
    """

    id: int | None
    usuario: str
    email: str
    nome_exibicao: str
    papel: Papel
    ativo: bool = True
    tentativas_falhas: int = 0
    ultimo_acesso: datetime | None = None
    empresas: tuple[int, ...] = field(default=())

    @property
    def bloqueado(self) -> bool:
        return self.tentativas_falhas >= MAX_TENTATIVAS

    def garantir_que_pode_entrar(self) -> None:
        """Ordem importa: inativo antes de bloqueado, porque desativar é uma
        decisão do gestor e bloquear é consequência automática."""
        if not self.ativo:
            raise UsuarioInativo()
        if self.bloqueado:
            raise UsuarioBloqueado(self.tentativas_falhas)

    def registrar_falha(self) -> None:
        self.tentativas_falhas += 1

    def registrar_sucesso(self, quando: datetime | None = None) -> None:
        self.tentativas_falhas = 0
        self.ultimo_acesso = quando or datetime.now(timezone.utc)

    def enxerga_empresa(self, empresa_id: int) -> bool:
        """Nenhuma consulta a dado fiscal passa sem esta pergunta."""
        return empresa_id in self.empresas

    @property
    def tentativas_restantes(self) -> int:
        return max(0, MAX_TENTATIVAS - self.tentativas_falhas)

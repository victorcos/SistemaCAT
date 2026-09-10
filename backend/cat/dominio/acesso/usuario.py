"""Domínio de acesso — puro, sem banco, sem framework, sem I/O.

Estas regras têm de rodar em teste de unidade em milissegundos. Se alguém
precisar de um banco para testar o que está aqui, o desenho quebrou.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

# ---------------------------------------------------------------------------
# Bloqueio em dois níveis.
#
# Destravar usuário é muito mais frequente que redefinir senha, então precisa
# ser barato. Cinco erros já inviabilizam força bruta; quinze minutos de espera
# resolvem sozinhos e não geram chamado. O bloqueio que exige gestor fica para
# quem insistiu vinte vezes, que aí não é mais distração.
# ---------------------------------------------------------------------------
TENTATIVAS_BLOQUEIO_TEMPORARIO = 5
MINUTOS_BLOQUEIO_TEMPORARIO = 15
TENTATIVAS_BLOQUEIO_PERMANENTE = 20

# O sistema recusa ficar com menos de três gestores ativos. São os cargos de
# direção, gerência e coordenação. Com um só, férias, desligamento ou senha
# esquecida travam o sistema inteiro e não há quem destrave; com três, sempre
# sobram dois. É regra de domínio, não de tela, para valer também na API.
MINIMO_DE_GESTORES = 3

TAMANHO_MINIMO_SENHA = 10

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_RE_USUARIO = re.compile(r"^[a-z0-9._-]{3,40}$")


def agora() -> datetime:
    return datetime.now(timezone.utc)


def com_fuso(momento: datetime | None) -> datetime | None:
    """Garante data ciente de fuso.

    O SQLite não guarda o fuso e devolve data ingênua, o que faz qualquer
    subtração explodir. Em vez de confiar no banco, o domínio normaliza:
    data sem fuso é tratada como UTC, que é o único fuso que gravamos.
    """
    if momento is None or momento.tzinfo is not None:
        return momento
    return momento.replace(tzinfo=timezone.utc)


class Cargo(str, Enum):
    """Posição na estrutura da empresa.

    Não confundir com Papel. Papel define permissão; cargo é informação
    organizacional, para a lista de usuários dizer quem é quem. Os três cargos
    de gestão existem para que o sistema nunca dependa de uma pessoa só.
    """

    DIRETOR = "diretor"
    GERENTE = "gerente"
    COORDENADOR = "coordenador"
    ANALISTA = "analista"
    ESTAGIARIO = "estagiario"
    OUTRO = "outro"

    @property
    def e_de_gestao(self) -> bool:
        return self in (Cargo.DIRETOR, Cargo.GERENTE, Cargo.COORDENADOR)


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


# ---------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------
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


class UsuarioBloqueadoTemporariamente(Exception):
    def __init__(self, minutos: int) -> None:
        self.minutos = minutos
        super().__init__(
            f"Muitas tentativas. Tente de novo em {minutos} "
            f"{'minuto' if minutos == 1 else 'minutos'}."
        )


class UsuarioBloqueado(Exception):
    def __init__(self, tentativas: int) -> None:
        self.tentativas = tentativas
        super().__init__(
            "Usuário bloqueado por excesso de tentativas. Procure um gestor."
        )


class UltimoGestor(Exception):
    """Impede o sistema de ficar sem quem administre."""

    def __init__(self, restantes: int) -> None:
        self.restantes = restantes
        super().__init__(
            f"O sistema precisa de pelo menos {MINIMO_DE_GESTORES} gestores "
            f"ativos. Promova outra pessoa antes de fazer esta alteração."
        )


class NaoPodeAlterarSiMesmo(Exception):
    def __init__(self, acao: str) -> None:
        super().__init__(f"Você não pode {acao} a si mesmo.")


# ---------------------------------------------------------------------------
# Validações
# ---------------------------------------------------------------------------
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


# alfabeto sem caractere ambíguo: quem recebe a senha provisória vai digitá-la
# lendo de um bilhete ou de uma mensagem
_ALFABETO_PROVISORIA = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def gerar_senha_provisoria(tamanho: int = 14) -> str:
    """Senha de uso único, gerada pelo sistema.

    O gestor nunca escolhe a senha de ninguém. Se escolhesse, passaria a saber a
    senha da pessoa, e toda a proteção do resumo perderia sentido na prática.
    """
    while True:
        candidata = "".join(
            secrets.choice(_ALFABETO_PROVISORIA) for _ in range(tamanho)
        )
        try:
            validar_politica_de_senha(candidata)
            return candidata
        except SenhaFraca:
            continue


def garantir_minimo_de_gestores(gestores_ativos_apos: int) -> None:
    """Chamado antes de desativar, rebaixar ou excluir um gestor."""
    if gestores_ativos_apos < MINIMO_DE_GESTORES:
        raise UltimoGestor(gestores_ativos_apos)


# ---------------------------------------------------------------------------
# Entidade
# ---------------------------------------------------------------------------
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
    cargo: Cargo = Cargo.OUTRO
    ativo: bool = True
    tentativas_falhas: int = 0
    bloqueado_ate: datetime | None = None
    senha_provisoria: bool = False
    ultimo_acesso: datetime | None = None
    empresas: tuple[int, ...] = field(default=())

    # ---------- estado de bloqueio ----------
    @property
    def bloqueado_em_definitivo(self) -> bool:
        return self.tentativas_falhas >= TENTATIVAS_BLOQUEIO_PERMANENTE

    def minutos_de_espera(self, quando: datetime | None = None) -> int:
        """Quanto falta do bloqueio temporário, arredondado para cima."""
        limite = com_fuso(self.bloqueado_ate)
        if limite is None:
            return 0
        restante = limite - (com_fuso(quando) or agora())
        segundos = restante.total_seconds()
        return max(0, -(-int(segundos) // 60)) if segundos > 0 else 0

    @property
    def bloqueado(self) -> bool:
        """Mantido para leitura externa: qualquer forma de bloqueio."""
        return self.bloqueado_em_definitivo or self.minutos_de_espera() > 0

    def garantir_que_pode_entrar(self, quando: datetime | None = None) -> None:
        """Ordem importa: inativo antes de bloqueado, porque desativar é uma
        decisão do gestor e bloquear é consequência automática. E o bloqueio
        permanente antes do temporário, porque é o mais grave."""
        if not self.ativo:
            raise UsuarioInativo()
        if self.bloqueado_em_definitivo:
            raise UsuarioBloqueado(self.tentativas_falhas)
        espera = self.minutos_de_espera(quando)
        if espera > 0:
            raise UsuarioBloqueadoTemporariamente(espera)

    def registrar_falha(self, quando: datetime | None = None) -> None:
        quando = com_fuso(quando) or agora()
        self.tentativas_falhas += 1
        # a cada patamar de 5 erros, mais 15 minutos de espera
        if (
            self.tentativas_falhas % TENTATIVAS_BLOQUEIO_TEMPORARIO == 0
            and not self.bloqueado_em_definitivo
        ):
            self.bloqueado_ate = quando + timedelta(
                minutes=MINUTOS_BLOQUEIO_TEMPORARIO
            )

    def registrar_sucesso(self, quando: datetime | None = None) -> None:
        self.tentativas_falhas = 0
        self.bloqueado_ate = None
        self.ultimo_acesso = com_fuso(quando) or agora()

    def desbloquear(self) -> None:
        """Ação do gestor. Zera contador e espera, sem tocar na senha."""
        self.tentativas_falhas = 0
        self.bloqueado_ate = None

    # ---------- senha ----------
    @property
    def precisa_trocar_senha(self) -> bool:
        """Quem entrou com senha provisória só faz isso: trocar a senha."""
        return self.senha_provisoria

    # ---------- escopo ----------
    def enxerga_empresa(self, empresa_id: int) -> bool:
        """Nenhuma consulta a dado fiscal passa sem esta pergunta."""
        return empresa_id in self.empresas

    @property
    def tentativas_restantes(self) -> int:
        """Quantas faltam para o próximo bloqueio temporário."""
        no_ciclo = self.tentativas_falhas % TENTATIVAS_BLOQUEIO_TEMPORARIO
        return TENTATIVAS_BLOQUEIO_TEMPORARIO - no_ciclo

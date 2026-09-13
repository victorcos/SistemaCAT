"""Domínio de acesso — puro, sem banco, sem framework, sem I/O.

Estas regras têm de rodar em teste de unidade em milissegundos. Se alguém
precisar de um banco para testar o que está aqui, o desenho quebrou.
"""

from __future__ import annotations

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

    DEV = "dev"             # manutenção do sistema; ignora o escopo de empresa
    GESTOR = "gestor"       # administra usuários e alocações
    ANALISTA = "analista"   # executa apuração e aprova de-para
    REVISOR = "revisor"     # confere e aprova entrega
    LEITURA = "leitura"     # só consulta

    @property
    def administra_usuarios(self) -> bool:
        return self in (Papel.DEV, Papel.GESTOR)

    @property
    def pode_escrever(self) -> bool:
        return self in (Papel.DEV, Papel.GESTOR, Papel.ANALISTA, Papel.REVISOR)

    @property
    def ignora_escopo_de_empresa(self) -> bool:
        """Quem enxerga empresa sem alocação: gestor e dev.

        **Gestor** porque é quem responde pela carteira inteira da casa —
        diretor, gerente e coordenador. Exigir que alguém os aloque em cada
        empresa nova era trabalho que ninguém faria: no banco real, dois dos
        três gestores não enxergavam empresa alguma e entravam num sistema
        vazio. E é incoerente com o que o papel já pode fazer — administrar
        usuários, apagar trabalho, passar trabalho adiante.

        **Dev** porque manutenção precisa reproduzir problema em qualquer
        cliente.

        A diferença entre os dois está em `acessa_por_excecao`: para o dev,
        cada acesso sem alocação é exceção e vai para o log; para o gestor, é
        o escopo normal do papel, e registrar a cada requisição só encheria o
        log de ruído.
        """
        return self in (Papel.DEV, Papel.GESTOR)

    @property
    def conta_como_gestor(self) -> bool:
        """DEV NÃO conta para o mínimo de gestores.

        Conta técnica não substitui responsável pelo negócio. Se contasse, dois
        gestores mais um dev pareceriam três e a salvaguarda estaria furada.
        """
        return self is Papel.GESTOR


# ---------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------
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
        if self.papel.ignora_escopo_de_empresa:
            return True
        return empresa_id in self.empresas

    def acessa_por_excecao(self, empresa_id: int) -> bool:
        """Verdadeiro quando o acesso só passou por ser **dev**.

        Serve para o log distinguir acesso normal de acesso por exceção. Sem
        isso, o bypass do dev some no meio do tráfego comum.

        Gestor sem alocação não entra aqui: ver toda a carteira é o escopo
        do papel, não um desvio dele. Marcar isso como exceção encheria o log
        a cada requisição e apagaria o sinal do que é mesmo excepcional.
        """
        return self.papel is Papel.DEV and empresa_id not in self.empresas

    @property
    def tentativas_restantes(self) -> int:
        """Quantas faltam para o próximo bloqueio temporário."""
        no_ciclo = self.tentativas_falhas % TENTATIVAS_BLOQUEIO_TEMPORARIO
        return TENTATIVAS_BLOQUEIO_TEMPORARIO - no_ciclo

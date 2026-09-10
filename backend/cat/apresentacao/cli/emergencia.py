"""Saída de emergência. Roda no servidor, com acesso ao sistema de arquivos.

Existe porque cadastro e redefinição estão na mão dos gestores. Se os três
estiverem indisponíveis ao mesmo tempo — férias, desligamento, senha esquecida —
sem isto o sistema trava e não há quem destrave.

Exigir acesso ao servidor é um segundo fator razoável para um sistema interno:
quem chega até aqui já tem a máquina.

    python -m cat.apresentacao.cli.emergencia listar-gestores
    python -m cat.apresentacao.cli.emergencia promover <usuario>
    python -m cat.apresentacao.cli.emergencia redefinir <usuario>
    python -m cat.apresentacao.cli.emergencia desbloquear <usuario>
    python -m cat.apresentacao.cli.emergencia criar-dev <usuario> <email> <nome>
"""

from __future__ import annotations

import sys

from cat.config import obter_config
from cat.dominio.acesso.usuario import (
    Cargo, Papel, gerar_senha_provisoria, validar_email, validar_nome_de_usuario,
)
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.banco import Sessao, criar_tabelas
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql
from cat.log import configurar, obter_log

log = obter_log(__name__)


def _repo():
    criar_tabelas()
    return UsuarioRepositorioSql(Sessao())


def listar_gestores() -> int:
    repo = _repo()
    gestores = [u for u in repo.listar() if u.papel is Papel.GESTOR]
    ativos = [u for u in gestores if u.ativo]
    print(f"\n  Gestores ativos: {len(ativos)}\n")
    for u in gestores:
        marca = " " if u.ativo else "×"
        trava = " [bloqueado]" if u.bloqueado else ""
        print(f"   {marca} {u.usuario:20} {u.cargo.value:12} {u.nome_exibicao}{trava}")
    print()
    return 0


def promover(nome: str) -> int:
    repo = _repo()
    alvo = repo.buscar_por_usuario(nome)
    if alvo is None:
        print(f"Usuário '{nome}' não encontrado.")
        return 1
    repo.definir_papel(alvo.id, Papel.GESTOR)
    repo.definir_situacao(alvo.id, True)
    log.warning(
        "promoção a gestor pela saída de emergência",
        extra={"usuario_id": alvo.id, "usuario": alvo.usuario,
               "papel_anterior": alvo.papel.value, "via": "cli_emergencia"},
    )
    print(f"'{nome}' agora é gestor e está ativo.")
    return 0


def redefinir(nome: str) -> int:
    repo = _repo()
    alvo = repo.buscar_por_usuario(nome)
    if alvo is None:
        print(f"Usuário '{nome}' não encontrado.")
        return 1
    senha = gerar_senha_provisoria()
    senhas = SenhasArgon2(obter_config().senha_pimenta)
    repo.definir_senha(alvo.id, senhas.gerar(senha), provisoria=True)
    repo.desbloquear(alvo.id)
    log.warning(
        "senha redefinida pela saída de emergência",
        extra={"usuario_id": alvo.id, "usuario": alvo.usuario,
               "via": "cli_emergencia"},
    )
    print(f"\n  Usuário .. {nome}")
    print(f"  Senha .... {senha}")
    print("\n  Provisória: a troca é obrigatória no primeiro acesso.\n")
    return 0


def desbloquear(nome: str) -> int:
    repo = _repo()
    alvo = repo.buscar_por_usuario(nome)
    if alvo is None:
        print(f"Usuário '{nome}' não encontrado.")
        return 1
    repo.desbloquear(alvo.id)
    log.warning("desbloqueio pela saída de emergência",
                extra={"usuario_id": alvo.id, "via": "cli_emergencia"})
    print(f"'{nome}' desbloqueado.")
    return 0


def criar_dev(nome_usuario: str, email: str, exibicao: str) -> int:
    """Cria conta de manutenção, com papel DEV.

    Só pela linha de comando, de propósito: conta que ignora o escopo de
    empresa não deve nascer por clique na tela.
    """
    repo = _repo()
    nome_usuario = validar_nome_de_usuario(nome_usuario)
    email = validar_email(email)

    if repo.buscar_por_usuario(nome_usuario) is not None:
        print(f"Ja existe usuario '{nome_usuario}'.")
        return 1
    if repo.buscar_por_email(email) is not None:
        print(f"Ja existe usuario com o e-mail '{email}'.")
        return 1

    senha = gerar_senha_provisoria()
    senhas = SenhasArgon2(obter_config().senha_pimenta)
    novo = repo.criar(
        usuario=nome_usuario,
        email=email,
        nome_exibicao=exibicao,
        senha_hash=senhas.gerar(senha),
        papel=Papel.DEV,
        cargo=Cargo.OUTRO,
        senha_provisoria=True,
    )
    log.warning(
        "conta de manutencao criada",
        extra={"usuario_id": novo.id, "usuario": nome_usuario,
               "papel": Papel.DEV.value, "via": "cli_emergencia",
               "ignora_escopo_de_empresa": True},
    )
    print(f"\n  Usuario .. {nome_usuario}")
    print(f"  Senha .... {senha}")
    print("\n  Papel dev: enxerga toda empresa, com ou sem alocacao.")
    print("  Cada acesso sem alocacao fica registrado no log como excecao.")
    print("  Provisoria: a troca e obrigatoria no primeiro acesso.\n")
    return 0


COMANDOS = {
    "criar-dev": (criar_dev, 3),
    "listar-gestores": (listar_gestores, 0),
    "promover": (promover, 1),
    "redefinir": (redefinir, 1),
    "desbloquear": (desbloquear, 1),
}


def main() -> int:
    configurar(obter_config().log_nivel)
    if len(sys.argv) < 2 or sys.argv[1] not in COMANDOS:
        print(__doc__)
        return 2
    funcao, n_args = COMANDOS[sys.argv[1]]
    if len(sys.argv) - 2 != n_args:
        print(f"Uso: {sys.argv[1]} exige {n_args} argumento(s).")
        return 2
    return funcao(*sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())

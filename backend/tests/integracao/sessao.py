"""Sessão para os testes de integração do motor.

O login mora na API em C# desde 13/09/2026 (docs/MIGRACAO_CSHARP.md). O motor
continua **validando** o token nas rotas que ainda atende, então os testes
precisam de um token de verdade — só não o pedem mais a uma rota de login.

`token_de` confere a senha e o estado da conta antes de emitir, como o login
fazia. Sem isso, um teste que dependesse de "a senha nova funciona" passaria
mesmo com a senha errada.
"""

from __future__ import annotations

from cat.apresentacao.api.seguranca import obter_tokens
from cat.config import obter_config
from cat.dominio.acesso.usuario import Usuario
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.banco import Sessao
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql


def usuario(nome: str) -> Usuario:
    with Sessao() as s:
        encontrado = UsuarioRepositorioSql(s).buscar_por_usuario(nome)
    assert encontrado is not None, f"usuário {nome!r} não existe no banco de teste"
    return encontrado


def senha_confere(nome: str, senha: str) -> bool:
    with Sessao() as s:
        repo = UsuarioRepositorioSql(s)
        alvo = repo.buscar_por_usuario(nome)
        assert alvo is not None, f"usuário {nome!r} não existe no banco de teste"
        resumo = repo.obter_hash_senha(alvo.id)
    return SenhasArgon2(obter_config().senha_pimenta).conferir(senha, resumo)


def token_de(nome: str, senha: str | None = None) -> str:
    alvo = usuario(nome)
    alvo.garantir_que_pode_entrar()
    if senha is not None:
        assert senha_confere(nome, senha), f"a senha informada não confere para {nome!r}"
    return obter_tokens().emitir(alvo)[0]


def cabecalhos_de(nome: str, senha: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_de(nome, senha)}"}

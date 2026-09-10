"""Caso de uso de autenticação, com dublês. Nenhum banco envolvido."""

import pytest

from cat.aplicacao.casos_de_uso.autenticar import AutenticarUseCase
from cat.dominio.acesso.usuario import (
    CredencialInvalida, MAX_TENTATIVAS, Papel, Usuario, UsuarioBloqueado,
    UsuarioInativo,
)


class RepoFalso:
    def __init__(self, usuario: Usuario | None, hash_senha: str = "hash-certo"):
        self._u = usuario
        self._h = hash_senha
        self.salvou = []

    def buscar_por_usuario(self, usuario):
        return self._u if self._u and self._u.usuario == usuario else None

    def obter_hash_senha(self, usuario_id):
        return self._h

    def salvar_tentativa(self, usuario):
        self.salvou.append((usuario.tentativas_falhas, usuario.ultimo_acesso))


class SenhasFalsas:
    def conferir(self, senha, hash_armazenado):
        return senha == "certa" and hash_armazenado == "hash-certo"


class TokensFalsos:
    def emitir(self, usuario):
        return f"token-de-{usuario.usuario}", 3600


def usuario_padrao(**t):
    base = dict(id=7, usuario="ana", email="ana@bms.local", nome_exibicao="Ana",
                papel=Papel.ANALISTA, empresas=(1, 2))
    base.update(t)
    return Usuario(**base)


def montar(usuario, hash_senha="hash-certo"):
    repo = RepoFalso(usuario, hash_senha)
    return AutenticarUseCase(repo, SenhasFalsas(), TokensFalsos()), repo


def test_login_certo_devolve_token_e_escopo():
    caso, repo = montar(usuario_padrao())
    r = caso.executar("ana", "certa")
    assert r.token == "token-de-ana"
    assert r.expira_em == 3600
    assert r.usuario.empresas == (1, 2)
    assert repo.salvou[-1][0] == 0          # tentativas zeradas
    assert repo.salvou[-1][1] is not None   # acesso registrado


def test_normaliza_o_nome_informado():
    caso, _ = montar(usuario_padrao())
    assert caso.executar("  ANA  ", "certa").token == "token-de-ana"


def test_usuario_inexistente_da_credencial_invalida():
    caso, _ = montar(None)
    with pytest.raises(CredencialInvalida):
        caso.executar("fantasma", "certa")


def test_senha_errada_conta_tentativa():
    u = usuario_padrao()
    caso, repo = montar(u)
    with pytest.raises(CredencialInvalida):
        caso.executar("ana", "errada")
    assert u.tentativas_falhas == 1
    assert repo.salvou[-1][0] == 1


def test_mensagem_nao_distingue_inexistente_de_senha_errada():
    """Mensagem diferente entregaria quais contas existem."""
    caso_a, _ = montar(None)
    caso_b, _ = montar(usuario_padrao())
    with pytest.raises(CredencialInvalida) as sem_conta:
        caso_a.executar("fantasma", "certa")
    with pytest.raises(CredencialInvalida) as senha_ruim:
        caso_b.executar("ana", "errada")
    assert str(sem_conta.value) == str(senha_ruim.value)


def test_inativo_e_recusado_antes_de_conferir_senha():
    caso, _ = montar(usuario_padrao(ativo=False))
    with pytest.raises(UsuarioInativo):
        caso.executar("ana", "certa")


def test_bloqueado_e_recusado_mesmo_com_senha_certa():
    caso, _ = montar(usuario_padrao(tentativas_falhas=MAX_TENTATIVAS))
    with pytest.raises(UsuarioBloqueado):
        caso.executar("ana", "certa")


def test_sucesso_apos_falhas_zera_o_contador():
    u = usuario_padrao(tentativas_falhas=2)
    caso, _ = montar(u)
    caso.executar("ana", "certa")
    assert u.tentativas_falhas == 0

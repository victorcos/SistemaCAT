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
        self.regravou = []

    def buscar_por_usuario(self, usuario):
        return self._u if self._u and self._u.usuario == usuario else None

    def obter_hash_senha(self, usuario_id):
        return self._h

    def salvar_tentativa(self, usuario):
        self.salvou.append((usuario.tentativas_falhas, usuario.ultimo_acesso))

    def regravar_hash_senha(self, usuario_id, novo_hash):
        self.regravou.append((usuario_id, novo_hash))
        self._h = novo_hash


class SenhasFalsas:
    """Aceita "certa" contra qualquer hash conhecido. O hash "hash-antigo"
    representa formato defasado, que deve disparar regravação."""

    def conferir(self, senha, hash_armazenado):
        return senha == "certa" and hash_armazenado in ("hash-certo", "hash-antigo")

    def precisa_regravar(self, hash_armazenado):
        return hash_armazenado == "hash-antigo"

    def gerar(self, senha):
        return "hash-novo"


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


def test_resumo_antigo_e_regravado_apos_login_certo():
    """A migração só cabe aqui: é a única janela com a senha em claro em mãos."""
    caso, repo = montar(usuario_padrao(), hash_senha="hash-antigo")
    caso.executar("ana", "certa")
    assert repo.regravou == [(7, "hash-novo")]


def test_resumo_atual_nao_e_regravado():
    caso, repo = montar(usuario_padrao(), hash_senha="hash-certo")
    caso.executar("ana", "certa")
    assert repo.regravou == []


def test_senha_errada_nao_regrava_nada():
    caso, repo = montar(usuario_padrao(), hash_senha="hash-antigo")
    with pytest.raises(CredencialInvalida):
        caso.executar("ana", "errada")
    assert repo.regravou == []

"""Proteção de senha.

Estes testes existem para travar três promessas: o resumo é de mão única, o sal
torna cada resumo único, e o resumo antigo continua sendo aceito enquanto migra.
"""

import pytest

from cat.infraestrutura.auth.senha import SenhaLonga, SenhasArgon2

SENHA = "Sistema2026cat"


@pytest.fixture
def senhas():
    return SenhasArgon2()


class TestResumo:
    def test_confere_a_senha_certa(self, senhas):
        assert senhas.conferir(SENHA, senhas.gerar(SENHA))

    def test_recusa_senha_errada(self, senhas):
        assert not senhas.conferir("OutraCoisa1", senhas.gerar(SENHA))

    def test_usa_argon2id(self, senhas):
        assert senhas.gerar(SENHA).startswith("$argon2id$")

    def test_o_resumo_nao_contem_a_senha(self, senhas):
        """De mão única: a senha não pode aparecer no resultado."""
        assert SENHA.lower() not in senhas.gerar(SENHA).lower()

    def test_sal_torna_cada_resumo_unico(self, senhas):
        """Mesma senha, resumos diferentes — tabela pronta de ataque não serve."""
        a, b = senhas.gerar(SENHA), senhas.gerar(SENHA)
        assert a != b
        assert senhas.conferir(SENHA, a) and senhas.conferir(SENHA, b)

    def test_senha_absurda_e_recusada(self, senhas):
        with pytest.raises(SenhaLonga):
            senhas.gerar("x" * 2000)


class TestPimenta:
    def test_resumo_com_pimenta_nao_confere_sem_ela(self):
        com = SenhasArgon2(pimenta="segredo-do-servidor")
        sem = SenhasArgon2()
        assert not sem.conferir(SENHA, com.gerar(SENHA))

    def test_pimenta_errada_nao_confere(self):
        a = SenhasArgon2(pimenta="pimenta-a")
        b = SenhasArgon2(pimenta="pimenta-b")
        assert not b.conferir(SENHA, a.gerar(SENHA))

    def test_pimenta_certa_confere(self):
        a = SenhasArgon2(pimenta="mesma")
        b = SenhasArgon2(pimenta="mesma")
        assert b.conferir(SENHA, a.gerar(SENHA))

    def test_pimenta_remove_o_limite_de_72_bytes(self):
        """O HMAC dá tamanho fixo, então senha longa não é truncada."""
        p = SenhasArgon2(pimenta="segredo")
        longa = "A1" + "z" * 100
        h = p.gerar(longa)
        assert p.conferir(longa, h)
        assert not p.conferir(longa[:72], h)


class TestMigracaoDoBcrypt:
    def _hash_bcrypt(self, senha: str) -> str:
        import bcrypt
        return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

    def test_ainda_aceita_resumo_bcrypt(self, senhas):
        """Ninguém pode ficar trancado para fora por causa da troca."""
        assert senhas.conferir(SENHA, self._hash_bcrypt(SENHA))

    def test_recusa_senha_errada_no_formato_antigo(self, senhas):
        assert not senhas.conferir("Errada1x", self._hash_bcrypt(SENHA))

    def test_bcrypt_e_marcado_para_regravar(self, senhas):
        assert senhas.precisa_regravar(self._hash_bcrypt(SENHA))

    def test_argon2_atual_nao_precisa_regravar(self, senhas):
        assert not senhas.precisa_regravar(senhas.gerar(SENHA))


class TestEntradaEstranha:
    @pytest.mark.parametrize("ruim", ["", "nao-e-hash", "$5$outro$coisa", "$2y$"])
    def test_resumo_invalido_nao_derruba_e_nao_autentica(self, senhas, ruim):
        """Hash corrompido é falha de conferência, não exceção que derruba a API."""
        assert senhas.conferir(SENHA, ruim) is False

    def test_resumo_desconhecido_pede_regravacao(self, senhas):
        assert senhas.precisa_regravar("formato-estranho")

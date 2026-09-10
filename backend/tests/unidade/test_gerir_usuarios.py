"""Gestão de usuários: as salvaguardas do modelo de administrador único.

Sem banco. Os dublês guardam estado suficiente para provar as regras.
"""

import pytest

from cat.aplicacao.casos_de_uso.gerir_usuarios import (
    GerirUsuariosUseCase,
    SenhaAtualIncorreta,
    SenhaRepetida,
    UsuarioJaExiste,
    UsuarioNaoEncontrado,
)
from cat.dominio.acesso.usuario import (
    Cargo,
    MINIMO_DE_GESTORES,
    NaoPodeAlterarSiMesmo,
    Papel,
    SenhaFraca,
    UltimoGestor,
    Usuario,
)


class RepoFalso:
    def __init__(self, usuarios: list[Usuario]):
        self._u = {u.id: u for u in usuarios}
        self._hash = {u.id: "hash-certo" for u in usuarios}
        self.proximo_id = max(self._u, default=0) + 1

    # ---------- leitura ----------
    def buscar_por_usuario(self, nome):
        return next((u for u in self._u.values() if u.usuario == nome), None)

    def buscar_por_email(self, email):
        return next((u for u in self._u.values() if u.email == email), None)

    def buscar_por_id(self, i):
        return self._u.get(i)

    def listar(self):
        return list(self._u.values())

    def contar_gestores_ativos(self):
        return sum(1 for u in self._u.values()
                   if u.papel is Papel.GESTOR and u.ativo)

    def obter_hash_senha(self, i):
        return self._hash.get(i, "")

    # ---------- escrita ----------
    def criar(self, *, usuario, email, nome_exibicao, senha_hash, papel,
              cargo=Cargo.OUTRO, senha_provisoria=False):
        novo = Usuario(id=self.proximo_id, usuario=usuario, email=email,
                       nome_exibicao=nome_exibicao, papel=papel, cargo=cargo,
                       senha_provisoria=senha_provisoria)
        self._u[novo.id] = novo
        self._hash[novo.id] = senha_hash
        self.proximo_id += 1
        return novo

    def definir_senha(self, i, novo_hash, *, provisoria):
        self._hash[i] = novo_hash
        self._u[i].senha_provisoria = provisoria

    def definir_papel(self, i, papel):
        self._u[i].papel = papel

    def definir_cargo(self, i, cargo):
        self._u[i].cargo = cargo

    def definir_situacao(self, i, ativo):
        self._u[i].ativo = ativo

    def desbloquear(self, i):
        self._u[i].desbloquear()

    def salvar_tentativa(self, u):
        pass

    def regravar_hash_senha(self, i, h):
        self._hash[i] = h


class SenhasFalsas:
    def conferir(self, senha, hash_armazenado):
        return hash_armazenado == f"hash-de-{senha}" or (
            senha == "certa" and hash_armazenado == "hash-certo"
        )

    def precisa_regravar(self, h):
        return False

    def gerar(self, senha):
        return f"hash-de-{senha}"


def gestor(i, nome, cargo=Cargo.DIRETOR, ativo=True):
    return Usuario(id=i, usuario=nome, email=f"{nome}@bms.local",
                   nome_exibicao=nome.title(), papel=Papel.GESTOR, cargo=cargo,
                   ativo=ativo)


def comum(i, nome, papel=Papel.ANALISTA):
    return Usuario(id=i, usuario=nome, email=f"{nome}@bms.local",
                   nome_exibicao=nome.title(), papel=papel, cargo=Cargo.ANALISTA)


@pytest.fixture
def cenario():
    """Três gestores, como o sistema exige, mais um analista."""
    usuarios = [
        gestor(1, "diretor", Cargo.DIRETOR),
        gestor(2, "gerente", Cargo.GERENTE),
        gestor(3, "coordenador", Cargo.COORDENADOR),
        comum(4, "ana"),
    ]
    repo = RepoFalso(usuarios)
    return GerirUsuariosUseCase(repo, SenhasFalsas()), repo, usuarios


class TestMinimoDeGestores:
    def test_sao_tres(self):
        assert MINIMO_DE_GESTORES == 3

    def test_recusa_rebaixar_deixando_menos_de_tres(self, cenario):
        caso, _, us = cenario
        with pytest.raises(UltimoGestor):
            caso.alterar_papel(alvo_id=2, papel=Papel.ANALISTA, por=us[0])

    def test_recusa_desativar_deixando_menos_de_tres(self, cenario):
        caso, _, us = cenario
        with pytest.raises(UltimoGestor):
            caso.definir_situacao(alvo_id=2, ativo=False, por=us[0])

    def test_com_quatro_gestores_da_para_rebaixar_um(self, cenario):
        caso, repo, us = cenario
        caso.alterar_papel(alvo_id=4, papel=Papel.GESTOR, por=us[0])
        assert repo.contar_gestores_ativos() == 4
        caso.alterar_papel(alvo_id=2, papel=Papel.ANALISTA, por=us[0])
        assert repo.contar_gestores_ativos() == 3

    def test_gestor_inativo_nao_conta(self, cenario):
        caso, repo, us = cenario
        repo.definir_situacao(3, False)
        with pytest.raises(UltimoGestor):
            caso.definir_situacao(alvo_id=2, ativo=False, por=us[0])

    def test_desativar_nao_gestor_nao_e_barrado(self, cenario):
        caso, _, us = cenario
        alvo = caso.definir_situacao(alvo_id=4, ativo=False, por=us[0])
        assert alvo.ativo is False


class TestNaoAlterarSiMesmo:
    def test_nao_se_rebaixa(self, cenario):
        caso, _, us = cenario
        with pytest.raises(NaoPodeAlterarSiMesmo):
            caso.alterar_papel(alvo_id=1, papel=Papel.LEITURA, por=us[0])

    def test_nao_se_desativa(self, cenario):
        caso, _, us = cenario
        with pytest.raises(NaoPodeAlterarSiMesmo):
            caso.definir_situacao(alvo_id=1, ativo=False, por=us[0])


class TestCadastro:
    def test_cria_com_senha_provisoria(self, cenario):
        caso, _, us = cenario
        r = caso.criar(usuario="novo.joao", email="joao@bms.local",
                       nome_exibicao="João", papel=Papel.ANALISTA,
                       cargo=Cargo.ANALISTA, criado_por=us[0])
        assert r.usuario.senha_provisoria is True
        assert r.usuario.precisa_trocar_senha
        assert len(r.senha_provisoria) >= 10

    def test_senha_e_gerada_pelo_sistema_e_muda_a_cada_vez(self, cenario):
        """O gestor nunca escolhe a senha. Se escolhesse, saberia a senha da
        pessoa, e o resumo de mão única perderia sentido na prática."""
        caso, _, us = cenario
        a = caso.criar(usuario="a.um", email="a@bms.local", nome_exibicao="A",
                       papel=Papel.LEITURA, cargo=Cargo.OUTRO, criado_por=us[0])
        b = caso.criar(usuario="b.dois", email="b@bms.local", nome_exibicao="B",
                       papel=Papel.LEITURA, cargo=Cargo.OUTRO, criado_por=us[0])
        assert a.senha_provisoria != b.senha_provisoria

    def test_normaliza_usuario_e_email(self, cenario):
        caso, _, us = cenario
        r = caso.criar(usuario="  Novo.Maria ", email=" Maria@BMS.Local ",
                       nome_exibicao="Maria", papel=Papel.LEITURA,
                       cargo=Cargo.OUTRO, criado_por=us[0])
        assert r.usuario.usuario == "novo.maria"
        assert r.usuario.email == "maria@bms.local"

    def test_recusa_usuario_repetido(self, cenario):
        caso, _, us = cenario
        with pytest.raises(UsuarioJaExiste):
            caso.criar(usuario="ana", email="outro@bms.local", nome_exibicao="X",
                       papel=Papel.LEITURA, cargo=Cargo.OUTRO, criado_por=us[0])

    def test_recusa_email_repetido(self, cenario):
        caso, _, us = cenario
        with pytest.raises(UsuarioJaExiste):
            caso.criar(usuario="outro.nome", email="ana@bms.local",
                       nome_exibicao="X", papel=Papel.LEITURA,
                       cargo=Cargo.OUTRO, criado_por=us[0])


class TestRedefinicao:
    def test_gera_provisoria_e_marca_troca_obrigatoria(self, cenario):
        caso, repo, us = cenario
        senha = caso.redefinir_senha(alvo_id=4, por=us[0])
        assert repo.buscar_por_id(4).senha_provisoria is True
        assert len(senha) >= 10

    def test_tambem_desbloqueia(self, cenario):
        """Quem esqueceu a senha em geral também se bloqueou tentando."""
        caso, repo, us = cenario
        for _ in range(20):
            repo.buscar_por_id(4).registrar_falha()
        caso.redefinir_senha(alvo_id=4, por=us[0])
        assert repo.buscar_por_id(4).tentativas_falhas == 0

    def test_usuario_inexistente(self, cenario):
        caso, _, us = cenario
        with pytest.raises(UsuarioNaoEncontrado):
            caso.redefinir_senha(alvo_id=999, por=us[0])


class TestTrocaDaPropriaSenha:
    def test_troca_sai_da_provisoria(self, cenario):
        caso, repo, _ = cenario
        repo.definir_senha(4, "hash-de-provisoria", provisoria=True)
        caso.trocar_propria_senha(usuario=repo.buscar_por_id(4),
                                  senha_atual="provisoria",
                                  senha_nova="MinhaNova2026")
        assert repo.buscar_por_id(4).senha_provisoria is False
        assert repo.obter_hash_senha(4) == "hash-de-MinhaNova2026"

    def test_senha_atual_errada(self, cenario):
        caso, repo, _ = cenario
        with pytest.raises(SenhaAtualIncorreta):
            caso.trocar_propria_senha(usuario=repo.buscar_por_id(4),
                                      senha_atual="errada",
                                      senha_nova="MinhaNova2026")

    def test_nao_aceita_repetir_a_mesma(self, cenario):
        caso, repo, _ = cenario
        with pytest.raises(SenhaRepetida):
            caso.trocar_propria_senha(usuario=repo.buscar_por_id(4),
                                      senha_atual="certa", senha_nova="certa")

    def test_nova_senha_passa_pela_politica(self, cenario):
        caso, repo, _ = cenario
        with pytest.raises(SenhaFraca):
            caso.trocar_propria_senha(usuario=repo.buscar_por_id(4),
                                      senha_atual="certa", senha_nova="curta1A")

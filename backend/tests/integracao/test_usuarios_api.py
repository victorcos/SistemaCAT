"""Gestão de usuários pela API, ponta a ponta.

Cenário: os três gestores que o sistema exige, mais um analista.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app  # noqa: E402
from cat.config import obter_config  # noqa: E402
from cat.dominio.acesso.usuario import Cargo, Papel  # noqa: E402
from cat.infraestrutura.auth.senha import SenhasArgon2  # noqa: E402
from cat.infraestrutura.repositorios.modelos import Base  # noqa: E402
from cat.infraestrutura.repositorios.usuario_repositorio import (  # noqa: E402
    UsuarioRepositorioSql,
)

SENHA = "Sistema2026cat"


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    repo = UsuarioRepositorioSql(s)
    senhas = SenhasArgon2(obter_config().senha_pimenta)

    for nome, cargo in [("diretor", Cargo.DIRETOR), ("gerente", Cargo.GERENTE),
                        ("coordenador", Cargo.COORDENADOR)]:
        repo.criar(usuario=nome, email=f"{nome}@bms.local",
                   nome_exibicao=nome.title(), senha_hash=senhas.gerar(SENHA),
                   papel=Papel.GESTOR, cargo=cargo)
    repo.criar(usuario="ana", email="ana@bms.local", nome_exibicao="Ana",
               senha_hash=senhas.gerar(SENHA), papel=Papel.ANALISTA,
               cargo=Cargo.ANALISTA)
    s.close()

    with TestClient(app) as c:
        yield c


def token(cliente, usuario, senha=SENHA):
    r = cliente.post("/api/auth/token",
                     data={"username": usuario, "password": senha})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def cab(cliente, usuario, senha=SENHA):
    return {"Authorization": f"Bearer {token(cliente, usuario, senha)}"}


def id_de(cliente, nome, como="diretor"):
    """Procura pelo nome. Identificador fixo quebra quando a bateria compartilha
    banco com outro módulo."""
    lista = cliente.get("/api/usuarios", headers=cab(cliente, como)).json()
    return next(u["id"] for u in lista if u["usuario"] == nome)


# ---------------------------------------------------------------------------
class TestPermissao:
    def test_sem_token_nao_lista(self, cliente):
        assert cliente.get("/api/usuarios").status_code == 401

    def test_analista_nao_lista(self, cliente):
        r = cliente.get("/api/usuarios", headers=cab(cliente, "ana"))
        assert r.status_code == 403

    def test_analista_nao_cria(self, cliente):
        r = cliente.post("/api/usuarios", headers=cab(cliente, "ana"), json={
            "usuario": "invasor", "email": "i@bms.local",
            "nome_exibicao": "I", "papel": "gestor", "cargo": "outro"})
        assert r.status_code == 403

    def test_analista_nao_redefine_senha_de_outro(self, cliente):
        alvo = id_de(cliente, "diretor")
        r = cliente.post(f"/api/usuarios/{alvo}/senha", headers=cab(cliente, "ana"))
        assert r.status_code == 403

    def test_gestor_lista(self, cliente):
        r = cliente.get("/api/usuarios", headers=cab(cliente, "diretor"))
        assert r.status_code == 200
        assert len(r.json()) >= 4


class TestCadastro:
    def test_gestor_cria_e_recebe_senha_provisoria(self, cliente):
        r = cliente.post("/api/usuarios", headers=cab(cliente, "diretor"), json={
            "usuario": "joao.novo", "email": "joao@bms.local",
            "nome_exibicao": "João", "papel": "analista", "cargo": "analista"})
        assert r.status_code == 201
        corpo = r.json()
        assert corpo["usuario"]["senha_provisoria"] is True
        assert len(corpo["senha_provisoria"]) >= 10
        assert "não será exibida de novo" in corpo["aviso"]

    def test_nao_aceita_usuario_repetido(self, cliente):
        r = cliente.post("/api/usuarios", headers=cab(cliente, "diretor"), json={
            "usuario": "ana", "email": "outra@bms.local",
            "nome_exibicao": "Outra", "papel": "leitura", "cargo": "outro"})
        assert r.status_code == 409


class TestMinimoDeGestores:
    def test_nao_rebaixa_deixando_menos_de_tres(self, cliente):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'gerente')}/papel",
                          headers=cab(cliente, "diretor"),
                          json={"papel": "analista"})
        assert r.status_code == 409
        assert "3 gestores" in r.json()["detail"]

    def test_nao_desativa_deixando_menos_de_tres(self, cliente):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'gerente')}/situacao",
                          headers=cab(cliente, "diretor"),
                          json={"ativo": False})
        assert r.status_code == 409

    def test_gestor_nao_se_desativa(self, cliente):
        r = cliente.patch(f"/api/usuarios/{id_de(cliente, 'diretor')}/situacao",
                          headers=cab(cliente, "diretor"),
                          json={"ativo": False})
        assert r.status_code == 409
        assert "si mesmo" in r.json()["detail"]


class TestFluxoDaSenhaProvisoria:
    def test_ciclo_completo(self, cliente):
        """Gestor redefine, a pessoa entra, é obrigada a trocar, e a provisória
        para de funcionar."""
        gestor = cab(cliente, "diretor")
        alvo = cliente.get("/api/usuarios", headers=gestor).json()
        ana = next(u for u in alvo if u["usuario"] == "ana")

        r = cliente.post(f"/api/usuarios/{ana['id']}/senha", headers=gestor)
        assert r.status_code == 200
        provisoria = r.json()["senha_provisoria"]

        # entra com a provisória e o sistema avisa que precisa trocar
        entrada = cliente.post("/api/auth/token",
                               data={"username": "ana", "password": provisoria})
        assert entrada.status_code == 200
        assert entrada.json()["usuario"]["senha_provisoria"] is True

        # troca
        nova = "TrocadaPelaAna2026"
        t = {"Authorization": f"Bearer {entrada.json()['access_token']}"}
        troca = cliente.post("/api/usuarios/eu/senha", headers=t,
                             json={"senha_atual": provisoria, "senha_nova": nova})
        assert troca.status_code == 204

        # a provisória morreu, a nova funciona e a marca de troca sumiu
        assert cliente.post("/api/auth/token",
                            data={"username": "ana",
                                  "password": provisoria}).status_code == 401
        depois = cliente.post("/api/auth/token",
                              data={"username": "ana", "password": nova})
        assert depois.status_code == 200
        assert depois.json()["usuario"]["senha_provisoria"] is False

    def test_troca_exige_a_senha_atual(self, cliente):
        t = cab(cliente, "coordenador")
        r = cliente.post("/api/usuarios/eu/senha", headers=t,
                         json={"senha_atual": "chutando", "senha_nova": "Nova2026abc"})
        assert r.status_code == 401

    def test_troca_recusa_senha_fraca(self, cliente):
        t = cab(cliente, "coordenador")
        r = cliente.post("/api/usuarios/eu/senha", headers=t,
                         json={"senha_atual": SENHA, "senha_nova": "curta1A"})
        assert r.status_code == 422

    def test_senha_provisoria_nunca_volta_em_listagem(self, cliente):
        """A senha só aparece uma vez, na resposta de quem a gerou."""
        corpo = cliente.get("/api/usuarios", headers=cab(cliente, "diretor")).text
        assert "senha_provisoria" in corpo          # o sinalizador, sim
        assert SENHA not in corpo                   # a senha, nunca


class TestDesbloqueio:
    def test_gestor_desbloqueia(self, cliente):
        gestor = cab(cliente, "diretor")
        lista = cliente.get("/api/usuarios", headers=gestor).json()
        alvo = next(u for u in lista if u["usuario"] == "joao.novo")

        for _ in range(5):
            cliente.post("/api/auth/token",
                         data={"username": "joao.novo", "password": "errada"})
        recusa = cliente.post("/api/auth/token",
                              data={"username": "joao.novo", "password": "errada"})
        assert recusa.status_code == 403
        assert "minuto" in recusa.json()["detail"]

        r = cliente.post(f"/api/usuarios/{alvo['id']}/desbloquear", headers=gestor)
        assert r.status_code == 200
        assert r.json()["tentativas_falhas"] == 0

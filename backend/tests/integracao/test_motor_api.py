"""O que o motor segue garantindo por conta própria, sem rota de login.

Estes três vieram de test_auth_api.py quando o login foi para a API em C#
(13/09/2026). Os cenários de login em si estão em
api/tests/Cat.Api.Testes/AutenticacaoTestes.cs.
"""

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from cat.apresentacao.api.app import app
from cat.config import obter_config
from cat.dominio.acesso.usuario import Papel
from cat.infraestrutura.auth.senha import SenhasArgon2
from cat.infraestrutura.repositorios.modelos import Base, UsuarioDB
from cat.infraestrutura.repositorios.usuario_repositorio import UsuarioRepositorioSql

SENHA = "Sistema2026cat"


@pytest.fixture(scope="module")
def cliente():
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor, expire_on_commit=False)()
    UsuarioRepositorioSql(s).criar(
        usuario="motor.ana", email="motor.ana@bms.local", nome_exibicao="Ana",
        senha_hash=SenhasArgon2(obter_config().senha_pimenta).gerar(SENHA),
        papel=Papel.ANALISTA)
    s.close()
    with TestClient(app) as c:
        yield c


def test_saude_responde(cliente):
    r = cliente.get("/api/saude")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_resposta_traz_identificador_de_requisicao(cliente):
    """Sem isso não dá para juntar as linhas de log de um mesmo pedido."""
    assert cliente.get("/api/saude").headers.get("X-Request-Id")


def test_login_nao_mora_mais_no_motor(cliente):
    """A regra de login existe num lugar só. Se esta rota voltar, voltam as duas."""
    r = cliente.post("/api/auth/token", data={"username": "motor.ana", "password": SENHA})
    assert r.status_code in (404, 405)


def test_gestao_de_usuarios_nao_mora_mais_no_motor(cliente):
    """Mínimo de gestores e senha provisória existem num lugar só: a API em C#."""
    assert cliente.get("/api/usuarios").status_code in (404, 405)
    assert cliente.post("/api/usuarios/eu/senha", json={}).status_code in (404, 405)


def test_empresas_projetos_e_exclusao_nao_moram_mais_no_motor(cliente):
    """Cadastro, etapas do projeto e a exclusão que pede senha: num lugar só, o C#."""
    for metodo, rota in [("GET", "/api/empresas"), ("POST", "/api/empresas"), ("GET", "/api/frentes"),
                         ("GET", "/api/projetos"), ("POST", "/api/projetos"), ("GET", "/api/projetos/1"),
                         ("GET", "/api/projetos/1/exclusao"), ("DELETE", "/api/projetos/1")]:
        assert cliente.request(metodo, rota).status_code in (404, 405), rota


def test_historico_nao_mora_mais_no_motor(cliente):
    """Linha do tempo, comentário, status e sucessão: num lugar só, o C#."""
    for metodo, rota in [("GET", "/api/projetos/1/historico"), ("POST", "/api/projetos/1/historico/comentarios"),
                         ("GET", "/api/status-de-projeto"), ("PATCH", "/api/projetos/1/status"),
                         ("GET", "/api/projetos/1/sucessores"), ("PATCH", "/api/projetos/1/responsavel")]:
        assert cliente.request(metodo, rota).status_code in (404, 405), rota


class TestCanalInterno:
    """A API em C# pede, o motor apaga — só com o segredo, e só na pasta de trabalho."""

    SEGREDO = {"X-Cat-Motor-Segredo": "segredo-do-canal-so-de-teste"}

    @pytest.fixture
    def pastas(self):
        raiz = obter_config().raiz_de_trabalho
        dentro = os.path.join(raiz, f"execucao-{os.urandom(4).hex()}")
        os.makedirs(os.path.join(dentro, "sub"))
        with open(os.path.join(dentro, "sub", "parquet.bin"), "wb") as f:
            f.write(b"x")
        fora = tempfile.mkdtemp(prefix="cat_fora_da_raiz_")
        yield dentro, fora, raiz
        shutil.rmtree(fora, ignore_errors=True)

    def test_sem_segredo_nao_apaga(self, cliente, pastas):
        dentro, _, _ = pastas
        r = cliente.post("/interno/pastas/apagar", json={"pastas": [dentro]})
        assert r.status_code == 403
        r = cliente.post("/interno/pastas/apagar", json={"pastas": [dentro]},
                         headers={"X-Cat-Motor-Segredo": "errado"})
        assert r.status_code == 403
        assert os.path.isdir(dentro)

    def test_apaga_dentro_da_raiz_e_recusa_fora_e_a_propria_raiz(self, cliente, pastas):
        dentro, fora, raiz = pastas
        r = cliente.post("/interno/pastas/apagar", headers=self.SEGREDO,
                         json={"pastas": [dentro, fora, raiz, os.path.join(dentro, "..", "..")]})
        assert r.status_code == 200, r.text
        assert r.json()["apagadas"] == [dentro]
        assert len(r.json()["recusadas"]) == 3
        assert not os.path.exists(dentro)
        assert os.path.isdir(fora)
        assert os.path.isdir(raiz)

    def test_canal_fica_fora_da_documentacao_publica(self, cliente):
        assert "/interno" not in cliente.get("/openapi.json").text

    def test_sem_segredo_configurado_o_canal_fica_fechado(self, cliente, pastas, monkeypatch):
        dentro, _, _ = pastas
        monkeypatch.setattr(obter_config(), "motor_segredo", "")
        r = cliente.post("/interno/pastas/apagar", headers=self.SEGREDO, json={"pastas": [dentro]})
        assert r.status_code == 503
        assert os.path.isdir(dentro)


def test_senha_nao_e_recuperavel_do_banco(cliente):
    """O sistema não pode ser capaz de descobrir a senha de ninguém."""
    motor = create_engine(obter_config().banco_url,
                          connect_args={"check_same_thread": False})
    s = sessionmaker(bind=motor)()
    for h in s.scalars(select(UsuarioDB.senha_hash)):
        assert SENHA not in h
        assert h.startswith(("$argon2", "$2"))
    s.close()
